# Command ↔ Action / Realtime Architecture Audit — SNTalkBot 5.1.20

## ผลการตรวจคำสั่ง

- Canonical commands: 121 = Common 21 + Player 51 + Server Manager 49; Full รวมทั้งสามฝ่าย
- Intentional short aliases: 52; aliases อยู่ใน mapping กลางและไม่สร้าง handler ซ้ำ
- validator parse `register_command()` ทุกจุดและบังคับให้ handler เป็น method จริงที่มี executable body; ห้าม command ที่ชี้ไป method หายหรือ `pass` อย่างเดียว
- reverse audit ตรวจ method ที่ตั้งชื่อ `handle_*_command`; ถ้าไม่มี command register ถึง method นั้น validator จะ fail. รอบ 5.1.13 ลบ dead `handle_help_list_command` และ `handle_tts_toggle_command` ที่ซ้ำกับ action จริงออกแล้ว
- runtime help และ `COMMANDS_TH.md` ต้อง match canonical set แบบ exact; validator จะ fail หากมีคำสั่งที่ถอดแล้วแต่ยังค้างในเอกสาร

## คำสั่งที่ถอดใน 5.1.13

- `rb`: action เดิมใช้ Random TTS scheduler ที่อ่าน `messages.txt`; เมื่อลบ data source/scheduler นี้แล้วจึงถอด command แทนการปล่อย command ที่ไม่มีความหมาย
- `bot`, `sbot`, `superbot`: ทั้งสามลงท้ายด้วย TeamTalk `MSGTYPE_BROADCAST` เหมือน `bm` และไม่ได้มี transport/scope แยกตามชื่อ จึงเป็น duplicate semantics ที่ทำให้ผู้ใช้เข้าใจผิด
- `bm` คงไว้เป็น manual broadcast action เดียวที่ตรงกับ TeamTalk transport จริง
- `globalbroadcast` / `gb` คงไว้เป็น Central Global Broadcast; `gb tts on|off` เปิดเสียงของข้อความส่วนกลางชุดเดียวกัน

## Action ที่ตั้งใจไม่มี TeamTalk command

- CRUD ข้อความ Central Broadcast อยู่ Web Manager Super Admin เท่านั้น เพราะเป็นข้อมูลส่วนกลางข้าม instance; การเพิ่ม command ใน TeamTalk จะเพิ่ม privilege surface และทำให้ tenant/instance ใด instance หนึ่งแก้ข้อมูลส่วนกลางได้โดยไม่จำเป็น
- instance lifecycle/restart jobs ที่ Web Manager สร้างหลัง Save Config ใช้ privileged bridge/TTUHelper ตามสิทธิ์ของ host; ไม่ทำ command ซ้ำเพราะ TeamTalk account ไม่ควรแทนสิทธิ์ระบบปฏิบัติการ
- HTTP `/v1/status` และ event endpoints เป็น machine-to-machine API บน loopback + Bearer token; ไม่ใช่คำสั่งผู้ใช้ จึงไม่มีเหตุผลเพิ่ม canonical command
- event hooks เช่น login/channel/status/playback END_FILE เป็น reaction ต่อ TeamTalk/mpv event โดยธรรมชาติ ไม่ควรมี command manual ที่ยิง event ปลอม

## Realtime / persistence contract

- Realtime/high-frequency: connection, users, room, media/playback, Voice TX, queue counters และ runtime health อยู่ RAM แล้วอ่านผ่าน loopback API; Web Manager fan-out ด้วย SSE
- Persistent mutable state ที่ต้องรอด restart อยู่ SQLite/WAL เช่น Queue, favorites, notification/offline-message state, timed moderation และ Central Broadcast message/rotation state
- Configuration/secrets ที่เปลี่ยนไม่ถี่ยังคงไฟล์ INI/conf/secret ตาม deployment contract และ Save Config ใช้ restart job เมื่อต้อง reload process
- ไม่มี production `runtime_status.json` หรือ `runtime/live/status*.json`; API unavailable ต้องแสดง unavailable ไม่ใช้ stale snapshot
- `favorites.json` ถูกอ่านเฉพาะ one-time migration จากรุ่นเก่าแล้วลบทิ้งหลังนำเข้า SQLite; ไม่ใช่ realtime writer
- JSON migration reports ของ TTUHelper เป็นรายงานงาน migration แบบ one-shot ไม่ใช่ runtime state
- Google TTS voice metadata cache เป็น cache ที่เปลี่ยนช้า ไม่ใช่ realtime status; จึงไม่อยู่ในเส้นทาง SSE/status และไม่เกิด write-per-event

## Performance rationale

การเก็บ state ที่เปลี่ยนถี่ใน RAM แล้วส่งผ่าน local HTTP/SSE ลด disk write amplification และ file-lock/contention โดยเฉพาะ playback progress/user activity. SQLite ใช้เฉพาะ state ที่ต้อง durable และมี transaction/WAL. การรวม broadcast ให้เหลือ data source/scheduler เดียวลด thread/timer ซ้ำและลดโอกาส duplicate delivery.
