"""ตรวจ/แก้สถานะส่งที่ไม่ชัดเจน หลังตรวจ Telegram ด้วยตนเองแล้วเท่านั้น"""
import argparse
import json
from pathlib import Path
import sqlite3

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--db',type=Path,default=Path(__file__).resolve().parents[1]/'job_runs.sqlite3')
p.add_argument('--confirm-sent',metavar='ID')
p.add_argument('--retry',metavar='ID')
a=p.parse_args()
if not a.db.exists():print('ยังไม่มี ledger');raise SystemExit(0)
with sqlite3.connect(a.db) as c:
    if a.confirm_sent or a.retry:
        key=a.confirm_sent or a.retry
        row=c.execute("SELECT run FROM messages WHERE id=? AND state IN ('sending','uncertain')",(key,)).fetchone()
        if not row:raise SystemExit('ไม่พบข้อความที่รอตรวจด้วย ID นี้')
        c.execute('UPDATE messages SET state=? WHERE id=?',('sent' if a.confirm_sent else 'pending',key))
        job,slot=row[0].split(':',1)
        c.execute("UPDATE runs SET state='failed' WHERE job=? AND slot=?",(job,slot))
        print('บันทึกแล้ว รอบ catch-up ถัดไปจะดำเนินงานต่อ')
    for row in c.execute("SELECT id,run,method,state FROM messages WHERE state IN ('sending','uncertain','pending')"):
        print(json.dumps(dict(zip(['id','run','method','state'],row)),ensure_ascii=False))
