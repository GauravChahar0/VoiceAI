"""
VoiceAI - Main FastAPI Application
Provides REST endpoints and WebSocket for speech-to-text, AI conversation, TTS, and call summarization.
"""

import os
import sys
import uuid
import json
import logging
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
RECORDINGS_DIR = os.path.join(BASE_DIR, "data", "recordings")

os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Import modular backend services
from backend.ai_service import ai_service
from backend.voice_service import voice_service
from backend.summary_service import summary_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAI")

app = FastAPI(
    title="VoiceAI - Bilingual AI Voice Assistant",
    description="Bilingual (English & Hindi) Voice Assistant with Call Summarization.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Static files mount
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")


# ── Pydantic Request Schemas ──────────────────────────────────────────

class TextQueryRequest(BaseModel):
    prompt: str
    provider: str = "ollama"  # "ollama" or "gemini"
    model: Optional[str] = None
    language: str = "auto"    # "en", "hi", or "auto"


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    provider: Optional[str] = None


class CallSummaryRequest(BaseModel):
    call_id: Optional[str] = None
    transcript: str
    provider: str = "ollama"
    model: Optional[str] = None
    language: str = "auto"


class SaveTranscriptRequest(BaseModel):
    transcript: str
    language: str = "auto"


# ── Root & Health Endpoints ───────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "VoiceAI", "languages": ["en", "hi"]}


# ── AI Provider & Models ──────────────────────────────────────────────

@app.get("/api/ai/models")
async def get_models():
    """Fetch installed Ollama models and available Gemini options."""
    ollama_models = ai_service.get_installed_ollama_models()
    return {
        "ollama": {
            "status": "connected" if len(ollama_models) > 0 else "offline",
            "models": ollama_models
        },
        "gemini": {
            "status": "configured" if bool(os.getenv("GEMINI_API_KEY")) else "missing_key",
            "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
        }
    }


# ── Voice Assistant Text & Audio Endpoints ─────────────────────────────

@app.post("/api/ai/chat")
async def chat(req: TextQueryRequest):
    """
    Process text query through selected AI (Ollama/Gemini)
    and synthesize spoken response.
    """
    ai_res = await ai_service.generate_response(
        prompt=req.prompt,
        provider=req.provider,
        model=req.model,
        language=req.language
    )

    # Synthesize speech for the response
    tts_res = await voice_service.text_to_speech(
        text=ai_res.get("text", ""),
        language=ai_res.get("language", "en")
    )

    return {
        "response": ai_res.get("text", ""),
        "language": ai_res.get("language", "en"),
        "provider": ai_res.get("provider", req.provider),
        "model": req.model,
        "audio_base64": tts_res.get("audio_base64", ""),
        "audio_format": tts_res.get("format", "wav")
    }


@app.post("/api/voice/transcribe")
async def transcribe(audio_file: UploadFile = File(...)):
    """Transcribe uploaded voice recording (WAV/WEBM) into English or Hindi text."""
    content = await audio_file.read()
    result = await voice_service.transcribe_audio_file(content, filename=audio_file.filename or "speech.wav")
    return result


@app.post("/api/voice/tts")
async def synthesize_speech(req: TTSRequest):
    """Convert text into speech audio."""
    return await voice_service.text_to_speech(
        text=req.text,
        language=req.language,
        provider=req.provider
    )


# ── Call Recording & Summarization Endpoints ──────────────────────────

@app.get("/api/call/list")
async def list_calls():
    """List all saved call text records on disk."""
    return {"calls": summary_service.list_calls()}


@app.post("/api/call/save")
async def save_call_text(req: SaveTranscriptRequest):
    """Directly save transcript text into a file on disk."""
    if not req.transcript or not req.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty.")
    result = summary_service.save_direct_transcript(req.transcript, req.language)
    return result


@app.get("/api/call/load/{call_id}")
async def load_call(call_id: str):
    """Load transcript and summary of a saved call."""
    transcript = summary_service.get_transcript(call_id)
    summary = summary_service.get_summary(call_id)
    if not transcript and not summary:
        raise HTTPException(status_code=404, detail="Call record not found.")
    return {
        "call_id": call_id,
        "transcript": transcript or "",
        "summary": summary or ""
    }


@app.post("/api/call/end")
async def end_call(
    audio_file: Optional[UploadFile] = File(None),
    transcript_text: Optional[str] = Form(None),
    duration: int = Form(0),
    language: str = Form("auto")
):
    """
    Called when user presses End Call:
    1. Transcribes audio if provided or uses live transcript.
    2. Stores transcript locally in data/recordings/{call_id}_transcript.txt.
    3. DOES NOT generate summary automatically (UI requires user to click 'Generate Summary').
    """
    call_id = f"call_{uuid.uuid4().hex[:8]}"
    transcript = transcript_text or ""

    if audio_file:
        content = await audio_file.read()
        res = await voice_service.transcribe_audio_file(content, filename=audio_file.filename or "call.wav")
        transcript = res.get("text", "")
        if language == "auto":
            language = res.get("language", "en")

    # Persist transcript to data/recordings/{call_id}_transcript.txt
    summary_service.save_call_record(
        call_id=call_id,
        transcript=transcript,
        language=language,
        duration_seconds=duration
    )

    return {
        "call_id": call_id,
        "transcript": transcript,
        "language": language,
        "message": "Call transcript saved to file. Click 'Generate Summary' to produce AI summary."
    }


@app.post("/api/call/summarize")
async def summarize_call(req: CallSummaryRequest):
    """
    Generate AI summary ONLY when user explicitly clicks 'Generate Summary'.
    """
    if not req.transcript or not req.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty.")

    res = await ai_service.generate_call_summary(
        transcript=req.transcript,
        provider=req.provider,
        model=req.model,
        language=req.language
    )

    call_id = req.call_id or f"call_{uuid.uuid4().hex[:8]}"
    summary_service.update_summary(call_id, res.get("summary", ""))

    return {
        "call_id": call_id,
        "summary": res.get("summary", ""),
        "language": res.get("language", "en")
    }


@app.get("/api/call/download/{call_id}/{doc_type}")
async def download_call_doc(call_id: str, doc_type: str):
    """Download transcript or summary as TXT file."""
    if doc_type == "transcript":
        content = summary_service.get_transcript(call_id)
        filename = f"{call_id}_transcript.txt"
    elif doc_type == "summary":
        content = summary_service.get_summary(call_id)
        filename = f"{call_id}_summary.txt"
    else:
        raise HTTPException(status_code=400, detail="Invalid doc_type. Choose 'transcript' or 'summary'.")

    if not content:
        raise HTTPException(status_code=404, detail="File content not found.")

    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── WebSocket Endpoint (Streaming Audio/Transcripts) ───────────────────

@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """WebSocket connection for real-time speech interaction."""
    await websocket.accept()
    logger.info("WebSocket connected for voice session.")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif msg_type == "chat":
                prompt = msg.get("text", "")
                provider = msg.get("provider", "ollama")
                model = msg.get("model")
                lang = msg.get("language", "auto")

                ai_res = await ai_service.generate_response(prompt, provider=provider, model=model, language=lang)
                tts_res = await voice_service.text_to_speech(ai_res.get("text", ""), ai_res.get("language", "en"))

                await websocket.send_text(json.dumps({
                    "type": "response",
                    "text": ai_res.get("text", ""),
                    "language": ai_res.get("language", "en"),
                    "audio_base64": tts_res.get("audio_base64", ""),
                    "format": tts_res.get("format", "wav")
                }))
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
