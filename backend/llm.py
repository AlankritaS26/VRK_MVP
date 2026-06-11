import os
import json
import math
import asyncio
import logging
import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ==========================================
# CONFIGURATION & GLOBAL VECTOR CACHE
# ==========================================
OLLAMA_BASE_URL = "http://localhost:11434"
GENERATE_MODEL = "llama3.1:latest"
EMBED_MODEL = "nomic-embed-text"
SIMILARITY_THRESHOLD = 0.42

# This file lives at: project_root/backend/app/services/llm.py
JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "college_info.json")

# In-memory cache: parallel arrays of text chunks and their embedding vectors
KNOWLEDGE_CHUNKS: list[str] = []
KNOWLEDGE_EMBEDDINGS: list[list[float]] = []


# ==========================================
# OLLAMA EMBEDDING API
# ==========================================
async def get_embedding(text: str) -> list[float]:
    """Calls Ollama's local embedding engine and returns a 768-dim vector."""
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json={"model": EMBED_MODEL, "prompt": text})
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ollama embedding failed: {e}")


# ==========================================
# COSINE SIMILARITY
# ==========================================
def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Returns a float representing semantic similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


# ==========================================
# DATA INGESTION & VECTOR INDEXING
# ==========================================
async def initialize_rag_knowledge_base():
    """
    Reads college_info.json on startup, converts nested data into flat text chunks,
    and pre-computes embeddings concurrently into server memory.
    """
    global KNOWLEDGE_CHUNKS, KNOWLEDGE_EMBEDDINGS

    if KNOWLEDGE_CHUNKS:  # Skip if already loaded
        return

    if not os.path.exists(JSON_PATH):
        logger.warning(f"[RAG] Knowledge base file not found at: {JSON_PATH}")
        return

    with open(JSON_PATH, "r") as file:
        data = json.load(file)

    chunks = []

    c_info = data.get("college", {})
    chunks.append(
        f"{c_info.get('name')} ({c_info.get('short_name')}) was established in {c_info.get('established')} "
        f"by founder {c_info.get('founder')}. It is an autonomous {c_info.get('type')} located at {c_info.get('location')}."
    )

    admin = data.get("administration", {})
    chunks.append(f"The college working hours are {admin.get('working_hours')}.")
    chunks.append(f"The Director of RNSIT is {admin.get('director', {}).get('name')}. Contact phone: {admin.get('director', {}).get('phone')}.")
    chunks.append(f"The Principal of RNSIT is {admin.get('principal', {}).get('name')}. Contact phone: {admin.get('principal', {}).get('phone')}.")

    for code, details in data.get("departments", {}).items():
        chunks.append(
            f"The department of {details.get('name')} ({code.upper()}) is located in the {details.get('block', 'Main campus block')}. "
            f"The HOD is {details.get('hod', 'the appointed department head')} and intake capacity is {details.get('intake', '180')} students per year."
        )

    for name, details in data.get("facilities", {}).items():
        if isinstance(details, dict):
            chunks.append(
                f"Facility: {name.replace('_', ' ').title()}. "
                f"Details: {details.get('name', '')} {details.get('location', '')} {details.get('timings', '')} {details.get('details', '')}."
            )

    placements = data.get("placements", {})
    chunks.append(
        f"RNSIT placements feature over {placements.get('total_companies')} total companies. "
        f"Major recent recruiters include: {', '.join(placements.get('recent_recruiters', []))}."
    )
    for year, stats in placements.get("stats", {}).items():
        chunks.append(f"In {year}, the highest package offered was {stats.get('highest_ctc_lpa')} LPA.")

    logger.info(f"[RAG] Indexing {len(chunks)} chunks concurrently...")
    KNOWLEDGE_CHUNKS = chunks
    KNOWLEDGE_EMBEDDINGS = await asyncio.gather(*[get_embedding(chunk) for chunk in chunks])

    logger.info("[RAG] Knowledge base fully loaded into memory.")


# ==========================================
# SEMANTIC RETRIEVAL
# ==========================================
async def retrieve_relevant_context(user_query: str, top_k: int = 3) -> tuple[str, float]:
    """
    Embeds the user query, scores all chunks by cosine similarity,
    and returns the top-k context strings joined as one block, plus the highest score.
    """
    query_vector = await get_embedding(user_query)
    if not query_vector:
        return "No context found.", 0.0

    scored_chunks = [
        (float(cosine_similarity(query_vector, chunk_vector)), KNOWLEDGE_CHUNKS[idx])
        for idx, chunk_vector in enumerate(KNOWLEDGE_EMBEDDINGS)
    ]
    scored_chunks.sort(key=lambda x: x[0], reverse=True)  # FIX 1: sort by score only, not full tuple

    max_score = scored_chunks[0][0] if scored_chunks else 0.0  # FIX 2: extract float from first tuple
    top_matches = [chunk for _, chunk in scored_chunks[:top_k]]

    return "\n\n".join(top_matches), max_score


# ==========================================
# RAG RESPONSE GENERATION
# ==========================================
async def generate_rag_kiosk_response(question: str, history: list = None) -> str:
    """
    Retrieves relevant context via semantic search, applies a similarity guardrail,
    then generates a kiosk-appropriate response using the local Llama model.
    """
    context_text, max_score = await retrieve_relevant_context(question, top_k=3)
    logger.debug(f"[RAG] Query: '{question}' | Max similarity: {max_score:.4f}")

    if max_score < SIMILARITY_THRESHOLD:
        logger.info(f"[RAG] Guardrail triggered — score {max_score:.4f} below threshold.")
        return (
            "I am the RNSIT Campus Kiosk virtual assistant. I can only answer questions "
            "regarding college departments, staff, timings, locations, and administration. "
            "Please ask a campus-related question."
        )

    history_context = ""
    if history:
        lines = ["--- RECENT CONVERSATION HISTORY ---"]
        for msg in history:
            speaker_val = msg.get("speaker") if isinstance(msg, dict) else getattr(msg, "speaker", None)
            text_val = msg.get("text") if isinstance(msg, dict) else getattr(msg, "text", None)
            if speaker_val and text_val:
                speaker = "Visitor" if str(speaker_val).lower() in ("visitor", "user") else "Kiosk AI"
                lines.append(f"{speaker}: {text_val}")
        lines.append("-----------------------------------")
        history_context = "\n".join(lines) + "\n"

    system_prompt = (
        "You are the official AI Digital Receptionist for RNS Institute of Technology (RNSIT), Bengaluru.\n"
        "Your tone must be warm, helpful, polite, and professional. Keep answers concise (2-4 sentences max) "
        "as they will be displayed on a public kiosk screen.\n\n"
        f"Use the following verified campus facts to answer the visitor:\n{context_text}\n\n"
        "RULES:\n"
        "1. Rely ONLY on the facts above. If the answer is not there, direct the visitor to the Admin Block.\n"
        "2. Do NOT invent phone numbers, emails, or office locations.\n"
        "3. Use conversation history to resolve pronouns like 'he', 'she', 'it', or 'there'.\n"
    )

    full_prompt = f"{system_prompt}\n{history_context}\nNew Visitor Question: {question}\nKiosk AI Response:"

    payload = {
        "model": GENERATE_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            logger.error(f"[Ollama] Status {response.status_code}: {response.text}")
            return "I am having trouble accessing my AI engine. Please try again in a moment."
    except httpx.ConnectError:
        logger.critical(f"[Ollama] Could not connect to {OLLAMA_BASE_URL}. Is Ollama running?")
        return "The kiosk AI engine is currently offline. Please visit the Admin Block for assistance."
    except httpx.TimeoutException:
        logger.warning("[Ollama] Request timed out — model may still be loading.")
        return "The AI engine is taking a moment to spin up. Please try your question again."
    except Exception as e:
        logger.exception(f"[Ollama] Unexpected error: {e}")
        return "An internal error occurred. Please visit the Admin Block."