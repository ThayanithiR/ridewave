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


class OpenRouterAssistant:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        self.model = settings.OPENROUTER_MODEL
        self.enabled = settings.AI_ENABLED and bool(self.api_key)

    async def generate_response(self, user_prompt: str, context_data: dict[str, Any]) -> str:
        """
        Executes free-tier inference using OpenRouter with authorized database context.
        Falls back gracefully if the provider is unavailable or quota is exceeded.
        """
        if not self.enabled:
            # Deterministic, zero-cost graceful fallback
            return (
                f"AI Trip Assistant (Offline Mode): Here is your authorized trip information: "
                f"{context_data}"
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Authorized User Trip Context: {context_data}"},
            {"role": "user", "content": user_prompt},
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": 250,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    return f"Trip Assistant: Unable to reach AI model ({resp.status_code}). Here is your trip data: {context_data}"
        except Exception:
            return f"Trip Assistant: AI service temporarily unavailable. Here is your trip record: {context_data}"


assistant_service = OpenRouterAssistant()
