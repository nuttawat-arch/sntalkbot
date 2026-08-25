# Development Report — SNTalkBot 5.1.6 (Radio Webpage Resolver / URL Compatibility)

## ปัญหาที่แก้
- URL ที่เป็นหน้าเว็บสถานีวิทยุบางแห่ง เช่น `https://90rakthai.com/` ให้ yt-dlp metadata แต่ไม่มี playable `url` จึงจบที่ `No playable URL found for the requested link.`
- fallback เดิมเมื่อ yt-dlp โยน exception ส่งหน้า HTML ตรงให้ mpv ซึ่งไม่ใช่ stream จริงและอาจล้มแบบไม่ชัดเจน

## การแก้ไข
- เพิ่ม bounded radio webpage resolver: direct audio response, ICY/Icecast/Shoutcast, `<audio>/<source>`, stream URL ใน HTML/JavaScript/data attributes และ playlist `.pls/.m3u/.m3u8`
- จำกัดการไล่หน้าเว็บสูงสุด 16 HTTP fetch และ depth 2 เพื่อไม่ให้สถานีที่มีลิงก์จำนวนมากทำให้คิวค้างนาน
- ใช้ resolver ทั้งกรณี yt-dlp exception และกรณี yt-dlp คืน info แต่ไม่มี playable URL; YouTube/YouTube Music ยังคงผ่าน yt-dlp เดิม
- regression fixture ของ 90 Rak Thai ยืนยันการค้นพบ `http://radio11.plathong.net:8896/;stream.mp3` โดยไม่ hard-code resolver ให้รองรับเฉพาะสถานีเดียว

## Validation
- canonical commands ยังคง 124
- Queue first-announcement/FIFO prefetch/race regressions จาก 5.1.5 ยังผ่าน
- radio resolver HTML + PLS indirection regression ผ่านโดยไม่ใช้อินเทอร์เน็ตจริง

---

# Development Report — SNTalkBot 5.1.5 (Queue Handoff / Prefetch Race Fix)

## ปัญหาที่แก้
- Queue Mode เพลงแรกเคยเริ่มเล่น/ประกาศ Now Playing ก่อนข้อความเพิ่มคิวถูกประกาศ
- เพลงถัดไปบางครั้งเริ่มช้า เพราะ prefetch เดิมอ่าน active collection ทั้งที่ queue playback ล้าง collection state แล้ว จึงไม่ preload FIFO item 2 จริง
- prefetch cache เดิมมี race เล็ก ๆ ระหว่างปล่อย yt-dlp lock กับ commit cache ทำให้ foreground มีโอกาส extract metadata ซ้ำ

## การแก้ไข
- reserve เพลงแรกใน queue ก่อน และเริ่ม playback หลัง enqueue announcement ถูกส่งเข้าคิว TTS แล้ว
- Queue Mode prefetch จาก FIFO queue โดยตรง สูงสุด 5 รายการถัดไป
- commit prefetch cache ก่อนปล่อย shared yt-dlp extraction lock และ foreground recheck cache หลังได้ lock

## Validation
- canonical commands ยังคง 124
- regression ทดสอบ queue announcement-before-play, FIFO next-item scheduling และ in-flight cache race จริง
- Python compile/help/locale/moderation/realtime/Linux LF gates ผ่าน

---

# Development Report — SNTalkBot 5.1.4 (Admin Credential Verifier / LF Closure)

## 2026-08-25
- เพิ่ม one-shot TeamTalk Administrator verifier ใน Docker image เพื่อให้ Web Manager พิสูจน์ credentials ของลูกค้าโดย login จริง ไม่อาศัยเพียงรายชื่อ admin ที่ออนไลน์
- password รับทาง stdin และอยู่ใน memory ชั่วคราวเท่านั้น; output/error ไม่ echo password
- callback `onCmdMyselfLoggedIn` ตรวจ `UserAccount.uUserType == USERTYPE_ADMIN`; account ที่ login ได้แต่ไม่ใช่ Admin ถูกปฏิเสธ
- คง/ตรวจ Linux SDK LF normalization เพื่อแก้ strict production failure ที่พบจริงใน `TeamTalk5.py` และ `TTSDK_license.txt`
- validator ผ่าน 124 commands, queue/moderation/realtime และ verifier regression

---

# Development Report — SNTalkBot 5.1.3 (Linux SDK LF Fix)

## 2026-08-25
- strict production verifier พบ CRLF ใน `TeamTalk5.py` และ `TTSDK_license.txt` ที่ official TeamTalk SDK นำเข้าระหว่าง Docker build
- แก้ที่ต้นทาง build: Linux SDK installer normalize text สองไฟล์เป็น LF หลัง copy โดยไม่แก้ native library หรือ semantics
- เพิ่ม validator gate ตรวจว่ากลไก normalize ยังอยู่ เพื่อไม่ให้ strict verifier กลับมาพังใน release ถัดไป
- ไม่มีการเปลี่ยน command catalog: canonical commands ยังคง 124

---

# DEVELOPMENT REPORT — SNTalkBot 5.1.3

## ปัญหาจากรอบก่อน
- Web Manager เห็น `users_online` เป็นจำนวนรวมทั้ง TeamTalk server ทั้งที่ข้อความบนการ์ดสื่อว่าคือคนในห้องปัจจุบัน
- การตัดบอตออกจาก Administrator อาศัย User ID เป็นหลัก จึงยังไม่ชัดเจนสำหรับ session อื่นที่ใช้ TeamTalk username เดียวกับบอต

## แก้ไข/เพิ่ม
- เปลี่ยน realtime snapshot ให้ room-scoped และคง server totals แยกต่างหาก
- เพิ่มรายชื่อผู้ใช้ในห้องพร้อม username/nickname/status/account type และ Voice/Media/Video/Desktop state
- ตัด bot TeamTalk username จาก human/admin metrics ทุก session

## ผลตรวจ
- `python3 tools/validate_project.py` ผ่านทั้งชุด: Python compile, 124-command/help parity, queue targeting, moderation, Linux LF, realtime HTTP API และ room/server/admin regression
- canonical commands = 124; `. [queue_position]` และ `, [queue_position]` ถูกตรวจเป็น syntax extension ของ 2 commands เดิม ไม่เพิ่ม command count
- realtime regression ยืนยันว่าคนในห้อง/ทั้งเซิร์ฟเวอร์แยกกัน และทุก session ที่ใช้ TeamTalk username ของบอตไม่ถูกนับเป็น human/Administrator

## คงเหลือ
- source/local validator พร้อม publish; ต้อง build/push Docker image 5.1.3, update running containers และผ่าน strict Linux production verification

# DEVELOPMENT REPORT — SNTalkBot 5.1.1

วันที่: 2026-08-24

## ปัญหาจากรอบก่อน
- Queue Mode ใช้ `search_results`/`current_search_index` ชุด global และ `,`/`.` แทน `queue[-1]` ทำให้ผู้ใช้หลายคนค้นหาต่อกันแล้วอาจเปลี่ยนเพลงผิดคิว
- source บางไฟล์เคยมี CRLF ซึ่งมีความเสี่ยงเมื่อรัน/แพ็กบน Linux

## การแก้ไข/ฟีเจอร์
- ผูก search session (`_search_results`, `_search_index`, `_search_source`) กับ queue item แต่ละรายการ
- เพิ่ม `. <queue_position>` และ `, <queue_position>` เช่น `. 34` / `, 34`; แบบไม่มีหมายเลขยังใช้ได้เหมือนเดิม
- เพิ่ม help, COMMANDS_TH, USER_GUIDE_TH และ Thai locale ให้ตรง syntax ใหม่
- เพิ่ม Linux LF-only validation

## การทดสอบรอบนี้
- Python compile / 124 command catalog / help-role-alias consistency / Linux LF checks ผ่าน
- เพิ่ม regression test multi-user queue search; พบ fixture เดิมถูก clear จาก test ก่อนหน้าและแก้ fixture ให้ restore normal search stateก่อนทดสอบ
- รัน validator ซ้ำหลังแก้ fixture แล้ว: queue regression ผ่าน, command-dispatch พิสูจน์ `. 34`/`, 34` ทั้ง Private และ Channel และ validator ทั้งชุดจบด้วย exit code 0

## ลบอะไรออก
- ไม่มี runtime feature เดิมถูกลบ; `,` และ `.` แบบเดิมยังคงทำงาน

## สถานะ
- Source implementation และ local final validator ผ่าน; รอ PublishFirst + strict Linux runtime verification
