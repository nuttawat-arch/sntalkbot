# ส่วนประกอบที่ต้องใช้และแหล่งดาวน์โหลด

เอกสารนี้สำหรับ SN TalkBot รุ่น Linux/Docker วันที่ 22 สิงหาคม 2026

## 1. Python

ใช้ CPython 3.10 ขึ้นไป โดย Dockerfile ใช้ Python 3.12

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

แหล่งทางการ: https://www.python.org/downloads/

## 2. ไลบรารี Python

ติดตั้งทั้งหมดจาก `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

รายการหลักที่ล็อกรุ่นไว้:

- `yt-dlp[default,curl-cffi]==2026.8.19`
- `edge-tts==7.2.8`
- `python-mpv==1.0.8`

`yt-dlp[default]` ทำให้แพ็กเกจ `yt-dlp-ejs` ถูกติดตั้งมาด้วยตามแนวทางปัจจุบันของ yt-dlp

แหล่งทางการ yt-dlp: https://github.com/yt-dlp/yt-dlp
เอกสาร EJS: https://github.com/yt-dlp/yt-dlp/wiki/EJS
PyPI: https://pypi.org/project/yt-dlp/

## 3. Deno สำหรับ YouTube EJS

yt-dlp รุ่นปัจจุบันต้องใช้ JavaScript runtime สำหรับ YouTube และเอกสารแนะนำ Deno โดยตรง Dockerfile ล็อก Deno `2.9.5` ซึ่งใหม่กว่าขั้นต่ำที่เอกสาร EJS ระบุ

ติดตั้งตามเอกสารทางการ:
https://docs.deno.com/runtime/getting_started/installation/

ตรวจสอบ:

```bash
deno --version
```

## 4. FFmpeg และ MPV

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg mpv libmpv2
```

MPV ใช้สำหรับเล่นเสียงจริง ส่วน FFmpeg/ffprobe ใช้โดย yt-dlp และงานแปลง/ประมวลผลสื่อ

แหล่งทางการ MPV: https://mpv.io/
แหล่งทางการ FFmpeg: https://ffmpeg.org/

## 5. PulseAudio สำหรับ Linux Server แบบไม่มีหน้าจอ

ติดตั้ง:

```bash
sudo apt install -y pulseaudio pulseaudio-utils
```

โปรเจกต์ใช้ `tools/setup_pulse_bridge.sh` สร้าง null sink ชื่อ `sntalkbot` (หรือชื่อ instance จาก TTUHelper) และตั้ง monitor source ของ sink นั้น เป็น input เริ่มต้นของ TeamTalk

เส้นทางเสียงคือ:

```text
MPV -> PulseAudio instance sink -> instance.monitor -> TeamTalk microphone/input -> ห้อง TeamTalk
```

ห้ามเปลี่ยน MPV เป็น `ao=null` หากต้องการส่งเสียงเข้า TeamTalk เพราะ null audio output จะทิ้งเสียงทั้งหมด

## 6. TeamTalk 5 SDK

โปรเจกต์ตั้งเป้า SDK Standard v5.22a สำหรับ Linux Ubuntu 22 x86_64

ดาวน์โหลดอัตโนมัติหลังติดตั้ง `p7zip-full`:

```bash
python tools/download_teamtalk_sdk.py
```

หรือดาวน์โหลดตรงจาก BearWare:
https://www.bearware.dk/teamtalksdk/v5.22a/tt5sdk_v5.22a_ubuntu22_x86_64.7z

หน้าดาวน์โหลดทางการ:
https://bearware.dk/?page_id=419

ตัวติดตั้งจะนำ `TeamTalk5.py` และ `libTeamTalk5.so` มาไว้ที่ root ของโปรเจกต์

### เรื่อง TeamTalk SDK License

ช่อง `license_name` และ `license_key` ใน `config.ini` ปล่อยว่างได้ในระหว่างใช้ SDK trial อย่างเป็นทางการ แต่เอกสารของ BearWare ระบุชัดว่า binary ใน SDK เป็น trial และจะ disable หลังใช้งาน 30 วัน หากใช้เป็น end-user application ต่อเนื่องต้องมี SDK license ที่ถูกต้อง

โปรเจกต์นี้ไม่มีและไม่ทำระบบข้าม/แก้ข้อจำกัด trial หากคุณมี license ภายหลัง ให้ใส่ใน `[teamtalk_license]`; โค้ดจะตั้ง license ก่อนสร้าง TeamTalk instance ตามลำดับที่ API กำหนด

เอกสารทางการ:
https://www.bearware.dk/teamtalksdk/v5.22a/docs/C-API/license.html

## 7. 7-Zip

ใช้แตก TeamTalk SDK:

```bash
sudo apt install -y p7zip-full
```

## 8. ตรวจสภาพแวดล้อม

หลังติดตั้ง:

```bash
python tools/check_environment.py
python tools/validate_project.py
```

`check_environment.py` ตรวจ runtime จริง เช่น Deno, FFmpeg, TeamTalk SDK และโมดูล Python ส่วน `validate_project.py` ตรวจโครง source โดยไม่ต้อง import TeamTalk SDK เช่น syntax, คำสั่งซ้ำ, help, ภาษาไทย และการหลงเหลือระบบหลายโปรไฟล์


## GUI / Windows

ไม่มี dependency GUI และไม่ใช้ wxPython โปรเจกต์นี้เป็น Linux/Docker only


## Google Standard TTS (gTTS)

โหมด Google ใช้แพ็กเกจ `gTTS` ซึ่งสร้างเสียงผ่าน Google Translate TTS แบบมาตรฐาน ไม่ใช้ Google Cloud Text-to-Speech API และไม่ต้องใช้ API key/service account/billing

ค่าเริ่มต้นทั้ง Player และ Server Manager คือ Google standard ภาษาไทย (`lang=th`). FFmpeg ที่มีอยู่ใน image ใช้ปรับความเร็วเมื่อ `/speed` หรือ `/pttsspeed` ไม่เท่ากับ `1.0`. Microsoft Edge TTS ยังคงติดตั้งไว้เป็น engine สำรองและสลับได้ด้วย `/ttsmode microsoft` หรือ `/pttsmode microsoft`.
