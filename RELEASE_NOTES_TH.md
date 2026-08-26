# SNTalkBot 5.1.7 — Dynamic URL / Nested Radio Resolver

- คง `yt-dlp` Generic Extractor เป็นด่านแรกสำหรับ `u <URL>`; fallback ใหม่ทำงานเฉพาะเมื่อ yt-dlp ไม่มี playable URL หรือ extract ไม่สำเร็จ
- เพิ่มการตาม `<iframe>/<embed>` แบบ bounded และลอง player URL ที่พบผ่าน yt-dlp ซ้ำได้สูงสุด 3 จุด เพื่อรองรับกรณีหน้าเว็บหลักไม่รู้จักแต่ provider ใน iframe มี extractor
- static fallback รองรับ `<audio>/<source>`, data attributes, JSON/JavaScript player config, URL ที่ escape/percent-encode, `atob()` base64 แบบไม่ execute JavaScript, Icecast/Shoutcast, HLS, PLS/M3U และ legacy ASX/XSPF
- เพิ่ม overall time budget, depth/fetch caps และไม่ไล่ ordinary navigation links จึงไม่เปลี่ยนเว็บทั่วไปให้เป็น crawler; URL ที่ไม่ใช่สื่อจะ fail แบบปลอดภัย
- Queue Mode `u <URL>` ใช้ resolver เดียวกันและ cache synthetic playable info ก่อนเริ่มคิว จึงรองรับหน้าเว็บสถานีเช่นเดียวกับการเล่นทันที
- regression ครอบคลุม 90 Rak Thai fixture, nested iframe/HLS, encoded/base64 config, PLS indirection, ordinary website safe-failure และลำดับ yt-dlp-first; canonical commands ยังคง 124

# SNTalkBot 5.1.6 — Radio Webpage / Stream Resolver

- เพิ่ม fallback สำหรับ URL ที่เป็นหน้าเว็บสถานีวิทยุ ไม่ใช่ direct media URL: ค้นหา stream จาก audio/source, script/data attribute, PLS/M3U/M3U8 และ Icecast/Shoutcast
- แก้กรณี yt-dlp คืน metadata แต่ไม่มี `url` ซึ่งเดิมแสดง `No playable URL found for the requested link.`
- resolver จำกัด depth/จำนวน request เพื่อไม่ทำให้ playback thread ไล่เว็บไม่สิ้นสุด และไม่เปลี่ยนเส้นทาง YouTube/YouTube Music เดิม
- fixture ของ `https://90rakthai.com/` ต้อง resolve stream ลูกทุ่งรักไทยได้; canonical commands ยังคง 124

# SNTalkBot 5.1.5 — Queue First-Announcement / FIFO Prefetch

- Queue Mode เพลงแรกประกาศ “เพิ่มเข้าคิว” ก่อน Now Playing โดย reserve queue item ก่อนและเริ่ม playback หลัง enqueue announcement ถูกส่งเข้าคิว TTS
- prefetch เพลงถัดไปอ่าน FIFO queue โดยตรง ไม่พึ่ง collection state ที่ queue playback ล้างออก
- commit prefetch cache ก่อนปล่อย shared yt-dlp lock และ foreground recheck cache หลังได้ lock ลด metadata extraction ซ้ำ/ช่องว่างระหว่างคิว 1→2
- จำนวน canonical commands ยังคง 124; ไม่มี command เดิมถูกลบ
- validator เพิ่ม regression ของ announcement order, FIFO item 2+ scheduling และ in-flight prefetch race

# SNTalkBot 5.1.4 — TeamTalk Admin Credential Proof / Linux SDK LF

- เพิ่ม `tools/verify_teamtalk_admin.py` สำหรับ Web Manager: รับ JSON ทาง stdin เท่านั้น, login ชั่วคราวด้วย TeamTalk SDK, ตรวจ `UserType.USERTYPE_ADMIN`, คืนผลแบบไม่มี secret และ disconnect/close ทันที
- ไม่ส่ง TeamTalk password ผ่าน argv และไม่บันทึก password ใน config/database/job log; Web Manager ใช้ verifier นี้เป็น owner proof ก่อนสร้าง persistent instance
- รวม Linux SDK LF fix: หลังดาวน์โหลด official TeamTalk SDK จะ normalize `TeamTalk5.py` และ `TTSDK_license.txt` เป็น LF เพื่อให้ strict production verifier ไม่ fail จาก vendor CRLF
- จำนวน canonical commands ยังคง 124; `. <queue_position>` / `, <queue_position>` ยังเป็น syntax extension ของคำสั่งเดิม
- validator เพิ่ม regression ของ AdminProbe: Administrator ผ่าน, account ปกติถูกปฏิเสธ และ verifier ต้องคง stdin/account-type/cleanup safety

# SNTalkBot 5.1.3 — Room-scoped Realtime Dashboard

- แก้ Realtime API/Runtime Bridge ให้ `users_online` หมายถึงจำนวนผู้ใช้จริงใน **ห้องที่บอตอยู่** โดยไม่นับตัวบอตเอง แทนการใช้ยอดรวมทั้งเซิร์ฟเวอร์
- เพิ่ม `room_users_online`, `server_users_online`, `room_users`, `admins_in_room_count` และ `server_teamtalk_activity` เพื่อให้ Web Manager แสดงรายละเอียดห้องและภาพรวมเซิร์ฟเวอร์แยกกันได้โดยไม่สับสน
- รายชื่อ Administrator ตัดทั้ง User ID ของบอตและทุก session ที่ใช้ TeamTalk username เดียวกับบัญชีบอต จึงไม่เอาบอตมานับเป็น Administrator มนุษย์
- `teamtalk_activity` เปลี่ยนเป็น Voice/Media/Video/Desktop ของห้องปัจจุบัน; ค่าทั้งเซิร์ฟเวอร์ยังมีแยกใน `server_teamtalk_activity`
- จำนวน canonical commands ยังคง **124 คำสั่ง**: `. [queue_position]` และ `, [queue_position]` เป็น syntax ที่ขยายจากคำสั่ง `.` และ `,` เดิม ไม่ใช่ command name ใหม่อีก 2 รายการ จึงไม่ควรนับเป็น 126
- เพิ่ม regression test จำลองห้อง, ผู้ใช้ทั้งเซิร์ฟเวอร์, Administrator และ duplicate session ของ username บอต เพื่อกันการนับผิดกลับมาอีก

# SNTalkBot 5.1.1 — Queue Search Isolation / Linux Hardening

## การเปลี่ยนแปลง

- แก้ Queue Mode ที่เดิมใช้ผลค้นหากลางชุดเดียวและ `.`/`,` ไปแก้รายการท้ายคิว ทำให้เมื่อหลายคนค้นหาต่อกัน ผู้ใช้คนก่อนอาจเลื่อนไปเป็นผลค้นหาของผู้ใช้คนล่าสุด
- แต่ละ queue item ที่เพิ่มจาก `p <คำค้น>` หรือ `pm <คำค้น>` เก็บ search-session ของตัวเองแล้ว โดย metadata นี้ไม่ถูกเปิดออกใน Realtime API/Dashboard
- `.` และ `,` แบบเดิมยังใช้กับรายการค้นหาล่าสุดได้เหมือนเดิม และเพิ่ม `. <queue_position>` / `, <queue_position>` เช่น `. 34` และ `, 34` เพื่อเปลี่ยนผลค้นหาของคิวที่ระบุโดยตรง
- ถ้าระบุคิวที่ไม่ได้มาจากการค้นหา เช่น URL/playlist ระบบจะแจ้งชัดเจนและไม่เปลี่ยนรายการอื่น
- เพิ่ม regression test สำหรับหลายผู้ใช้/หลาย search-session, queue position targeting, provenance และการไม่เล่นเพลงที่ไม่ใช่ current queue โดยไม่ตั้งใจ
- เพิ่มการตรวจ line ending สำหรับไฟล์ Linux/Python สำคัญเพื่อป้องกัน CRLF regression ก่อนสร้าง Docker/release

## ปัญหาที่ตรวจพบจากรุ่นก่อน

- 5.1.0 ผ่าน validator เดิม 124 คำสั่ง แต่ validator เดิมยังไม่จำลองกรณีผู้ใช้หลายคนมี pending search ใน Queue Mode พร้อมกัน จึงไม่พบ shared-search-state bug นี้
- พบไฟล์ Python/ข้อความเก่าบางไฟล์ยังมี CRLF แม้ `.gitattributes` กำหนด LF แล้ว; รุ่นนี้ normalize source ที่ Linux ใช้งานเป็น LF และให้ validator ตรวจซ้ำ

## สถานะการตรวจ

- ต้องผ่าน Python compile, command/help parity, Queue/Radio regression, Linux line-ending checks และ Docker/release validation ก่อน publish
- ขั้น production หลัง publish ยังต้อง `ttuhelper update` เพื่อ recreate container ที่กำลังรันด้วย image ใหม่ แล้วรัน server verification แบบ strict

---

# SNTalkBot 5.1.0 — Realtime API สำหรับ Web Manager

## สิ่งที่ผู้ใช้ควรรู้

- เพิ่ม HTTP API แบบอ่านอย่างเดียวสำหรับ Web Manager: `GET /healthz` และ `GET /v1/status` โดยใช้ Bearer token แยกต่อ instance และ bind ที่ `127.0.0.1` เท่านั้นตามค่าที่ TTUHelper กำหนด
- TTUHelper 1.5.0 จะจัดพอร์ต API ของแต่ละ instance จากช่วง `20000-27999` แบบไม่ซ้ำกัน ทำให้หลายบอตบน IP เดียวส่งสถานะ realtime ได้โดยไม่ชนพอร์ต
- Web Manager 1.1.0 อ่านสถานะจาก API ภายในแล้วส่งต่อให้ browser ผ่าน SSE; ถ้า API ใช้ไม่ได้ยัง fallback ไป `runtime_status.json` ได้
- Dashboard สามารถเห็น connection/server/channel, จำนวนผู้ใช้, ผู้ที่กำลังพูด/stream/video/desktop, Administrator ที่ออนไลน์โดยไม่รวมบัญชีบอตเอง และข้อมูล Player/Manager ตาม role
- Player ส่งข้อมูลเพลงปัจจุบัน โหมดการเล่น คิว จำนวนคิว และผู้เพิ่มคิวให้ Dashboard โดยไม่เปิด password, token, API key หรือค่า cookie
- `runtime_status.json` ยังคงเป็น fallback แบบ atomic write และ snapshot ทั้ง API/JSON ใช้โครงข้อมูลเดียวกัน
- แก้ compatibility กับ TTUHelper: `cookies.txt` ที่มีเพียง Netscape header จะไม่ถูกถือเป็น cookie session จริง จึง fallback ไป default cookie ของโปรเจกต์จนกว่าจะมี cookie ที่ใช้งานได้มาทับ
- การเปลี่ยนแปลง 5.1.0 เป็น management/realtime bridge แบบ additive; ความหมายคำสั่ง Player/Manager, Queue FIFO, Playlist/Related Radio และ moderation เดิมไม่เปลี่ยน

## ความปลอดภัยและการแยก instance

- API ของบอตไม่เปิดออก Internet โดยค่าเริ่มต้นและไม่ควรถูก Reverse Proxy โดยตรง; browser ติดต่อ Web Manager เท่านั้น
- API token อยู่ใน metadata ของ instance และไม่ถูกใส่ใน runtime snapshot หรือหน้าเว็บ
- API เป็น read-only ไม่มี endpoint สำหรับ stop/restart/delete/update; action จัดการระบบต้องผ่าน TTUHelper/Web Manager privileged bridge ตามสิทธิ์ผู้ใช้
- validator ทดสอบว่า request ที่ไม่มี token ถูกปฏิเสธ และ request ที่มี token ถูกต้องอ่านสถานะบน loopback ได้จริง

---

# SNTalkBot 5.0.0

## การเปลี่ยนแปลงที่ผู้ใช้ควรรู้ — รวมทุกงานที่ยังไม่เคย publish ตั้งแต่ฐาน r7.4.3

- แยกประเภทบอตชัดเจน: **Full Bot**, **Player Bot**, **Server Manager Bot**; Full รวมสองฝ่าย ส่วน Player/Manager ไม่ลงทะเบียนคำสั่งข้ามหน้าที่
- เพิ่ม `status` เป็นแดชบอร์ดคำสั่งเดียวตามประเภทบอต: ทุกโหมดเห็น uptime/ห้อง/จำนวนผู้ใช้/กิจกรรม TeamTalk; Player/Full เห็นเพลง คิว M1-M3 Autoplay และ Cookies; ผู้ดูแล Manager/Full เห็น filter/ci/ic/lock/welcome เพิ่มเติม
- เพิ่ม `events [1-25]` สำหรับผู้ดูแล Manager/Full เพื่อดูเหตุการณ์ล่าสุดที่เกิดขึ้นจริงใน TeamTalk เช่น login/join/leave, เปลี่ยนชื่อหรือสถานะ, ห้องถูกสร้าง/แก้/ลบ, ไฟล์ในห้อง, server update และการเริ่ม/หยุด media/video/desktop; เก็บแบบวงแหวนในหน่วยความจำและล้างเมื่อบอตรีสตาร์ต
- ขยาย moderation ไปยัง event แก้ไขข้อมูลจริง: ถ้าผู้ใช้ล็อกอินด้วยชื่อปกติแล้วเปลี่ยน nickname/status เป็นคำต้องห้าม หรือแก้ชื่อ/Topic Channel ภายหลัง `filter on` จะตรวจซ้ำทันที; `filter off` ปิดทั้งหมดตามเดิม
- คำสั่งผู้ดูแลที่ทำงานผ่านบอตถูกบันทึกใน `events` เฉพาะชื่อ action และผู้สั่ง โดยไม่เก็บ argument จึงไม่บันทึกรหัสผ่าน ข้อความส่วนตัว token หรือ payload ลับลง audit ring
- คำสั่งใช้แบบไม่มี `/` ได้ทั้ง Private และ Channel; `/` ยังรับเพื่อ compatibility และ `ci off` ปิดการตอบสนอง Channel โดยไม่ทำให้ moderation หยุด
- Private ที่ไม่ตรงคำสั่ง/workflow จะบอกว่าไม่รู้จักคำสั่งและแนะนำ `h`; ข้อความสนทนาปกติใน Channel/CUSTOM ไม่โดนตอบรบกวน
- สถานะอัตโนมัติบอกประเภทบอตและลงท้าย `พิมพ์ h เพื่อดูวิธีใช้`; `about` แนะนำ `dr <ข้อความของคุณ>` สำหรับแจ้งบั๊ก ขอ/เสนอฟีเจอร์ โดยไม่แสดง URL support ที่ไม่มีแบบฟอร์ม
- จัดคำสั่งย่อใหม่ให้ **หนึ่งคำสั่งหลักมี shorthand เดียวเท่านั้น**: ใช้ `a`→about, `c`→select, `j`→join, `vt`→voicetx; ตัด alias ซ้ำ `ab`, `sel`, `i`, `jc`, `va`
- แก้ Linux TeamTalk text/bytes regression เพื่อให้คำสั่งและ moderation รับข้อความจริงจาก SDK ได้โดยไม่ทำ event loop ล้ม
- ระบบกรองใช้ `blacklist.txt` multilingual path เดียวสำหรับไทย/อังกฤษ/ภาษาอื่น; `filter on|off|status` คุมทั้งหมด และ filter ทำงานก่อน `ci`
- แก้ Queue FIFO ที่จังหวะเพลงจบ: รายการใหม่ไม่แซงของเก่า, เพลงที่เล่นจบถูกนำออกทีละตัว, `dq` ลบทีละรายการ, `cq` ล้างคิว, `s` หยุดและล้างคิวทั้งหมด
- ทุก queue item เก็บชื่อผู้เพิ่มและเวลาที่เพิ่ม; `ql` แสดงเพลง + ผู้เพิ่ม + อายุของรายการ และข้อความ/TTS ตอนเพิ่มเพลง, playlist หรือ Favorites บอกชื่อผู้เพิ่มกับหมายเลข/ช่วงคิว
- โหมดปกติแยก navigation: `,`/`.` เลื่อนผลค้นหา, `n`/`b` เดิน Related Radio history; `c 56` หรือ `select 56` กระโดดไปเพลงที่ 56 ของ playlist/session
- M2/Autoplay ใช้ YouTube Mix / YouTube Music Radio ก่อน fallback related search; Playlist/Channel/Favorites เล่นตามลำดับก่อนและไม่ถูก recommendation แทรก
- เพิ่ม `pp <playlist_link>` เพื่อ **ต่อ playlist ชุดที่ 2, 3, ...** โดยไม่หยุดเพลงปัจจุบัน; Queue Mode เพิ่ม playlist ทั้งชุดต่อท้าย FIFO และประกาศช่วงคิว
- คืน **default YouTube cookies จากโปรเจกต์เดิม** เป็น bootstrap สำหรับ Player/Full: instance ใหม่จะได้ `/app/data/cookies.txt` อัตโนมัติ ถ้ามี cookie ที่ผู้ใช้ติดตั้งไว้แล้วจะไม่ถูก overwrite; วันหลังใช้ `ttuhelper cks` แทนไฟล์ชื่อเดิมได้
- TTUHelper 1.4 รองรับ `cks`, `cks-all`, `cks-check`; cookie commands ใช้เฉพาะ Player/Full และ `cks-all` ข้าม Server Manager
- คู่มือ TTUHelper รองรับทั้งดาวน์โหลด ZIP และ `git clone`; คู่มือ cookies มีการเลือก browser profile และสคริปต์ `-ListProfiles` สำหรับวันที่ต้องการแทน default cookie ด้วยชุดใหม่

## การป้องกัน regression

- validator บังคับ role isolation, one-alias-per-command, Linux bytes, unknown-command routing, moderation-before-ci และ canonical multilingual blacklist
- validator จำลอง queue race ตรง playback-end, queue ownership metadata, playlist append, `select 56`, Related Radio navigation และ Queue Mode isolation
- validator ตรวจ default cookie bootstrap ว่ามี Netscape YouTube records, image มีเฉพาะ bundled default และ entrypoint ไม่ overwrite persistent replacement
- validator ตรวจ callback ที่มีจริงของ TeamTalk สำหรับ user/channel/server/file/state update, ทดสอบ `status`/`events` แบบ runtime และบังคับว่า `events` อยู่เฉพาะ Manager/Full
- Dashboard นับสถานะพูด/stream/video/desktop แบบสด แต่ไม่เก็บ voice start/stop ทุกครั้งลง event log เพื่อไม่ให้รายการเหตุการณ์ถูก spam จากการพูดปกติ

# 2026.08.23-r7.4.5

## สิ่งที่ผู้ใช้ควรรู้
- แก้บั๊กคิวช่วงเพลงจบ: เพลงที่เพิ่มใหม่จะต่อท้าย FIFO และไม่แซงรายการเก่าที่รออยู่ แม้เพิ่มตรงจังหวะ playback-end
- เพลงในคิวที่เล่นจบจะถูกนำออกทีละรายการ; `dq <ลำดับ|ชื่อเพลง>` ลบทีละรายการ, `cq` ล้างคิว, และ `s` หยุดพร้อมล้างคิวทั้งหมด
- Queue Mode แยกจาก Related Radio: ถ้า `q` ยังเปิดแต่คิวหมด/ถูก `cq` ล้าง เพลงปัจจุบันจบแล้วจะหยุด ไม่ไหลไป recommendation ของโหมดปกติ
- โหมดปกติแยก navigation ชัดเจน: `,`/`.` ใช้ผลการค้นหา ส่วน `b`/`n` ใช้ประวัติ Related Radio
- M2/Autoplay หลังเพลงค้นหาปกติจะต่อด้วย YouTube Mix / YouTube Music Radio แทนการไล่ผลค้นหาถัดไป; Playlist/Channel/Favorites ที่เปิดโดยตรงยังเล่นตามลำดับเดิม
- ระบบกรองใช้ `blacklist.txt` multilingual เป็น runtime path เดียว; `filter on/off` ยังคุมทั้งหมด และ `ci off` ไม่ปิด moderation

## การป้องกัน regression
- เพิ่ม runtime test จำลองจังหวะเพิ่มเพลงตรง playback-end เพื่อยืนยันว่าคิวเดิมไม่หายและเพลงใหม่ไม่แซง
- เพิ่ม test แยก Related Radio history ออกจาก search navigation และตรวจ canonical blacklist ครอบคลุม `badword.txt` ทั้งหมด

# 2026.08.23-r7.4.4

## สิ่งที่ผู้ใช้ควรรู้
- แยก 3 ประเภทชัดเจน: Full Bot, Player Bot และ Server Manager Bot; Player-only ไม่ได้คำสั่ง Manager และ Manager-only ไม่ได้คำสั่ง Player
- เมื่อข้อความ Private ไม่ตรงกับคำสั่งหรือ workflow ที่เปิดใช้งาน บอตตอบว่าไม่รู้จัก/คำสั่งไม่ถูกต้องและแนะนำ `h` เพื่อดูวิธีใช้; Channel สนทนาปกติไม่โดน fallback นี้
- คืน alias เดิมที่ไม่ชนระบบใหม่ตาม role: Common `a`; Player/Full `gl`, `c`, `sb`, `sf`; Manager/Full `jc`, `sc`, `va`
- สถานะอัตโนมัติระบุประเภทบอตและลงท้าย `พิมพ์ h เพื่อดูวิธีใช้`
- `about` แสดงประเภทบอตและเปลี่ยนจาก URL support เป็นคำแนะนำ `dr <ข้อความของคุณ>` สำหรับแจ้งบั๊ก รายงานปัญหา ขอฟีเจอร์ หรือเสนอแนะ

## การป้องกัน regression
- validator ตรวจ role/alias isolation, unknown-command fallback, about ที่ไม่เปิดเผยหน้า support URL, คำสั่งครบ และ Linux TeamTalk bytes regression เดิม
- ไม่ย้อน Google Cloud TTS, service abstraction, alias ที่ชนคำสั่งใหม่ หรือโค้ด legacy ที่ไม่มี runtime parity

# 2026.08.23-r7.4.3

- แก้ Linux TeamTalk runtime: ข้อความขาเข้าจาก SDK อาจเป็น `bytes`; แปลง UTF-8 เป็น `str` ก่อน Unicode normalization/command parsing
- แก้อาการส่งคำสั่งทั้งแบบมี `/` และไม่มี `/` แล้วบอตเงียบ พร้อมป้องกัน event-loop `TypeError: normalize() argument 2 must be str, not bytes`
- ตัวกรองคำหยาบใช้ตัวถอดข้อความเดียวกัน จึงรองรับภาษาไทยจาก TeamTalk Linux จริง ไม่ใช่เฉพาะ test ที่จำลองเป็น `str`
- เพิ่ม regression test ให้จำลอง Linux `ttstr()` ที่คืน bytes เพื่อไม่ให้บั๊กนี้ผ่าน validator อีก

# SNTalkBot 2026.08.23-r7.4.2

- แก้ regression ของ r7.4.1: คืนคำสั่ง prefix-free ให้ใช้ได้ทั้ง Private และ Channel/Broadcast เช่น `h`, `p เพลง`, `ap on`, `ci off`, `filter on`; `/` เป็นเพียง compatibility และไม่บังคับ
- ย้ายรายการคำหยาบภาษาไทยเข้า `blacklist.txt` เดียวกับภาษาอังกฤษ/อาหรับและรายการเดิมทั้งหมด โดยคง `badword.txt` ไว้เป็น supplemental compatibility เพื่อไม่รื้อของเก่า
- ทำ `filter on|off|status` เป็น master switch ของ word moderation: ปิด/เปิด blacklist และ badword พร้อมกัน รวมข้อความ ชื่อผู้ใช้ และชื่อ/หัวข้อ Channel
- แก้ blacklist matcher ให้รองรับภาษาไทย/Unicode และรูปแบบเว้นวรรค เช่น `ค ว ย` พร้อมป้องกัน false positive คำสั้นอย่าง `หี` ไม่จับ `หีบ`
- แก้กรณี `files/blacklist.wav` ไม่มีในแพ็กเกจ: เสียงเตือนเป็น optional และไม่สามารถทำให้การเตะ/แบนหยุดด้วย exception ได้อีก
- คงลำดับ moderation ก่อน `ci` ดังนั้น `ci off` ปิดการตอบสนองปกติใน Channel แต่ไม่ปิดตัวกรองที่เปิดอยู่; ใช้ `filter off` เมื่อต้องการปิดการกรองทั้งหมด
- สถานะอัตโนมัติกลับเป็นแบบสั้น `พิมพ์ h เพื่อดูคำสั่ง` โดยยังรู้จักสถานะ r7.4.1 เพื่อ migration

# Release 2026.08.23-r7.4.1

- แก้ regression จากชุด r7.4 pre-release: คำสั่งแบบไม่ใส่ `/` ใช้เฉพาะ Private; Channel/Broadcast บังคับ `/` ทุกคำสั่ง เช่น Private `h`, `p เพลง`, `ci off` แต่ในห้องใช้ `/h`, `/p เพลง`, `/ci off`
- คง parser แบบสั้นตาม TTMediaBot สำหรับ Private พร้อม Unicode normalization เพื่อรองรับอักขระ format/control ที่อาจติดมาจากช่องข้อความ
- ปรับสถานะอัตโนมัติให้บอกสั้นและชัดตามบริบท: `ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h` โดยยัง migrate ข้อความสถานะอัตโนมัติรุ่นเก่าได้
- `ci off` ปิดเฉพาะ command/TTS/Player/translation จาก Channel แต่ moderation/blacklist/ตัวกรองคำหยาบยังทำงานกับข้อความที่บอตได้รับ; Private ยังใช้ `ci on` เพื่อเปิดกลับได้เสมอ
- `intercept on|off|status` คำสั่งย่อ `ic` สำหรับ Manager/Full ยังเปิด/ปิดการดักข้อความจากทุก Channel แบบ runtime และบันทึกค่าใน config ตามเดิม
- `filter on|off|status` และ `badword.txt` ภาษาไทยยังทำงานก่อน `ci` พร้อม matcher รูปเว้นวรรค/อักขระแฝงและการลด false positive ของคำสั้น
- `about`/`ab` และ `dr <ข้อความ>` คงข้อมูลผู้พัฒนา/ช่องทาง report service ตามชุด r7.4
- คำสั่งหลัก 121 คำสั่ง และ alias 47 ตัว; validator เพิ่ม regression test บังคับว่า plain channel text เช่น `h`, `s`, `p เพลง`, `ap on` ต้องไม่ถูก dispatch และรูปแบบ `/...` เท่านั้นที่ทำงานใน Channel

---

# Release 2026.08.23-r7.3.1

- Hotfix การอัปเกรด config สำหรับ Docker instance เดิม: setting ใหม่ที่เป็น optional จะเติมค่า default ลง `config.ini` อัตโนมัติก่อน validation
- แก้ปัญหา r7.3 ที่ instance เดิมไม่มี `channel_input_enabled` แล้วถูกส่งเข้า interactive setup wizard ใน container แบบ detached ทำให้บอตไม่ถึงขั้น login TeamTalk
- `channel_input_enabled` ของ config เก่าจะถูกเพิ่มเป็น `True` อัตโนมัติ โดยรักษาค่าเดิมอื่นทั้งหมด
- ถ้าค่าที่จำเป็นจริง ๆ หายและไม่มี interactive terminal ระบบจะแจ้งชื่อ `[section] key` ที่ขาดอย่างชัดเจนแทนการล้มด้วย EOF
- เพิ่ม validator จำลอง config เก่าจริงเพื่อกัน regression นี้ใน release ต่อไป
- ฟีเจอร์ r7.3 (`ci`, `cm`, คำสั่งรูปแบบเดียวกันใน Private + Channel) คงเดิมทั้งหมด

---

# Release 2026.08.23-r7.3

- เปลี่ยนคำสั่งให้ใช้รูปแบบเดียวกันทั้ง Private และ Channel เช่น `h`, `s`, `p เพลง`
- เพิ่ม `channelinput on|off|status` คำสั่งย่อ `ci` สำหรับผู้ดูแล
  - `ci off` = บอตไม่อ่านและไม่ตอบสนองต่อข้อความจาก Channel ทั้งหมด
  - Private Message ยังทำงาน จึงใช้ `ci on` ทาง Private เพื่อเปิด Channel กลับได้เสมอ
- ขยาย `cm` เป็น `cm on|off|status` และยังรองรับ `cm` เปล่าเพื่อสลับสถานะแบบเดิม
  - `cm off` ปิดข้อความ Player ที่ประกาศลง Channel เช่น ใครเปิดเพลงหรือเพิ่มเพลงเข้าคิว
  - ไม่กระทบการรับคำสั่ง; `ci` และ `cm` แยกจากกัน
- เพิ่ม config `channel_input_enabled = True` และบันทึกค่าที่เปลี่ยนจากคำสั่งลง `config.ini`
- สถานะอัตโนมัติย่อเป็น `พิมพ์ h เพื่อดูคำสั่ง`
- Validator เพิ่ม regression test สำหรับคำสั่งตรงใน Private + Channel, Channel Input OFF, alias/argument และความคงอยู่ของ config
- คำสั่งหลักรวม 120 คำสั่ง และ alias 46 ตัว

---

# 2026.08.23-r7.1

- สถานะเริ่มต้นระบุประเภทบอตอัตโนมัติ: Player Bot, Server Manager Bot หรือ Full Bot
- config เก่าที่ใช้ `status_message = SN TalkBot` จะได้รับสถานะตามประเภทโดยไม่ต้องแก้ config เอง
- สถานะที่ผู้ดูแลตั้งเองยังคงใช้ตามเดิม และ `cs auto` ใช้กลับสู่สถานะอัตโนมัติ
- เมื่อ Player หยุดเพลงหรือเปิดการแสดงสถานะกลับมา ระบบคืนสถานะประเภทบอตอย่างถูกต้อง

# Release 2026.08.23-r7

- เริ่มรองรับการพิมพ์คำสั่งโดยตรงในข้อความส่วนตัว เช่น `help`, `ap on`, `wb off`, `rs`
- alias ส่ง argument ต่อเหมือนคำสั่งหลัก จึงใช้ `ap on`, `ap off`, `wb on`, `wb off`, `acs on`, `vt off` ได้
- การ block คำสั่งหลักยัง block alias ของคำสั่งนั้นด้วย และ `blockcmd` หรือ `bc` ยัง resolve alias เป็นคำสั่งหลัก
- เพิ่ม regression test สำหรับคำสั่งส่วนตัวและ on/off ผ่าน alias
- `help` แสดงคำสั่งแบบตรงเป็นรูปแบบหลัก

# SNTalkBot 2026.08.23-r6

## แก้ไขหลัก

- Welcome broadcast และ welcome ตอนเข้าห้องไม่ประกาศย้อนหลังให้ผู้ใช้ที่ออนไลน์อยู่ก่อนบอตเริ่มหรือ reconnect
- ผู้ใช้ที่อยู่ในชุด startup sync จะถูกกันไว้จน logout ป้องกัน event ซ้ำที่มาช้ากว่าเวลา bootstrap
- เพิ่มระบบคำสั่งย่อผ่าน alias resolver โดยไม่ลงทะเบียน command handler ซ้ำ
- คำสั่งย่อสำคัญ เช่น `h` → `help`, `rs` → `restart`, `sd` → `shutdown` และคำสั่งย่ออื่นจะแสดงใน `help`
- `cc`, `csize`, `cm` อยู่ใน PlayerCog เท่านั้น จึงไม่โผล่ใน Server Manager
- แก้ `split_long_message()` ไม่ให้ข้อความช่วงรอยต่อหายเมื่อแบ่งที่ช่องว่าง
- เพิ่ม guard ในงาน Player/Weather/SSH บางส่วนเมื่อผู้ใช้ออกจาก TeamTalk ระหว่างงาน async
- blocked command ที่เคยบันทึกด้วยชื่อ alias จะถูก normalize กลับเป็นชื่อคำสั่งหลัก
- คง Google standard gTTS, FIFO Player TTS, No Music Ducking และ `dr` จาก r5

## การตรวจสอบ

- Python compile
- ชื่อคำสั่งหลักไม่ซ้ำ
- alias ไม่ชนชื่อคำสั่งหลักและ target ต้องมีจริง
- Player/Manager role-specific commands ไม่ชนกัน
- `help` และ `COMMANDS_TH.md` ตรงกับคำสั่งหลักที่ลงทะเบียน
- ไม่มี Telegram bot token ในไฟล์ release

# SNTalkBot 2026.08.23-r5

- `dr` เปลี่ยนเป็นระบบรายงานถึงผู้พัฒนาแบบ relay กลาง ผู้ใช้ส่งได้โดยตรงด้วย `dr <ข้อความ>` โดยไม่ต้องเปิด URL รายงานแยก
- ไม่ต้องและไม่ควรฝัง Telegram Bot Token ใน Docker image หรือ config ของลูกค้า
- API ล่ม/timeout แล้วคำสั่งจบอย่างปลอดภัย ไม่ทำให้บอต crash
- จำกัดข้อความ `dr` สูงสุด 2000 ตัวอักษร
- `about` อ่านเวอร์ชันจากไฟล์ VERSION จริง ไม่ hard-code รุ่นเก่า
- คง Google standard gTTS และ FIFO TTS จาก r3
- คง No Music Ducking จาก r4: TTS Player ไม่ปรับ volume เพลง

# Release notes — 2026.08.23-r4

- แก้ Player TTS announcement ไม่ให้ลด/duck/พักเพลงอีกต่อไป
- TTS announcement ใช้ libmpv แยก stream แล้ว mix กับเพลงผ่าน PulseAudio sink เดียวกัน
- เพลงรักษา volume เดิมตลอดระหว่างข้อความ “เพิ่มเพลงเข้าคิว”, “กำลังเล่น” และประกาศ Player อื่น ๆ
- คง FIFO announcement queue จาก r3 เพื่อให้ TTS หลายข้อความไม่พูดซ้อนกันเอง
- คง Google standard gTTS เป็นค่าเริ่มต้นทั้ง Player และ Manager

# SN TalkBot 2026.08.23-r3 — Google Standard TTS

## เปลี่ยน TTS หลัก

- ตัด Google Cloud Text-to-Speech ออกจาก runtime และลบ `bot/GoogleCloudTTSClient.py`
- โหมด `google` ใช้ `gTTS` (Google Translate TTS แบบมาตรฐาน) ไม่ต้องใช้ API key
- Player และ Server Manager ตั้ง Google standard เป็นค่าเริ่มต้นทั้งคู่
- ค่าเริ่มต้นภาษาไทยคือ `th`
- `voice` และ `pvoice` ใน Google mode ใช้รหัสภาษา เช่น `th`, `en`, `ja` แทนชื่อ Cloud voice
- `get_voices` และ `pvoices` ใน Google mode แสดงภาษาที่ gTTS รองรับ
- `speed` และ `pttsspeed` ยังรองรับ `0.25..4.0` โดยใช้ FFmpeg `atempo`
- Microsoft Edge TTS ยังอยู่เป็น engine สำรอง ไม่ได้ลบออก
- มี migration ครั้งเดียวสำหรับ config r2: ลบ key Google Cloud เก่าและเปลี่ยนค่าเริ่มต้นทั้ง Manager/Player เป็น gTTS
- FIFO Player announcement จาก r2 ยังคงอยู่ จึงยังพูดทีละข้อความไม่ซ้อนกัน

# SN TalkBot 2026.08.23-r2 — Release Notes

## แก้ไขสำคัญ

- Player TTS announcement เปลี่ยนเป็น FIFO queue + worker เดียว ป้องกันเสียง "เพิ่มเข้าคิว" และ "กำลังเล่น" พูดซ้อนกัน
- แก้ Player-only logout callback ที่อาจเรียก `AccountRequestCog` ซึ่งไม่มีในโหมด Player และเกิด `AttributeError`
- ลบ public command aliases ที่ทำงานซ้ำกัน: `h`, `gl`, `rs`, `sd`
  - ใช้ `help`, `l`, `restart`, `shutdown` แทน
- validator เพิ่มการตรวจชื่อคำสั่งซ้ำและคำสั่งหลายชื่อที่ชี้ handler เดียวกันใน module เดียว

## Player TTS ใหม่

Player announcement TTS แยกจาก Server Manager TTS อย่างชัดเจน:

- `ptts [on|off|status]`
- `ptts tracks on|off`
- `ptts queue on|off`
- `pttsmode microsoft|google`
- `pvoices [langcode]`
- `pvoice <voice_name>`
- `pttsrate <-100..100>` สำหรับ Microsoft
- `pttsspeed <0.25..4.0>` สำหรับ Google

หมายเหตุประวัติ r2: รุ่นนั้นเคยใช้ Google Cloud สำหรับโหมด Google; r3 ยกเลิกแนวทางนี้แล้วและใช้ gTTS มาตรฐานแทน

## Server Manager TTS

ชุดเดิมยังอยู่เฉพาะ Manager/Full เช่น `say`, `tts`, `ttsmode`, `voice`, `get_voices`, `rate`, `pitch`, `volume`, `speed` และ `st`

หมายเหตุประวัติ r2: พฤติกรรม API key นี้ถูกยกเลิกใน r3 เพราะ Google mode ไม่ต้องใช้ API key แล้ว

## Telegram Direct Report

- `report <message>` ยังคงส่งหาแอดมิน TeamTalk และ register เฉพาะ Manager/Full
- เพิ่ม `dr <message>` ทุกโหมด เพื่อส่งรายงานตรงไป Telegram
- รายงานประกอบด้วย TeamTalk server, bot/mode, nickname, username, channel และข้อความ
- ถ้า token/chat ID ไม่ครบ `dr` จะตอบว่าไม่ได้ตั้งค่าและไม่ throw exception
- รองรับ environment `SNTALKBOT_TELEGRAM_BOT_TOKEN` และ `SNTALKBOT_TELEGRAM_REPORT_CHAT_ID` เพื่อไม่ต้องฝัง secret ใน Git/Docker image

## Validation

Static release validator ตรวจ:

- Python compile
- command name uniqueness
- same-handler alias duplication
- retired aliases
- Player TTS command set
- `dr`
- `help` parity
- `COMMANDS_TH.md` parity
- Thai message size
- Thai translations
- no legacy multi-profile references

หมายเหตุ: static/unit checks ไม่แทน live TeamTalk + PulseAudio + MPV + Google/Telegram network integration test บนเซิร์ฟเวอร์จริง
