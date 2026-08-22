import json
import os
import requests
import base64

GOOGLE_TTS_TIMEOUT_SECONDS = 180

class GoogleCloudTTSClient:
    def __init__(self, api_key, base_url="https://texttospeech.googleapis.com/v1"):
        self.api_key = (api_key or "").strip()
        # ใช้ Base URL มาตรฐานของ Google Cloud TTS
        self.base_url = (base_url or "https://texttospeech.googleapis.com/v1").strip()

    def is_configured(self):
        return bool(self.api_key)

    def list_models(self):
        # Google Cloud TTS ไม่ได้แยก Endpoint สำหรับ Model เหมือน ElevenLabs
        # โมเดล (เช่น Standard, WaveNet, Neural2, Journey) จะรวมอยู่ในชื่อ Voice ID แล้ว
        # จึงส่งค่าดัมมี่ (Dummy) กลับไปเพื่อให้สอดคล้องกับ Interface เดิม
        return {
            "models": [
                {"model_id": "standard", "name": "Standard"},
                {"model_id": "wavenet", "name": "WaveNet"},
                {"model_id": "neural2", "name": "Neural2"},
                {"model_id": "journey", "name": "Journey"}
            ]
        }

    def list_voices(self):
        # คืนค่าข้อมูลเสียงที่มีทั้งหมดจาก Google TTS
        return self._get_json("/voices")

    def synthesize(self, text, voice_id, model_id, output_path, voice_settings=None):
        if not self.api_key:
            raise ValueError("Google Cloud TTS API key is not configured.")
            
        url = f"{self.base_url}/text:synthesize"
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "Content-Type": "application/json; charset=utf-8",
        }
        
        if voice_settings is None:
            voice_settings = {}
            
        # ประยุกต์ใช้ค่า speed จาก ElevenLabs ให้เข้ากับ speakingRate ของ Google (ช่วงค่า 0.25 - 4.0)
        speaking_rate = voice_settings.get("speed", 1.0)
        
        # ดึงรหัสภาษาออกมาจาก Voice ID (ตัวอย่างเช่น "th-TH-Standard-A" -> "th-TH")
        parts = voice_id.split("-")
        language_code = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else "en-US"

        # จัดรูปแบบ Payload ให้ตรงกับ Google Cloud TTS API
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": language_code,
                "name": voice_id
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": speaking_rate,
                # ค่าอื่นๆ ของ ElevenLabs เช่น stability หรือ similarity_boost ไม่มีใน Google
                # เราสามารถเพิ่ม "pitch": voice_settings.get("pitch", 0.0) เข้าไปได้ถ้าต้องการ
            }
        }
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=GOOGLE_TTS_TIMEOUT_SECONDS,
        )
        
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if detail:
                raise ValueError(f"Google Cloud TTS API error: {detail}") from exc
            raise
            
        # Google Cloud TTS คืนค่าเสียงกลับมาเป็น Base64 String
        data = response.json()
        audio_content = data.get("audioContent")
        if not audio_content:
            raise ValueError("No audioContent returned from Google Cloud TTS API.")
            
        audio_bytes = base64.b64decode(audio_content)
        
        with open(output_path, "wb") as handle:
            handle.write(audio_bytes)
            
        return os.path.getsize(output_path)

    def _get_json(self, path):
        if not self.api_key:
            raise ValueError("Google Cloud TTS API key is not configured.")
        url = f"{self.base_url}{path}"
        headers = {"X-Goog-Api-Key": self.api_key}
        response = requests.get(url, headers=headers, timeout=GOOGLE_TTS_TIMEOUT_SECONDS)
        
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if detail:
                raise ValueError(f"Google Cloud TTS API error: {detail}") from exc
            raise
            
        return response.json()

    def load_cache(self, cache_path):
        if not os.path.exists(cache_path):
            return {}
        with open(cache_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_cache(self, cache_path, data):
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def resolve_voice_id(self, voice_name, voices):
        if not voice_name or not voices:
            return None
            
        voice_list = voices
        if isinstance(voices, dict) and "voices" in voices:
            voice_list = voices["voices"]
            
        lowered_target = voice_name.strip().lower()
        
        for voice in voice_list:
            # ของ Google TTS ฟิลด์ชื่อคือ 'name' ตัวอย่างเช่น "th-TH-Standard-A"
            name = str(voice.get("name", "")).strip()
            if name.lower() == lowered_target:
                return name
        return None