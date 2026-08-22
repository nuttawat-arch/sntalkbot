import json
import requests


class GroqClient:
    def __init__(self, api_key, model="llama-3.1-8b-instant", base_url="https://api.groq.com/openai/v1"):
        self.api_key = (api_key or "").strip()
        self.model = (model or "llama-3.1-8b-instant").strip()
        self.base_url = (base_url or "https://api.groq.com/openai/v1").strip()

    def is_configured(self):
        return bool(self.api_key)

    def translate(self, text, source_lang, target_lang):
        if not self.api_key:
            return None
        if not text:
            return ""
        if source_lang and source_lang.lower() != "auto":
            user_prompt = (
                f"Translate from {source_lang} to {target_lang}. "
                "Only return the translated text.\n\n"
                f"Text:\n{text}"
            )
        else:
            user_prompt = (
                f"Translate to {target_lang}. Auto-detect the source language. "
                "Only return the translated text.\n\n"
                f"Text:\n{text}"
            )
        return self._chat(user_prompt, temperature=0.1, max_tokens=512)

    def should_block_message(self, text, bad_words=None):
        if not self.api_key:
            return None
        bad_words = [word for word in (bad_words or []) if word]
        system_prompt = (
            "You are a strict chat moderation classifier. Block messages that contain explicit "
            "profanity, sexual content, hateful slurs, threats of violence, or direct insults/"
            "harassment toward a person or group. Allow neutral messages, mild disagreements, "
            "and playful banter without targeted insults."
        )
        if bad_words:
            system_prompt += (
                "\n\nIf any banned words (or close variants) appear, you MUST block. "
                "Include any matched banned words in matched_words. "
                "You may still block for direct insults or harassment even if no "
                "banned words appear.\n"
                f"Banned words: {', '.join(bad_words)}"
            )
        system_prompt += (
            "\n\nRespond ONLY in valid JSON with keys: action (ALLOW or BLOCK), "
            "matched_words (array), category (profanity|insult|sexual|hate|threat|other), "
            "reason (short string)."
        )
        result = self._chat(text, temperature=0.0, max_tokens=80, system_prompt=system_prompt)
        if not result:
            return None

        parsed = self._parse_moderation_result(result)
        if parsed is not None:
            return parsed

        normalized = result.strip().upper()
        if normalized in ("ALLOW", "BLOCK"):
            return {
                "block": normalized == "BLOCK",
                "matched_words": [],
                "reason": "",
                "action": normalized,
                "category": "none",
            }
        return None

    def analyze_moderation(self, text):
        if not self.api_key:
            return None
        system_prompt = (
            "انت مساعد لمراقبة رسائل السيرفر. صنّف الرسالة حسب القوانين التالية:\n"
            "- STRIKE: سب الدين او التعرض الديني، او كلام/تلميحات جنسية واضحة.\n"
            "- KICK: شتائم مباشرة/موجهة لشخص او اهانه قوية.\n"
            "- WARN: شتائم خفيفة داخل جملة طويلة او هزار بسيط.\n"
            "- ALLOW: كلام عادي او هزار غير مؤذي.\n\n"
            "مهم: لا تعاقب على المزاح الخفيف اذا كان واضح انه مزاح.\n"
            "ارجع النتيجة كـ JSON فقط بالشكل:\n"
            "{\"action\":\"ALLOW|WARN|KICK|STRIKE\",\"category\":\"none|insult|religion|sexual\",\"reason\":\"...\"}\n\n"
            "امثلة:\n"
            "- \"hi, my fucking friend\" => WARN (مزاح فيه لفظ سيء)\n"
            "- \"انت وسخ\" => WARN\n"
            "- \"انت كلب\" => KICK\n"
            "- \"سأقيم علاقة جنسية\" => STRIKE\n"
            "- \"سب الدين\" => STRIKE"
        )
        result = self._chat(text, temperature=0.0, max_tokens=120, system_prompt=system_prompt)
        if not result:
            return None
        return self._parse_moderation_result(result)

    def is_account_request(self, text):
        if not self.api_key:
            return None
        if not text:
            return None
        system_prompt = (
            "You are an intent classifier. Determine whether the user is asking to create "
            "or request a new account for the service. Return JSON only:\n"
            "{\"intent\":\"ACCOUNT\"|\"OTHER\",\"reason\":\"short\"}"
        )
        result = self._chat(text, temperature=0.0, max_tokens=60, system_prompt=system_prompt)
        if not result:
            return None
        return self._parse_account_intent(result)

    def _chat(self, user_prompt, temperature=0.2, max_tokens=256, system_prompt=None):
        if not self.api_key:
            raise ValueError("Groq API key is not configured.")
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return self._extract_text(data)

    def _extract_text(self, data):
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        text = message.get("content", "")
        return text.strip()

    def _parse_moderation_result(self, result):
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return None
        action = str(data.get("action", "")).strip().upper()
        matched_words = data.get("matched_words") or []
        if not isinstance(matched_words, list):
            matched_words = []
        matched_words = [str(word).strip() for word in matched_words if str(word).strip()]
        return {
            "block": action == "BLOCK",
            "matched_words": matched_words,
            "reason": str(data.get("reason", "")).strip(),
            "action": action,
            "category": str(data.get("category", "")).strip().lower(),
        }

    def _parse_account_intent(self, result):
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return None
        intent = str(data.get("intent", "")).strip().upper()
        if intent not in ("ACCOUNT", "OTHER"):
            return None
        return {
            "intent": intent,
            "reason": str(data.get("reason", "")).strip(),
        }
