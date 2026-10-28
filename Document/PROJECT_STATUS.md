# sntalkbot 5.1.43

## รอบ 29 ต.ค. 2569: Full Player Audit / Related-Radio Prewarm / Audio-Ready Announcements

- **DONE (full Player audit):** ตรวจ Player subsystem ครบเส้นทาง search/discovery -> resolver -> stream cache/prefetch -> MPV/PulseAudio -> TeamTalk voice -> terminal events -> Queue/Related Radio -> Player TTS รวมทุก `play_stream()` call site, Docker audio dependencies, config migration และ regression gates.
- **DONE (เพลงลำดับหลังช้า):** พบว่า normal M2/Autoplay เล่นจริงจาก `radio_candidates` แต่ 5.1.42 prefetch ปกติยังอุ่น `search_results`/active list เป็นหลัก. เมื่อเข้าสู่ Related Radio ต่อเนื่อง รายการที่ autoplay จะใช้จริงจึงอาจยังไม่ถูก resolve และเพลงลำดับ 4+ ต้องทำ network work ตอน handoff. 5.1.43 prewarms Related Radio ระหว่างเพลงปัจจุบันและ prefetch candidate ตัวแรกที่ autoplay จะ consume จริง; ทุก radio item จะอุ่น successor ต่อทันที.
- **DONE (TTS ก่อนเพลงดัง):** `play_stream()` return/START_FILE ไม่ได้พิสูจน์ว่า audio sample เริ่มไหล. เพิ่ม `PLAYBACK_RESTART` + time-pos fallback เป็น audio-ready generation signal และ Player TTS `Now playing` จะเข้าคิวเมื่อ generation ปัจจุบัน ready แล้วเท่านั้น; stale generation/timeout จะไม่ประกาศหลอก.
- **DONE (MPV latency policy):** คืน `audio-buffer` baseline จาก project override 0.5s เป็น 0.2s และมี one-time migration สำหรับ config เดิม; ไม่บังคับ `audio-stream-silence=yes` บน virtual PulseAudio sink อีกต่อไป โดยคง env `SNTALKBOT_MPV_KEEP_AUDIO_OPEN` เป็น explicit escape hatch. 48 kHz/stereo/s16, gapless, cache และ resolver policy เดิมยังอยู่.
- **DONE (readiness race/deadlock):** เปลี่ยน end/readiness lock เป็น `RLock` เพราะ watchdog สามารถ mark audio-ready ขณะถือ lock เดียวกัน; reject late `PLAYBACK_RESTART` ที่มาก่อน START_FILE ของ generation ปัจจุบัน และสร้าง readiness event แบบ defensive สำหรับ restored/test instances.
- **DONE (Queue/normal preservation):** คง 5.1.42 queue ownership, clean EOF fast path, immediate MPV -13 retry และ public-fast -> cookie-aware stable fallback โดยไม่ย้อน regression ที่ทำให้ Queue/normal เดินต่อเร็ว.
- **VLC evaluation:** Linux/Debian สามารถใช้ LibVLC/PulseAudio แบบ headless ได้ แต่ latency ที่พบรอบนี้มาจาก orchestration เหนือ engine. ไม่เพิ่ม VLC เป็น default backend ใน 5.1.43 เพราะจะเพิ่ม dependency/backend surface และยังต้องแก้ resolver/prefetch/TTS เดิม; เก็บเป็น optional A/B transport ในอนาคตหาก live trace หลัง 5.1.43 ยังชี้ว่า MPV transport เองเป็นคอขวด.
- **DONE (offline QA):** full package tree ผ่าน Unit tests 143/143 และ `python tools/validate_project.py` ครบ รวม Related Radio prewarm priority, audio-ready TTS, stale PLAYBACK_RESTART, reentrant readiness lock, legacy buffer migration และทุก release contract เดิม.
- **DOING (live QA):** ทดสอบ normal M2/Autoplay อย่างน้อย 6-10 เพลงต่อเนื่องและ Queue 5+ เพลง. PLAYTRACE ควรมี `radio_warm_schedule/radio_warm_done/radio_prefetch_schedule` ก่อน handoff และ `audio_ready` ก่อน `track_announce_queued`. หากเพลงใดยังมีเสียงมาช้า ให้ส่งช่วง PLAYTRACE ของ generation นั้นเพื่อแยก resolver/prefetch กับ MPV transport โดยตรง.

## รอบ 29 ต.ค. 2569: Normal Autoplay Ownership / Fast Stable Retry

- **DONE (live trace root cause):** ในโหมดปกติหลัง `q` ถูกปิด ยังมี `queue_index=0`/queue item ค้างได้. เมื่อเพลงปกติจบ 5.1.41 ตรวจเพียงว่ามี queue current จึงเข้า Queue EOF fast path, consume queue ค้าง และ return ก่อน normal Related Radio/Autoplay. ผู้ใช้จึงเห็นสถานะว่างจนกด `n` เอง.
- **DONE (ownership fix):** Queue EOF/error path ใช้ playback context (`kind=queue`) เป็น ownership ของเพลงปัจจุบัน ไม่ใช้ `queue_index>=0` เพียงอย่างเดียว. Queue takeover จากเพลงปกติเกิดได้เฉพาะเมื่อ `queue_mode=True` และมี pending item จริง. stale queue state จึงไม่แย่ง normal autoplay อีก.
- **DONE (q toggle state):** ปิด Q จะปล่อย stale queue index เมื่อเพลงปัจจุบันไม่ใช่ queue-context และเปิด Q ขณะ idle + มี pending queue จะ reserve/start item แรกอัตโนมัติ. Pending items ไม่ถูกลบทิ้งเพียงเพราะปิด Q.
- **DONE (first-queue latency):** MPV `-13` จาก direct URL retry ทันทีไม่รอ generic retry delay และ `stable_only`/background prefetch ใช้ public-fast no-cookie yt-dlp ก่อน full cookie-aware recovery. Restricted/18+ media ยัง fallback ไป full cookie-aware extractor.
- **DONE (regression):** เพิ่ม tests สำหรับ normal EOF ที่มี stale queue index, ปิด Q กลาง queue-context, immediate `-13` retry และ stable-fast public->full fallback.
- **DONE (offline QA):** Complete Package 5.1.42 ผ่าน Unit tests 138/138 และ `python tools/validate_project.py` ครบ รวม normal autoplay with stale queue index, queue ownership after q off, immediate MPV -13 retry และ stable-fast public->full fallback. **DOING (live QA):** normal M2/Autoplay ต้องต่อเพลง 2 เองหลัง q off และ Queue เพลงแรกต้องไม่มี dead-air retry 2 วินาที.

## รอบ 29 ต.ค. 2569: Fast First Track Validation / Deep Bass Recovery

- **DONE (live trace root cause):** โหมดปกติบางเพลง resolve direct URL ได้ภายใน ~0.1–0.2 วินาทีและ MPV START_FILE สำเร็จ แต่ภายหลังจบด้วย error `-13` หลังหลายวินาที ก่อน retry แบบ stable จะใช้เพิ่ม ~10–16 วินาที. ปัญหาความรู้สึกว่าเพลงแรกช้าจึงมาจาก unvalidated direct stream มากกว่า search metadata.
- **DONE (cold-start fix):** direct YouTube candidate ต้องผ่าน streamed Range probe แบบสั้นก่อนชนะ resolver; direct path แข่งกับ no-cookie public yt-dlp ที่ timeout/retry สั้น และใช้ full cookie-aware resilient extractor เฉพาะเมื่อ fast paths ทั้งคู่ล้ม. direct cache ที่ probe/retry fail ถูก invalidate.
- **DONE (Queue preservation):** ไม่เปลี่ยน clean Queue EOF fast path/stable prefetch ของ 5.1.40; เพลง 2/3 ยังคงใช้ background stable yt-dlp stream info + headers เพื่อรักษา handoff ที่เร็วและเสถียร.
- **DONE (Bass recovery):** ย้อนตรวจรุ่นแรกพบ Bass เดิมเน้นราว 50 Hz (+15 dB) ขณะที่รุ่นหลังย้ายเป็น +6 dB ที่ 90 Hz. 5.1.41 คืนคาแรกเตอร์ deep bass ที่ 55 Hz แต่เพิ่ม -4 dB headroom และ `alimiter` ป้องกัน clipping: `volume=-4dB,bass=g=10:f=55:w=0.5,alimiter=limit=0.97:attack=5:release=80:level=0`.
- **DONE (offline QA):** Complete Package tree ผ่าน Unit tests 133/133, `python tools/validate_project.py`, และ FFmpeg runtime parse ของ Bass chain จริง.
- **DOING (live QA):** ทดสอบ normal-mode cold start หลายเพลง โดย PLAYTRACE ควรเห็น `direct_probe valid=true` ก่อน direct win หรือ `public_ytdlp` win เมื่อ direct ไม่ผ่าน; ทดสอบ Bass ที่ volume ใช้งานจริงทั้ง Bass เดี่ยวและร่วม 3D/Extra Stereo.

## รอบ 29 ต.ค. 2569: Queue EOF Fast Path / Stable Prefetch / MPV -13 Recovery

- **DONE (live trace root cause):** Queue เพลงแรกจบด้วย MPV EOF จริงและ `cog_playback_end_enter` ถูกเรียก แต่ 5.1.39 ไม่ถึง `cog_playback_end_state/queue_advance_schedule`; manual `n` จึงทำให้คิวเดินทันที. แก้โดยให้ clean Queue EOF ข้าม generic retry/cancel markers และ consume current -> schedule next โดยตรงหลัง Player generation dedupe แล้ว.
- **DONE (stream stability):** เพลง Queue ถัดไปที่ prefetch จาก lightweight direct YouTube endpoint สามารถ `START_FILE` แล้ว MPV จบด้วย error `-13`; เปลี่ยน background prefetch ให้ใช้ cookie-aware yt-dlp stream metadata/headers เป็น authoritative source และใช้ direct endpoint เป็น fallback เท่านั้น.
- **DONE (retry):** retry หลัง asynchronous MPV error บังคับ `stable_only=True` เพื่อ re-resolve ด้วย yt-dlp ไม่ให้ direct resolver ที่เพิ่ง fail ชนะซ้ำ.
- **DONE (observability):** playback executor future มี done-callback รายงาน `playback_worker_error` เพื่อไม่ให้ exception ใน worker หายเงียบ; PLAYTRACE queue_index แสดง 0 ถูกต้องแล้ว.
- **DONE (offline QA):** Complete Package 5.1.40 ผ่าน Unit tests 129/129 และ `python tools/validate_project.py` ครบ รวม live-trace regression ของ stale terminal cancel, clean Queue EOF fast path, stable retry, stable prefetch และ playback-worker diagnostics. **DOING (live QA):** Queue 3+ เพลงต้อง auto-advance โดยไม่กด `n`; MPV -13 ต้อง retry stable อัตโนมัติ; normal mode ยังใช้ fast direct resolver เป็น cold-start optimization.

## รอบ 28 ต.ค. 2569: Queue Trace / Terminal Readiness / Player Runtime Diagnostics (5.1.39 source)

- **DONE (runtime evidence):** ผู้ใช้ publish 5.1.38 สำเร็จจริง: validator ผ่าน, Docker `5.1.38` และ `latest` ใช้ digest เดียวกัน, ZIP/เว็บไซต์สำเร็จ และ tag `v5.1.38` ถูก push. ปัญหาที่เหลือจึงเป็น Player runtime/Queue behavior ไม่ใช่ deployment mismatch.
- **DONE (Queue root-cause hardening):** permanent `idle-active`/`eof-reached` จาก 5.1.38 มี race ใหม่ได้ หาก property terminal ของเพลงเก่าค้างหลัง `_arm_end_detection()` ของเพลงใหม่. เพิ่ม `_terminal_generation_ready()` ให้ property terminal ทำงานเฉพาะเมื่อ generation ปัจจุบันเคย START_FILE, active หรือมี time-pos แล้ว; ค่า terminal เก่าจึงไม่สามารถจบเพลงใหม่ก่อนเริ่ม.
- **DONE (missed START_FILE recovery):** watchdog EOF ไม่บังคับ `_watchdog_seen_start` อย่างเดียวอีกต่อไป; generation ที่เห็น active/time-pos แล้วสามารถจบผ่าน `eof-reached` ได้แม้ START_FILE callback หาย.
- **DONE (observer lifetime):** ลบ code path ที่ `stop_transport()` หรือ radio playback อาจถอด/ลงทะเบียน `idle-active` ซ้ำ. Terminal property observers เป็น single permanent observers ตลอดอายุ Player.
- **DONE (observability):** เพิ่ม bounded `PLAYTRACE` ring 500 เหตุการณ์ + stdout JSON ต่อ instance โดยไม่บันทึก cookies/auth headers/full URLs. Trace ครอบคลุม arm, resolver race winner, prefetch begin/end, MPV START/END, idle/eof property, watchdog, terminal dispatch/drop, queue enqueue/play/prefetch/advance, Cog playback-end และ manual next.
- **DONE (debug workflow):** instance ใดกำลังทดสอบให้ใช้ `sudo ttuhelper logs <name>` แล้วส่งช่วง `PLAYTRACE` ตั้งแต่ก่อนเริ่มเพลง 1 จนหลังเพลงจบ/ค้าง. เพราะ TTUHelper logs อ่าน Docker container ของ instance ชื่อนั้นโดยตรง จึงไม่ปนบอตอื่น.
- **DONE (offline QA):** Complete Package 5.1.39 ผ่าน Unit tests 127/127 และ `python tools/validate_project.py` ครบ รวม stale terminal property, missed START_FILE recovery, permanent observer และ PLAYTRACE validator. **DOING (live QA):** Queue 3+ เพลง โดยปล่อยจบเองอย่างน้อย 2 handoff และเปรียบเทียบกับ manual `n` จาก PLAYTRACE เดียวกัน.

## รอบ 28 ต.ค. 2569: Redundant EOF / Resolver Race / Fast Discovery (5.1.38 source)

- **DONE (runtime evidence):** 5.1.37 ถูก publish จริงแล้ว: Docker tag `5.1.37` และ `latest` เป็น digest เดียวกัน, ZIP/เว็บไซต์สำเร็จ, tag `v5.1.37` ถูก push และ ServerManager broadcast แจ้งรุ่นใหม่ จึงตัดสมมติฐานว่า instance เห็น source เก่าออกจาก root cause รอบนี้.
- **DONE (reference audit):** เปิดซอร์ส TikTok Music Player ที่ผู้ใช้อัปโหลดจริง: VLC ผูก `MediaPlayerEndReached -> play_next` บน daemon thread, `MediaPlayerPlaying` เรียก prefetch เพลงถัดไป, และ queue เริ่ม prefetch ตั้งแต่ item ยัง Waiting. YouTubeService ใช้ flat yt-dlp search แบบเบา (socket timeout 12s, retries/extractor retries 2) และ cache metadata; TTMediaBot reference แยก search ออกจาก full stream extraction และใช้ timeout 5s.
- **DONE (root cause - auto next):** 5.1.37 ลงทะเบียน MPV END_FILE ได้จึงไม่เปิด idle observer แบบถาวร; production สามารถลงทะเบียน callback สำเร็จแต่พลาด delivery ระหว่าง remote-stream handoff ได้ ทำให้ callback queue ไม่เกิด แม้ manual `n` จะใช้ queue state machine เดียวกันแล้วเล่นเพลงถัดไปได้.
- **DONE (fix - terminal redundancy):** เปิด permanent `idle-active` และ `eof-reached` observers ตลอดเวลา ควบคู่ END_FILE + watchdog; ทุกสัญญาณรวมที่ `_dispatch_end_once()` จึง dedupe ได้และไม่มี terminal signal ตัวเดียวเป็น single point of failure. intentional stop ไม่ unobserve idle อีกต่อไป.
- **DONE (root cause - first track):** fast resolver 5.1.37 ทำงานแบบ serial ก่อน yt-dlp; ถ้า YouTube คืน cipher-only/no direct URL จะเพิ่ม timeout เข้า cold start. Text search ยัง cookie-first และใช้ retry/timeout แบบ playback หนักกว่าตัวอ้างอิง.
- **DONE (fix - first track):** direct resolver กับ cookie-aware yt-dlp แข่งพร้อมกันและใช้ผล playable ตัวแรก; cold search ขอผลแรกเพียง 1 รายการแล้วเติมรายการเต็ม background; metadata search ใช้ public/no-cookie ก่อน cookie fallback และ flat-search timeout/retry จำกัด 12s/2 ครั้ง โดย playback 18+ ยัง cookie-first ตามเดิม.
- **DONE (offline QA):** complete-package test tree ผ่าน Unit tests 125/125 และ `python tools/validate_project.py` ผ่านครบ รวม regression ของ eof-reached without END_FILE, permanent idle observer, one-result cold start, resolver race และ prefetch-lock isolation.
- **DOING (live QA):** ต้อง publish 5.1.38 แล้ววัด `p`/`pm` เพลงแรก, Queue 3+ เพลงจนจบเองหลายรอบ, manual `n`, 18+ cookie, และ log terminal signal บน Docker/TeamTalk จริง. ถ้ายังช้ากว่า reference มาก ให้พิจารณาแยก search backend แบบ `VideosSearch`/YTMusic API เป็นขั้นถัดไป ไม่ย้อนกลับไปเพิ่ม timeout/watchdog แบบสุ่ม.

## รอบ 28 ต.ค. 2569: Realtime Audio Handoff / Fast Resolver / Reference Player Audit (5.1.37 source)

- **DONE (reference audit):** ตรวจไฟล์ที่ผู้ใช้อัปโหลดรอบนี้จริง: TikTok Live Reader/Music Player ใช้ VLC `MediaPlayerEndReached` ส่ง `play_next()` ทันทีและ prefetch ตอน `MediaPlayerPlaying`; TT Utilities ใช้ MPV 48 kHz/stereo/s16, gapless audio, connection keepalive, direct YouTube resolver + cache แล้วค่อย fallback yt-dlp; TTMediaBot ใช้คิว/event-driven handoff และ search หน้าแรกจำนวนน้อย.
- **DONE (queue start):** Queue เปิด TeamTalk voice transmission **ก่อน** `play_stream()` เพื่อไม่ให้ MPV ปล่อย sample แรกเข้า PulseAudio ก่อน TeamTalk เริ่มส่งเสียง.
- **DONE (natural handoff):** จบเพลงตามธรรมชาติไม่สั่ง `stop_transport()` ซ้ำเมื่อ transport idle แล้ว; manual next/select ยังหยุดเพลงเดิมตามปกติ. ทำให้ MPV gapless/output path มีโอกาสคงอุปกรณ์เสียงไว้ระหว่างเพลง.
- **DONE (audio format):** Linux/PulseAudio path ล็อก 48 kHz / stereo / s16 ให้ตรงกับ null sink ของโปรเจกต์, เปิด gapless และ cache/reconnect ที่เหมาะกับ network audio; `audio-stream-silence` จำกัดเฉพาะ PulseAudio server path เพราะ MPV ระบุว่ามี side effects กับ timing.
- **DONE (first-track latency):** ลด initial search จาก 12 เหลือ 4 ผลตามแนว TTMediaBot แล้วเติม 50/20 ผลเดิมเบื้องหลัง; prefetch URL เดียวกันรอ foreground สูงสุด 120 ms.
- **DONE (fast YouTube path):** เพิ่ม bounded direct YouTube audio resolver + connection prewarm/keepalive/cache; จำกัด fast attempt ราว 1.4 วินาทีและถ้า login/age/content check required จะกลับ cookie-aware yt-dlp ทันที. generic URLs และ 18+ path เดิมยังอยู่.
- **DONE (MPV event race):** เมื่อ END_FILE พิสูจน์ entry ใหม่ได้ในช่วง START_FILE race จะ refresh active entry ID ก่อนตรวจ stale event ป้องกัน EOF/ERROR ที่เพิ่ง adopt ถูกทิ้งจาก local snapshot เก่า.
- **DONE (regression source):** เพิ่ม tests สำหรับ direct resolver/cache/restricted fallback, adopted MPV entry ID, no redundant stop ที่ natural queue handoff และลำดับเปิด TeamTalk voice ก่อน MPV play; ปรับ tests ของ initial search เป็น 4 ผล.
- **DONE (offline QA):** รันจาก complete package หลังประกอบ release จริงแล้ว: `python -m unittest discover -s tests -q` ผ่าน 123/123 และ `python tools/validate_project.py` ผ่านครบ; ระหว่าง QA พบและแก้ test fixture ของ staticmethod, `BotUtils.VERSION`, และ validator assumptions ของ 12-result/250ms ให้ตรง 5.1.37.
- **DOING (live):** ยังต้องทดสอบ Queue 3+ เพลง, manual Next หลายครั้งติดกัน, p/pm เพลงแรก, 18+ cookies, SoundCloud/Twitch/Vimeo/radio, speaking state และเก็บ `Playback preparation took` / `MPV start-file took` บน Docker/TeamTalk จริงหลัง publish Docker.
- **DESIGN (effects):** ไม่ย้าย backend ไป `vlc_libs` ในแพตช์ playback นี้. Portable `vlc_libs` ในตัวอย่างเป็นแนว Windows; Linux ควรใช้ system libVLC หากเลือก VLC. สำหรับ SNTalkBot ปัจจุบัน MPV + FFmpeg/lavfi รองรับ preset/effect chain ได้กว้างกว่าและไม่ต้องเพิ่ม player backend ใหม่; Web Manager preset จะทำเป็น allow-listed audio-only profile ต่อจาก playback validation.

## รอบ 27 ต.ค. 2569: MPV Native EOF / Retry Cancellation / Historical Player Audit (5.1.36 ยังไม่เผยแพร่)

- **DONE (หลักฐาน):** ตรวจต้นฉบับ `tt_utilities-main.zip` (`bot/player.py`, `bot/modules/player.py`) และ `TTMediaBot_v2.3.5.zip` รวมถึงซอร์ส Git baseline 5.1.27; สิ่งที่นัทเรียกว่า GT Unity น่าจะเป็น TT Utilities ที่แนบไว้ ไม่พบต้นฉบับชื่อ GT Unity โดยตรง จึงไม่อ้างว่าได้ตรวจตัวนั้นแล้ว
- **DONE (runtime evidence):** Publisher log ล่าสุดยืนยันว่าผู้ใช้เผยแพร่ SNTalkBot 5.1.35 ผ่าน Docker, ZIP เว็บไซต์ และ GitHub tag; บรรทัด ServerManager ใน log ยังบอกบาง runtime ใช้ 5.1.34 ตอนจบการเผยแพร่ จึงต้องยืนยัน Docker instance ที่กำลังเล่นจริงก่อนตีความผลทดสอบสด
- **DONE (root cause):** เส้นทางยกเลิก retry ขณะ `play_stream` ทำงานก่อนหน้านี้ไม่เรียก `_finish_loading_transition()` ส่งผล `loading_new_track=True` ค้างถาวร และ callback เพลงจบทุกเพลงหลังจากนั้นถูก defer; `_on_end_file_event` เดิมทิ้ง EOF/ERROR หาก `START_FILE` ยังไม่ถึง แม้ `playlist_entry_id` จะเป็นตัวใหม่ที่พิสูจน์ได้
- **DONE (fix):** ทำให้ retry หลังรออยู่บน playback executor เดียวกับ end/next/previous เพื่อไม่ให้ retry แข่ง stop/play กับเพลงที่ผู้ใช้เลือก; เคลียร์ `loading_new_track` เมื่อยกเลิก retry ระหว่าง extraction; ใช้ MPV entry ID กู้ EOF/ERROR ของเพลงใหม่เมื่อ START_FILE หาย และคงกรอง stale ID ของเพลงเก่า
- **DONE (finite stream recovery):** เพิ่ม MPV watchdog ตรวจว่าตำแหน่งเสียงหยุดนิ่งที่ท้ายเพลงจริง (`duration` ทราบ, ต่างไม่เกิน 0.35s, เคยมี progress, ไม่ pause/buffer และค้าง ≥3s) จึงแจ้ง EOF; live/unknown-duration ไม่ถูกข้ามจากเงื่อนไขนี้
- **DONE (handoff):** normal autoplay, repeat, collection, manual next/previous, sync-error callback และคำสั่ง restart/select/delete queue ส่งงานเล่นลง worker เฉพาะ ไม่เข้าคิวค้นหา/download; คง FIFO/SQLite/TeamTalk API เดิม
- **DONE (compatibility):** ไม่แก้โครงสร้าง DB, config, cookies, วิดีโอจำกัดอายุ 18+, MPV/PulseAudio output, การค้นหา 12 ผล, แพลตฟอร์มผ่าน generic yt-dlp และ Web Manager 1.1.29
- **DONE (offline QA):** Unit tests 118/118 ผ่าน รวม cancel-while-retry, missed START_FILE, EOF ที่เฟรมท้ายและ unknown-duration, normal autoplay priority; `tools/validate_project.py` ผ่าน (123 commands/role mappings, Python syntax, schema policy); `git diff --check` และ live QA รอตรวจขั้นสุดท้าย
- **DOING (Linux validation):** ทดสอบเพลง 3 เพลงต่อเนื่องหลายแหล่ง รวมเพลงสั้น/ยาว/คลิป 18+ และสถานะ speaking เมื่อหมดคิวบน instance ที่ยืนยันว่ารัน 5.1.36 แล้ว พร้อมเก็บเวลา `MPV start-file took` / `Playback preparation took` / `MPV watchdog recovered`
- **TODO:** ถ้ายังเงียบ ให้เก็บ log runtime ระหว่างเพลงเพื่อแยก yt-dlp network, MPV startup, PulseAudio output และ TeamTalk voice device; การทดสอบออฟไลน์ไม่รับรองการส่งเสียงจริง

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
