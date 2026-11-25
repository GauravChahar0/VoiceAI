"""
VoiceAI - Voice Service
Speech-to-Text with Faster-Whisper and Text-to-Speech with pyttsx3, Edge-TTS, or gTTS.
"""

import os
import io
import wave
import base64
import logging
import asyncio
import tempfile
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
DEFAULT_TTS_PROVIDER = os.getenv("TTS_PROVIDER", "pyttsx3")


_tts_lock = asyncio.Lock()

class VoiceService:
    def __init__(self):
        self.whisper_model_size = WHISPER_MODEL_SIZE
        self.tts_provider = DEFAULT_TTS_PROVIDER
        self._whisper_model = None

    def _get_whisper(self):
        """Lazy load Faster-Whisper model on CPU."""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Faster-Whisper ({self.whisper_model_size}) on CPU...")
            self._whisper_model = WhisperModel(
                self.whisper_model_size,
                device="cpu",
                compute_type="int8"
            )
            logger.info("Faster-Whisper loaded successfully.")
        return self._whisper_model

    async def transcribe_audio_file(self, audio_bytes: bytes, filename: str = "audio.wav") -> Dict[str, Any]:
        """Transcribe uploaded audio bytes (WAV, WEBM, MP3) using Faster-Whisper."""
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        def _transcribe():
            model = self._get_whisper()
            segments, info = model.transcribe(
                tmp_path,
                beam_size=5,
                vad_filter=True,
                language=None  # auto-detect (en / hi)
            )
            full_text = " ".join(seg.text.strip() for seg in segments).strip()
            detected_lang = "hi" if info.language == "hi" else "en"
            return {
                "text": full_text,
                "language": detected_lang,
                "confidence": round(info.language_probability, 3) if info.language_probability else 0.0
            }

        try:
            result = await asyncio.to_thread(_transcribe)
            return result
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"text": "", "language": "en", "error": str(e)}
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    async def text_to_speech(self, text: str, language: str = "en", provider: Optional[str] = None) -> Dict[str, Any]:
        """Convert text into spoken audio bytes and base64 string."""
        if not text or not text.strip():
            return {"audio_base64": "", "format": "wav"}
        async with _tts_lock:
            prov = provider or self.tts_provider
            try:
                if prov == "edge":
                    return await self._tts_edge(text, language)
                elif prov == "gtts":
                    return await self._tts_gtts(text, language)
                else:
                    return await self._tts_pyttsx3(text, language)
            except Exception as e:
                logger.error(f"TTS generation error: {e}")
                return {"audio_base64": "", "format": "wav", "error": str(e)}

    async def _tts_pyttsx3(self, text: str, language: str) -> Dict[str, Any]:
        """Fast offline Text-to-Speech using pyttsx3."""
        def _run_pyttsx3():
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                out_path = tmp.name

            try:
                engine.save_to_file(text, out_path)
                engine.runAndWait()
                with open(out_path, "rb") as f:
                    audio_bytes = f.read()
                return audio_bytes
            finally:
                if os.path.exists(out_path):
                    try:
                        os.unlink(out_path)
                    except Exception:
                        pass

        try:
            audio_bytes = await asyncio.to_thread(_run_pyttsx3)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return {"audio_base64": b64, "format": "wav", "provider": "pyttsx3"}
        except Exception as e:
            logger.warning(f"pyttsx3 failed ({e}), falling back to gTTS")
            return await self._tts_gtts(text, language)

    async def _tts_gtts(self, text: str, language: str) -> Dict[str, Any]:
        """Google Text-to-Speech (free, online)."""
        def _run_gtts():
            from gtts import gTTS
            lang_code = "hi" if language == "hi" else "en"
            tts = gTTS(text=text, lang=lang_code)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue()

        try:
            audio_bytes = await asyncio.to_thread(_run_gtts)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return {"audio_base64": b64, "format": "mp3", "provider": "gtts"}
        except Exception as e:
            logger.error(f"gTTS failed: {e}")
            return {"audio_base64": "", "format": "mp3", "error": str(e)}

    async def _tts_edge(self, text: str, language: str) -> Dict[str, Any]:
        """Microsoft Edge TTS (free neural voices)."""
        try:
            import edge_tts
            voice = "hi-IN-SwaraNeural" if language == "hi" else "en-US-JennyNeural"
            communicate = edge_tts.Communicate(text, voice)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            audio_bytes = buf.getvalue()
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return {"audio_base64": b64, "format": "mp3", "provider": "edge"}
        except Exception as e:
            logger.warning(f"Edge TTS failed ({e}), falling back to pyttsx3")
            return await self._tts_pyttsx3(text, language)


voice_service = VoiceService()
