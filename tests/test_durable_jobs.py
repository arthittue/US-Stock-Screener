import importlib.util
import asyncio
import pytest


def module():
    assert importlib.util.find_spec('durable_jobs'), 'ต้องกู้ claim และ dedup การส่งหลัง crash ได้'
    import durable_jobs
    return durable_jobs


def test_dead_owner_claim_recovered_but_success_never_replayed(tmp_path):
    d=module();db=tmp_path/'jobs.sqlite3'
    first=d.Ledger(db,owner='old',pid=99999999)
    assert first.claim('scan','2026-09-09')
    second=d.Ledger(db,owner='new')
    assert second.claim('scan','2026-09-09')
    second.complete('scan','2026-09-09')
    assert not first.claim('scan','2026-09-09')


def test_confirmed_notification_is_not_sent_twice_after_retry(tmp_path):
    d=module();calls=[]
    class Bot:
        async def send_message(self,**kw):calls.append(kw)
    ledger=d.Ledger(tmp_path/'jobs.sqlite3')
    async def run():
        proxy=d.DurableBot(Bot(),ledger,'scan:2026-09-09')
        await proxy.send_message(chat_id=1,text='same result')
        await proxy.send_message(chat_id=1,text='same result')
    asyncio.run(run());assert len(calls)==1


def test_crash_at_send_boundary_requires_review_not_duplicate(tmp_path):
    d=module();ledger=d.Ledger(tmp_path/'jobs.sqlite3')
    class Bot:
        async def send_message(self,**kw):raise KeyboardInterrupt()
    async def run():
        proxy=d.DurableBot(Bot(),ledger,'scan:2026-09-09')
        with pytest.raises(KeyboardInterrupt):await proxy.send_message(chat_id=1,text='x')
        with pytest.raises(d.DeliveryReviewRequired):await proxy.send_message(chat_id=1,text='x')
    asyncio.run(run())
