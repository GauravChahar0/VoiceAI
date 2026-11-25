"""
VoiceAI - Summary Service
Local file persistence and export for call recordings, transcripts, and generated summaries.
"""

import os
import glob
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")

os.makedirs(RECORDINGS_DIR, exist_ok=True)


class SummaryService:
    def __init__(self):
        self.recordings_dir = RECORDINGS_DIR

    def save_call_record(
        self,
        call_id: str,
        transcript: str,
        summary: Optional[str] = None,
        language: str = "en",
        duration_seconds: int = 0
    ) -> str:
        """Save call metadata and text files to local disk."""
        meta = {
            "call_id": call_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "language": language,
            "duration_seconds": duration_seconds,
            "has_summary": bool(summary)
        }

        # Save metadata JSON
        meta_file = os.path.join(self.recordings_dir, f"{call_id}_meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # Save transcript TXT
        transcript_file = os.path.join(self.recordings_dir, f"{call_id}_transcript.txt")
        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(transcript)

        # Save summary TXT if available
        if summary:
            summary_file = os.path.join(self.recordings_dir, f"{call_id}_summary.txt")
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(summary)

        return call_id

    def save_direct_transcript(self, transcript: str, language: str = "auto") -> Dict[str, Any]:
        """Save a new transcript text directly to a file."""
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        self.save_call_record(
            call_id=call_id,
            transcript=transcript,
            language=language,
            duration_seconds=0
        )
        return {
            "call_id": call_id,
            "transcript_file": f"{call_id}_transcript.txt",
            "message": "Call transcript saved successfully to file."
        }

    def update_summary(self, call_id: str, summary: str) -> bool:
        """Add or update generated summary for an existing call."""
        summary_file = os.path.join(self.recordings_dir, f"{call_id}_summary.txt")
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary)

        meta_file = os.path.join(self.recordings_dir, f"{call_id}_meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["has_summary"] = True
                meta["summary_generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass
        return True

    def get_transcript(self, call_id: str) -> Optional[str]:
        path = os.path.join(self.recordings_dir, f"{call_id}_transcript.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def get_summary(self, call_id: str) -> Optional[str]:
        path = os.path.join(self.recordings_dir, f"{call_id}_summary.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def list_calls(self) -> List[Dict[str, Any]]:
        """List all saved call text files on disk."""
        calls = []
        meta_files = glob.glob(os.path.join(self.recordings_dir, "*_meta.json"))
        for mf in meta_files:
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                call_id = meta.get("call_id")
                transcript = self.get_transcript(call_id) or ""
                meta["preview"] = transcript[:80] + ("..." if len(transcript) > 80 else "")
                calls.append(meta)
            except Exception:
                pass

        # Sort newest first
        calls.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return calls


summary_service = SummaryService()
