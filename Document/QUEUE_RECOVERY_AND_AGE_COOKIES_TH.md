# แก้เพลงถูกข้ามในคิวและคุกกี้วิดีโอจำกัดอายุ

26 ตุลาคม 2026 — Bot 5.1.27 / Manager 1.1.26 / TTUHelper 1.5.10 (Helper ไม่เปลี่ยนจากรอบก่อน)

## การแก้โค้ดในรอบนี้

ใช้ debugging-strategies และ python-testing-patterns จาก skills.zip ตรวจระบบ retry, event callbacks, prefetch และ SQLite เดิมก่อนแก้ ไม่สร้าง player หรือ dispatcher ตัวที่สอง

พบช่องว่างที่จำลองได้ดังนี้:

- callback ซ้ำหลังส่ง retry แต่ก่อน worker เริ่ม อาจใช้ retry budget ซ้ำและข้ามคิว
- callback เก่าที่รออยู่ใน IO pool อาจมาถึงหลังเปลี่ยนรายการ และไป consume รายการถัดไป
- retry ที่รออยู่ไม่มีการยกเลิกอย่างชัดเจนเมื่อผู้ใช้กดหยุด/เลือกเพลงใหม่
- prefetch ตรวจอายุ 5 นาที แต่ไม่ตรวจ expire ของ URL สตรีมจริง
- mpv ทำ HTTP request แยกจาก yt-dlp แต่ไม่ได้รับ User-Agent/Referer/Origin ที่ extractor ระบุ
- เมื่อหมด retry รายการที่เสียถูกนำออกโดยไม่มี persistent failed history ให้เรียกกลับ

แก้ภายในเมธอดเดิมโดย:

1. reserve pending retry ตั้งแต่ก่อน submit และ deduplicate terminal callback ตาม context/epoch/error generation
2. ใช้ native mpv playlist_entry_id เมื่อ binding รองรับ แยก event เก่าจาก event ของเพลงใหม่ และคง fallback ของ binding เก่า
3. retry ขอ metadata/stream URL ใหม่ ไม่ใช้ prefetch เก่า; ตรวจ signed URL expire พร้อมระยะเผื่อ 60 วินาที
4. ตั้งค่าเริ่มต้น retry เพิ่มได้ 3 ครั้งหลังครั้งแรก รอ 2, 4, 6 วินาทีก่อนลองตามลำดับ ปรับได้ที่ Manager > ตั้งค่าบอต > การเล่นเสียง: playback_retry_attempts (1–5), playback_retry_delay (0–30 วินาที)
5. ยกเลิก retry ที่ค้างเมื่อ Stop/Next/Previous/Select/CQ/เปลี่ยนเพลง และตรวจ cancel หลัง resolve ก่อนสั่ง mpv; CQ ระหว่างรอ retry จะปิด voice transmission ที่ค้างด้วย
6. ส่งเฉพาะ HTTP headers ที่จำเป็นและปลอดภัยให้ mpv และ reset ทุกไฟล์ ไม่ส่ง Cookie/Authorization จาก metadata เพิ่มโดยพลการ
7. เมื่อยังเล่นไม่ได้ เก็บรายการพร้อมเหตุผล/จำนวนครั้งใน SQLite แล้วเดินต่อไปเพลงถัดไป มีข้อความแจ้ง ไม่ทำให้เพลงหายโดยต้องค้นใหม่
8. explicit age-auth error จะไม่วนลองแบบไม่ล็อกอิน เพราะไม่ช่วยให้มีสิทธิ์เข้าถึง; เก็บรายการไว้รอแก้บัญชี/คุกกี้

คง FIFO, คิวที่เหลือ, favorites, คำสั่ง CQ, source routing YouTube/YouTube Music, config safety และแผงควบคุมของรอบก่อน

## รายการที่เล่นไม่สำเร็จ

Manager > instance > ควบคุมเพลงและประกาศ > รายการที่เล่นไม่สำเร็จ > ส่งกลับท้ายคิว

แสดง 100 รายการล่าสุด แต่ฐานข้อมูลไม่ตัดรายการที่เกิน 100 ออก เมื่อกดส่งกลับ ระบบย้ายรายการกลับท้ายคิวและลบจาก failed history ใน transaction เดียว ไม่ส่งซ้ำเมื่อกดรายการเดิมสองครั้ง

การเก็บ failed item และนำออกจาก active queue ก็อยู่ใน transaction เดียว: ถ้าเขียนฐานข้อมูลล้มเหลว เพลงยังอยู่ในคิว ไม่หายจากทั้งสองที่ รายการที่จบปกติไม่เข้า failed history

ส่งกลับท้ายคิวไม่ได้สั่งเล่นทันที หากบอตหยุดอยู่ให้กดเล่นรายการนั้นจากคิว ถ้าคุกกี้หรือสิทธิ์ยังไม่ถูกต้องก็ยังอาจเล่นไม่ได้

SQLite schema ขยับจาก 3 เป็น 4 โดยเพิ่ม queue_failures; migration รักษา queue_entries เดิมและทดสอบกับ 1,000 รายการแล้ว บอตรุ่นเก่าจะปฏิเสธฐาน schema ใหม่ตามกฎป้องกัน downgrade เดิม

## คุกกี้สำหรับคลิปจำกัดอายุ

ต้องเป็น session ของบัญชีที่มีสิทธิ์ดูคลิปนั้นจริง และผ่านการยืนยันอายุตามที่ Google/YouTube กำหนดแล้ว การมีไฟล์ cookies.txt หรือเปลี่ยนค่าภายในไฟล์ไม่ได้ทำให้บัญชีได้รับสิทธิ์ดังกล่าว

ใช้เครื่องมือเดิมในโปรเจกต์ได้ดังนี้:

1. เปิด browser profile ที่ต้องการใช้กับบอตและล็อกอิน YouTube ด้วยบัญชีที่มีอายุถึงเกณฑ์
2. เปิดคลิปที่มีปัญหา ยืนยันตามหน้าของ YouTube และตรวจว่าคลิปเล่นได้จริงด้วยบัญชีนั้นก่อน
3. ส่งออกคุกกี้จาก profile เดียวกันหลังขั้นตอนนี้ เลือก BrowserSpec ให้ตรงตามที่สคริปต์ -ListProfiles แสดง เช่น chrome:Profile 2; ไม่เลือก profile อื่นที่ยังไม่ได้ล็อกอิน
4. อัปโหลดผ่าน Manager > ระบบและอัปเดต > Cookies เพื่อแทนค่าเริ่มต้นและทุก Player/Full หรืออัปโหลดราย instance ที่ต้องการ
5. ส่งเพลงใน failed history กลับท้ายคิวเพื่อลองอีกครั้ง

สคริปต์ tools/export_youtube_cookies.ps1 ใช้ --cookies-from-browser จึงอ่าน profile ปกติ ไม่ใช่คุกกี้จาก private/incognito session

หากต้องการใช้วิธี private session ที่เอกสาร yt-dlp แนะนำ: เปิดหน้าต่าง private ใหม่ ล็อกอินและตรวจสิทธิ์ดูคลิป จากแท็บเดียวกันไป https://www.youtube.com/robots.txt ส่งออก youtube.com cookies ด้วยเครื่องมือที่อ่าน private session นั้นได้จริง แล้วปิดหน้าต่าง private ไม่เปิด session นั้นใช้งานต่อ วิธีนี้ต้องใช้ exporter/extension ที่รองรับ private session; สคริปต์ CLI เดิมไม่ใช่เครื่องมือสำหรับขั้นตอนนี้

ไม่รับรองว่าจะไม่มี prompt หรือข้อจำกัดอีกตลอดไป เพราะ YouTube อาจเปลี่ยน session/ข้อกำหนดการเข้าถึง คุกกี้ของบัญชีที่ยังดูคลิปไม่ได้ใน browser ก็ไม่ได้ทำให้บอตดูได้

## แหล่งอ้างอิง

- [YouTube: Watch age-restricted videos](https://support.google.com/youtube/answer/10070779?hl=en)
- [yt-dlp: Exporting YouTube cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)
- [mpv: Network options and native events](https://mpv.io/manual/stable/)

## ขอบเขตการทดสอบ

จำลอง error/callback/HTTP metadata และ SQLite transactions รวมคิว 1,000 เพลง ไม่ได้ใช้ cookie หรือเชื่อม TeamTalk/YouTube จริง จึงยังต้องลองกับคลิปที่มีปัญหาบนเซิร์ฟเวอร์จริง การแก้ไม่สามารถทำให้ session ที่ไม่มีสิทธิ์กลายเป็น session ที่มีสิทธิ์ได้
