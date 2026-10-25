# วิธีใช้คุกกี้และล้างแคช

## ติดตั้งรุ่นนี้

อัปเดตทั้ง Bot 5.1.25, TTUHelper 1.5.9 และ Web Manager 1.1.24 ร่วมกัน ชุดนี้เป็น source package ยังไม่ได้ deploy/publish ไปเซิร์ฟเวอร์จริง ใช้ SNTalkBot-Release-Automation/Publish-SNTalkBot.cmd เพื่อ build/publish ตาม workflow เดิม หรือใช้ install.sh ของแต่ละ component หลังแทนที่ source ที่ต้องการ

ข้อมูลจริงเก็บนอก source: /opt/sntalkbot-bots/<instance>/, /var/lib/sntalkbot-web-manager และ /etc อย่าลบ directory เหล่านี้ระหว่างเปลี่ยน source

หลังอัปเดต image และ Helper ให้สร้าง container เดิมใหม่ผ่าน Restart/Update หนึ่งครั้ง เพื่อรับโค้ดใหม่และ mount /app/shared จากนั้นการเปลี่ยนคุกกี้ไม่ต้อง restart ทุกครั้ง เพลงที่กำลังเล่นจะจบต่อได้และ operation ใหม่อ่านไฟล์ใหม่

หากใช้ docker-compose เอง ให้ bind directory ส่วนกลางเป็น /app/shared แบบ read-only หรือกำหนด SNTALKBOT_SHARED_COOKIES_FILE ให้ตรงกับพาธที่ mount; หากไม่ mount บอตยังเลือก instance/bundled ได้ตามปกติ cks-all ยังคัดลอกไฟล์ให้ existing instances ด้วย

## คุกกี้เริ่มต้นและทุก instance

Super Admin > ระบบและอัปเดต > Cookies > อัปโหลด Netscape cookies.txt > บันทึกค่าเริ่มต้นและอัปเดตทุก Player/Full

- existing Player/Full ได้ไฟล์ใหม่, Manager-only ถูกข้าม
- เก็บ default ส่วนกลางที่ /opt/sntalkbot-bots/.shared/cookies.txt (หรือ TTU_BOTS_ROOT ที่ตั้งเอง)
- ตัวใหม่ที่สร้างผ่านเว็บหรือ TTUHelper ใช้ default นี้ก่อน fallback ของ image
- ใช้ cks <name> <file> หรืออัปโหลดราย instance เมื่อต้องการ session เฉพาะตัว; บอตเลือกไฟล์ที่ใหม่กว่าระหว่างส่วนกลาง/เฉพาะตัว/bundled
- หลังมี global upload ที่ใหม่กว่า ไฟล์ส่วนกลางจะชนะ local override เก่าตามนโยบายเลือกอันใหม่เสมอ
- ระบบวัดความใหม่จากเวลารับ/เวลาไฟล์ ไม่ใช้วันหมดอายุ และไม่สามารถพิสูจน์ว่าส่งออกจาก browser เมื่อใดหากไฟล์ไม่มีข้อมูลนั้น

## กำหนดเวลาล้างแคช

Super Admin > ระบบและอัปเดต > Cookies > เวลาล้างแคชเริ่มต้น

ค่าเริ่มต้น 00:00 / Asia/Bangkok ทุกวัน เลือก “นำไปใช้กับ Player/Full ที่มีอยู่ทั้งหมดด้วย” เพื่อแก้ตัวเดิม; หากไม่เลือก จะใช้กับตัวใหม่ที่สร้างผ่านเว็บ ค่าเริ่มต้นนี้เก็บใน SQLite ของ Manager; TTUHelper สร้างตรงจาก CLI ใช้ค่าใน config_default.ini ของ image

ราย instance: จัดการบอต > ตั้งค่าทั้งหมด > การเล่นเสียง > cache_cleanup_* บอทรุ่นใหม่ live apply ได้ทันที บอตเก่าต้องอัปเดตก่อน

หากปิดบอตตอนถึงเวลา จะ catch up หนึ่งครั้งเมื่อเปิดหลังเวลานั้น ไม่ทำซ้ำในวันเดิมแม้ restart; ปุ่มล้างทันทีทำเพิ่มได้โดยไม่เปลี่ยนเวลารายวัน

## วางเสียงตรงไหน

สร้าง/วางไฟล์ที่:

/opt/sntalkbot-bots/<ชื่อ-instance>/sounds/cache-cleanup.mp3

พาธใน container คือ /app/data/sounds/cache-cleanup.mp3 ตั้งค่าหน้าเว็บเป็น sounds/cache-cleanup.mp3 ใช้ .wav/.ogg หรือรูปแบบที่ libmpv รองรับได้เมื่อเปลี่ยนพาธให้ตรงกัน เว้นว่างเพื่อปิดเสียง

ถ้าเปลี่ยน TTU_BOTS_ROOT ให้แทน /opt/sntalkbot-bots ด้วยพาธจริง ในการ run รุ่นใหม่ Helper จะสร้าง sounds ให้ ไม่มีไฟล์เสียงก็ยังล้างแคชได้ ไม่ต้องใส่ไฟล์ไว้ในโฟลเดอร์ source เพื่อไม่ให้หายเมื่ออัปเดต image

เสียงแจ้งเล่นผ่าน TeamTalk ในห้องของบอต ใช้ output device เดียวกับเพลง จึงอาจได้ยินผสมกับเพลงที่เล่นอยู่ ไม่หยุด/ล้างรายการที่ผู้ใช้กำลังฟัง จำกัดเสียงแจ้งหนึ่งครั้งไม่เกิน 60 วินาทีเพื่อป้องกันไฟล์เสียค้าง

## Cache ต่างจาก Playlist/CQ

Cache คือ metadata/URL ที่ resolve ล่วงหน้าและไฟล์ media ชั่วคราว ล้างแล้วดาวน์โหลด/resolve ใหม่เมื่อจำเป็น

Playlist/Queue คือรายการที่ผู้ใช้เพิ่ม เก็บใน SQLite คำสั่ง CQ มีหน้าที่ล้างรายการนั้นเอง Daily cleanup และปุ่มล้างแคชไม่เรียก CQ ไม่ลบคิว ไม่ลบ favorites และไม่เปลี่ยนลำดับรายการ

ไฟล์ชั่วคราวที่กำลังเล่นจะถูกข้ามและลบภายหลังเมื่อเลิกใช้ ไม่ได้ล้างไฟล์ที่ผู้ใช้ดาวน์โหลดถาวร ไฟล์อัปโหลด channel, log, TTS cache หรือ cache ภายนอกระบบ media ทั้งหมดโดยกวาด directory

## Media Player ครบหรือยัง

มี search, YouTube/YouTube Music, URL/radio resolver, playlist/channel, queue persistence, favorites, playback retry/skip, mode, effects และ controls ทาง TeamTalk ตาม command audit เดิม ชุดนี้เพิ่มการจัดการแคช/คุกกี้ผ่านเว็บ ยังไม่อ้างว่าทุกฟีเจอร์ควบคุมจากเว็บได้ หรือเล่นได้กับทุกลิงก์/ทุกบัญชี

ดู PROJECT_STATUS.md สำหรับส่วนที่ใช้ SQLite อยู่แล้วและงานต่อไป เอกสารประกอบของทุก component อยู่ใน Document ของ component นั้น
