# CLAUDE.md

> 🔗 **โปรเจกต์นี้เป็น 1 ใน 5 ของ pipeline เดียวกัน** — แผนที่ภาพรวมและสัญญาระหว่างโปรเจกต์อยู่ที่ `C:/Users/arthi/Desktop/Stock Screener/AGENTS.md`
> แก้ของที่โปรเจกต์อื่นอ่านอยู่ (`scan_log.csv` · `signals.json` · `breakouts.json` · ไฟล์ import watchlist) **ต้องอัปเดตไฟล์นั้นในรอบเดียวกัน**

คำแนะนำสำหรับ Claude Code เมื่อทำงานกับ repo นี้

## Agent skills

### Issue tracker

Local markdown — issue เก็บเป็นไฟล์ใน `.scratch/<feature>/` (ไม่ใช้ GitHub Issues) ดู `docs/agents/issue-tracker.md`

### Triage labels

ใช้ชุดมาตรฐาน 5 ตัว (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) บันทึกเป็นบรรทัด `Status:` ในไฟล์ issue ดู `docs/agents/triage-labels.md`

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` ที่ราก repo ดู `docs/agents/domain.md`

## การแก้โค้ดและเครื่องรันจริง
ใช้ Linux ผ่าน SSH และ worktree ตาม REMOTE_WORKFLOW.md; GitHub origin เป็น source หลัก คู่มือ scan delivery v1 อยู่ใน README และ scan_delivery.py (บอท) / lib/scan-status.mjs (Gem)

## ข้อความค้าง (DeliveryReviewRequired)
`durable_jobs.py` mark ข้อความเป็น `uncertain` เมื่อ Telegram timeout เพราะ timeout อาจเกิด**หลัง**
Telegram รับไปแล้ว → payload เดิมโดน `DeliveryReviewRequired` งานตายจนกว่าคนจะตัดสิน
เป็นพฤติกรรมที่ตั้งใจ (ห้ามเปลี่ยนให้ส่งซ้ำอัตโนมัติ — จะยิงซ้ำของที่ถึงแล้ว)

**เครื่องมือคือ `tools/recover_jobs.py`** (ไฟล์เดียวกันเป๊ะทั้ง repo US และ HK เหมือน `durable_jobs.py`):
รันเปล่า = ดูรายการที่รอตรวจ · `--confirm-sent <ID>` = เห็นใน Telegram แล้ว ไม่ส่งซ้ำ ·
`--retry <ID>` = ไม่ถึง ให้ส่งใหม่ · ทั้งสองแบบ**รีเซ็ต `runs` ของ slot นั้นเป็น `failed` ด้วย**
รอบ catch-up ถัดไปจึงทำงานต่อ (ถ้าไม่รีเซ็ต แก้ messages อย่างเดียวจะไม่มีอะไรเกิดขึ้น)
ต้องใส่ ID เต็ม ทำทีละอัน · `health_text()` ใน `durable_jobs.py` โชว์จำนวนที่รอตรวจ

`run` = `job:YYYY-MM-DD` และ key = sha256(run+method+payload) → **แถวค้างของวันเก่าไม่บล็อกวันใหม่**
ที่ต้องปลดจริงคือ slot ของวันที่ยังต้องส่ง ของเก่าปล่อยไว้ได้ (หรือ `--confirm-sent` เก็บกวาด)

สาเหตุที่ค้างบ่อยบนเครื่องนี้ = WiFi หลุดวันละ 1–2 ครั้ง (ไดรเวอร์ `wl` ของ BCM4360) ดู `Trading view/CLAUDE.md`