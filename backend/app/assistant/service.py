from typing import Any
import httpx

from app.core.config import settings

SYSTEM_PROMPT = """
You are RideWave's authorized AI Trip Assistant.
Rules:
1. Always use provided trip context to answer user questions truthfully.
2. NEVER guess, invent fares, change ride status, or calculate unauthorized prices.
3. Keep answers concise, helpful, and polite.
"""


class AITripAssistant:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.enabled = settings.AI_ENABLED

    async def generate_response(self, user_prompt: str, context_data: dict[str, Any]) -> str:
        """
        Executes free-to-run inference via local Ollama or free OpenRouter models.
        The AI assistant is strictly off the critical path of ride operations and degrades gracefully.
        """
        if not self.enabled:
            return (
                f"AI Trip Assistant (Offline Mode): Here is your authorized trip information: "
                f"{context_data}"
            )

        # 1. Local Ollama Provider (Default free-to-run local model)
        if self.provider == "ollama":
            prompt = (
                f"{SYSTEM_PROMPT}\n"
                f"Trip Context: {context_data}\n"
                f"User Question: {user_prompt}\n"
                f"Assistant:"
            )
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        f"{settings.OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": settings.OLLAMA_MODEL,
                            "prompt": prompt,
                            "stream": False,
                        },
                    )
                    if resp.status_code == 200:
                        return resp.json().get("response", "").strip()
            except Exception:
                pass
            return (
                f"Trip Assistant (Local Fallback): Unable to reach local Ollama daemon. "
                f"Your trip summary: {context_data}"
            )

        # 2. OpenRouter Free Catalog Provider
        if self.provider == "openrouter" and settings.OPENROUTER_API_KEY:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": f"Authorized User Trip Context: {context_data}"},
                {"role": "user", "content": user_prompt},
            ]
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": settings.OPENROUTER_MODEL,
                            "messages": messages,
                            "temperature": 0.2,
                            "max_tokens": 250,
                        },
                    )
                    if resp.status_code == 200:
                        return resp.json()["choices"][0]["message"]["content"]
            except Exception:
                pass

        return f"Trip Assistant: AI service unavailable. Here is your trip data: {context_data}"


assistant_service = AITripAssistant()
