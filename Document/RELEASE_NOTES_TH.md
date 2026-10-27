# SNTalkBot 5.1.35 — คิวเพลงต่อเนื่องและผลค้นหา 12 ทางเลือก (ยังไม่เผยแพร่)

- แยก ordered playback worker สำหรับ callback จบเพลง / ส่งต่อคิว / เล่นเพลงแรก / เปลี่ยนผลคิว ไม่ให้รอการค้นหา/download บน io_pool
- ปรับผลค้นหาเบื้องต้นจาก 1 เป็น 12 ทางเลือกที่เลือกได้เลย ทั้ง YouTube และ YouTube Music; ยังคงเติม 50/20 รายการเต็มใน background
- foreground yt-dlp ไม่ถูกล็อกโดย prefetch ของเพลงอื่น และรอแค่ 250ms เมื่อ prefetch URL เดียวกันใกล้เสร็จ
- เพิ่ม `eof-reached` fallback ให้ MPV watchdog ในกรณี END_FILE หายและ idle ไม่เปลี่ยน คงการตรวจซ้ำ/รุ่น playback ที่ถูกต้อง
- ไม่เปลี่ยน TeamTalk API, cookie policy, 18+, generic URLs, SQLite schema หรือ Web Manager 1.1.29
- Unit tests 111/111 และ `tools/validate_project.py` ผ่าน; ต้องยืนยันการเล่นจริงบน Linux/TeamTalk หลังอัปเดต

---

# SNTalkBot 5.1.34 — เพลงจบแล้วเลื่อนคิวเองและไม่ค้าง Speaking (เผยแพร่แล้ว)

- เพิ่มตัวตรวจจับสำรองเมื่อ MPV ไม่ส่ง END_FILE: เช็ก idle ทุก 1 วินาที พร้อม guard กันสลับเพลงซ้ำและข้ามเพลงเก่า; เมื่อมี time-pos หยุดเดินผิดปกติจึงเข้า retry/skip ที่มีอยู่แล้ว
- คิวเพลงสุดท้ายจบ: ปิดการส่งเสียง TeamTalk, เปลี่ยนสถานะกลับเป็น idle ตามที่ตั้งไว้ และล้าง now-playing; หาก Autoplay ไม่มีเพลงถัดไปให้หยุดอย่างเรียบร้อย
- อิงแนวคิด final-stop และ watchdog จากซอร์ส TTMediaBot โดยไม่เปลี่ยนระบบ MPV, FFmpeg path, SQLite, cookie 18+ หรือแพลตฟอร์มที่รองรับ
- รวมงาน 5.1.32–5.1.33 ที่ยังไม่เผยแพร่ (เตรียมเพลงถัดไป + เริ่มเพลงแรกเร็วขึ้น)
- ออฟไลน์ Unit tests 104 ผ่าน; ต้องทดสอบ TeamTalk/Docker จริงก่อนถือว่ายืนยันแก้อาการบนเซิร์ฟเวอร์แล้ว

---

# SNTalkBot 5.1.33 — Fast First Track / TTMediaBot comparison (ยังไม่เผยแพร่)

- เลือกนำแนวคิดค้นหาผลแรกจำนวนน้อยจาก TTMediaBot มาใช้กับทั้ง Queue Mode และโหมดปกติ; เริ่มเพลงก่อนขอผลค้นหาครบ 50/20 รายการ
- เติมผลการเลือกเพลงใน background โดยไม่เปลี่ยนเพลงที่กำลังเล่นและไม่เขียนทับคำค้นหา/รายการคิวใหม่
- รักษาความเข้ากันได้ของ 18+, yt-dlp ทั่วไป, mpv บน Docker, YouTube Music และ Web Manager เดิม
- ดู `Document/TTMEDIABOT_COMPARISON_TH.md` สำหรับหลักฐานข้อดี/ข้อจำกัดและเหตุผลที่ไม่ย้ายเครื่องเล่น

---

# SNTalkBot 5.1.32 — Playback Handoff Latency Patch (ยังไม่เผยแพร่)

- ลดงาน prefetch เหลือเพลงถัดไปเพียงเพลงเดียวใน Queue และ Playlist เพื่อหลีกเลี่ยงการรอ yt-dlp lock ของเพลงลำดับไกล
- ปรับ cache ของ metadata ที่เตรียมไว้ให้มีอายุสูงสุด 30 นาที พร้อมตรวจลิงก์ที่มีวันหมดอายุจริงก่อนเล่น
- เพิ่ม log เตือนการเตรียมเพลงนานกว่า 2 วินาที; ไม่บันทึก URL หรือความลับใน log
- คงระบบคุกกี้สำหรับคลิปจำกัดอายุและ config lock Windows/Linux ของรุ่น 5.1.31; Web Manager 1.1.29 ไม่ต้องเปลี่ยน
- ต้องวัดช่องว่างเสียงจริงหลังอัปเดต Docker/TeamTalk; ยังไม่อ้างว่าได้เวลา 0 วินาที

---

# SNTalkBot 5.1.30 — Shared Config Lock Permission Hotfix

- บอตแก้ group-write `0660` ของ stable `config.ini.lock` หลังเปิดไฟล์ แม้ umask เข้ม เพื่อป้องกัน Web Manager ติด PermissionError
- คง queue SQLite, TeamTalk, config และ cookies ทั้งหมด; Web Manager 1.1.28 repair permission ไฟล์ล็อกเก่าเมื่ออัปเดต
- Unit tests ออฟไลน์ 84 ผ่าน; ยังต้องตรวจ Linux/TeamTalk จริง

---

# SNTalkBot 5.1.29 — Live Player Settings for Web Manager

- เพิ่มสถานะ Player ที่จำเป็นต่อ Checkbox/Radio Button ของ Web Manager 1.1.27 ผ่าน RAM snapshot โดยไม่เปลี่ยน Queue/TeamTalk/Cookie
- เตรียมเวอร์ชันถัดจาก 5.1.28 ซึ่ง Windows Publisher log ระบุว่าเผยแพร่ Docker/ZIP/เว็บไซต์ และผลักแท็ก GitHub สำเร็จแล้ว
- ทดสอบบน Linux/TeamTalk/NVDA จริงหลังเผยแพร่

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
