# SNTalkBot 5.1.42 — Normal Autoplay Ownership / Fast Stable Retry

- แก้โหมดปกติเพลงถัดไปไม่เล่นเมื่อมี queue_index ค้างจาก Q: Queue จะถือ ownership เฉพาะ playback context ที่เป็น `queue` หรือเมื่อ Q เปิดและมี pending queue จริง.
- ปิด Q จะไม่ปล่อย stale current index ไปแย่ง normal autoplay; เปิด Q ตอน idle พร้อม pending queue จะเริ่ม item แรกได้.
- MPV `error=-13` retry ทันที ไม่รอ retry delay และลอง public-fast yt-dlp ก่อน full cookie-aware recovery.
- Background prefetch/stable retry ใช้ public-fast -> full recovery เพื่อลดเวลารอของเพลง Queue แรก/stream ที่ direct URL ใช้ไม่ได้ โดยยังรักษา 18+/cookie fallback.

---

# SNTalkBot 5.1.41 — Fast First Track Validation / Deep Bass Recovery

- เพลงแรกโหมดปกติไม่ส่ง direct YouTube URL ที่ยังไม่ตรวจให้ MPV อีกต่อไป; direct candidate ต้องผ่าน Range probe สั้น ๆ ก่อน และแข่งกับ public no-cookie yt-dlp fast path.
- ถ้า fast paths ใช้ไม่ได้จึงค่อยเข้า cookie-aware stable resolver ทำให้ไม่เสียเวลา MPV error -13 หลายวินาทีก่อน fallback.
- direct stream cache ถูก invalidate เมื่อ probe/retry fail เพื่อไม่วนใช้ CDN URL เดิม.
- Queue fast handoff/stable prefetch จาก 5.1.40 คงไว้ ไม่ย้อนกลับไปใช้ direct prefetch ที่เปราะ.
- Bass คืนโทนลึกแบบรุ่นแรกแถว 55 Hz แต่เพิ่ม -4 dB headroom และ look-ahead limiter ป้องกัน peak clipping/เสียงแตก.
- Offline QA: Unit tests 133/133, validator ผ่าน และ FFmpeg ยอมรับ Bass filter chain จริง.

---

# SNTalkBot 5.1.40 — Queue EOF Fast Path / Stable Prefetch

- แก้ Queue จบเพลงแล้วไม่เดินต่อ โดย clean EOF ของ Queue advance โดยตรง ไม่ผ่าน generic cancel/retry guard ที่เคยกลืน handoff.
- Background prefetch ของเพลงถัดไปใช้ yt-dlp stream info + headers เป็นหลัก; direct YouTube endpoint ใช้เป็น fallback ไม่ใช่ cache หลักของ Queue.
- MPV error `-13` retry ด้วย stable yt-dlp resolver เท่านั้น ไม่กลับไปเลือก direct URL เดิมซ้ำ.
- เพิ่ม log `playback_worker_error` ป้องกัน exception ใน playback executor หายเงียบ และแก้ PLAYTRACE queue_index=0 ให้แสดงถูกต้อง.

---

# SNTalkBot 5.1.39 — Queue Trace / Terminal Readiness (source ยังไม่เผยแพร่)

- เพิ่ม `PLAYTRACE` แบบ JSON ที่ log ของแต่ละ Docker instance เพื่อเห็น search/resolver/prefetch/MPV terminal/queue transition แบบลำดับเหตุการณ์เดียวกัน โดยไม่เผย cookie/token/full URL.
- กัน stale `idle-active=True` และ `eof-reached=True` ของเพลงเก่าจบ generation ใหม่ก่อน MPV เริ่มเพลง.
- Watchdog ยอมกู้ EOF จาก generation ที่เห็น active/time-pos แม้ START_FILE event หาย.
- Terminal property observers อยู่ถาวรและไม่ถูก stop/radio path ถอดหรือลงทะเบียนซ้ำ.
- Queue trace ครอบคลุม enqueue, first start, next prefetch, end callback, queue pop/schedule, play request/load และ manual `n` เพื่อเทียบ auto-next กับ manual-next จาก runtime จริง.

---

# SNTalkBot 5.1.38 — Redundant EOF / Resolver Race / Fast Discovery (source ยังไม่เผยแพร่)

- แก้ Queue เพลงถัดไปไม่เริ่มเองด้วย terminal detection 4 ชั้น: MPV END_FILE + permanent `eof-reached` + permanent `idle-active` + watchdog โดยใช้ one-shot dedupe เดียวกัน.
- intentional stop ไม่ถอด idle observer ออกอีก จึงไม่ทำให้ autoplay รอบถัดไปเงียบโดยไม่ตั้งใจ.
- แก้ cold-start regression ของ 5.1.37: direct resolver กับ yt-dlp ทำงานแข่งกันแทนการรอ fast resolver ก่อนแล้วค่อย fallback.
- ค้นหาเพลงแรกเพียง 1 ผลเพื่อเริ่มเสียงก่อน แล้วเติมผลเต็มใน background; flat search ใช้ public/no-cookie ก่อน, timeout สูงสุด 12 วินาทีและ retries 2 แบบเดียวกับแนว reference player ขณะที่ playback 18+ ยังคง cookie-first.
- เทียบกับ TikTok Music Player/TTMediaBot ที่ผู้ใช้ส่งจริง: event-driven next, prefetch ตั้งแต่ Waiting/Playing และ metadata search แยกจาก full stream extraction.
- Offline QA ผ่าน Unit tests 125/125 และ `tools/validate_project.py`; live Docker/TeamTalk ยังเป็น gate ก่อนยืนยัน latency จริง.

---

# SNTalkBot 5.1.37 — Realtime Audio Handoff / Fast First Track (source ยังไม่เผยแพร่)

- Queue เปิด TeamTalk voice ก่อนเริ่ม MPV เพื่อไม่ตัดต้นเพลง และไม่สั่ง stop ซ้ำเมื่อเพลงก่อนจบตามธรรมชาติแล้ว.
- MPV Linux/PulseAudio ใช้ output คงที่ 48 kHz/stereo/s16 + gapless/cache/reconnect ให้ตรงกับ virtual sink ของ SNTalkBot; continuous-silence จำกัดเฉพาะ Pulse backend.
- ลดผลค้นหาชุดแรกจาก 12 เหลือ 4 แล้วเติมรายการเต็มเบื้องหลัง เพื่อให้เพลงแรกเริ่มเร็วขึ้นโดยยังมีตัวเลือกทันที.
- เพิ่ม fast public-YouTube direct resolver แบบ bounded พร้อม connection prewarm/keepalive/cache; ถ้าไม่สำเร็จหรือเป็น login/age/content restricted จะกลับ yt-dlp + cookies เดิมทันที.
- แก้ MPV END_FILE race ให้ active entry ID ที่เพิ่งยืนยันใหม่ไม่ถูกเทียบกับ snapshot เก่าแล้วทิ้ง terminal event.
- เพิ่ม regression tests สำหรับ fast resolver, restricted fallback, adopted entry ID, natural handoff no-stop และ voice-before-play.
- ยังไม่เปลี่ยน backend เป็น VLC และยังไม่เพิ่ม dependency ใหม่; generic yt-dlp URLs, radio fallback, SQLite queue, 18+ cookies, TeamTalk commands และ Web Manager API เดิมยังคงอยู่.
- Offline QA จาก complete package ผ่าน Unit tests 123/123 และ `tools/validate_project.py`; ยังต้องฟัง/ทดสอบ Docker + TeamTalk live หลัง publish.

---

# SNTalkBot 5.1.36 — แก้เพลงจบแล้วไม่ข้ามคิว (ยังไม่เผยแพร่)

- แก้การยกเลิก retry ระหว่าง yt-dlp extraction แล้วไม่คืนสถานะ `loading_new_track` จน end callback ของเพลงใหม่ไม่ถูกประมวลผล
- อ่าน MPV `playlist_entry_id` ยืนยัน EOF/ERROR เพลงใหม่แม้ START_FILE callback หาย คง guard เพลงเก่าและ dedupe เดิม
- เพิ่ม watchdog สำหรับสตรีมมี duration ที่ time-pos ค้างตรงท้ายไฟล์ ≥3s; ไม่กระทบ live/paused/buffering streams
- สั่ง stop/play จาก retry, manual next/previous, repeat, playlist/normal autoplay และ queue selection ผ่าน playback worker เฉพาะเดียวกัน
- ตรวจเทียบกับ TT Utilities จาก `tt_utilities-main.zip`, TTMediaBot ที่ผู้ใช้ส่ง และ baseline 5.1.27; ยังคง 12 search results, 18+ cookies, generic URLs, SQLite, TeamTalk และ Web Manager เดิม
- Unit tests 118 รายการผ่าน; ต้องยืนยัน MPV/PulseAudio/TeamTalk บน Linux จริงหลังเผยแพร่

---

# SNTalkBot 5.1.35 — คิวเพลงต่อเนื่องและผลค้นหา 12 ทางเลือก (เผยแพร่แล้วตาม Publisher log)

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
