import os
import json
import asyncio
import anthropic
from llm.base import LLMProvider
from llm.prompts import SYSTEM_PROMPT, build_user_prompt
from schemas import TriageResult

MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 400
REQUEST_TIMEOUT = 15
MAX_INPUT_CHARS = 4000
MAX_RETRIES = 2

# anthropic doesn't have native structured output like openai,
# so we tell the model to return JSON and parse it ourselves
JSON_INSTRUCTIONS = """

Respond ONLY with a valid JSON object with these exact keys:
- "category": one of "Billing", "Bug", "Feature Request", "General"
- "priority": one of "Low", "Med", "High"
- "reply": your drafted reply as a string

No markdown, no explanation, just the raw JSON object."""


class AnthropicProvider(LLMProvider):
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            timeout=REQUEST_TIMEOUT,
        )

    async def triage_ticket(self, subject: str, description: str) -> TriageResult:
        subject = subject[:MAX_INPUT_CHARS]
        description = description[:MAX_INPUT_CHARS]

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    temperature=TEMPERATURE,
                    system=SYSTEM_PROMPT + JSON_INSTRUCTIONS,
                    messages=[
                        {"role": "user", "content": build_user_prompt(subject, description)},
                    ],
                )

                raw = response.content[0].text
                if not raw:
                    raise ValueError("Empty response from model")

                # strip markdown fences if the model wraps them anyway
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1]
                    raw = raw.rsplit("```", 1)[0]

                data = json.loads(raw)
                return TriageResult(**data)

            except (anthropic.APITimeoutError, anthropic.APIError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

        raise RuntimeError(f"LLM call failed after {MAX_RETRIES + 1} attempts: {last_error}")
