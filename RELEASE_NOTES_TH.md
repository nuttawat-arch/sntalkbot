# SNTalkBot 5.1.17 — Ecosystem Broadcast Correction Release

- SNTalkBot runtime/audio/command behavior คงจาก 5.1.16; รุ่นนี้ sync เลข release กับ Web Manager 1.1.19 ที่แก้ Global Broadcast composer และ random-without-replacement scheduler ให้ตรงพฤติกรรมที่ต้องการ
- คง 121 canonical commands / 52 aliases, API-only realtime, Queue/persistent state และ audio effects จาก 5.1.16 โดยไม่รื้อระบบเดิม

# SNTalkBot 5.1.16 — Audio Effects Modernization

- คงคำสั่ง `3d`, `3d2`, `bass` และ config key เดิมเพื่อ compatibility แต่แก้ filter chain ให้ใช้ FFmpeg/libavfilter ปัจจุบันผ่าน mpv อย่างถูกต้อง
- `3d` ใช้ Stereo Widen parameters ปัจจุบัน (`delay/feedback/crossfeed/drymix`) แทน legacy `drytx/dryrx` ที่ FFmpeg ไม่รองรับ
- `3d2` ระบุความหมายให้ถูกว่าเป็น Extra Stereo ไม่ใช่ Echo และใช้ preset ที่ลดความรุนแรงจากค่า legacy
- `bass` ใช้ FFmpeg Bass/Lowshelf ผ่าน `lavfi` พร้อมลด boost จาก preset เก่าเพื่อช่วยลดความเสี่ยง clipping
- ไม่บังคับ `scaletempo2` ตลอดเวลาอีกต่อไป; mpv เป็นผู้จัดการ pitch correction อัตโนมัติเมื่อเปลี่ยน playback speed ตาม behavior ปัจจุบัน

# SNTalkBot 5.1.15 — Windows Publish Policy Hotfix

- ไม่มีการเปลี่ยน playback/runtime ของบอตจาก 5.1.14; คง API-only realtime, Central Global Broadcast, 121 canonical commands / 52 aliases และ SQLite state hotfix เดิมทั้งหมด
- รุ่น ecosystem นี้จับคู่กับ Release Automation 5.1.15 และ Web Manager 1.1.17 เพื่อให้ Windows Publisher ตรวจเฉพาะ portable gates แล้วเลื่อน Linux-only runtime validation ไป `server_verify.sh` บน production host ตามนโยบาย Publish-first เดิม
- Linux final acceptance ยังคงต้องรัน `SNT_SERVER_VERIFY_STRICT=1 bash /tmp/sntalkbot-server-verify.sh` หลังติดตั้ง/อัปเดต service
