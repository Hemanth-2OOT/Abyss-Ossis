import requests
from config import MODEL
from core.logger import get_logger

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
TIMEOUT_SECONDS = 120

# Hard cap on generated tokens per call. Without this, a model that starts
# generating runaway <think> reasoning (or just rambling) has no upper bound
# and can run for many minutes while pinning CPU/GPU, with no error surfaced
# to the user — the streaming connection stays "alive" the whole time so
# TIMEOUT_SECONDS never fires.
DEFAULT_NUM_PREDICT = 2048

logger = get_logger(__name__)


def chat_ollama(messages, model=None, temperature=None, stream=False, num_predict=None):
    """
    Send a chat request to the local Ollama instance.

    Returns the assistant's reply as a string, or a generator if stream=True.
    Raises RuntimeError if Ollama is unreachable.
    """
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "stream": stream,
        # Disable hidden reasoning/<think> blocks for models that support it
        # (e.g. qwen3). Ollama ignores this option for models that don't
        # support thinking mode, so it's safe to always include.
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
            stream=stream
        )
        response.raise_for_status()
        
        if stream:
            def generate():
                import json
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        yield data["message"]["content"]
            return generate()
        else:
            data = response.json()
            return data["message"]["content"]

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