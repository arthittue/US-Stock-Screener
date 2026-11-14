import importlib.util
import json
import hashlib
import pytest

def module():
    assert importlib.util.find_spec('scan_delivery'), 'ต้องมี durable scan delivery ที่แยกสถานะออกจาก CSV'
    import scan_delivery
    return scan_delivery


def test_empty_success_has_status_without_fake_rows(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    delivery.submit(p,['scan_date','ticker'],[],market='TH')
    s=json.loads((tmp_path/'scan_status.json').read_text())
    assert s['status']=='success' and s['qualified_count']==0
    assert s['csv_sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(p.read_text(encoding='utf-8-sig').splitlines())==1


def test_export_failure_is_durable_and_retry_needs_no_scan(tmp_path,monkeypatch):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    original=delivery.replace_csv
    monkeypatch.setattr(delivery,'replace_csv',lambda *a: (_ for _ in ()).throw(OSError('locked')))
    assert delivery.submit(p,['scan_date','ticker'],[['2026-09-09','A']],market='US')==0
    assert json.loads((tmp_path/'scan_status.json').read_text())['status']=='export_failed'
    monkeypatch.setattr(delivery,'replace_csv',original)
    assert delivery.retry_exports(p)==1
    assert json.loads((tmp_path/'scan_status.json').read_text())['status']=='success'
    assert p.read_text(encoding='utf-8-sig').count('2026-09-09,A')==1
    delivery.retry_exports(p)
    assert p.read_text(encoding='utf-8-sig').count('2026-09-09,A')==1


def test_round_aggregates_initial_and_rescore_before_ready(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    with delivery.round_scan('HK',p):
        delivery.submit(p,['scan_date','ticker'],[['2026-09-09','A']],market='HK')
        assert json.loads((tmp_path/'scan_status.json').read_text())['status']=='running'
        delivery.submit(p,['scan_date','ticker'],[['2026-09-09','B']],market='HK')
    s=json.loads((tmp_path/'scan_status.json').read_text())
    assert s['status']=='success' and s['qualified_count']==2


def test_partial_is_not_success_and_records_missing_symbols(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    with delivery.round_scan('TH',p):
        delivery.note_scan(candidate_count=3,evaluated_count=2,retry_symbols=['B'])
        delivery.submit(p,['scan_date','ticker'],[],market='TH')
    s=json.loads((tmp_path/'scan_status.json').read_text())
    assert s['status']=='partial' and s['retry_symbols']==['B']


def test_exception_is_failed_not_empty_success(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    with pytest.raises(ValueError):
        with delivery.round_scan('TH',p):
            raise ValueError('upstream')
    assert json.loads((tmp_path/'scan_status.json').read_text())['status']=='failed'


def test_partial_retry_only_fetches_missing_and_preserves_first_results(tmp_path):
    delivery=module();p=tmp_path/'scan_log.csv';columns=['scan_date','ticker']
    with delivery.round_scan('US',p):
        delivery.note_scan(candidate_count=2,evaluated_count=1,retry_symbols=['B'])
        delivery.submit(p,columns,[['2026-09-09','A']],market='US')
    assert hasattr(delivery,'retry_partial'), 'ต้อง retry เฉพาะส่วนที่ขาดโดยไม่สแกนทั้งตลาด'
    calls=[]
    def fetch(symbols):
        calls.extend(symbols)
        delivery.submit(p,columns,[['2026-09-09','B']],market='US')
        return []
    assert delivery.retry_partial(p,'US',fetch,min_wait=0)
    assert calls==['B']
    status=json.loads((tmp_path/'scan_status.json').read_text())
    assert status['status']=='success' and status['qualified_count']==2


def test_new_round_is_not_success_while_older_export_is_blocked(tmp_path,monkeypatch):
    delivery=module();p=tmp_path/'scan_log.csv'
    monkeypatch.setattr(delivery,'replace_csv',lambda *a: (_ for _ in ()).throw(OSError('disk')))
    for ticker in ['A','B']:
        assert delivery.submit(p,['scan_date','ticker'],[['2026-09-09',ticker]],market='US')==0
    assert json.loads((tmp_path/'scan_status.json').read_text())['status']=='export_failed'


def test_error_after_submit_still_exports_scan_rows(tmp_path):
    """Telegram timeout หลังเขียนผลสแกน ต้องไม่ทิ้งผลสแกน (เคส US 6/9 พ.ย. 2026)"""
    delivery=module()
    p=tmp_path/'scan_log.csv'
    class TimedOut(Exception):pass
    with pytest.raises(TimedOut):
        with delivery.round_scan('US',p):
            delivery.submit(p,['scan_date','ticker'],[['2026-11-06','SONY'],['2026-11-06','PFE']],market='US')
            raise TimedOut()
    s=json.loads((tmp_path/'scan_status.json').read_text())
    assert s['status']=='success' and s['qualified_count']==2
    assert s['post_scan_error']=='TimedOut' and s['error'] is None
    assert s['csv_sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert p.read_text(encoding='utf-8-sig').count('2026-11-06,')==2
    assert not [f for f in (tmp_path/'.scan_delivery').glob('*.json')]


def test_error_after_submit_keeps_partial_when_symbols_were_skipped(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    with pytest.raises(RuntimeError):
        with delivery.round_scan('US',p):
            delivery.note_scan(candidate_count=3,evaluated_count=2,retry_symbols=['B'])
            delivery.submit(p,['scan_date','ticker'],[['2026-11-06','A']],market='US')
            raise RuntimeError('send failed')
    s=json.loads((tmp_path/'scan_status.json').read_text())
    assert s['status']=='partial' and s['retry_symbols']==['B'] and s['post_scan_error']=='RuntimeError'


def test_error_before_submit_is_still_failed(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    with pytest.raises(RuntimeError):
        with delivery.round_scan('US',p):
            raise RuntimeError('fetch failed')
    s=json.loads((tmp_path/'scan_status.json').read_text())
    assert s['status']=='failed' and not p.exists()


def test_cancel_after_submit_is_failed_not_exported(tmp_path):
    delivery=module()
    p=tmp_path/'scan_log.csv'
    with pytest.raises(KeyboardInterrupt):
        with delivery.round_scan('US',p):
            delivery.submit(p,['scan_date','ticker'],[['2026-11-06','A']],market='US')
            raise KeyboardInterrupt()
    assert json.loads((tmp_path/'scan_status.json').read_text())['status']=='failed'
