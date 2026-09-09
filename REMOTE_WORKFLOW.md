# วิธีทำงานผ่าน Remote

GitHub `origin` ของ arthittue เป็นแหล่งโค้ดหลัก Linux `meawnam@192.168.1.82` เป็นเครื่องรันจริง Windows ใช้ remote/อ่านโค้ด ไม่เปิดบอทหรือ pipeline อัตโนมัติซ้ำ

- เริ่มด้วย git status และ fetch บน Linux; ไม่แก้ไฟล์ใน checkout ที่ systemd ใช้อยู่
- สร้าง branch codex/... และ worktree แยก ทดสอบด้วยไฟล์ state ชั่วคราว ห้ามเปิด Telegram polling ตัวที่สองด้วย token เดิม
- Commit/push ไป origin หลังทดสอบ รวมเข้า branch ที่ service ใช้ แล้ว fast-forward checkout จริงและ restart เฉพาะ service ที่เปลี่ยน
- ตรวจ commit, service, job result หลัง rollout; เก็บ .env, SQLite, browser profile และ backups แยกจาก Git source
- Remote peod เป็น upstream ภายนอก นำเข้าผ่าน review เท่านั้น ไม่สลับ push ไปมา
- การเปลี่ยน schema scan_status หรือ CSV ต้องปรับบอท, Gem และ Dashboard พร้อมกัน ดู README
- เครื่อง laptop ต้องตื่นและต่อเครือข่ายเพื่อให้รอบอัตโนมัติทำงาน การมี timer ไม่ทำให้เครื่องที่หลับสแกนได้
