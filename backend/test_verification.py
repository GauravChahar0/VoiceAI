"""
VoiceAI - Automated Verification & Test Script (No RAG, Focus on Voice, Ollama Models & Call Summarization)
"""

import sys
import os

sys.path.insert(0, r"D:\VoiceAI")

from fastapi.testclient import TestClient
from backend.main import app
from backend.ai_service import ai_service
from backend.summary_service import summary_service

def run_tests():
    print("\n" + "=" * 60)
    print("  RUNNING VOICEAI SYSTEM VERIFICATION")
    print("=" * 60)

    # 1. Language detection test
    print("\n[1] Testing Bilingual Detection (English & Hindi)...")
    en_det = ai_service.detect_language("Hello, how can you help me today?")
    hi_det = ai_service.detect_language("नमस्ते, क्या आप मेरी मदद कर सकते हैं?")
    hinglish_det = ai_service.detect_language("Namaste, aap kaise ho?")
    print(f"  - 'Hello, how can you help me today?' -> {en_det}")
    print(f"  - 'नमस्ते, क्या आप मेरी मदद कर सकते हैं?' -> {hi_det}")
    print(f"  - 'Namaste, aap kaise ho?' -> {hinglish_det}")
    assert en_det == "en", "English detection failed"
    assert hi_det == "hi", "Hindi detection failed"
    print("  ✓ Language detection OK.")

    with TestClient(app) as client:
        # 2. Health & Models API
        print("\n[2] Testing Health & Models API...")
        r = client.get("/api/health")
        assert r.status_code == 200, f"Health check failed: {r.text}"
        print(f"  ✓ /api/health -> {r.json()}")

        r = client.get("/api/ai/models")
        assert r.status_code == 200
        models_data = r.json()
        ollama_models = models_data.get("ollama", {}).get("models", [])
        print(f"  ✓ Installed Ollama models found: {ollama_models}")
        assert "llama3.1:8b" in ollama_models or "qwen3.5:9b" in ollama_models, "Ollama models missing"

        # 3. AI Chat Endpoint
        print("\n[3] Testing /api/ai/chat with Ollama...")
        r = client.post("/api/ai/chat", json={
            "prompt": "Hello I want to call",
            "provider": "ollama",
            "model": "llama3.1:8b",
            "language": "en"
        })
        assert r.status_code == 200, f"Chat failed: {r.text}"
        chat_data = r.json()
        print(f"  ✓ Response received: {chat_data.get('response')[:80]}...")
        assert len(chat_data.get("response", "")) > 0

        # 4. Call Recording & File Persistence (Task 2)
        print("\n[4] Testing Call Transcript Storage to File...")
        transcript_sample = (
            "Customer: Hello, I want to inquire about renewing my maintenance contract.\n"
            "Agent: Hello! Yes, we can renew your contract today. The annual renewal fee is 5000 rupees.\n"
            "Customer: That sounds good. Please send the invoice to my email.\n"
            "Agent: Certainly, I will email the invoice by 3 PM and our team will follow up tomorrow."
        )

        r = client.post("/api/call/end", data={
            "transcript_text": transcript_sample,
            "duration": 45,
            "language": "en"
        })
        assert r.status_code == 200
        end_data = r.json()
        call_id = end_data["call_id"]
        print(f"  ✓ Call record saved with ID: {call_id}")

        # Check file exists on disk
        transcript_file = os.path.join(r"D:\VoiceAI\data\recordings", f"{call_id}_transcript.txt")
        assert os.path.exists(transcript_file), f"File {transcript_file} not found on disk"
        print(f"  ✓ Confirmed file exists on disk: {transcript_file}")

        # 5. List and Load Call Records
        print("\n[5] Testing List and Load Calls...")
        r = client.get("/api/call/list")
        assert r.status_code == 200
        calls_list = r.json().get("calls", [])
        assert any(c["call_id"] == call_id for c in calls_list), "Call not listed in calls list"
        print(f"  ✓ Call {call_id} listed in saved calls: {len(calls_list)} total calls.")

        r = client.get(f"/api/call/load/{call_id}")
        assert r.status_code == 200
        loaded = r.json()
        assert "Customer: Hello" in loaded["transcript"]
        print(f"  ✓ Call {call_id} successfully loaded.")

        # 6. Call Summarization (Triggered On-Demand Only)
        print("\n[6] Testing On-Demand Summary Generation (5 Sections)...")
        r = client.post("/api/call/summarize", json={
            "call_id": call_id,
            "transcript": transcript_sample,
            "provider": "ollama",
            "model": "llama3.1:8b",
            "language": "en"
        })
        assert r.status_code == 200
        summary_res = r.json()
        summary_text = summary_res.get("summary", "")
        print(f"  ✓ Summary generated:\n{summary_text[:250]}...\n")
        assert len(summary_text) > 20

        # Check summary file on disk
        summary_file = os.path.join(r"D:\VoiceAI\data\recordings", f"{call_id}_summary.txt")
        assert os.path.exists(summary_file), f"Summary file {summary_file} not found on disk"
        print(f"  ✓ Summary file confirmed on disk: {summary_file}")

        # 7. Verify TXT Downloads
        print("\n[7] Testing TXT Downloads...")
        r_t = client.get(f"/api/call/download/{call_id}/transcript")
        assert r_t.status_code == 200
        assert "Customer: Hello" in r_t.text
        print("  ✓ Transcript TXT download verified.")

        r_s = client.get(f"/api/call/download/{call_id}/summary")
        assert r_s.status_code == 200
        assert len(r_s.text) > 20
        print("  ✓ Summary TXT download verified.")

    print("\n" + "=" * 60)
    print("  ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_tests()
