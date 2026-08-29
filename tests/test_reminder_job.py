"""reminder_job รันจนจบโดยไม่ล้ม (bot/main.py)

บั๊กเดิม: bot/main.py import datetime มาไม่ครบ — ขาด timedelta ที่ reminder_job
ใช้คิดวันปลายทางของคลังวันงบ → NameError ทุกเช้า 08:25 ผู้ใช้เห็นแต่ข้อความ
"job reminder ล้มเหลว" ใน Telegram (weekly_job 09:00 วันอาทิตย์ก็ใช้ชื่อเดียวกัน)

ไม่มีเทสต์ไหนเรียก job พวกนี้เลย บั๊กจึงผ่าน 632 เทสต์มาได้ — ไฟล์นี้ปิดรูนั้น
"""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from bot import jobstate
from bot import main
from bot.config import Config

DUMMY_CONFIG = Config(telegram_token="123:ABC", chat_id="1", fmp_api_key="k")


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id=None, text=None, **kwargs):
        self.sent.append(text)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """claim/release ลงไฟล์ชั่วคราว + config หลอก + ตัดทุกอย่างที่ยิงเน็ต"""
    state = tmp_path / "job_state.json"
    monkeypatch.setattr(main, "claim", lambda name: jobstate.claim(name, path=state))
    monkeypatch.setattr(main, "release", lambda name: jobstate.release(name, path=state))
    monkeypatch.setattr(main, "CONFIG", DUMMY_CONFIG)
    main._fail_counts.clear()

    calls = {}
    monkeypatch.setattr(main, "all_watched", lambda: [])
    monkeypatch.setattr(main, "FMPClient", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(main, "default_sources", lambda client, key: ["src"])

    def fake_refresh(sources, from_date, to_date, today):
        calls["refresh"] = (from_date, to_date, today)

    monkeypatch.setattr(main, "refresh", fake_refresh)

    bot = FakeBot()
    return SimpleNamespace(bot=bot, ctx=SimpleNamespace(bot=bot), calls=calls)


def test_reminder_job_runs_without_failing(env):
    """ไม่มีข้อความ "ล้มเหลว" ส่งออก = job ไม่โยน exception"""
    asyncio.run(main.reminder_job(env.ctx))
    assert env.bot.sent == []


def test_reminder_job_refreshes_seven_days_ahead(env):
    """ปลายทางของคลังวันงบ = วันนี้ + REFRESH_AHEAD_DAYS (บรรทัดที่เคยพัง)"""
    asyncio.run(main.reminder_job(env.ctx))
    from_date, to_date, today = env.calls["refresh"]
    assert from_date == today.isoformat()
    assert to_date == (today + timedelta(days=main.REFRESH_AHEAD_DAYS)).isoformat()
    assert isinstance(today, date)
