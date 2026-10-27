# SNTalkBot 5.1.35 — Queue Handoff และผลค้นหา 12 รายการ

วันที่ 27 ต.ค. 2569 — แพตช์นี้ยังไม่ได้ติดตั้งบน Linux/TeamTalk จริง

## เหตุผลของการปรับ

บันทึกที่ผู้ใช้ส่งเป็น Publisher log ซึ่งยืนยันว่า GitHub tag, Docker image และ ZIP **5.1.34 เผยแพร่แล้ว** แต่ไม่ใช่ log runtime จาก TeamTalk จึงยังพิสูจน์ไม่ได้ว่า Linux instance ใช้รุ่น 5.1.34 จริง หรือเกิดความล่าช้าจากขั้นตอนใด

จากการไล่โค้ด 5.1.34:

1. การเปลี่ยนเพลงเมื่อ END_FILE ใช้ I/O executor เดียวกับการค้นหา/download
2. การกด `.`/`,` เลือกผลของคิวที่กำลังเล่นเรียก yt-dlp ในเธรด TeamTalk โดยตรง
3. prefetch ยึดล็อก yt-dlp เดียวกับเพลง foreground ตลอดเวลาโหลดจากเครือข่าย
4. คิวใหม่มีผลค้นหาแค่ 1 รายการชั่วคราวจน background โหลด 50/20 ครบ

## สิ่งที่เปลี่ยนใน 5.1.35

- คิวเล่นเพลงลำดับเดียวแยกจากงานค้นหา/download (1 worker); MPV callback แค่ส่งคำสั่งไปงานนั้น ไม่ทำ SQLite/yt-dlp ใน callback
- Search หน้าแรก **12 ผลลัพธ์** แล้วค่อยเติมเต็ม 50/20 รายการเบื้องหลัง; เปลี่ยนผลได้เร็วตั้งแต่แรก
- คำสั่งเลือก `.`/`,` ตอบรับทันทีและส่ง restart ไป worker; คำสั่งเก่าที่ยังไม่ได้เริ่มจะตรวจ queue token และลิงก์ก่อนสั่งเล่นเพื่อไม่เล่นผลที่ถูกเปลี่ยนไปแล้ว
- prefetch network ไม่ยึดล็อกข้อมูลกลาง; ถ้าเล่น URL เดียวกับที่ prefetch อยู่ รอผลที่ใกล้เสร็จสูงสุด 250 มิลลิวินาที มิฉะนั้นเริ่ม foreground extraction ทันที
- เมื่อคิวไม่มีเพลงถัดไป จะเตรียมตัวเลือกถัดไปของเพลงปัจจุบันจากชุดผลค้นหาที่ผูกอยู่กับคิว
- MPV watchdog ตรวจ eof-reached เพิ่มจาก END_FILE/idle-active เพื่อกู้กรณี callback จบเพลงหาย แต่ไม่ข้ามเพลงที่ Pause/กำลัง Buffer

ไม่เปลี่ยน MPV/PulseAudio เป็น TTMediaBot, ไม่เปลี่ยน SQLite/schema, TeamTalk commands, Web Manager, หรือ cookies/18+ และยังคง URL จากแพลตฟอร์มอื่น

## การนำไปใช้

ZIP นี้เป็น **source overlay ของ Bot** ไม่ใช่ Full Project, ไม่มี config.ini / cookies.txt / .env / ฐานข้อมูล

1. สำรองซอร์สโปรเจกต์ SNTalkBot เดิมและค่าตั้งค่าทั้งหมดก่อนลงแพตช์
2. แตก ZIP ทับโฟลเดอร์ **ซอร์ส** ของ SNTalkBot ตามโครงสร้างเดิม เช่น `bot/player.py` และ `bot/modules/player.py` ไม่ใช่โฟลเดอร์ instance
3. รัน `python -m unittest discover -s tests -q` แล้ว `python tools/validate_project.py` ให้ผ่าน
4. ใช้ Publisher workflow เดิมออก **5.1.35** และอัปเดต Docker Bot instances; Web Manager 1.1.29 ไม่ต้องเปลี่ยน
5. ตรวจเวอร์ชัน runtime จริงบน Docker/TeamTalk และรัน server verification gate ตาม workflow ผู้ใช้

## ทดสอบบน TeamTalk

- Queue Mode ON: เพิ่ม 3 เพลง ปล่อยเล่นจนจบ ตรวจ auto-advance ทุกครั้งและสถานะ Speaking ดับหลังคิวหมด
- กด `p <ชื่อเพลง>` / `pm <ชื่อเพลง>` ควรเลือกผล 1–12 ได้ก่อน background expansion เสร็จ รวมกด `.` หรือ `,` หลายครั้งติดกัน
- ระหว่างมีเพลงอยู่ในคิว ให้เพิ่มหลายรายการและตรวจว่าเรียง FIFO แม้มี prefetch อยู่
- Queue OFF: ลองโหมดปกติและ Auto/Next รวมเพลงสั้น, เพลงยาว, Pause/Resume
- ทดสอบ 18+ ที่ใช้ cookies, URL SoundCloud/Twitch/Vimeo หรือ radio/webpage ที่เคยใช้
- ตรวจเวลา log `Playback preparation took`, `Next-track prefetch took`, `MPV watchdog recovered missing playback end` เทียบเสียงจริง

## ผล QA

Unit tests **111/111** ผ่าน และตัวตรวจสอบโครงการผ่าน; ยังไม่ได้ทดสอบการออกเสียงและ TeamTalk SDK บนเซิร์ฟเวอร์จริง

