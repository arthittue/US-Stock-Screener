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
