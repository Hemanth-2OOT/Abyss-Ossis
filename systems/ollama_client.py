import requests
from config import DEFAULT_MODEL
from core.logger import get_logger

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
TIMEOUT_SECONDS = 120

# Reduced default token cap to protect against runaway generations
DEFAULT_NUM_PREDICT = 768

logger = get_logger(__name__)


def unload_active_models():
    """Unloads all currently loaded models from Ollama."""
    try:
        res = requests.get("http://localhost:11434/api/ps", timeout=2)
        if res.status_code == 200:
            models = [m["name"] for m in res.json().get("models", [])]
            for m in models:
                requests.post(
                    "http://localhost:11434/api/generate",
                    json={"model": m, "keep_alive": 0},
                    timeout=2
                )
    except Exception as e:
        logger.debug(f"Failed to unload active models: {e}")

def chat_ollama(messages, model=None, temperature=None, stream=False, num_predict=None):
    """
    Send a chat request to the local Ollama instance.

    Returns the assistant's reply as a string, or a generator if stream=True.
    Raises RuntimeError if Ollama is unreachable.
    """
    from core.resource_monitor import watchdog
    
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": True,  # ALWAYS stream internally for watchdog cancellation
        "think": False,
        "options": {
            "temperature": temperature if temperature is not None else 0.2,
            "num_predict": num_predict if num_predict is not None else DEFAULT_NUM_PREDICT
        }
    }

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            stream=True
        )
        response.raise_for_status()
        
        def generate():
            import json
            for line in response.iter_lines():
                watchdog.check()
                if line:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]
                        
        if stream:
            return generate()
        else:
            return "".join(list(generate()))

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Cannot connect to Ollama at localhost:11434. "
            "Is Ollama running? Try: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Ollama request timed out after {TIMEOUT_SECONDS}s. "
            "The model may be overloaded or the prompt too large."
        )
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Ollama returned HTTP error: {e}")
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Unexpected Ollama response format: {e}")