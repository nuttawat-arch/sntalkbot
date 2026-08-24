# คู่มือ YouTube / YouTube Music cookies สำหรับ SNTalkBot 5

เอกสารนี้ใช้กับ **Player Bot** และ **Full Bot** เท่านั้น Server Manager Bot ไม่ต้องมี cookies ของ YouTube

## สรุปก่อนเริ่ม

SNTalkBot 5 มี **default YouTube cookies จากโปรเจกต์เดิม** ติดมากับ Player/Full เพื่อให้ผู้ใช้ทั่วไปเริ่มเล่น YouTube/YouTube Music ได้โดยไม่ต้องตั้ง cookie ก่อน ระบบเก็บต้นฉบับ default ไว้ที่:

```text
/app/defaults/cookies.txt
```

เมื่อ instance เริ่มครั้งแรก ถ้ายังไม่มีไฟล์ persistent ระบบจะคัดลอกเป็น:

```text
/app/data/cookies.txt
```

ถ้า `/app/data/cookies.txt` มีอยู่แล้ว ระบบ **ไม่ overwrite** ดังนั้นในอนาคตเมื่อคุณ export ชุดที่ใหม่หรือครบกว่า สามารถใช้ `ttuhelper cks` แทนไฟล์ชื่อเดิมได้เลย และการอัปเดต image จะรักษาไฟล์ persistent ที่คุณแทนไว้

Default cookie อาจหมดอายุหรือไม่พอสำหรับเนื้อหาที่ต้องล็อกอินทุกประเภท หากต้องใช้วิดีโอจำกัดอายุ playlist ส่วนตัว หรือสิทธิ์เฉพาะบัญชี จึงค่อย export cookie ของบัญชีที่มีสิทธิ์มาแทน

**cookie ที่คุณ export จากบัญชีของตัวเอง** ไม่ได้เก็บรหัสผ่าน Google เป็นข้อความธรรมดา แต่มี session credentials ที่อาจใช้ YouTube ในนามบัญชีคุณได้โดยไม่ต้องรู้รหัสผ่าน จึงต้องถือว่าไฟล์ส่วนตัวนี้เป็น secret ระดับเดียวกับรหัสผ่าน: ห้าม commit, ห้ามส่งในแชต และห้ามนำไปแทน `defaults/cookies.txt` ก่อน build/push image สาธารณะ

TTUHelper เก็บไฟล์ที่ผู้ใช้แทนเองไว้ใน persistent data ของ Player/Full แต่ละ instance; Server Manager ไม่ต้องรับ YouTube cookies

## วิธีที่แนะนำในการเลือก Browser Profile

ควรสร้าง **browser profile แยกสำหรับ SNTalkBot** แล้วล็อกอินเฉพาะบัญชี YouTube ที่ใช้กับบอต เหตุผลคือคำสั่ง `--cookies-from-browser` สามารถ export cookies ของเว็บไซต์อื่นใน profile เดียวกันได้ด้วย ถ้าใช้ profile หลัก ไฟล์ที่ได้อาจมี session ของเว็บไซต์อื่นติดมาด้วย

### Chrome / Edge / Brave / Chromium / Vivaldi

หลังสร้าง profile สำหรับบอตแล้ว ให้เปิด PowerShell ในโฟลเดอร์ SNTalkBot และใช้สคริปต์ค้นหา profile ที่มีอยู่:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_youtube_cookies.ps1 -BrowserSpec chrome -ListProfiles
```

เปลี่ยน `chrome` เป็น `edge`, `brave`, `chromium` หรือ `vivaldi` ตาม browser ที่ใช้ สคริปต์จะแสดงทั้งชื่อ profile, ชื่อโฟลเดอร์ และค่า `BrowserSpec` ที่ใช้ได้ เช่น:

```text
Profile: SNTalkBot
  Folder: Profile 2
  BrowserSpec: "chrome:Profile 2"
```

ชื่อที่เห็นบนปุ่ม profile กับชื่อโฟลเดอร์อาจไม่เหมือนกัน ดังนั้นให้ใช้ค่าหลัง `BrowserSpec:` ที่สคริปต์แสดง

ตรวจด้วย browser เองได้อีกทาง:

- Chrome เปิด `chrome://version`
- Edge เปิด `edge://version`
- Brave เปิด `brave://version`

หา **Profile Path** เช่น:

```text
C:\Users\nuttawat\AppData\Local\Google\Chrome\User Data\Profile 2
```

ในตัวอย่างนี้ค่า profile คือ `Profile 2` จึงใช้:

```text
chrome:Profile 2
```

ถ้า Profile Path ลงท้าย `Default` ให้ใช้ `chrome:Default`

### Firefox

เปิด `about:profiles` แล้วดู profile ที่ต้องการ ค่า **Root Directory** คือ path ของ profile นั้น หรือให้สคริปต์แสดงให้:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_youtube_cookies.ps1 -BrowserSpec firefox -ListProfiles
```

สคริปต์จะแสดงตัวอย่าง:

```text
BrowserSpec: "firefox:C:\Users\nuttawat\AppData\Roaming\Mozilla\Firefox\Profiles\abc123.sntalkbot"
```

yt-dlp รองรับรูปแบบ `BROWSER[:PROFILE]` และ profile สามารถเป็นชื่อหรือ path ได้

## ขั้นที่ 1: เตรียมบัญชี YouTube

แนะนำให้ใช้บัญชี Google/YouTube แยกสำหรับบอต หากบัญชีนั้นต้องผ่านการยืนยันอายุหรือมีสิทธิ์ดู playlist/private content ให้ทำให้บัญชีเปิดเนื้อหานั้นใน browser ได้ก่อน

1. เปิด browser ด้วย **profile สำหรับ SNTalkBot**
2. เข้า YouTube และกด Sign in/ลงชื่อเข้าใช้
3. ลงชื่อด้วยบัญชีที่ต้องการให้บอตใช้ ไม่ต้องกรอกรหัสผ่านลง SNTalkBot หรือ TTUHelper เลย รหัสผ่านกรอกเฉพาะหน้า Google ใน browser
4. ถ้ามี 2-Step Verification ให้ยืนยันใน browser ตามปกติ
5. เปิดวิดีโอจำกัดอายุหรือ playlist ที่ต้องการทดสอบให้แน่ใจว่า account นี้ดูได้
6. ถ้าจะใช้วิธี export จาก profile ปกติ ให้ปิดหน้าต่าง browser ของ profile นั้นก่อน export เพื่อลดปัญหาไฟล์ cookie ถูกล็อก

**ข้อควรจำ:** yt-dlp เตือนว่าการใช้บัญชีกับ automated access มีความเสี่ยงที่บัญชีอาจถูกจำกัดหรือแบน จึงควรใช้เฉพาะเมื่อจำเป็นและหลีกเลี่ยงการยิงคำขอจำนวนมาก

## ขั้นที่ 2A: วิธีง่าย — export จาก Browser Profile ด้วยสคริปต์

ติดตั้ง/อัปเดต yt-dlp บน Windows:

```powershell
py -m pip install -U yt-dlp
py -m yt_dlp --version
```

ดู profile ก่อน เช่น Chrome:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_youtube_cookies.ps1 -BrowserSpec chrome -ListProfiles
```

ถ้า profile สำหรับบอตคือ `Profile 2`:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_youtube_cookies.ps1 -BrowserSpec "chrome:Profile 2"
```

Edge ตัวอย่าง:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_youtube_cookies.ps1 -BrowserSpec "edge:Profile 1"
```

Firefox ตัวอย่าง:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_youtube_cookies.ps1 -BrowserSpec "firefox:C:\Users\nuttawat\AppData\Roaming\Mozilla\Firefox\Profiles\abc123.sntalkbot"
```

ค่าเริ่มต้นสร้างไฟล์:

```text
%USERPROFILE%\Downloads\sntalkbot-youtube-cookies.txt
```

สคริปต์ไม่พิมพ์ค่า cookie ออกหน้าจอ และจะแสดงเฉพาะจำนวน record ของโดเมน YouTube

### ข้อจำกัดของวิธี 2A

YouTube หมุน account cookies ของ session ที่ยังเปิดใน browser เป็นระยะ วิธี export จาก profile ปกติจึงสะดวกแต่ cookie ที่ copy ออกมาอาจหมดอายุหรือถูกหมุนภายหลัง โดยเฉพาะเมื่อกลับไปเปิด profile/session เดิมอีก

## ขั้นที่ 2B: วิธีที่ yt-dlp แนะนำสำหรับ YouTube session ที่ไม่ควรถูกหมุน

เอกสาร YouTube extractor ของ yt-dlp แนะนำวิธี private/incognito สำหรับ account cookies ที่ต้องการเก็บใช้กับ yt-dlp:

1. เปิด **หน้าต่าง Incognito/Private ใหม่** และให้มี private window/session นี้สำหรับงาน export โดยเฉพาะ
2. เข้า YouTube และลงชื่อเข้าใช้บัญชีสำหรับบอต
3. ใน **tab เดิม** หลัง login สำเร็จ เปิด:

```text
https://www.youtube.com/robots.txt
```

4. Export cookies ของ `youtube.com` จาก private/incognito session เป็นไฟล์ Netscape cookies
5. ปิด private/incognito window ทันทีหลัง export และ **อย่าเปิด session เดิมนั้นใน browser อีก**

เหตุผลคือ YouTube หมุน account cookies บน tab ที่เปิดใช้งานอยู่ วิธีนี้ช่วยให้สำเนาที่ export ไม่ถูก browser session เดิมหมุนตามหลัง

### แล้ว export Incognito อย่างไร

`--cookies-from-browser` อ่าน cookie store บนดิสก์ จึงไม่ใช่วิธีที่เหมาะกับ incognito cookie ที่อยู่ใน memory คุณต้องใช้เครื่องมือ export cookies ที่รองรับ private/incognito และออกไฟล์ **Netscape/Mozilla cookies.txt**

yt-dlp FAQ ยกตัวอย่างส่วนขยายที่ export ในเครื่อง เช่น **Get cookies.txt LOCALLY** สำหรับ Chromium และ **cookies.txt** สำหรับ Firefox แต่ควรติดตั้งเฉพาะส่วนขยายที่เชื่อถือได้ ตรวจ publisher/permission และอนุญาต Incognito/Private เฉพาะตอน export เท่านั้น

**สำคัญ:** อย่าใช้ส่วนขยายชื่อคล้ายกันแบบสุ่ม ๆ และอย่าอัปโหลด cookie ไปเว็บ converter ภายนอก เพราะไฟล์นี้คือ session secret

## ขั้นที่ 3: ตรวจไฟล์ก่อนส่งขึ้น server

ไฟล์ต้องเป็น Netscape/Mozilla format โดยบรรทัดแรกเป็นหนึ่งใน:

```text
# Netscape HTTP Cookie File
```

หรือ:

```text
# HTTP Cookie File
```

อย่าเปิดเผยบรรทัด cookie ใน log หรือแชต หากต้องการตรวจแบบปลอดภัยให้ใช้ TTUHelper หลังอัปโหลด

## ขั้นที่ 4: ส่งไฟล์จาก Windows ไป Linux

จาก PowerShell:

```powershell
scp "$env:USERPROFILE\Downloads\sntalkbot-youtube-cookies.txt" root@YOUR_SERVER:/root/sntalkbot-youtube-cookies.txt
```

เปลี่ยน `YOUR_SERVER` เป็น IP หรือ hostname ของเซิร์ฟเวอร์

## ขั้นที่ 5: ติดตั้งให้ Player/Full instance

ตัวอย่าง instance ชื่อ `Multipurpose`:

```bash
sudo ttuhelper cks Multipurpose /root/sntalkbot-youtube-cookies.txt
sudo ttuhelper cks-check Multipurpose
sudo ttuhelper restart Multipurpose
```

ถ้าต้องการใช้ชุดเดียวกับ Player/Full ทุก instance:

```bash
sudo ttuhelper cks-all /root/sntalkbot-youtube-cookies.txt
```

`cks-all` จะข้าม Server Manager อัตโนมัติ

TTUHelper 1.4 ตรวจ header/record, รองรับ `#HttpOnly_`, แปลง CRLF เป็น LF, จำกัด permission และไม่แสดงค่าของ cookie

## ขั้นที่ 6: ลบไฟล์ชั่วคราว

หลังติดตั้งสำเร็จ:

```bash
rm -f /root/sntalkbot-youtube-cookies.txt
```

ถ้าใช้ไฟล์ชั่วคราวบน Windows และไม่ต้องเก็บไว้ ให้ลบด้วยเช่นกัน:

```powershell
Remove-Item "$env:USERPROFILE\Downloads\sntalkbot-youtube-cookies.txt" -Force
```

ไฟล์ persistent ของ instance จะอยู่ประมาณ:

```text
/opt/sntalkbot-bots/Multipurpose/cookies.txt
```

## ขั้นที่ 7: ทดสอบโดยไม่เปิดเผย secret

ตรวจไฟล์:

```bash
sudo ttuhelper cks-check Multipurpose
```

ดู log:

```bash
sudo ttuhelper logs Multipurpose
```

จาก TeamTalk ให้ลองเล่นวิดีโอจำกัดอายุที่บัญชีนี้เปิดได้ใน browser หากยังไม่ได้ ให้ export session ใหม่ก่อน ไม่ควร paste cookie value ลง log เพื่อวิเคราะห์

## ถ้า cookies ยังใช้ไม่ได้

1. ยืนยันว่าบัญชีที่ export เปิดเนื้อหานั้นใน browser ได้จริง
2. ตรวจว่าเลือก **profile ถูกตัว** ด้วย `-ListProfiles` หรือ Profile Path
3. export ใหม่ แล้ว `cks` + `cks-check` + restart
4. ถ้า export จาก profile ปกติแล้วหมดเร็ว ให้ใช้ private/incognito workflow ของ yt-dlp
5. YouTube เปลี่ยนระบบป้องกันเป็นระยะ บาง client/format อาจต้องใช้ **PO Token** เพิ่ม Cookies อย่างเดียวจึงไม่รับประกันวิดีโอทุกตัว
6. SNTalkBot ไม่ bake PO Token คงที่และไม่ bundle provider ภายนอกอัตโนมัติ เพื่อไม่ให้ dependency ที่เปลี่ยนเร็วทำ image หลักพัง

## สิ่งที่ห้ามทำ

- ห้าม commit **cookie ส่วนตัวที่ export เอง** ลง GitHub
- ห้ามเอา cookie ส่วนตัวไปแทน `defaults/cookies.txt` ก่อน build image สาธารณะ
- ห้าม push Docker image ที่มี session cookie ส่วนตัวของคุณ
- ห้าม paste cookie ในแชต, issue, log หรือหน้าเว็บ
- ห้ามใช้เว็บออนไลน์แปลง cookies
- ถ้าสงสัยว่า cookie หลุด ให้ logout/revoke session ของบัญชี แล้ว export ชุดใหม่

SNTalkBot 5 กัน `cookies.txt`, `config.ini` และ `.env*` ที่วางผิดตำแหน่งออกจาก Docker build context แต่อนุญาตเฉพาะ `defaults/cookies.txt` ที่เป็น bundled bootstrap ของโปรเจกต์; cookie ส่วนตัวควรติดตั้งด้วย TTUHelper ไปยัง persistent data เท่านั้น

## อ้างอิง

- yt-dlp FAQ — cookies จาก browser และ Netscape format: https://github.com/yt-dlp/yt-dlp/wiki/FAQ
- yt-dlp Extractors — YouTube account cookies และ private/incognito workflow: https://github.com/yt-dlp/yt-dlp/wiki/Extractors
- yt-dlp PO Token Guide: https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide
