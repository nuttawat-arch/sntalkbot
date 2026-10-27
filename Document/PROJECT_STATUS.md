# sntalkbot 5.1.31

## รอบ 27 ต.ค. 2569: Windows Publisher regression hotfix (5.1.31 ยังไม่เผยแพร่)

- **DONE (Root cause):** Windows Publisher เมนู 1 ตรวจ Bot 5.1.30 ล้มที่ `non-interactive config migration regression: module 'os' has no attribute 'geteuid'`; Windows ไม่มี POSIX `os.geteuid()` ซึ่ง Bot `_file_lock` เรียกโดยไม่ตรวจแพลตฟอร์ม
- **DONE (Code):** จำกัด `fchmod`/`geteuid` เพื่อซ่อม group-write lock เฉพาะ POSIX (`os.name == 'posix'`) และตรวจว่าฟังก์ชันมีจริงก่อนเรียก; ยังรักษา Linux lock mode `0660` และไม่แตะข้อมูลเดิม
- **DONE (Regression):** เพิ่ม unit test จำลอง Windows ที่ `geteuid` เรียกไม่ได้ และจำกัด test mode `0660` เฉพาะ POSIX; Bot tests **85/85 ผ่าน** บน Linux, project validator ผ่าน
- **DOING:** ยังต้องรัน Publisher บน Windows จริงอีกครั้งและตรวจ GitHub/Docker/Linux live หลังเผยแพร่; Log ที่แนบเป็น run ล้มก่อน publish
- **TODO:** ยืนยัน native Windows Python 3.14 validation แทน simulation และ Linux container permissions หลัง deploy

## รอบ 27 ต.ค. 2569: Lock File Permission Hotfix (5.1.30 ยังไม่เผยแพร่)

- **DONE:** ปรับ `_file_lock` ของ `config.ini` ให้ยืนยัน mode `0660` เมื่อสร้าง/เปิดไฟล์ล็อกที่เป็นเจ้าของ แม้กระบวนการบอตตั้ง umask แบบเข้ม ทำให้กลุ่มข้อมูลของ Web Manager เปิดได้
- **DONE:** คง stable `flock` ข้าม Bot และ Web Manager, atomic config writes, queue SQLite, TeamTalk action เดิม และ cookies เดิมทั้งหมด
- **DONE (Offline QA):** Unit tests 84/84 ผ่าน รวม regression restrictive umask; ทำงานร่วม Web Manager 1.1.28 และ installer auto-repair ไฟล์ล็อกเก่า
- **DOING:** ยังไม่ได้ทดสอบบน Docker/TeamTalk จริง; ต้องเผยแพร่ image 5.1.30 แล้วตรวจอัปเดต/บันทึกจาก Web Manager หลัง installer 1.1.28
- **TODO:** คงรอบต่อไปสำหรับ WebSockets/event signaling และ queue placement หลัง live QA

## รอบ 27 ต.ค. 2569: Player status สำหรับ Web Manager รุ่น 1.1.27

- **DONE (Bot 5.1.29):** เพิ่ม `channel_messages`, `announce_tracks`, `announce_queue`, `announcement_tts_mode` ใน snapshot RAM ของ Player เพื่อแสดงสถานะสวิตช์และตัวเลือก TTS ตรงกับค่าจริงบนเว็บ
- **DONE (ความเข้ากันได้):** คงคำสั่ง TeamTalk, API เดิม, คิว SQLite, ข้อมูลอื่น และ Cookie ทั้งหมดจาก 5.1.28; ไม่เปลี่ยนนโยบาย default cookies
- **DOING:** รัน Unit tests/validator ของ Bot หลังแก้ snapshot และทดสอบร่วม Web Manager บน Linux/TeamTalk/NVDA จริง
- **TODO:** เพิ่ม queue placement ใหม่ได้ต่อเมื่อผ่านการทดสอบไม่ให้กระทบความต่อเนื่องของเพลงและลำดับรายการคิว
- **DONE (QA offline):** Unit tests 83/83 ผ่าน (เพิ่ม regression ตรวจสถานะสวิตช์ Player); `tools/validate_project.py` ผ่านและยืนยัน version 5.1.29 ตรงกัน


## รอบ 27 ต.ค. 2569: เตรียม Release 5.1.28 แก้ความขัดแย้งของ Git tag

- **DONE (ซอร์ส):** เปลี่ยน `VERSION` และ `BotUtils.VERSION` เป็น `5.1.28` โดยคงฟีเจอร์ Playlist, Web Manager, TeamTalk และไฟล์ Cookie ทั้งหมดตามรุ่นที่พัฒนาก่อนหน้า
- **DONE (เอกสาร):** อัปเดตชื่อรุ่นปัจจุบันในคู่มือหลัก โดยไม่เปลี่ยนบันทึกประวัติรุ่นเก่า
- **DONE (QA offline):** SNTalkBot unit tests 82 ผ่าน; `tools/validate_project.py` ผ่าน (123 canonical commands); TTUHelper validator ผ่าน; Web Manager portable validator และ unit tests 25 ผ่าน; Python AST 37 ไฟล์ผ่าน; `git diff --check` ผ่าน
- **DONE (Windows Publish 5.1.28):** จากล็อกผู้ใช้ เมนู 1 ส่ง GitHub tag `v5.1.28`, Docker `5.1.28`/`latest`, ZIP เว็บไซต์ และหน้า Download สำเร็จแล้ว; ขั้นตอน GitHub Actions และตรวจ Linux runtime ยังต้องยืนยันภายหลัง
- **KNOWN WARNING:** Starlette เตือน `TemplateResponse(name, context)` เป็นรูปแบบเก่า แต่ Web Manager unit tests ยังผ่าน 25/25; พิจารณาปรับ API นี้ในรอบ Web Manager ใหม่โดยไม่แตะ Release 1.1.26 ที่ใช้งานอยู่
- **DONE (Windows):** ผู้ใช้เผยแพร่ 5.1.28 สำเร็จแล้วตามล็อก; ไม่แก้หรือย้าย tag รุ่นเก่า
- **TODO (Live):** ตรวจ GitHub Actions, Docker digest, ZIP/เว็บไซต์ และ Linux runtime/TeamTalk/YouTube หลัง Publish บนเครื่องจริง

## รอบ 26 ต.ค. 2569: บัญชี YouTube สำหรับบอต (Cookie Default)

- **DONE (ซอร์ส):** รวม `www.youtube.com_cookies.txt` ที่ผู้ใช้แนบ โดยแทนที่เฉพาะ records ของโดเมน `youtube.com`/subdomain ใน `defaults/cookies.txt`; คง records ของโดเมนอื่นเดิมไว้โดยไม่รับจากไฟล์ใหม่ (ไฟล์รอบนี้เดิม 13 YouTube → ใหม่ 21 YouTube และ 0 โดเมนอื่น)
- **DONE (ความถูกต้อง):** เพิ่ม `tools/merge_default_youtube_cookies.py` แบบตรวจ Netscape format, เขียน atomically ด้วย permission 0600, ไม่แสดงค่า session และทดสอบการรักษาคุกกี้ต่างโดเมน/ปฏิเสธไฟล์เสีย
- **DONE (Validator):** เปลี่ยนการตรวจบันเดิลให้ยืนยันว่ามี YouTube cookie อย่างน้อยหนึ่งรายการโดยไม่ปฏิเสธคุกกี้โดเมนอื่นที่ตั้งใจรักษาไว้
- **DOING:** ตรวจการเล่น YouTube/คลิปจำกัดอายุบนเซิร์ฟเวอร์จริง; การมี cookie ไม่ยืนยันสิทธิ์ทุกคลิปหรือป้องกันการหมดอายุ/ถูกเพิกถอน
- **SECURITY:** คุกกี้จากบัญชีบอตที่ใช้เผยแพร่ร่วมกับ ZIP/Registry ยังเป็น session credentials; ผู้ใช้ยืนยันว่าเป็นบัญชีแยกสำหรับบอตและอนุมัติการรวมไฟล์ ควรเก็บ ZIP เป็นส่วนตัว ควบคุมการเผยแพร่และเพิกถอน session หากสงสัยว่ารั่ว

## รอบ 26 ต.ค. 2569: ค้นหา Playlist และคำสั่งดูแลเพิ่มเติม (Source DEV)

- **DONE (Player):** `pp <ลิงก์ Playlist>` คงการเพิ่มท้ายคิวแบบเดิม; `pp <ชื่อ>` ค้นหา Playlist ของ YouTube และ `pps <หมายเลข>` เลือกผลค้นหาเฉพาะผู้ใช้ภายใน 180 วินาที; ไม่มีคำสั่งย้ายคิวขึ้น/ลงใหม่
- **DONE (Player/Web):** หน้าเว็บค้นหา Playlist ด้วยชื่อ แสดงผลพร้อมปุ่มเลือกเพิ่มท้ายคิว/ใช้ token หมดอายุเพื่อกันผลเก่า เพิ่มการตั้งค่าเสียงประกาศเพลง/คิว, เอนจิน TTS และเสียงพูดที่มีคำสั่งบอตอยู่แล้ว
- **DONE (Manager/Web):** เพิ่มเครื่องมือ Jail/Unjail, เตะ/แบนแบบกำหนดเวลา, ดูโทษที่มีผล, ปลดโทษตามเวลา; ตรวจสิทธิ์ TeamTalk Administrator และฟอร์ม typed allowlist; โทษส่วนกลางจำกัด Web Super Admin
- **DONE (offline):** unit tests 79 ผ่าน (รวมทดสอบค้นหา Playlist/เลือกผู้ใช้/ลิงก์เดิม), `tools/validate_project.py` ผ่านครบ 123 คำสั่ง และ `git diff --check` ผ่าน
- **DOING:** ทดลองค้นหา YouTube จริง, TeamTalk Server, เสียง mpv และ NVDA ก่อนเผยแพร่; ไม่มีการรับรอง live integration จาก offline test
- **TODO:** เพิ่มความครอบคลุม UI/SDK ส่วนที่ยังอยู่ใน [TEAMTALK_SERVER_ADMIN_TH.md](../TEAMTALK_SERVER_ADMIN_TH.md) โดยไม่เปิด arbitrary SSH/PowerShell ผ่านเว็บ

วิธีใช้และหลักการแยกสิทธิ์: [PLAYLIST_WEB_CONTROL_TH.md](PLAYLIST_WEB_CONTROL_TH.md)

## รอบต่อเนื่อง 26 ต.ค. 2569: Role-based Web Controls (ยังไม่เผยแพร่)

- **DONE (ซอร์ส):** Player-only ไม่เปิดประกาศ/ควบคุม Manager; Manager-only ไม่มีปุ่มเล่นเพลง/คิว; Full ใช้ทั้งสองชุดแบบมีป้ายแยกกัน และการบังคับสิทธิ์อยู่ที่บอต ไม่ใช่แค่ซ่อน UI
- **DONE (ซอร์ส):** เว็บเลือกผลค้นหาก่อนหน้า/ถัดไปใน *คิวตำแหน่งที่เลือก* ด้วยคำสั่งจุด (`.`) และจุลภาค (`,`) ที่มีอยู่แล้ว; ไม่มีการแทรกหรือย้ายลำดับคิวขึ้น/ลงตามคำขอ
- **DONE (ซอร์ส):** นำตัวเปิด/ปิด Channel Input, All-Channel Intercept, กรองคำ, Welcome, Welcome Broadcast, VPN, NoName, Global Broadcast/TTS/interval ของ Manager ที่มี handler เดิมและบันทึกค่าอยู่แล้วมาให้สั่งผ่านเว็บแบบ typed allowlist
- **DONE (ความถูกต้อง SDK):** ปฏิเสธการเปลี่ยนชื่อห้องผ่าน `doUpdateChannel` เพราะ TeamTalk SDK ไม่ใช้ `szName` ใน Update; ป้องกันการแจ้งสำเร็จลวง
- **DONE (ซอร์ส):** ปรับการเตะ/แบนผู้ใช้ออนไลน์ผ่านเว็บให้ส่งคำสั่ง TeamTalk ด้วย Command ID และรอ callback สำเร็จ/ถูกปฏิเสธจริง แทนการรายงานจาก Boolean ก่อนเซิร์ฟเวอร์ตอบ
- **DONE (offline):** unit tests 70 ผ่าน, `tools/validate_project.py` ผ่าน โดยใช้ dependency แยกเฉพาะทดสอบ
- **DOING:** ทดสอบ live TeamTalk, HTTP/UI จริง, สตรีม และ NVDA ก่อนเผยแพร่

## รอบพัฒนาใหม่: Remote TeamTalk administration (ยังไม่เผยแพร่)

- **DONE (ซอร์ส):** เทียบ BearWare SDK 5.22A, เพิ่ม typed TeamTalkAdministration สำหรับตั้งค่า/บันทึก/สถิติเซิร์ฟเวอร์, CRUD ห้อง, จัดการบัญชีและสิทธิ์, Ban/Unban IP/username, Operator/เตะจากห้อง; เพิ่มคำสั่ง `ttadmin` รวม canonical เป็น 122
- **DONE (offline):** TeamTalk callback confirmation/error, cache ไม่เก็บรหัสผ่าน, revision สำหรับ Server/Channel, แยกสิทธิ์ Manager/Full; unittest และ static validator
- **DOING:** ตรวจ integration กับ TeamTalk Server จริง และการใช้งานด้วย NVDA
- **TODO:** ความสามารถ SDK เพิ่มเติมตาม [TEAMTALK_SERVER_ADMIN_TH.md](../TEAMTALK_SERVER_ADMIN_TH.md); ยังไม่ครบ SDK 100%

รอบ 26 ตุลาคม 2026: config safety และ Web Controls เสร็จแล้ว ดูรายละเอียดการแก้ วิธีใช้ และข้อจำกัดที่ [AUDIT_AND_CONTROLS_TH.md](AUDIT_AND_CONTROLS_TH.md)

สถานะ validation ผ่านแบบ offline; ต้องตรวจ TeamTalk/YouTube/PulseAudio/libmpv/NVDA บนเครื่องจริงก่อนรับรองการใช้งานจริงครบทุกกรณี

รอบแก้คิว: pending retry/event dedupe/refresh URL/cancel และ failed history เสร็จแล้ว ดู QUEUE_RECOVERY_AND_AGE_COOKIES_TH.md
