# SNTalkBot 5.1.23 — Restart/Shutdown Lifecycle Signal Hardening

## แก้คำสั่ง restart / shutdown แบบรากฐาน

- แก้ `restart` / `rs` ที่อาจตอบ `Command restart failed: RestartSignal` แทนการรีสตาร์ทจริง
- แก้ `shutdown` / `sd` ด้วยกฎเดียวกัน เพื่อไม่ให้เกิดอาการแบบเดียวกันในอนาคต
- `RestartSignal` และ `ShutdownSignal` เปลี่ยนเป็น control-flow signal เฉพาะที่สืบทอดจาก `BaseException` ผ่าน `LifecycleSignal` จึงไม่ถูก `except Exception` ของ wrapper/โมดูลทั่วไปกลืนอีก
- CommandHandler ยังบันทึก `command_signal` แล้ว re-raise ไปยัง `main.py`; main launcher เป็นผู้จับ signal เพื่อ shutdown/restart ตามสถาปัตยกรรมเดิม
- เพิ่ม regression ใช้ alias จริง `rs` และ `sd` ผ่าน CommandHandler และตรวจว่า signal หลุดถึง launcher boundary

## ไม่เปลี่ยน action เพลงและระบบอื่น

- คง `p` = YouTube, `pm` = YouTube Music, `u` = URL, `select/c` = Queue/Playlist และ `.` / `,` = ผลค้นหา
- คง logging/action lifecycle, Queue/SQLite/WAL, playback recovery, Telegram precedence, GitHub Release webhook และ Web Manager 1.1.22 จากรุ่นก่อน
- 121 canonical commands / 52 aliases เท่าเดิม
- Web Manager 1.1.22 และ TTUHelper 1.5.7 ไม่ต้องเปลี่ยนโค้ดใน hotfix นี้
