import json
import urllib.request
import urllib.error

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:e2b"


class OllamaResponse:
    def __init__(self, content: str):
        self.content = content


class OllamaClient:
    def invoke(self, prompt: str) -> OllamaResponse:
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64,
        }
        return OllamaResponse(self._call_ollama(payload))

    def _call_ollama(self, payload: dict) -> str:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return f"[Ollama error: {exc}]"

        if isinstance(body, dict):
            if "response" in body:
                return body["response"]
            if "content" in body:
                return body["content"]
            if "choices" in body and body["choices"]:
                first = body["choices"][0]
                return first.get("message", {}).get("content", "") or first.get("content", "")
        return json.dumps(body)


llm = OllamaClient()

