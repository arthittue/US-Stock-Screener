"""สัญญา scan delivery v1: เก็บผลก่อน export และแยกไม่มีหุ้นจากเขียนไฟล์ล้มเหลว"""
import contextvars
import csv
import functools
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_log=logging.getLogger(__name__)
_active=contextvars.ContextVar('scan_delivery',default=None)
_lock=threading.RLock()

def _now():
    return datetime.now(timezone.utc).isoformat()

def _atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def replace_csv(path,data):
    _atomic(path,data)

def _json(path,value):
    _atomic(path,json.dumps(value,ensure_ascii=False,sort_keys=True).encode())

def _spool(path):
    return Path(path).parent/'.scan_delivery'

@contextmanager
def _writing(path):
    folder=_spool(path);folder.mkdir(parents=True,exist_ok=True)
    with _lock, (folder/'writer.lock').open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            f.seek(0);f.write(b'0');f.flush();f.seek(0)
            msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX)
        try:yield
        finally:
            if os.name=='nt':
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

def _public(batch):
    return {k:v for k,v in batch.items() if k not in ('rows','columns','path')}

def _status(path,batch):
    target=Path(path).parent/'scan_status.json'
    try:previous=json.loads(target.read_text())
    except (OSError,ValueError):previous={}
    if previous.get('started_at','')>batch['started_at']:return
    _json(target,_public(batch))

def _new(market,path):
    at=_now()
    return dict(schema_version=1,market=market,run_id=uuid.uuid4().hex,
        started_at=at,completed_at=None,scan_date=datetime.now(ZoneInfo('Asia/Bangkok')).date().isoformat(),
        status='running',candidate_count=0,evaluated_count=0,qualified_count=0,
        skipped_count=0,retry_symbols=[],data_asof=None,signal_date=None,
        csv_sha256=None,error=None,rows=[],columns=[],path=str(path))

def _save(batch):
    path=Path(batch['path'])
    folder=_spool(path);folder.mkdir(parents=True,exist_ok=True)
    _json(folder/(batch['run_id']+'.json'),batch)
    _status(path,batch)

def note_scan(*,candidate_count=None,evaluated_count=None,retry_symbols=()):
    batch=_active.get()
    if batch is None:return
    if candidate_count is not None:batch['candidate_count']=max(batch['candidate_count'],candidate_count)
    if evaluated_count is not None:batch['evaluated_count']=max(batch['evaluated_count'],evaluated_count)
    batch['retry_symbols']=sorted(set(batch['retry_symbols'])|set(retry_symbols))
    batch['skipped_count']=len(batch['retry_symbols'])

@contextmanager
def round_scan(market,path):
    path=Path(path)
    current=_active.get()
    if current is not None:
        yield current
        return
    batch=_new(market,path);token=_active.set(batch)
    with _writing(path):_save(batch)
    try:
        yield batch
    except BaseException as error:
        batch.update(status='failed',completed_at=_now(),error=type(error).__name__)
        with _writing(path):_save(batch)
        raise
    else:
        batch.update(status='partial' if batch['retry_symbols'] else 'success',completed_at=_now())
        with _writing(path):_save(batch)
        retry_exports(path)
    finally:_active.reset(token)

def async_round(market,path_fn):
    def decorate(fn):
        @functools.wraps(fn)
        async def wrapped(*args,**kwargs):
            with round_scan(market,path_fn()):return await fn(*args,**kwargs)
        return wrapped
    return decorate

def submit(path,columns,rows,*,market):
    path=Path(path);batch=_active.get()
    if batch is None:
        with round_scan(market,path):
            submit(path,columns,rows,market=market)
        s=json.loads((path.parent/'scan_status.json').read_text())
        return len(rows) if s['status'] in ('success','partial') else 0
    if Path(batch['path'])!=path:raise ValueError('scan path ไม่ตรงกับรอบที่กำลังทำ')
    batch['columns']=list(columns)
    bykey={tuple(r[:2]):r for r in batch['rows']}
    for r in rows:bykey[tuple(str(v) for v in r[:2])]=list(r)
    batch['rows']=list(bykey.values());batch['run_keys']=[list(k) for k in bykey];batch['qualified_count']=len(bykey)
    batch['evaluated_count']=max(batch['evaluated_count'],len(bykey))
    batch['candidate_count']=max(batch['candidate_count'],len(bykey))
    batch['data_asof']=max((str(r[0]) for r in batch['rows']),default=None)
    with _writing(path):_save(batch)
    return len(rows)

def retry_exports(path):
    path=Path(path);written=0
    with _writing(path):
        batches=[]
        for file in _spool(path).glob('*.json'):
            batch=json.loads(file.read_text())
            if batch['status'] in ('success','partial','export_failed'):batches.append((batch,file))
        for batch,file in sorted(batches,key=lambda pair:pair[0]['started_at']):
            if not batch['columns']:
                continue
            try:
                existing=[]
                if path.exists():
                    with path.open(encoding='utf-8-sig',newline='') as f:
                        reader=csv.reader(f);header=next(reader,None)
                        if header and header!=batch['columns']:raise ValueError('CSV schema ไม่ตรง')
                        existing=list(reader)
                merged={tuple(r[:2]):r for r in existing if len(r)>=2}
                for row in batch['rows']:
                    key=tuple(str(v) for v in row[:2]);merged.pop(key,None);merged[key]=row
                out=io.StringIO(newline='');writer=csv.writer(out)
                writer.writerow(batch['columns']);writer.writerows(merged.values())
                content=out.getvalue().encode('utf-8-sig');replace_csv(path,content)
                batch.update(status='partial' if batch['retry_symbols'] else 'success',error=None,
                    csv_sha256=hashlib.sha256(content).hexdigest(),
                    signal_date=max((str(r[0]) for r in merged.values()),default=None))
                _status(path,batch);file.unlink();written+=len(batch['rows'])
            except (OSError,ValueError) as error:
                batch.update(status='export_failed',error=type(error).__name__)
                _json(file,batch);_status(path,batch)
                for waiting,waiting_file in batches:
                    if waiting['started_at']>batch['started_at']:
                        waiting.update(status='export_failed',error='previous_export_pending')
                        _json(waiting_file,waiting);_status(path,waiting)
                _log.error('ส่ง scan_log.csv ไม่สำเร็จ เก็บผลรอ retry แล้ว: %s',type(error).__name__)
                break
    return written


def retry_partial(path,market,fetch_missing,*,min_wait=900):
    path=Path(path)
    try:status=json.loads((path.parent/'scan_status.json').read_text())
    except (OSError,ValueError):return False
    if status.get('status')!='partial' or not status.get('retry_symbols') or status.get('retry_attempts',0)>=2:return False
    if status.get('scan_date')!=datetime.now(ZoneInfo('Asia/Bangkok')).date().isoformat():return False
    if (datetime.now(timezone.utc)-datetime.fromisoformat(status['completed_at'])).total_seconds()<min_wait:return False
    # ไฟล์ถูกเปลี่ยนโดยรอบอื่นต้องรอหลักฐานใหม่ ไม่ต่อผลคนละรอบเข้าด้วยกัน
    if hashlib.sha256(path.read_bytes()).hexdigest()!=status.get('csv_sha256'):return False
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.reader(f);columns=next(reader)
        keys={tuple(k) for k in status.get('run_keys',[])}
        rows=[r for r in reader if tuple(r[:2]) in keys]
    with round_scan(market,path) as batch:
        batch['retry_attempts']=status.get('retry_attempts',0)+1
        submit(path,columns,rows,market=market)
        remaining=fetch_missing(status['retry_symbols'])
        note_scan(candidate_count=status['candidate_count'],evaluated_count=max(0,status['candidate_count']-len(remaining)),retry_symbols=remaining)
    return True
