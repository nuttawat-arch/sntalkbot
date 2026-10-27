# เปรียบเทียบ TTMediaBot กับ SNTalkBot เพื่อแก้เวลาเริ่มเพลง (27–28 ต.ค. 2569)

## เพิ่มเติมใน 5.1.37: TikTok Music Player + TT Utilities fast-path

- TikTok Music Player ที่อัปโหลดรอบ 28 ต.ค. ใช้ VLC event `MediaPlayerEndReached` แล้วเรียก next บน thread ทันที และเริ่ม prefetch next YouTube stream เมื่อ player เข้าสถานะ Playing; นำหลัก event-driven + prefetch มาเทียบ ไม่ย้าย VLC backend เข้ามา.
- TT Utilities ที่อัปโหลดรอบเดียวกันล็อก MPV เป็น 48 kHz/stereo/s16, ใช้ gapless/audio cache, warm HTTP connection และ direct YouTube resolver/cache ก่อน yt-dlp fallback. SNTalkBot 5.1.37 นำแนวทางนี้มาใช้เฉพาะที่เข้ากับ Linux/PulseAudio architecture.
- พบว่า Queue ของ SNTalkBot เปิด TeamTalk voice หลัง `play_stream()`; แก้เป็นเปิดก่อนเสียงเริ่ม. Natural EOF ยังเรียก `stop_transport()` ซ้ำ; แก้ให้ stop เฉพาะเมื่อ transport ยัง active เพื่อไม่ทำลาย handoff.
- Initial search 12 ผลเพิ่ม latency โดยไม่จำเป็นกับ critical path จึงลดเป็น 4 ตาม TTMediaBot และเติมผลเต็มเบื้องหลัง.
- Fast resolver เป็น optimization แบบ bounded เท่านั้น: login/age/content restricted และ failure ทุกชนิดกลับไป yt-dlp/cookies เดิม; ไม่ลดการรองรับ generic URLs.
- ไม่คัดลอก `vlc_libs` portable bundle ไป Linux. ถ้าต้องใช้ VLC ในอนาคตให้ติดตั้ง system libVLC; สำหรับ effect presets ปัจจุบันเลือก MPV + FFmpeg/lavfi เพราะเป็น backend เดิมและยืดหยุ่นกว่า built-in VLC equalizer.

## เพิ่มเติมใน 5.1.36: เทียบ TT Utilities และ SNTalkBot baseline 5.1.27

- ตรวจ `tt_utilities-main.zip` ที่ผู้ใช้อัปโหลดไว้ (อาจเป็นไฟล์ที่เรียกด้วยเสียงว่า GT Unity): `bot/player.py::_register_end_callback` ฟัง `end-file` เหตุผล EOF/ERROR แล้วเรียก callback ทันที; `bot/modules/player.py::on_playback_end` เลือกรายการถัดไปใน thread pool ทั่วไป ไม่มี queue generation guard ของเรา ส่วน `TTMediaBot` จบเพลงผ่าน `_handle_track_finished`/`play_from_queue` และล้างสถานะตอนคิวหมด
- เทียบ `git show HEAD:bot/player.py` และ `git show HEAD:bot/modules/player.py` จาก baseline 5.1.27 ที่มีจริง: ระบบของเรามี MPV entry-ID filter อยู่ก่อนแล้ว แต่เวอร์ชันต่อมามีทางพิเศษที่ทิ้ง `END_FILE` เมื่อยังรอ `START_FILE` แม้ entry ID จะไม่ใช่เพลงเก่า; เพิ่ม watchdog/retry มากขึ้น แต่พบ `loading_new_track` ไม่ถูกคืนค่าเมื่อยกเลิก retry กลางงาน
- **เลือกวิธี:** ใช้การส่งต่อ EOF/ERROR ทันทีแบบตัวอ้างอิงเมื่อ `playlist_entry_id` เป็นเพลงใหม่ที่พิสูจน์ได้; ถ้า ID เป็นเพลงเก่ายังต้องทิ้งเพื่อป้องกันข้ามซ้ำ; จัด stop/play และ retry ใน ordered worker เดียว; กู้ MPV ค้างที่เฟรมสุดท้ายแทนการใช้ PCM watchdog ของ TTMediaBot โดยตรง
- ตรวจจากต้นฉบับ `python-mpv==1.0.8` ใน requirements: `MpvEvent.data` รองรับ `MpvEventEndFile.reason/error/playlist_entry_id` และ `MpvEventStartFile.playlist_entry_id`; การใช้ชื่อ callback `END_FILE`/`START_FILE` แบบปัจจุบันใช้ได้จริง
- ยังไม่มีหลักฐานว่าแพตช์นี้แก้เวลาที่เสียงเริ่มออกจากอุปกรณ์ TeamTalk ได้ทุกกรณี ต้องทดสอบ Docker/TeamTalk จริง; ไม่ได้ใช้ FFmpeg/PCM หรือ InnerTube ที่ผูกกับแพลตฟอร์มเดียวมาแทนเครื่องเล่นเดิม

## เพิ่มเติมใน 5.1.35

- TTMediaBot มีช่องทางส่งต่อคิวที่ชัดเจนผ่าน `_handle_track_finished()` และ `play_from_queue()`; นำหลักการแยกงานส่งต่อเพลงออกจากงานค้นหาทั่วไปมาใช้กับ SNTalkBot ด้วย ordered playback worker ไม่ได้ย้าย FFmpeg/PCM หรือ QueueManager ของ TTMediaBot มาแทน
- เส้นทางการค้นหาของ TTMediaBot ใช้ VideosSearch จำกัด 4 ผล ส่วน SNTalkBot เคยใช้ yt-dlp ผลแรกเพียง 1 ผลแล้วเติม 50/20 ภายหลัง แต่ผู้ใช้เปลี่ยนผลไม่ทัน จึงปรับ SNTalkBot ให้โหลด 12 ผลก่อนเริ่ม และเติมรายการเต็มต่อใน background
- Prefetch เดิมของเราใช้ล็อกเดียวกับ foreground yt-dlp ทำให้กดเปลี่ยนเพลงใหม่ต้องรอ URL ที่กำลัง prefetch; 5.1.35 แยกล็อก network ออกเหลือเพียง cache mutex และรอ URL เดียวกันสูงสุด 250ms
- เพิ่มการตรวจ MPV `eof-reached` ประกอบ `END_FILE` และ `idle-active`; ยังต้องตรวจความเร็วและสถานะ TeamTalk บน Linux จริง

## เพิ่มเติมใน SNTalkBot 5.1.34: จบเพลงและปิดไมค์

ใน TTMediaBot เส้นทาง `_handle_track_finished()` ส่งต่อเพลงในคิวทันที; เมื่อไม่มีเพลงถัดไป `stop()` จะล้าง state และ `TTPlayerConnector` รับสถานะ Stopped เพื่อปิด TeamTalk voice transmission. มี watchdog ตรวจเวลาที่ไม่มี PCM เพื่อกู้การเล่นที่ค้างด้วย ใน SNTalkBot เราคง MPV/SQLite เดิม แล้วเพิ่ม watchdog สังเกต `idle-active` และ `time-pos` พร้อม generation/dedup guard ก่อนเรียก callback เดิม; เมื่อจบคิวจริงจัดการ voice, status และ now-playing ให้ครบ. ไม่ย้าย FFmpeg/PCM หรือระบบคิวของ TTMediaBot มาแทน

การตรวจยืนยันนี้ทำจากซอร์ส ZIP และ Unit tests เท่านั้น ยังต้องทดสอบการเปลี่ยนเพลงและสถานะ TeamTalk SDK บนเซิร์ฟเวอร์จริง

ตรวจซอร์สในไฟล์แนบ `TTMediaBot_v2.3.5.zip` จริง ไม่ได้ติดตั้งหรือเรียกใช้งานบอทอ้างอิงบน TeamTalk เซิร์ฟเวอร์จริง หมายเหตุ: `TTMediaBot/bot/app_vars.py` ภายใน ZIP ระบุ `app_version = "3.2.4"` แม้ชื่อ ZIP เขียน `2.3.5`; ใช้โค้ดจริงใน ZIP เป็นหลัก

| ประเด็น | TTMediaBot ตามไฟล์แนบ | SNTalkBot 5.1.33 | การตัดสินใจ |
| --- | --- | --- | --- |
| ค้นหา YouTube | `bot/services/yt.py` ใช้ `VideosSearch` จำกัด 4 ผล | `bot/player.py` มีค้นหา 50 ผล | **นำแนวคิดมา:** ค้นผลแรก 1 รายการเพื่อเริ่มก่อน แต่เติมผล 50 ที่เหลือแบบ background หลังเริ่มเล่นแล้ว |
| ค้นหา YouTube Music | `bot/services/ytm.py` ค้นเพลง 1 รายการ | ค้น 20 ผลและ fallback เป็น URL เพลงจาก YouTube | **นำแนวคิดมา:** เริ่มจาก 1 ผล เติมครบ 20 หลังเริ่ม และรักษา `music.youtube.com` กับ Cookie policy |
| การเปลี่ยนเพลง | `QueueManager` ใช้ `deque`, `_handle_track_finished()` ส่งต่อการเล่นทันที | Queue Mode ใช้ SQLite-backed queue, ลำดับ FIFO และ retry แยกกรณี | **คงของเรา:** ป้องกัน duplicate end/retry และคิวข้าม restart; รอบ 5.1.32 prefetch เฉพาะเพลงถัดไป |
| Prefetch | ใช้ dynamic `Track.url`, timer เตรียมก่อนจบประมาณ 120 วินาทีเมื่อทราบ duration | Cache ของ yt-dlp พร้อมตรวจ signed URL expiry และ TTL 30 นาที | **คงของเรา:** ดึงเพลงถัดไปเร็วตั้งแต่เพลงปัจจุบันเริ่มเพราะเหมาะกับเพลงสั้น; ยังไม่ใช้ timer ที่อาจพลาดเพลงสั้นหรือคลิปไม่มี duration |
| เครื่องเล่น | FFmpeg decode เป็น PCM 48k stereo แล้วส่งตรงผ่าน TeamTalk SDK, เน้น Windows | `python-mpv` / PulseAudio virtual sink บน Linux/Docker | **ไม่แทนที่:** ต้องเปลี่ยนโครงสร้างเสียง/SDK และทดสอบ Server/Docker ใหม่; เสี่ยงต่อการเล่นที่ปัจจุบันใช้งานได้ |
| อาการเสียงค้าง | มี watchdog นับเวลาที่ไม่มี PCM และ retry เริ่มต้น | มี MPV `END_FILE`/error handling และ queue recovery | **บันทึกไว้พิจารณา:** ต้องวัด event/output ของ MPV ก่อนสร้าง watchdog ไม่ใช่คัดลอกกลไก PCM ที่ใช้ไม่ได้โดยตรง |
| yt-dlp และการเชื่อมต่อ | ตั้ง timeout การค้นหา/ดึงข้อมูล, retry, streaming ผ่าน downloader | `yt-dlp` ดึง URL, MPV โหลดแยก, รองรับ cookies 18+ | **คงของเรา:** ไม่ตัด cookie-first หรือ retry fallback; เก็บ timings สำหรับระบุที่ช้า แล้วจึงเลือก timeout ที่เหมาะสม |
| แพลตฟอร์มอื่น | `Streamer` แยก Service ที่รู้จัก + fallback และ HTTP/RTMP/RTSP | yt-dlp รองรับลิงก์ทั่วไป รวม radio/webpage fallback และ URL/playlist | **ไม่จำกัดเพิ่ม:** เส้นทางใหม่ปรับเฉพาะคำสั่งค้นหา `p`/`pm`; URL ของบริการอื่นยังเข้าทางเดิม |

## ข้อควรระวังด้านพฤติกรรม

- การดึงผลแรกอย่างเดียวลดงานค้นหาบน critical path แต่ **ไม่ได้ทำให้ yt-dlp หรือ MPV สั่งเล่นใน 0 ms** เพราะต้องขอ stream URL และบัฟเฟอร์เสียงจากเครือข่ายจริง
- ระหว่างโหลดทางเลือกครบ 50/20 รายการ การเลือกผลอื่นอาจยังมีเพียงผลแรกชั่วคราว เมื่อโหลดเสร็จแล้วจึงเลือกต่อได้ครบตามเดิม
- งานค้นหา background จะผูกกับ queue token หรือ search session เพื่อไม่ทับรายการของผู้ใช้คนอื่นและไม่ทับคำสั่งเพลงที่สั่งมาทีหลัง
- เพลง 18+ ยังคงผ่านกระบวนการ cookie-first; ไม่ให้ข้ามการยืนยันอายุด้วยการสลับกลับเป็น anonymous
- ไม่มีการคัดลอก FFmpeg player หรือส่วนของซอร์สจาก TTMediaBot มาแทนคลาส Player ของเรา มีเพียงการนำหลักการลดงานก่อนเริ่มเล่นมาปรับใช้

## การวัดผลหลังเผยแพร่

1. ทดสอบเพลงแรกจากข้อความค้นหา `p` และ `pm` ทั้ง Queue Mode และโหมดปกติ
2. ทดสอบเพลงต่อเนื่องสั้น/ยาว, การกดเปลี่ยนผลค้นหาและเปลี่ยนคำค้นหาก่อน background search เสร็จ
3. ทดสอบ `u` ด้วยลิงก์เพลง/สตรีมจากแพลตฟอร์มอื่น, การเล่นเพลง 18+, และคำสั่งจัดการเพลงผ่าน Web Manager
4. เทียบ `Playback preparation took`, `Next-track prefetch took` กับเวลาที่เสียงออกจริง หากยังช้า ให้ตรวจ MPV/network buffering แยกจากเวลาค้นหา
