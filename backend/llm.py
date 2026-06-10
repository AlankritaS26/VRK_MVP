import os
import json
import math
import httpx
from fastapi import HTTPException

# ==========================================
# CONFIGURATION & GLOBAL VECTOR CACHE
# ==========================================
OLLAMA_BASE_URL = "http://localhost:11434"
GENERATE_MODEL = "llama3.1"
EMBED_MODEL = "nomic-embed-text"

# This assumes your structure is: project_root/backend/app/services/llm.py
# Moving up 3 levels lands at the project root where the 'data' folder lives.
JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "college_info.json")

# Global arrays to cache text chunks and their matching embeddings in memory
KNOWLEDGE_CHUNKS = []
KNOWLEDGE_EMBEDDINGS = []

# ==========================================
# 1. LOCAL OLLAMA EMBEDDING API
# ==========================================
async def get_embedding(text: str) -> list[float]:
    """
    Calls Ollama's local embedding engine to turn a text string 
    into a 768-dimensional vector coordinate list.
    """
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json={"model": EMBED_MODEL, "prompt": text})
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ollama Embedding compilation failed: {e}")

# ==========================================
# 2. MATHEMATICAL COSINE SIMILARITY
# ==========================================
def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Calculates the mathematical cosine similarity score between two vector arrays.
    Returns a float value between 0 (completely different) and 1 (exact semantic match).
    """
    if not vec1 or not vec2:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)

# ==========================================
# 3. DATA EXTRACTION & INGESTION
# ==========================================
async def initialize_rag_knowledge_base():
    """
    Reads college_info.json on startup, flattens the nested structures into clean 
    standalone sentences, and pre-computes their vectors into server memory.
    """
    global KNOWLEDGE_CHUNKS, KNOWLEDGE_EMBEDDINGS
    
    if KNOWLEDGE_CHUNKS: # Prevent reprocessing if already cached in memory
        return

    if not os.path.exists(JSON_PATH):
        print(f"[RAG WARNING] Knowledge base file missing at expected path: {JSON_PATH}")
        return

    with open(JSON_PATH, "r") as file:
        data = json.load(file)

    raw_paragraphs = []
    
    # 1. Parse operational metadata
    c_info = data.get("college", {})
    raw_paragraphs.append(
        f"{c_info.get('name')} ({c_info.get('short_name')}) was established in {c_info.get('established')} "
        f"by founder {c_info.get('founder')}. It is an autonomous {c_info.get('type')} located at {c_info.get('location')}."
    )
    
    # 2. Parse administration details
    admin = data.get("administration", {})
    raw_paragraphs.append(f"The college working hours are {admin.get('working_hours')}.")
    raw_paragraphs.append(f"The Director of RNSIT is {admin.get('director', {}).get('name')}. Contact phone: {admin.get('director', {}).get('phone')}.")
    raw_paragraphs.append(f"The Principal of RNSIT is {admin.get('principal', {}).get('name')}. Contact phone: {admin.get('principal', {}).get('phone')}.")

    # 3. Parse departments structural loop
    for code, details in data.get("departments", {}).items():
        raw_paragraphs.append(
            f"The department of {details.get('name')} ({code.upper()}) is located in the {details.get('block', 'Main campus block')}. "
            f"The Head of Department (HOD) is {details.get('hod', 'the appointed department head')} and the student intake capacity is {details.get('intake', '180')} students per year."
        )

    # 4. Parse facilities segments
    for name, details in data.get("facilities", {}).items():
        if isinstance(details, dict):
            raw_paragraphs.append(
                f"Facility: {name.replace('_', ' ').title()}. Details: {details.get('name', '')} {details.get('location', '')} {details.get('timings', '')} {details.get('details', '')}."
            )

    # 5. Parse placement stats
    placements = data.get("placements", {})
    raw_paragraphs.append(f"RNSIT placements feature over {placements.get('total_companies')} total companies. Major recent recruiters include: {', '.join(placements.get('recent_recruiters', []))}.")
    for year, stats in placements.get("stats", {}).items():
        raw_paragraphs.append(f"In the year {year} placement cycle, the highest package (CTC) offered was {stats.get('highest_ctc_lpa')} LPA.")

    print(f"[RAG] Generated {len(raw_paragraphs)} distinct factual paragraphs. Compiling vectors...")
    
    # Generate vector coordinates for every single paragraph segment sequentially
    KNOWLEDGE_CHUNKS = raw_paragraphs
    for paragraph in raw_paragraphs:
        vector = await get_embedding(paragraph)
        KNOWLEDGE_EMBEDDINGS.append(vector)
    
    print("🚀 [RAG SUCCESS] Core Knowledge Base vector grid loaded into server memory.")

# ==========================================
# 4. SEMANTIC SEARCH & LLM INFERENCE
# ==========================================
async def retrieve_relevant_context(user_query: str, top_k: int = 3) -> str:
    """
    Embeds the user query, compares vectors using cosine similarity, 
    and picks the top K closest matching context strings.
    """
    global KNOWLEDGE_CHUNKS, KNOWLEDGE_EMBEDDINGS
    
    query_vector = await get_embedding(user_query)
    if not query_vector:
        return "No context found."

    scored_chunks = []
    for idx, chunk_vector in enumerate(KNOWLEDGE_EMBEDDINGS):
        score = cosine_similarity(query_vector, chunk_vector)
        scored_chunks.append((score, KNOWLEDGE_CHUNKS[idx]))

    # Sort chunks strictly by their similarity scores (index 0) in descending order
    scored_chunks.sort(key=lambda x: x, reverse=True)
    
    # Take the text content of the top matching segments
    top_matches = [chunk for score, chunk in scored_chunks[:top_k]]
    return "\n\n".join(top_matches)

async def generate_rag_kiosk_response(question: str, history: list = None) -> str:
    """
    Generates a response using local semantic context search combined with 
    a rolling short-term conversation history buffer.
    """
    # 1. FIXED: Retrieve matching factual text directly as a string
    context_text = await retrieve_relevant_context(question, top_k=3)

    # 2. FIXED: Safely format rolling history using string casting to protect Enums
    history_context = ""
    if history:
        history_context = "\n--- RECENT CONVERSATION HISTORY ---\n"
        for msg in history:
            speaker_val = getattr(msg, "speaker", None) or (msg.get("speaker") if isinstance(msg, dict) else None)
            text_val = getattr(msg, "text", None) or (msg.get("text") if isinstance(msg, dict) else None)
            
            if speaker_val and text_val:
                speaker = "Visitor" if str(speaker_val).lower() in ["visitor", "user"] else "Kiosk AI"
                history_context += f"{speaker}: {text_val}\n"
        history_context += "-----------------------------------\n"

    # 3. Construct the brain prompt with both permanent facts and conversational memory
    system_prompt = (
        "You are the official AI Digital Receptionist for RNS Institute of Technology (RNSIT), Bengaluru.\n"
        "Your tone must be warm, helpful, polite, and professional. Keep answers concise (2-4 sentences max) "
        "as they will be displayed on a public kiosk screen.\n\n"
        f"Use the following official verified campus facts to answer the visitor:\n{context_text}\n\n"
        "CRITICAL RULES:\n"
        "1. Rely ONLY on the verified facts above. If the answer cannot be found there, politely direct them to the Admin Block window.\n"
        "2. Do NOT invent phone numbers, emails, or office locations.\n"
        "3. Use the conversation history below to resolve pronouns like 'he', 'she', 'it', 'there', or 'his'.\n"
    )

    full_prompt = f"{system_prompt}\n{history_context}\nNew Visitor Question: {question}\nKiosk AI Response:"

    # 4. Stream the compiled prompt to your local Llama model
    payload = {
        "model": "llama3.1",
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.3  # Lower temperature keeps the response factual and precise
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            raise Exception(f"Ollama returned error status: {response.status_code}")