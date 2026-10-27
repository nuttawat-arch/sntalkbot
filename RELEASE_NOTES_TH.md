# SNTalkBot 5.1.31 — Windows Publisher Compatibility Fix

- แก้ความผิดพลาดของตัวตรวจ Config migration บน Windows ที่ไม่มี `os.geteuid()` ใน Bot 5.1.30
- บอตยังจัดสิทธิ์ `config.ini.lock` เป็น `0660` เฉพาะ Linux/POSIX; Windows validation ไม่เรียกคำสั่งระบบที่ไม่มี
- เพิ่ม unit test จำลอง Windows และรักษา Linux restrictive-umask regression; offline tests 85 ผ่าน
- ไม่เปลี่ยน TeamTalk, SQLite, cookies, config หรือคำสั่งจากรุ่นเดิม; ใช้กับ Web Manager 1.1.29

---

# SNTalkBot 5.1.30 — Shared Config Lock Permission Hotfix

- แก้ `config.ini.lock` ให้เป็น mode `0660` เมื่อไฟล์เป็นของ process บอต แม้ Linux ใช้ restrictive umask เพื่อให้ Web Manager 1.1.28 เขียนร่วมกับบอตได้
- คง stable cross-process flock, ทุกค่าตั้งค่าเดิม, คำสั่ง TeamTalk, SQLite queue และ cookies ทุกตัว
- Unit tests ออฟไลน์ 84 ผ่าน; ต้องตรวจ Docker/TeamTalk จริงหลังเผยแพร่

---

# SNTalkBot 5.1.29 — Live Player Settings for Web Manager

- เพิ่มสถานะ `channel_messages`, `announce_tracks`, `announce_queue`, `announcement_tts_mode` ใน RAM snapshot ที่ API ส่งให้เว็บ เพื่อแสดง Checkbox/Radio Button ตรงกับค่า Player จริง
- ไม่มีการเปลี่ยนการเล่นเพลง, คิว SQLite, TeamTalk commands หรือ Cookie; ใช้งานร่วม Web Manager 1.1.27
- เตรียมออกเวอร์ชันใหม่หลัง 5.1.28 ซึ่งเผยแพร่ GitHub/Docker/ZIP/เว็บไซต์สำเร็จแล้วตาม Windows Publisher log; ตรวจ Linux runtime จริงหลังติดตั้ง

---

# SNTalkBot 5.1.24 — Full Playlist Loading

- แก้ Playlist ที่มีมากกว่า 100 เพลงถูกตัดเหลือ 100 ทั้ง Queue Mode และโหมดปกติ
- Playlist YouTube/YouTube Music ไม่มี default cap 100 อีกต่อไป; ทดสอบ fixture 350 เพลงแล้วโหลดครบ
- Search และ channel discovery ยังคง limit ของตัวเอง ไม่ถูกปลดเพดานตาม Playlist
- ไม่เปลี่ยน source intent: `p` = YouTube, `pm` = YouTube Music, `u` = URL, `select/c` = Queue/Playlist
- ทำงานคู่กับ TTUHelper 1.5.8 และ Web Manager 1.1.23 ซึ่งสร้าง Player/Full ใหม่พร้อม persistent default `cookies.txt` จาก Docker image

---

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
