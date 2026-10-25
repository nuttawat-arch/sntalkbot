# ตรวจ config และเพิ่มแผงควบคุมบอต — 26 ตุลาคม 2026

รุ่น: Bot 5.1.26 / TTUHelper 1.5.10 / Manager 1.1.25

## สิ่งที่ตรวจพบ

1. ระบบ repair เดิมสร้าง parser ใหม่จาก template และเติม default เมื่อช่องของ config ปัจจุบันไม่ตรง schema เช่น server.hostname แทน server.address จึงสร้าง address=CHANGE_ME ได้ แม้ hostname จริงยังอยู่ในไฟล์ ทดสอบจำลองกรณีนี้ได้แล้ว
2. repair เดิมปรับค่าการเชื่อมต่อที่ผิดชนิด/ช่วงให้เป็น default และอาจสร้าง config ใหม่จาก legacy source หาก parser อ่านไฟล์ปัจจุบันไม่ได้ ค่าจาก legacy อาจเก่ากว่าค่าที่ผู้ใช้แก้ภายหลัง
3. restart เดิม stop container ก่อนเข้าเส้นทาง repair/run และ repair failure เป็นเพียง warning จึงเสียโอกาสรักษาบอตเก่าที่ยังเชื่อมต่ออยู่
4. ConfigHandler เก็บ parser ไว้ในหน่วยความจำและเขียนทั้งไฟล์เมื่อแก้การเล่นเสียง จึงอาจทับ server ที่เพิ่งเปลี่ยนจากเว็บด้วยสำเนาเก่า
5. การเขียน config โดยเปิดไฟล์โหมด w ไม่เป็น atomic ถ้า process หยุดระหว่างเขียน ไฟล์อาจว่างหรือไม่สมบูรณ์
6. หน้า config ที่เปิดค้างไว้สามารถส่งค่ารุ่นเก่ากลับไปทับค่าล่าสุดได้ แม้ใช้ atomic rename แล้ว เพราะไม่มี revision check
7. ข้อความประกาศที่สะท้อนกลับจากเซิร์ฟเวอร์ยังมีทางผ่านเข้า command dispatcher ของตัวเอง จึงเพิ่มการข้ามข้อความที่ผู้ส่งเป็น bot เอง ป้องกันประกาศที่มีคำอย่าง shutdown กลายเป็นคำสั่ง
8. queue_index=0 ถูกตีความเป็น -1 ใน snapshot/API บางจุด ทำให้เพลงแรกไม่ถูกแสดงเป็นรายการที่กำลังเล่น

ข้อ 1 เป็นการยืนยันเส้นทางทำข้อมูลผิดจาก source และ fixture ไม่ใช่การยืนยันเหตุการณ์บนเซิร์ฟเวอร์จริง เพราะไม่มี config/log จากเครื่องนั้นให้เทียบ

## วิธีแก้ในรุ่นนี้

- Normalize section และ alias การเชื่อมต่อที่รู้จักอย่างชัดเจน ก่อนเติมค่า optional; รักษา server/login/password/default room/channel password/license
- หาก host/port/username แบบ placeholder ไม่ถูกต้อง หรือ config อ่านไม่ได้ ให้ block โดยไม่เขียน CHANGE_ME ทับ และไม่เดาค่า login จากไฟล์เก่า
- ค่าที่ไม่รู้จักจากรุ่นอื่นถูกเก็บไว้ ไม่ลบทิ้งระหว่าง Restart/Update; feature flags ที่ถูกต้องไม่ถูกบังคับย้อนกลับตาม migration role เก่า
- preflight connection ก่อน stop ทั้งรายตัวและ batch update; คง queue preflight เดิม
- Docker managed instance จะไม่สร้าง config_default.ini อัตโนมัติเมื่อ config หาย
- Config writes ใช้ temporary file + fsync + atomic replace และใช้ lock file inode คงที่ร่วมกันระหว่าง Bot, Manager และ repair/recovery
- Bot reload parser ล่าสุดก่อนแก้เป็นราย section; config startup migrations เขียนแบบ atomic; เก็บ % ในรหัสผ่านเป็น literal
- ฟอร์ม config ใช้ revision hash ป้องกัน stale submit; HTTP 409 หมายถึงข้อมูลเปลี่ยนและยังไม่ได้เขียนทับ ให้รีเฟรชก่อนแก้ใหม่
- general runtime save ไม่แก้ default room/channel password และ Jail บันทึกเฉพาะรายการ jail_users
- แก้ queue index ศูนย์ให้ยังเป็นรายการแรกตามจริง

## กรณีตัวที่เสียไปก่อนหน้านี้

ติดตั้งทั้งสาม component ก่อน แล้วเปิด instance ใน Manager ด้วย Super Admin > “ตรวจและกู้ค่าการเชื่อมต่อจาก backup” > ตรวจหา backup ที่กู้ได้ > ยืนยันกู้ค่าการเชื่อมต่อ

ระบบค้นเฉพาะ backup ของชื่อ instance เดียวกันใน TTU_BOTS_ROOT/.migration-repair-backups/<เวลา>/<ชื่อ>/config.ini ตรวจว่า host/ports/username ใช้เป็น config ได้ แล้วนำกลับเฉพาะ identity fields ปัจจุบัน จึงคง playback settings ของตัวปัจจุบัน ไม่พิมพ์รหัสผ่านลง Job และเก็บก่อนกู้ไว้ใน Document/Recovery/<ชื่อ>/before-recovery.ini

เครื่องมือ CLI สำรอง:

    sudo python3 /usr/local/lib/ttuhelper/recover_instance_config.py --instance ชื่อบอต
    sudo python3 /usr/local/lib/ttuhelper/recover_instance_config.py --instance ชื่อบอต --apply

คำสั่งแรกเป็น preview ไม่มีการเขียนไฟล์ ถ้าใช้ TTU_BOTS_ROOT เอง ให้เพิ่ม --bots-root ตาม path จริง

หากไม่พบ backup ที่ใช้ได้ ต้องกรอกค่าจริงใน Manager > ตั้งค่าการเชื่อมต่อ ระบบไม่สามารถสร้างรหัสผ่านหรือ hostname ที่สูญหายแล้วขึ้นมาเอง และจะไม่กู้ทับ config ที่ตรวจว่าการเชื่อมต่อยังถูกต้อง

หลังตรวจค่าที่กู้แล้วจึง Restart บอตตัวนั้น เพื่อใช้การเชื่อมต่อที่กู้กลับมา ไม่ restart ทุก instance โดยอัตโนมัติจากปุ่มกู้

## แผงควบคุมใหม่

หน้า instance > “ควบคุมเพลงและประกาศ” ใช้ฟอร์มและปุ่ม ไม่ต้องพิมพ์คำสั่งบอต

### Player / Full

- ค้นหาและเล่น YouTube / YouTube Music
- เล่น URL เพลง วิทยุ หรือ Playlist และเพิ่ม Playlist
- พัก/เล่นต่อ หยุด เล่นตั้งแต่ต้น ก่อนหน้า/ถัดไป และผลค้นหาก่อนหน้า/ถัดไป
- ปรับระดับเสียง ความเร็ว เลื่อนไปวินาทีที่กำหนด เลือกเล่นเดี่ยว/ต่ออัตโนมัติ/ซ้ำ และเปิด/ปิด queue mode
- ดูคิว 250 รายการแรก พร้อมปุ่มเล่น/ลบรายรายการ; ใช้หมายเลขเลือกตำแหน่งนอกช่วงแสดงได้
- สลับคิว ล้างคิวด้วยช่องยืนยัน และจัดการ favorites
- เปิด/ปิด stereo, extra stereo, bass และ fade

### ประกาศ / Server Manager

- ส่งข้อความเข้าห้องที่บอตอยู่
- อ่านประกาศเป็นเสียงในห้องที่บอตอยู่ เมื่อเปิด TTS
- Manager/Full ส่งข้อความประกาศถึงทั้งเซิร์ฟเวอร์ได้โดยตรง ไม่ต้องเปิด scheduled Global Broadcast เพื่อส่งข้อความครั้งเดียว
- Manager/Full เลือกผู้ใช้ออนไลน์เพื่อ kick, ban หรือ move; ให้บอตเข้าห้องโดยระบุหมายเลขห้องและรหัสห้องได้

เสียงประกาศทำงานในห้องของบอต ไม่ใช่เสียงพร้อมกันทุกห้อง การประกาศข้อความทั้งเซิร์ฟเวอร์ต้องอาศัยสิทธิ์ TeamTalk ของบัญชีบอตด้วย

### ขอบเขตและสิทธิ์

- Super Admin จัดการทุก instance; tenant ใช้ได้เฉพาะ instance ที่เป็นเจ้าของ
- ทุก POST ตรวจ CSRF; API บอตตรวจ bearer token และ role allowlist ซ้ำ
- ใช้ typed action registry ไม่ส่งข้อความผ่าน CommandHandler และไม่เปิด SSH/exec/reboot จากแผงนี้
- งานควบคุมมีคิวจำกัด 8 งานและ worker เดียวเพื่อจัดลำดับ; งานค้นหา/เล่นที่ระบบเดิมทำต่อใน worker จะแสดงการรับคำขอและ feedback ภายหลัง
- API ตอบ accepted/dispatched คือรับหรือส่งงานให้บอตแล้ว ไม่ได้อ้างว่า YouTube เล่นสำเร็จหรือ TeamTalk ส่งถึงผู้รับแล้วก่อนมีผลจริง
- Poll สถานะ/feedback ทุก 3 วินาทีโดยไม่ย้ายโฟกัสหรือเขียนทับฟอร์มที่กำลังกรอก ปุ่มและช่องกรอกมี label; ยังต้องทดสอบ NVDA จริง
- ยังไม่เปิดทุกคำสั่งใน catalog เป็นปุ่ม เช่น SSH หรือ workflow บัญชีเฉพาะทาง; การตั้งค่าทั้งหมด Logs, lifecycle, Cookies, maintenance และ broadcast scheduler เดิมยังอยู่

## ผลการตรวจ

ดู TEST_REPORT_TH.md และ Document/TestResults รอบนี้ไม่ได้เชื่อมต่อ TeamTalk/YouTube ของผู้ใช้จริง จึงไม่อ้างว่าไม่มี error ได้ทุกสภาพแวดล้อม การกู้ backup ตรวจโครงสร้าง config เท่านั้น ไม่ได้ทดลอง login ด้วยรหัสผ่านนั้น
