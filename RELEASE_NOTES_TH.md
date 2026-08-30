# SNTalkBot 5.1.21 — Playback Recovery + Visible Command Ingress

## แก้ปัญหาหลัก

- แก้ regression ที่ผู้ใช้เห็นว่า `p`, `pm` และการเล่น YouTube/YouTube Music เงียบหรือไม่เริ่มเล่นโดยไม่มีสาเหตุใน log
- `p <คำค้น>` กลับมาใช้ `ytsearch:` เป็นเส้นทางหลัก และมี YouTube Search URL เป็น fallback อิสระ
- `pm <คำค้น>` ยังคงเจตนา YouTube Music; ถ้า Music search extractor ว่าง จะ fallback หา video ID ผ่าน YouTube แล้ว canonicalize กลับเป็น `music.youtube.com/watch`
- yt-dlp Python API ชี้ Deno ที่ติดตั้งใน Docker image โดยตรง เพื่อไม่ให้ EJS/JavaScript runtime หายเพราะ PATH/environment
- ถ้า cookie ของ instance/default ล้าสมัยจน public YouTube ใช้ไม่ได้ จะ retry แบบ no-cookie หนึ่งครั้งโดยไม่ลบ/เขียนทับ cookie ของผู้ใช้
- เวลา `music.youtube.com` extraction ล้ม จะ retry canonical `youtube.com/watch?v=...` เป็น transport fallback โดยยังรักษา source intent/history เดิม

## Logging / diagnostics

- command ที่รับจริง (`p`, `pm`, `s`, `q`, ฯลฯ) แสดงใน console ก่อน dispatch แล้ว
- admin-only command แสดงชื่อคำสั่งแต่ redact arguments เพื่อไม่ให้ token/password หลุดใน log
- TeamTalk CUSTOM `typing` event ไม่ spam console อีก
- ถ้า Channel Input ปิดอยู่ command ในห้องจะถูก log ว่า `[ignored: Channel Input OFF]` แทนการหายเงียบ
- async search/play/enqueue failure จะมีสาเหตุใน console และตอบผู้สั่งแบบ private เมื่อ channel announcement ปิดอยู่

## คงพฤติกรรมเดิม

- 121 canonical commands / 52 aliases เท่าเดิม
- `select/c N` ยังเลือกตำแหน่ง Queue/Playlist เท่านั้น ไม่เลือก search result
- `pm` ยังเป็น YouTube Music; `p` ยังเป็น YouTube ปกติ
- Queue, SQLite/WAL, no-auto-stop, stale-END_FILE guard, one-retry playback policy, Telegram precedence และ live config policy ไม่ถูกรื้อ
