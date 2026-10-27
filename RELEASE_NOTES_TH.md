# SNTalkBot 5.1.35 — ส่งต่อเพลงอัตโนมัติและเลือกผลค้นหาได้ไว (ยังไม่เผยแพร่)

- แยกงานเปลี่ยนเพลง/จบคิวเป็นคิวเล่นเพลงเฉพาะ ไม่ต้องรอ IO pool ที่กำลังค้นหา/download
- คิวผลค้นหา YouTube/YouTube Music พร้อมเลือก 12 ทางเลือกตั้งแต่แรกแทน 1 ทางเลือก แล้วเติม 50/20 ในเบื้องหลังต่อ
- แก้การเลือกผล `.`/`,` ไม่ให้เรียก yt-dlp ค้างใน TeamTalk event thread; งานเลือกเก่าที่ยังรออยู่จะไม่ทับตัวเลือกใหม่
- งาน prefetch ไม่ขังล็อกของเพลงที่ผู้ใช้กำลังจะเล่น; foreground รอผลของ URL เดียวกันไม่เกิน 250ms
- MPV watchdog กู้ EOF ที่แจ้งผ่าน `eof-reached` แต่ไม่มี END_FILE/idle transition; คงการปิด Speaking เมื่อจบคิว
- ไม่แก้ฐานข้อมูล คุกกี้ 18+ ระบบรองรับแพลตฟอร์มอื่น และ Web Manager 1.1.29
- Unit tests 111 ผ่านและ validator ผ่าน; ยังต้องทดสอบเสียงบน TeamTalk Server จริง

---

# SNTalkBot 5.1.34 — แก้การไม่เลื่อนเพลงและ Speaking ค้าง (เผยแพร่แล้ว)

- เพิ่ม MPV watchdog ตรวจ idle / ความคืบหน้าตำแหน่งเพลง หาก callback จบเพลงหายจะกู้การเล่นต่อโดยไม่ข้ามคิวซ้ำ
- เมื่อเล่นจนหมดคิว จะล้างสถานะเพลงและปิด TeamTalk voice transmission พร้อมคืนสถานะว่าง; คง 18+ และการรองรับแพลตฟอร์มเดิม
- ใช้เฉพาะหลักการ auto-stop/watchdog จาก TTMediaBot ไม่เปลี่ยน MPV/SQLite หรือ Web Manager เดิม
- รวมงานเร่งเริ่มเพลงแรกและเตรียมเพลงถัดไปในรุ่น 5.1.32–5.1.33; การทดสอบบน TeamTalk จริงยังค้างอยู่

---

# SNTalkBot 5.1.33 — เริ่มเพลงแรกเร็วขึ้น (ยังไม่เผยแพร่)

- เปรียบเทียบแนวทางจาก TTMediaBot: ใช้การค้นหาผลแรกให้ไว แล้วค่อยดึงทางเลือกที่เหลือ โดยไม่ย้ายระบบ FFmpeg/PCM สำหรับ Windows มาแทน MPV/PulseAudio บน Linux ของเรา
- เพลงแรกของ Queue Mode และโหมดปกติสำหรับ `p` (YouTube) และ `pm` (YouTube Music) ไม่ต้องรอผลค้นหาทั้งชุด 50/20 รายการก่อนสั่งเล่นแล้ว
- ระบบเติมผลค้นหาทางเลือกในเบื้องหลัง พร้อมป้องกันการอัปเดตทับคำขอใหม่หรือคิวเพลงของคนอื่นด้วย queue token/search session
- เพิ่ม log เวลาค้นหาที่ช้าเกิน 2 วินาที แยกให้เห็นว่ารอก่อนผลแรกหรือรอขั้นเตรียม stream/MPV
- คงความสามารถเลือกผลค้นหาเต็มชุดเมื่อโหลดเสร็จ, ชื่อ/แหล่งที่มาของ YouTube Music, วิดีโอ 18+ และแพลตฟอร์มทั่วไปที่ yt-dlp รองรับ
- ต่อจาก 5.1.32 ซึ่งเร่งการเตรียมเพลงถัดไปและแก้ TTL ของข้อมูลที่เตรียมแล้ว; ไม่เปลี่ยน Web Manager 1.1.29 หรือไฟล์คุกกี้
- **ต้องทดสอบเวลาที่เสียงเริ่มจริงบน Docker/TeamTalk** เพราะเวลาใน yt-dlp และ MPV ขึ้นกับเครือข่าย/เซิร์ฟเวอร์ภายนอก
- **QA ออฟไลน์:** Unit tests 97 รายการผ่าน รวมกรณีค้นหาผลแรกไม่สำเร็จแล้ว fallback เป็นวิธีเต็มชุด และ generic resolver ของแพลตฟอร์มอื่น

---

# SNTalkBot 5.1.32 — เร่งการเล่นเพลงและต่อคิว (ยังไม่เผยแพร่)

- ป้องกันงานเตรียมเพลงลำดับไกล 3–6 แย่งใช้ล็อก yt-dlp กับเพลงถัดไป ให้เตรียมเฉพาะเพลงที่กำลังจะมาถึง
- เพลงยาวเกิน 5 นาทีไม่ทำให้ข้อมูลเพลงถัดไปที่ยังใช้ได้ถูกทิ้งก่อนเวลา: เก็บได้ถึง 30 นาที โดยยังตรวจ signed URL expiration ก่อนใช้
- ถ้าเตรียม/ดึงข้อมูลช้าเกิน 2 วินาที บันทึกเวลาใน log โดยไม่เปิดเผยลิงก์หรือ Cookie เพื่อใช้วิเคราะห์ความหน่วงต่อ
- คงความสามารถเล่นคลิป 18+ ผ่าน Cookie-first; คงลำดับ Queue, ตัวเลือก Player, config.ini.lock ที่ใช้ร่วมกับ Manager, Web Manager 1.1.29 และข้อมูลเดิมทุกตัว
- **QA:** Unit tests 90/90 ผ่าน และตัวตรวจโปรเจกต์ออฟไลน์ผ่าน; การรับรองช่องว่างเวลาเล่นจริงต้องตรวจบน Docker/TeamTalk หลังติดตั้ง; ไม่มีการปรับไฟล์ Cookie

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
