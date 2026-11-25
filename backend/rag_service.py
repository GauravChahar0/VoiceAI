"""
VoiceAI - RAG Service
Simple RAG implementation using ChromaDB and multilingual Sentence Transformers.
Extracts text from PDF and TXT, chunks it, and indexes it for contextual Q&A.
"""

import os
import logging
from typing import List, Dict, Any, Optional
import chromadb
from sentence_transformers import SentenceTransformer
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)


class RAGService:
    def __init__(self):
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.collection = self.chroma_client.get_or_create_collection(
            name="voiceai_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        self._embedder = None

    def _get_embedder(self):
        """Lazy load multilingual embedding model (paraphrase-multilingual-MiniLM-L12-v2 or all-MiniLM-L6-v2)."""
        if self._embedder is None:
            # sentence-transformers model supporting English, Hindi, and 50+ languages
            model_name = "paraphrase-multilingual-MiniLM-L12-v2"
            logger.info(f"Loading embedding model: {model_name}...")
            try:
                self._embedder = SentenceTransformer(model_name)
            except Exception:
                # Fallback to local cached all-MiniLM-L6-v2 if offline
                logger.info("Falling back to all-MiniLM-L6-v2...")
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded.")
        return self._embedder

    def extract_text_from_file(self, file_path: str) -> str:
        """Extract plain text from PDF or TXT files."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            reader = PdfReader(file_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip()
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        else:
            raise ValueError(f"Unsupported file format: {ext}. Only PDF and TXT are supported.")

    def split_into_chunks(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        """Simple, robust paragraph/character chunking."""
        if not text:
            return []
        
        # Split by double newlines or sentences
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        # Fallback if any single chunk exceeds chunk_size
        refined_chunks = []
        for c in chunks:
            if len(c) > chunk_size + overlap:
                for i in range(0, len(c), chunk_size - overlap):
                    sub = c[i:i + chunk_size].strip()
                    if sub:
                        refined_chunks.append(sub)
            else:
                refined_chunks.append(c)

        return refined_chunks

    def ingest_document(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Extract text, chunk it, embed, and store in ChromaDB."""
        text = self.extract_text_from_file(file_path)
        if not text:
            return {"success": False, "filename": filename, "chunks": 0, "message": "No text extracted."}

        chunks = self.split_into_chunks(text)
        if not chunks:
            return {"success": False, "filename": filename, "chunks": 0, "message": "Could not chunk text."}

        embedder = self._get_embedder()
        embeddings = embedder.encode(chunks).tolist()

        ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

        # Delete older chunks with same filename if re-uploaded
        try:
            self.collection.delete(where={"source": filename})
        except Exception:
            pass

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

        return {
            "success": True,
            "filename": filename,
            "chunks": len(chunks),
            "character_count": len(text)
        }

    def query(self, question: str, n_results: int = 3) -> Dict[str, Any]:
        """Search ChromaDB for chunks matching the question."""
        if self.collection.count() == 0:
            return {
                "context": "",
                "sources": [],
                "found": False,
                "message": "Knowledge base is currently empty. Please upload PDF or TXT documents first."
            }

        embedder = self._get_embedder()
        query_embedding = embedder.encode([question]).tolist()

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(n_results, self.collection.count())
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return {"context": "", "sources": [], "found": False}

        sources = list({m.get("source", "Unknown") for m in metadatas if m})
        context = "\n---\n".join(documents)

        return {
            "context": context,
            "sources": sources,
            "found": True
        }

    def get_uploaded_documents(self) -> List[str]:
        """List distinct document names stored in ChromaDB and uploads directory."""
        if os.path.exists(UPLOADS_DIR):
            return sorted(os.listdir(UPLOADS_DIR))
        return []


rag_service = RAGService()
