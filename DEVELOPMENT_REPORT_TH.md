# DEVELOPMENT REPORT — SNTalkBot 5.1.1

วันที่: 2026-08-24

## ปัญหาจากรอบก่อน
- Queue Mode ใช้ `search_results`/`current_search_index` ชุด global และ `,`/`.` แทน `queue[-1]` ทำให้ผู้ใช้หลายคนค้นหาต่อกันแล้วอาจเปลี่ยนเพลงผิดคิว
- source บางไฟล์เคยมี CRLF ซึ่งมีความเสี่ยงเมื่อรัน/แพ็กบน Linux

## การแก้ไข/ฟีเจอร์
- ผูก search session (`_search_results`, `_search_index`, `_search_source`) กับ queue item แต่ละรายการ
- เพิ่ม `. <queue_position>` และ `, <queue_position>` เช่น `. 34` / `, 34`; แบบไม่มีหมายเลขยังใช้ได้เหมือนเดิม
- เพิ่ม help, COMMANDS_TH, USER_GUIDE_TH และ Thai locale ให้ตรง syntax ใหม่
- เพิ่ม Linux LF-only validation

## การทดสอบรอบนี้
- Python compile / 124 command catalog / help-role-alias consistency / Linux LF checks ผ่าน
- เพิ่ม regression test multi-user queue search; พบ fixture เดิมถูก clear จาก test ก่อนหน้าและแก้ fixture ให้ restore normal search stateก่อนทดสอบ
- รัน validator ซ้ำหลังแก้ fixture แล้ว: queue regression ผ่าน, command-dispatch พิสูจน์ `. 34`/`, 34` ทั้ง Private และ Channel และ validator ทั้งชุดจบด้วย exit code 0

## ลบอะไรออก
- ไม่มี runtime feature เดิมถูกลบ; `,` และ `.` แบบเดิมยังคงทำงาน

## สถานะ
- Source implementation และ local final validator ผ่าน; รอ PublishFirst + strict Linux runtime verification
