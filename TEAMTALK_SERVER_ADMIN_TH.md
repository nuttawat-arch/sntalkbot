# SNTalkBot — TeamTalk Server Administration (Development Draft)

พัฒนาต่อจาก Bot 5.1.27 / Web Manager 1.1.26 / TTUHelper 1.5.10 ยังไม่ได้เผยแพร่เป็น Release ใหม่

## แหล่งทางการที่อ้างอิง

- [BearWare TeamTalk SDK 5.22A — Client/Server Commands](https://www.bearware.dk/teamtalksdk/v5.22a/docs/C-API/group__commands.html)
- [Server Administration](https://www.bearware.dk/teamtalksdk/v5.22a/docs/C-API/group__server.html)
- [ServerProperties](https://www.bearware.dk/teamtalksdk/v5.22a/docs/C-API/struct_server_properties.html)
- [Channel](https://www.bearware.dk/teamtalksdk/v5.22a/docs/C-API/struct_channel.html)
- [UserAccount](https://www.bearware.dk/teamtalksdk/v5.22a/docs/C-API/struct_user_account.html)
- [TeamTalkPy source](https://github.com/BearWare/TeamTalk5/tree/master/Library/TeamTalkPy)

## ทำแล้วในซอร์ส

| การจัดการ | SDK function/event | ความสามารถผ่านเว็บ |
| --- | --- | --- |
| ตั้งค่า Server | `getServerProperties`, `doUpdateServer` | ชื่อ/MOTD, จำนวนผู้ใช้, จำกัด login, timeout, autosave |
| Save/Stats | `doSaveConfig`, `doQueryServerStats`, `onServerStatistics` | บันทึกค่าเซิร์ฟเวอร์และขอสถิติ |
| ห้อง | `getServerChannels`, `doMakeChannel`, `doUpdateChannel`, `doRemoveChannel` | สร้าง/แก้/ลบ (ห้ามลบ root, คง codec เดิม) |
| ผู้ใช้ | `doKickUser`, `doMoveUser`, `doJoinChannelByID` | เตะจากห้อง, ย้าย, ให้บอตเข้าห้อง; ของเดิมยังใช้ได้ |
| Operator | `doChannelOp` | มอบ/ถอนสิทธิ์ Operator |
| บัญชี | `doListUserAccounts`, `doNewUserAccount`, `doDeleteUserAccount`, `onUserAccount` | ดู/สร้าง/ลบ (ไม่ส่งรหัสผ่านกลับเว็บ; รายการสูงสุด 500) |
| Ban | `doListBans`, `doBanIPAddress`, `doUnBanUser`, `doBan`, `doUnbanUserEx`, `onBannedUser` | ดูการแบน, แบน/ปลดแบน IP หรือ username แม้ไม่ออนไลน์ |
| ผลคำสั่ง | `onCmdProcessing`, `onCmdError` | accepted → awaiting_server → confirmed/rejected พร้อมประวัติไม่มีอาร์กิวเมนต์ |

- เพิ่มคำสั่ง Manager/Full `ttadmin help` สำหรับ status/stats/save/accounts/bans/banip/unban/banuser/unbanuser/op/kickroom/name/motd (ต้องผ่าน `admin_only` และบัญชีบอตเป็น TeamTalk Administrator)
- Web Manager จำกัด Server/Channel/Account administration สำหรับ Web Super Admin เท่านั้น; ผู้ใช้แบบเจ้าของ instance ยังใช้ Player และ moderation เดิม
- ใช้ typed action allowlist ผ่าน loopback Bearer, Web CSRF และ owner checks; ไม่มี arbitrary shell/SDK reflection
- ไม่มี password, channel secret หรือ access token ใน JSON/history; callback บัญชีเดิมถูกปรับไม่ให้ส่งรหัสผ่านออกทางข้อความส่วนตัว
- ตรวจ revision ของ server/channel ก่อนแก้ไข ป้องกันฟอร์มเก่าทับค่าระหว่างบริหารหลายเครื่อง
- คำสั่ง `doSaveConfig` บันทึกเฉพาะห้องถาวรตามข้อกำหนด BearWare; แยกจากการ Save Config ของบอต

## ยังขาด (ไม่กล่าวอ้าง SDK parity 100%)

> หมายเหตุทางเทคนิค: TeamTalk SDK 5.22A ระบุว่า `TT_DoUpdateChannel()` ไม่ใช้ `szName`/`nParentID` ที่ส่งเข้ามา ดังนั้นไม่รองรับการเปลี่ยนชื่อหรือย้ายห้องด้วยฟอร์ม Update; บอตจะปฏิเสธคำขอเปลี่ยนชื่อที่ไม่มีผลจริง และเว็บแสดงชื่อแบบ read-only. การลบห้องมีผลต่อห้องย่อยและผู้ใช้ที่อยู่ภายในตามเอกสาร SDK.

1. UI โอน/ลบไฟล์ห้อง `doSendFile`, `doRecvFile`, `doDeleteFile` พร้อม path confinement และ limits
2. แก้ไขข้อมูลบัญชีเดิมโดยไม่เปลี่ยน/ล้างรหัสผ่าน, fields ขั้นสูง (init channel, notes, abuse prevention, audio limits, auto-operator)
3. สิทธิ์ transmit ACL / classroom / solo และ AudioCodec ของห้องอย่างปลอดภัย โดยเฉพาะเมื่อมีผู้ใช้ในห้อง
4. Bandwidth/server log events/advanced ServerProperties และการจัดการ server process/port ซึ่งไม่ใช่ client SDK command ทั่วไป
5. การสมัคร/ยกเลิก stream (`doSubscribe`/`doUnsubscribe`) และ file/video/desktop controls แบบเจาะจงผู้ใช้
6. ทดสอบ TeamTalk จริงบน Linux SDK, permission denial, reconnect, NVDA และ Browser ก่อนรับรอง production

## ตรวจสอบก่อนเผยแพร่

- Bot: `python3 -B tools/validate_project.py` และ `python3 -B -m unittest discover -s tests -q`
- Manager: `python3 -B tools/validate_web_manager.py` และ `python3 -B -m unittest discover -s tests -q`
- Helper: `python3 -B tools/validate_helper.py` และ `python3 -B -m unittest discover -s tests -q`
- ติดตั้งทั้งสามส่วนที่เวอร์ชันเข้ากันได้บน staging; ทดสอบทั้ง command success และ server rejection จริง
