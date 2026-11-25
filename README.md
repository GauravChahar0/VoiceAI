# VoiceAI - Bilingual AI Voice Assistant (English & हिन्दी)

VoiceAI is a full-stack AI Voice Assistant and Call Summarizer built with FastAPI, Vanilla JavaScript, Local Ollama models (`qwen3.5:9b`, `llama3.1:8b`), Google Gemini, and Faster-Whisper.

---

## Key Features

1. **Bilingual Speech & Chat**:
   - Supports English and Hindi with automatic language detection.
   - Text-to-Speech (TTS) plays AI responses through laptop speakers.
   - Faster-Whisper speech-to-text with Web Speech fallback.

2. **Two AI Providers**:
   - **Local Ollama**: Connects to `http://localhost:11434` or `http://127.0.0.1:11434`. Automatically lists and lets you choose between `qwen3.5:9b` and `llama3.1:8b`.
   - **Online Gemini**: Connects to Google Gemini API (set `GEMINI_API_KEY` in `.env`).

3. **Call Recording, Transcript File Storage & Summarization (Task 2)**:
   - **Start Call** / **End Call** records microphone audio and calculates duration.
   - Automatically transcribes and saves call text to local file in `data/recordings/{call_id}_transcript.txt`.
   - The current call text automatically appears in the **Call Summarization** tab.
   - **Send to Summary** button in Voice Assistant to transfer chat history into call summarization.
   - **Generate Summary** button is prominently visible. The summary is **ONLY** generated when the user clicks this button.
   - Generates the 5 structured sections:
     1. Short Call Overview
     2. Main Discussion Points
     3. Important Decisions
     4. Action Items
     5. Follow-up Tasks
   - Download transcripts and summaries as `.txt` files anytime.

---

## Project Structure

```
D:\VoiceAI\
├── backend\
│   ├── ai_service.py         # Ollama & Gemini interaction, language detection
│   ├── main.py               # FastAPI application & REST endpoints
│   ├── summary_service.py    # Local file persistence for transcripts & summaries
│   ├── voice_service.py      # Faster-Whisper STT & pyttsx3/SAPI5 TTS
│   ├── test_verification.py  # Automated test suite
│   └── requirements.txt
├── data\
│   └── recordings\           # Saved call transcripts (*_transcript.txt) & summaries (*_summary.txt)
├── frontend\
│   ├── index.html            # 2-tab UI: Voice Assistant & Call Summarization
│   ├── script.js             # Client logic, speech recognition, audio player
│   └── style.css             # Responsive modern styling with dark/light themes
├── run.py                    # Server startup script
└── .env                      # API keys & configuration
```

---

## How to Run

1. Open PowerShell or Command Prompt:
   ```powershell
   cd D:\VoiceAI
   python run.py
   ```

2. Open your browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```
   *(or `http://localhost:8000`)*

3. Select your model (`llama3.1:8b` or `qwen3.5:9b`) from the top navigation bar.
4. Speak or type in English or Hindi!
