import requests
from core.logger import get_logger

logger = get_logger(__name__)

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
EMBED_TIMEOUT = 30  # seconds — prevents indefinite hang on cold model start

def embed_text(texts):
    if isinstance(texts, str):
        texts = [texts]

    payload = {
        "model": EMBED_MODEL,
        "input": texts
    }

    try:
        response = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=EMBED_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [])
    except Exception as e:
        logger.error(f"Failed to get embeddings from Ollama: {e}")
        return []