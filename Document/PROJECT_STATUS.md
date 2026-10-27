# sntalkbot 5.1.35

## รอบ 27 ต.ค. 2569: Playback Handoff Priority / 12-Result Selection (5.1.35 ยังไม่เผยแพร่)

- **DONE (published baseline):** Publisher log จากผู้ใช้ยืนยัน 5.1.34 เผยแพร่ GitHub tag, Docker image และ ZIP สำเร็จแล้ว แต่ log เป็น Build/Publish ไม่ใช่ log การเล่นจาก instance บน Linux จึงยังไม่มีหลักฐานว่าแต่ละ instance อัปเดต runtime แล้ว
- **DONE (root cause candidates):** จบเพลงใช้ io_pool ที่ใช้ร่วมกับงานค้นหา/download, การกด `.`/`,` บนคิวปัจจุบันเรียก yt-dlp ใน TeamTalk event thread, และ prefetch ขัง network extraction ภายใต้ล็อกเดียวกับ foreground play; เสี่ยงต่อคิวไม่ขยับ/เพลงแรกเงียบ/เปลี่ยนเพลงช้า แม้ MPV EOF watchdog มีอยู่แล้ว
- **DONE (handoff):** แยก ordered playback executor 1 worker สำหรับ end callback, queue handoff, queue first-start และ queued selection; callback ของ MPV ทำแค่ส่งงาน จึงไม่ค้างกับ DB/network; guard ด้วย token+link เพื่อทิ้งการเลือกผลค้นหาเก่าที่ยังไม่ได้เริ่ม
- **DONE (search):** ค้นหาหน้าแรก 12 ผลพร้อมเลือกทั้ง p/pm และ Queue/Normal; คง full-result expansion 50/20 ใน background โดยผูก token/search session และไม่ทับการเลือกของผู้ใช้
- **DONE (resolution):** ยกการดึง yt-dlp จาก prefetch ออกจาก shared cache lock; foreground รอ prefetch ของ URL เดียวกันไม่เกิน 250ms แล้ว resolve เอง; เตรียมผลค้นหาถัดไปเมื่อคิวไม่มีเพลงถัดไป
- **DONE (MPV):** watchdog ตรวจ `eof-reached` เป็นทางเสริมเมื่อ MPV ไม่ flip idle แต่รู้ว่า EOF จริง; คง 1-second idle watchdog, stall protection, no-skip paused/buffering และ dedupe per generation
- **DONE (compatibility):** ไม่มี dependency ใหม่; ไม่แก้ Cookie 18+, yt-dlp generic URL/แพลตฟอร์มอื่น, SQLite schema, Web Manager, TeamTalk commands หรือ persistent config
- **DONE (offline QA):** Unit tests 111/111 ผ่าน รวม native MPV→Cog→Queue, stale selection, search 12 ทางเลือก, foreground ไม่รอ unrelated prefetch, short/end/paused and 18+; validator ผ่าน
- **DOING (Linux QA):** ต้องลง 5.1.35 ใน Bot instance จริงและตรวจ `MPV watchdog recovered`, เสียงออกครั้งแรก, เว้นเพลง, speaking, ข้อความสถานะ และเปิด/ปิด Queue Mode
- **TODO:** เก็บเวลา MPV audio output / live TeamTalk SDK event เพื่อแยกปัญหาบัฟเฟอร์เสียงที่ unit test จำลองไม่ได้

## รอบ 27 ต.ค. 2569: Auto-Advance / Clear Speaking State (5.1.34 ยังไม่เผยแพร่)

- **DONE (root-cause risk):** MPV เดิมจะเฝ้าดู idle-active แค่เมื่อไม่มี END_FILE callback; ถ้า END_FILE/START_FILE สูญหายหรือถูกกรองเพราะ entry-id race จึงไม่มีสัญญาณสำรองให้ขยับคิว และ TeamTalk voice/status อาจค้าง
- **DONE (MPV):** เพิ่ม background watchdog ทุก 1 วินาที แยกจาก event callbacks; กู้ terminal event เมื่อ MPV idle จริงต่อเนื่องหลังเริ่มเล่น, รวมเพลงสั้นที่ได้รับ START_FILE แต่ไม่ได้รับ END_FILE; ป้องกัน generation เก่า/การหยุดเอง/การแจ้งจบซ้ำ; ตั้ง grace 3 วินาทีและ idle เสถียร 1 วินาที
- **DONE (stalled transport):** ถ้าตำแหน่งเสียงเคยเดินแล้วหยุดเกิน 40 วินาทีขณะไม่ได้กด Pause และไม่ได้รอบัฟเฟอร์ จะเข้า bounded retry/skip เดิม; ถ้าโหลดใหม่ค้าง idle 45 วินาทีโดยไม่เคยเริ่ม จะเข้า error retry แทน; ไม่บังคับข้ามสตรีมที่ไม่มี time-pos
- **DONE (Queue/TeamTalk):** เมื่อคิวจบและไม่มีเพลงถัดไป ล้าง now-playing ในหน่วยความจำ ปิด voice transmission และตั้ง status idle ตามค่าที่ผู้ใช้กำหนด; รวมเมื่อ Related Radio ไม่มีเพลงต่อหรือเจอข้อผิดพลาดขณะค้นเพลงใหม่
- **DONE (scope):** ไม่เปลี่ยนไฟล์ config, cookies, SQLite schema, การค้นหา generic URLs, 18+, playlist, MPV/PulseAudio หรือ Web Manager 1.1.29; รวมงานเร่งเพลงแรก/เพลงถัดไป 5.1.32–5.1.33 ที่ยังไม่เผยแพร่
- **DONE (offline QA):** Unit tests 104/104 ผ่าน รวม watchdog idle/short/stall/pause และคิวสุดท้ายปิด mic+status; validator ผ่าน
- **DOING (live QA):** ยังต้องฟัง TeamTalk Docker จริงโดยมีเพลงสั้น/ยาว/18+ และตรวจ User State VOICE/ข้อความ status หลังคิวหมด; รุ่น 5.1.31 เป็นรุ่นที่ผู้ใช้พบปัญหา
- **TODO:** ถ้า TeamTalk บอก speaking หลัง disableVoiceTransmission(False) ให้เก็บ SDK event/server log เพื่อแยกการส่งเสียงจริงกับ state UI ที่รายงานล่าช้า

## รอบ 27 ต.ค. 2569: TTMediaBot comparison / Fast First Track (5.1.33 ยังไม่เผยแพร่)

- **DONE (evidence):** ตรวจซอร์ส `TTMediaBot_v2.3.5.zip` จริง; `bot/app_vars.py` ใน ZIP ระบุ runtime 3.2.4 แม้ชื่อ ZIP เป็น 2.3.5; โครงสร้างเป็น Windows FFmpeg direct PCM ไม่ใช่ Linux/Docker MPV ของเรา
- **DONE (comparative):** พบการค้นหา YouTube เพียง 4 ผลและ YouTube Music 1 ผลก่อนเล่น, lazy dynamic track, prefetch เฉพาะเพลงถัดไปแบบตั้งเวลา, bounded search/extraction และ watchdog; คงโครงสร้างของเราแล้วเลือกใช้เฉพาะแนวคิดที่ไม่ทำลายฟีเจอร์
- **DONE (Bot):** เมื่อเริ่มค้นหาเพลงแรกจาก Queue Mode (`p`/`pm`) หรือเล่นโหมดปกติ ให้ดึงผลแรกเพียงรายการเดียวก่อนเริ่ม MPV แล้วค่อยเติมชุดผลค้นหา 50/20 รายการแบบเบื้องหลัง
- **DONE (observability):** เพิ่มการวัดขั้นค้นหาผลแรกใน `First-track search took` / `Queue search took` แยกจากขั้น yt-dlp resolve ของ MPV โดยไม่เปิดเผยข้อความคำค้นหาหรือ URL ในข้อความเวลา
- **DONE (data safety):** ป้องกันผลค้นหาเก่าทับคิวด้วย `_queue_token` ป้องกันผลค้นหาโหมดปกติเก่าทับคำสั่งใหม่ด้วย search-session object identity; เก็บ Token ตอนเปลี่ยนผลค้นหาในคิว; รายการทางเลือกยังคงครบเมื่อการโหลดเบื้องหลังเสร็จ
- **DONE (compatibility):** คงการดึงลิงก์ generic สำหรับ SoundCloud, Twitch, Vimeo และบริการอื่นผ่าน yt-dlp; คง cookies/18+, fallback YouTube Music, MPV/PulseAudio, Server Manager, SQLite และคำสั่งเดิมทั้งหมด
- **DONE (offline QA):** Unit tests 97/97 และ `tools/validate_project.py` ผ่าน รวมการเริ่มเร็วของทั้งสองโหมด, การเติมผลครบ, fallback เมื่อค้นหาผลแรกไม่สำเร็จ, ยกเลิกการเขียนทับรายการใหม่, SoundCloud/Twitch/Vimeo ผ่าน generic resolver และ cookie-first วิดีโอ 18+
- **DOING (live QA):** รอทดสอบเวลาจริงของ MPV/YouTube/TeamTalk หลังนำลง Linux/Docker; ยังไม่ได้ยืนยันว่าเริ่มเพลงเป็น 0 วินาที
- **TODO:** เก็บเวลาที่เสียงออกจริงเพื่อแยกความช้าของ YouTube/yt-dlp, MPV buffer และ Network; พิจารณา watchdog หลังได้บันทึกจากการใช้งานจริง

## รอบ 27 ต.ค. 2569: เร่งเริ่มเพลงและเปลี่ยนเพลง (5.1.32 ยังไม่เผยแพร่)

- **DONE (source):** Prefetch เฉพาะเพลงถัดไปใน Queue Mode และ Playlist ป้องกันการ resolve เพลงลำดับไกลไปแย่งล็อก yt-dlp ตอนเปลี่ยนเพลง
- **DONE (source):** ขยายอายุข้อมูลเตรียมไว้จาก 5 เป็น 30 นาทีสำหรับเพลงยาว โดยยังตรวจ signed-URL `expire` ล่วงหน้า 60 วินาทีเพื่อไม่ใช้ลิงก์หมดอายุ
- **DONE (source):** บันทึกเวลาเตรียมเพลง/Prefetch ที่ช้ากว่า 2 วินาทีเพื่อช่วยแยกปัญหา extractor กับ MPV โดยไม่พิมพ์ URL/Cookie; รักษา policy ของวิดีโอจำกัดอายุ
- **DONE (compatibility):** คงการป้องกันไฟล์ `config.ini.lock` บน Linux พร้อม guard สำหรับ Windows จากรุ่นที่เผยแพร่แล้ว; ไม่แก้ configuration, cookie หรือตัว Web Manager 1.1.29
- **DONE (release baseline):** ผู้ใช้ส่ง Publisher log ยืนยันว่า Bot 5.1.31 เผยแพร่แล้ว; 5.1.32 เป็นแพตช์ต่อยอด ยังไม่ได้เผยแพร่
- **DONE (offline QA):** Unit tests 90/90 ผ่าน และ `tools/validate_project.py` ผ่าน รวมการสลับคิว FIFO, URL expiry, cookie-first อายุ 18+ และ file lock ข้ามแพลตฟอร์ม
- **DOING (live QA):** ตรวจการออกเสียงจริงบน Docker/TeamTalk และวัดช่องว่างเพลงหลังนำแพตช์ขึ้นเท่านั้น
- **TODO (runtime):** วัดเวลาเริ่มเพลงแรก/ช่องว่างระหว่างเพลงจริง พร้อม log ก่อนปรับ MPV และ yt-dlp เพิ่มเติม เพราะ Publisher log ที่แนบไม่ใช่ performance trace

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
