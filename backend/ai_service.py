"""
VoiceAI - AI Service
Handles interactions with local Ollama models and Google Gemini API.
Supports English and Hindi conversations, automatic language detection, and structured call summarization.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
import httpx
from dotenv import load_dotenv
import asyncio

load_dotenv()

logger = logging.getLogger(__name__)

# Serialize AI requests so concurrent queries don't overload Ollama
_ai_lock = asyncio.Lock()

# Use 127.0.0.1 to avoid Windows IPv6 localhost delay
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_PROVIDER = os.getenv("AI_PROVIDER", "ollama")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


class AIService:
    def __init__(self):
        self.ollama_base_url = OLLAMA_BASE_URL
        self.gemini_api_key = GEMINI_API_KEY

    def get_installed_ollama_models(self) -> List[str]:
        """Fetch all models currently installed in Ollama."""
        urls_to_try = [
            f"{self.ollama_base_url}/api/tags",
            "http://127.0.0.1:11434/api/tags",
            "http://localhost:11434/api/tags"
        ]
        for url in urls_to_try:
            try:
                with httpx.Client(timeout=5.0) as client:
                    res = client.get(url)
                    if res.status_code == 200:
                        data = res.json()
                        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                        if models:
                            return models
            except Exception as e:
                logger.debug(f"Could not reach {url}: {e}")
        return ["llama3.1:8b", "qwen3.5:9b"]

    def detect_language(self, text: str) -> str:
        if not text or not text.strip():
            return "en"

        # Check for Devanagari Unicode characters (0x0900 to 0x097F)
        devanagari_count = sum(1 for c in text if '\u0900' <= c <= '\u097f')
        if devanagari_count > 0:
            return "hi"

        # Check common Romanized Hindi keywords (Hinglish/Hindi in Latin script)
        hindi_keywords = {
            "kya", "hai", "nahi", "haan", "kaise", "kaisa", "namaste", "dhanyavaad",
            "kripya", "mujhe", "tumhe", "aap", "batao", "karo", "accha", "theek",
            "suno", "boliye", "kahan", "kab", "kyun", "mera", "meri", "hum"
        }
        words = set(text.lower().split())
        if len(words.intersection(hindi_keywords)) >= 2:
            return "hi"

        try:
            from langdetect import detect
            lang = detect(text)
            return "hi" if lang == "hi" else "en"
        except Exception:
            return "en"

    async def generate_response(
        self,
        prompt: str,
        provider: str = "ollama",
        model: Optional[str] = None,
        language: str = "auto",
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate response from either local Ollama or Google Gemini.
        """
        detected_lang = self.detect_language(prompt) if language == "auto" else language
        lang_instruction = (
            "You MUST respond ONLY in Hindi (हिन्दी भाषा में उत्तर दें). "
            if detected_lang == "hi"
            else "You MUST respond in clear English. "
        )

        system_instruction = (
            "You are VoiceAI, a helpful, polite, and intelligent bilingual voice assistant. "
            + lang_instruction
            + "Keep your response conversational, concise (2-4 sentences max), and suitable to be spoken aloud. "
        )

        if provider == "gemini":
            return await self._generate_gemini(prompt, system_instruction, model or DEFAULT_GEMINI_MODEL, detected_lang)
        else:
            return await self._generate_ollama(prompt, system_instruction, model or DEFAULT_OLLAMA_MODEL, detected_lang, history)

    async def _generate_ollama(
        self,
        prompt: str,
        system_instruction: str,
        model: str,
        lang: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Generate text using Ollama /api/chat with serialization."""
        async with _ai_lock:
            messages = [{"role": "system", "content": system_instruction}]
            if history:
                for item in history[-6:]:
                    messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
            messages.append({"role": "user", "content": prompt})

        # Try 127.0.0.1 first for fastest response on Windows
        endpoints = [
            f"{self.ollama_base_url}/api/chat",
            "http://127.0.0.1:11434/api/chat",
            "http://localhost:11434/api/chat"
        ]

        last_err = None
        for endpoint in endpoints:
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    res = await client.post(
                        endpoint,
                        json={"model": model, "messages": messages, "stream": False}
                    )
                    if res.status_code == 200:
                        data = res.json()
                        response_text = data.get("message", {}).get("content", "").strip()
                        return {"text": response_text, "language": lang, "provider": "ollama", "model": model}
                    else:
                        return {
                            "text": f"Ollama status {res.status_code}: Model '{model}' might be loading. Please try again in a few seconds.",
                            "language": "en",
                            "error": res.text
                        }
            except Exception as e:
                last_err = e

        return {
            "text": f"Could not connect to Ollama. Please ensure Ollama is running at {self.ollama_base_url}.",
            "language": "en",
            "error": str(last_err)
        }

    async def _generate_gemini(
        self,
        prompt: str,
        system_instruction: str,
        model_name: str,
        lang: str
    ) -> Dict[str, Any]:
        """Generate text using Google Gemini API."""
        api_key = os.getenv("GEMINI_API_KEY", self.gemini_api_key)
        if not api_key:
            return {
                "text": "Gemini API key is not configured. Please add GEMINI_API_KEY in the backend .env file.",
                "language": "en",
                "error": "missing_api_key"
            }

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name=model_name or "gemini-1.5-flash",
                system_instruction=system_instruction
            )
            response = await model.generate_content_async(prompt)
            return {"text": response.text.strip(), "language": lang, "provider": "gemini", "model": model_name}
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return {"text": f"Gemini API error: {str(e)}", "language": "en", "error": str(e)}

    async def generate_call_summary(
        self,
        transcript: str,
        provider: str = "ollama",
        model: Optional[str] = None,
        language: str = "auto"
    ) -> Dict[str, Any]:
        """
        Generate structured call summary strictly when requested.
        Contains:
        1. Short call overview
        2. Main discussion points
        3. Important decisions
        4. Action items
        5. Follow-up tasks
        """
        detected_lang = self.detect_language(transcript) if language == "auto" else language
        lang_note = (
            "Provide the summary in Hindi (हिन्दी में)."
            if detected_lang == "hi"
            else "Provide the summary in English."
        )

        prompt = f"""You are an executive assistant analyzing a recorded phone call transcript.
{lang_note}

Transcript:
\"\"\"
{transcript}
\"\"\"

Please analyze the transcript and generate a structured summary with EXACTLY these 5 sections:
1. Short Call Overview (2-3 sentences summarizing the purpose and tone of the call)
2. Main Discussion Points (bullet points of the primary topics discussed)
3. Important Decisions (decisions reached during the call)
4. Action Items (concrete actions identified)
5. Follow-up Tasks (next steps, deadlines, or who needs to contact whom)

Format clearly with numbered headers.
"""
        res = await self.generate_response(
            prompt=prompt,
            provider=provider,
            model=model,
            language=detected_lang
        )
        return {
            "summary": res.get("text", "Could not generate summary."),
            "language": detected_lang,
            "provider": provider
        }


ai_service = AIService()
