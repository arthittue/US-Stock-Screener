"""กู้รอบงานหลังโปรเซสดับ และเก็บหลักฐานการส่งก่อนเรียก Telegram"""
import asyncio
import base64
import contextvars
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

_session=uuid.uuid4().hex
_current=contextvars.ContextVar('durable_bot',default=None)

class DeliveryReviewRequired(RuntimeError):
    pass

def _alive(pid):
    try:os.kill(pid,0);return True
    except (OSError,ValueError):return False

class Ledger:
    def __init__(self,path,owner=None,pid=None):
        self.path=Path(path);self.owner=owner or _session;self.pid=os.getpid() if pid is None else pid
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS runs(job TEXT,slot TEXT,state TEXT,owner TEXT,pid INTEGER,updated REAL,PRIMARY KEY(job,slot));
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,run TEXT,method TEXT,payload TEXT,state TEXT,updated REAL);
            ''')
    def connect(self):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row;return c
    def claim(self,job,slot):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM runs WHERE job=? AND slot=?',(job,slot)).fetchone()
            if row and row['state']=='succeeded':return False
            if row and row['state']=='running' and (row['owner']==self.owner or (_alive(row['pid']) and time.time()-row['updated']<1800)):return False
            c.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?)',(job,slot,'running',self.owner,self.pid,time.time()))
            return True
    def state(self,job,slot):
        with self.connect() as c:
            r=c.execute('SELECT * FROM runs WHERE job=? AND slot=?',(job,slot)).fetchone()
            if not r:return None
            if r['state']=='running' and r['owner']!=self.owner and (not _alive(r['pid']) or time.time()-r['updated']>=1800):return 'abandoned'
            return r['state']
    def complete(self,job,slot):
        with self.connect() as c:c.execute('UPDATE runs SET state=?,updated=? WHERE job=? AND slot=?',('succeeded',time.time(),job,slot))
    def release(self,job,slot):
        with self.connect() as c:c.execute('UPDATE runs SET state=?,updated=? WHERE job=? AND slot=?',('failed',time.time(),job,slot))
    def review(self):
        with self.connect() as c:return [dict(r) for r in c.execute("SELECT id,run,method,state FROM messages WHERE state IN ('sending','uncertain')")]

def _encode(x):
    if isinstance(x,bytes):return {'_bytes':base64.b64encode(x).decode()}
    if hasattr(x,'read'):
        pos=x.tell() if hasattr(x,'tell') else None
        raw=x.read()
        if pos is not None:x.seek(pos)
        return _encode(raw)
    if hasattr(x,'to_dict'):return _encode(x.to_dict())
    if isinstance(x,dict):return {k:_encode(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [_encode(v) for v in x]
    return x

class DurableBot:
    def __init__(self,bot,ledger,run):self.bot=bot;self.ledger=ledger;self.run=run
    def __getattr__(self,name):return getattr(self.bot,name)
    async def _send(self,method,args,kwargs):
        payload=json.dumps({'args':_encode(args),'kwargs':_encode(kwargs)},sort_keys=True,ensure_ascii=False)
        key=hashlib.sha256((self.run+method+payload).encode()).hexdigest()
        with self.ledger.connect() as c:
            row=c.execute('SELECT state FROM messages WHERE id=?',(key,)).fetchone()
            if row and row['state']=='sent':return None
            if row and row['state'] in ('sending','uncertain'):
                raise DeliveryReviewRequired('การส่งอาจสำเร็จก่อนโปรเซสดับ ต้องตรวจ Telegram ก่อน retry: '+key[:12])
            c.execute('INSERT OR REPLACE INTO messages VALUES(?,?,?,?,?,?)',(key,self.run,method,payload,'sending',time.time()))
        try:
            result=await getattr(self.bot,method)(*args,**kwargs)
        except BaseException as error:
            # Timeout อาจเกิดหลัง Telegram รับแล้ว จึงไม่ส่งซ้ำอัตโนมัติแบบเดา
            state='pending' if type(error).__name__ in ('RetryAfter','BadRequest','Forbidden') else 'uncertain'
            with self.ledger.connect() as c:c.execute('UPDATE messages SET state=?,updated=? WHERE id=?',(state,time.time(),key))
            raise
        with self.ledger.connect() as c:c.execute('UPDATE messages SET state=?,updated=? WHERE id=?',('sent',time.time(),key))
        return result
    async def send_message(self,*args,**kwargs):return await self._send('send_message',args,kwargs)
    async def send_photo(self,*args,**kwargs):return await self._send('send_photo',args,kwargs)
    async def send_document(self,*args,**kwargs):return await self._send('send_document',args,kwargs)

def job_bot(bot):
    return _current.get() or bot

def bind(bot,ledger,run):
    return _current.set(DurableBot(bot,ledger,run))

def unbind(token):
    _current.reset(token)


def health_text(path):
    path=Path(path)
    if not path.exists():return ''
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as c:
        review=c.execute("SELECT COUNT(*) FROM messages WHERE state IN ('sending','uncertain')").fetchone()[0]
        running=c.execute("SELECT COUNT(*) FROM runs WHERE state='running'").fetchone()[0]
    return ('\n⚠️ การส่ง '+str(review)+' รายการรอตรวจ Telegram ก่อน retry (tools/recover_jobs.py)' if review else '')+('\nรอบงานกำลังทำ '+str(running)+' รอบ' if running else '')
