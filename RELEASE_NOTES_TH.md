# SNTalkBot 5.1.15 — Windows Publish Policy Hotfix

- ไม่มีการเปลี่ยน playback/runtime ของบอตจาก 5.1.14; คง API-only realtime, Central Global Broadcast, 121 canonical commands / 52 aliases และ SQLite state hotfix เดิมทั้งหมด
- รุ่น ecosystem นี้จับคู่กับ Release Automation 5.1.15 และ Web Manager 1.1.17 เพื่อให้ Windows Publisher ตรวจเฉพาะ portable gates แล้วเลื่อน Linux-only runtime validation ไป `server_verify.sh` บน production host ตามนโยบาย Publish-first เดิม
- Linux final acceptance ยังคงต้องรัน `SNT_SERVER_VERIFY_STRICT=1 bash /tmp/sntalkbot-server-verify.sh` หลังติดตั้ง/อัปเดต service
