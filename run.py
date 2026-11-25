"""
VoiceAI - Server Launcher
Entry point to run the application on Windows.
"""

import os
import sys

# Ensure backend package is in pythonpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    print("\n" + "=" * 65)
    print("  VoiceAI - Bilingual AI Voice Assistant")
    print(f"  Open your browser at: http://{host}:{port}")
    print("=" * 65 + "\n")
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=True
    )
