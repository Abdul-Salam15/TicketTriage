import os
import json
import asyncio
from google import genai
from google.genai import types
from llm.base import LLMProvider
from llm.prompts import SYSTEM_PROMPT, build_user_prompt
from schemas import TriageResult

MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 400
REQUEST_TIMEOUT = 15
MAX_INPUT_CHARS = 4000
MAX_RETRIES = 2

JSON_INSTRUCTIONS = """

Respond ONLY with a valid JSON object with these exact keys:
- "category": one of "Billing", "Bug", "Feature Request", "General"
- "priority": one of "Low", "Med", "High"
- "reply": your drafted reply as a string

No markdown, no explanation, just the raw JSON object."""


class GeminiProvider(LLMProvider):
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    async def triage_ticket(self, subject: str, description: str) -> TriageResult:
        subject = subject[:MAX_INPUT_CHARS]
        description = description[:MAX_INPUT_CHARS]

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.aio.models.generate_content(
                    model=MODEL,
                    contents=build_user_prompt(subject, description),
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT + JSON_INSTRUCTIONS,
                        temperature=TEMPERATURE,
                        max_output_tokens=MAX_OUTPUT_TOKENS,
                    ),
                )

                raw = response.text
                if not raw:
                    raise ValueError("Empty response from model")

                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1]
                    raw = raw.rsplit("```", 1)[0]

                data = json.loads(raw)
                return TriageResult(**data)

            except (json.JSONDecodeError, ValueError, Exception) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

        raise RuntimeError(f"LLM call failed after {MAX_RETRIES + 1} attempts: {last_error}")
