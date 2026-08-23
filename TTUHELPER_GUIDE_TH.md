# คู่มือคำสั่ง TTUHelper

TTUHelper ใช้จัดการ SNTalkBot หลาย instance บน Linux ด้วย Docker โดยแต่ละ instance เก็บ config และข้อมูลของตัวเองแยกกัน

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `ttuhelper new` | สร้าง instance ใหม่ และเลือกโหมด Full / Player / Server Manager |
| `ttuhelper run <name>` | เริ่มบอตจาก config/data ของ instance นั้น |
| `ttuhelper stop <name>` | หยุดและลบ container แต่เก็บ config/data ไว้ |
| `ttuhelper restart <name>` | รีสตาร์ตบอตหนึ่งตัวโดยสร้าง container ใหม่ |
| `ttuhelper logs <name>` | ดูบันทึกการทำงานแบบสด กด `Ctrl+C` เพื่อออก |
| `ttuhelper ls` | ดูรายชื่อ instance ทั้งหมดพร้อมสถานะ running/stopped |
| `ttuhelper ps` | ดู container ที่ TTUHelper จัดการ พร้อมสถานะและ image |
| `ttuhelper start-all` | เริ่มทุก instance ที่มี `config.ini` |
| `ttuhelper stop-all` | หยุด container ทุกตัวที่ TTUHelper จัดการ โดยไม่ลบข้อมูลถาวร |
| `ttuhelper pull` | ดาวน์โหลด Docker image/tag ที่ตั้งไว้ |
| `ttuhelper update` | pull image ใหม่ แล้วอัปเดตเฉพาะ instance ที่กำลังรัน โดยรักษา config/data เดิม |
| `ttuhelper cks <name>` | แทนที่ `cookies.txt` ของ instance หนึ่งตัว |
| `ttuhelper cks-all` | ใส่ cookies ชุดเดียวให้ทุก instance |
| `ttuhelper limit <name>` | ตั้งข้อจำกัด CPU/RAM ของ instance มีผลหลัง restart |
| `ttuhelper edit <name>` | เปิด `config.ini` ของ instance ค่าเริ่มต้นใช้ `nano` |
| `ttuhelper path <name>` | แสดงตำแหน่งโฟลเดอร์ config/data ของ instance |
| `ttuhelper doctor` | ตรวจ Docker daemon, image, data root และค่าหลักของ helper |
| `ttuhelper version` | แสดงเวอร์ชัน TTUHelper |
| `ttuhelper help` | แสดงคำอธิบายคำสั่งทั้งหมด |

## ติดตั้ง

```bash
git clone https://github.com/nuttawat-arch/ttuhelper.git
cd ttuhelper
chmod +x install.sh ttuhelper.sh
sudo ./install.sh
sudo ttuhelper doctor
```

สร้างบอต:

```bash
sudo ttuhelper new
sudo ttuhelper run <ชื่อบอต>
```

ดู log:

```bash
sudo ttuhelper logs <ชื่อบอต>
```

อัปเดตบอตที่กำลังรันทั้งหมดโดยรักษาข้อมูลเดิม:

```bash
sudo ttuhelper update
```
