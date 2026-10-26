# sntalkbot 5.1.27

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
