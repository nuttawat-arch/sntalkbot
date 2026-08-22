# นำ SNTalkBot ขึ้น GitHub ครั้งแรก

ชื่อ repository ที่แนะนำ:

```text
sntalkbot
```

URL สำหรับบัญชีปัจจุบันตัวอย่าง:

```text
https://github.com/nuttawat-arch/sntalkbot.git
```

## ครั้งแรกบน Windows PowerShell

เข้าโฟลเดอร์ SNTalkBot แล้วรันทีละคำสั่ง:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial release of SNTalkBot"
git remote add origin https://github.com/nuttawat-arch/sntalkbot.git
git push -u origin main
```

ถ้า Git ยังไม่รู้ชื่อผู้เขียน:

```powershell
git config --global user.name "Nuttawat"
git config --global user.email "YOUR_GITHUB_EMAIL"
```

## รอบถัดไป

```powershell
git pull --rebase
git add .
git commit -m "Update SNTalkBot"
git push
```

## Line endings

Repository มี `.gitattributes` เพื่อบังคับไฟล์ shell เป็น LF สำหรับ Linux/Docker ไม่ให้เกิด `/bin/bash^M`.
