import os
import json
import asyncio
from openai import AsyncOpenAI, APITimeoutError, APIError
from llm.base import LLMProvider
from llm.prompts import SYSTEM_PROMPT, build_user_prompt
from schemas import TriageResult

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.2          # low but not zero — keeps classification consistent
                            # while letting the reply sound natural
MAX_OUTPUT_TOKENS = 400     # plenty of headroom for a short reply + two enum fields
REQUEST_TIMEOUT = 15        # don't let a hanging API call freeze the user's browser
MAX_INPUT_CHARS = 4000      # cap input length to avoid huge costs on long pastes
MAX_RETRIES = 2             # retry transient failures before giving up


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=REQUEST_TIMEOUT,
        )

    async def triage_ticket(self, subject: str, description: str) -> TriageResult:
        # truncate oversized input
        subject = subject[:MAX_INPUT_CHARS]
        description = description[:MAX_INPUT_CHARS]

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=MODEL,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(subject, description)},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "triage_result",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "category": {
                                        "type": "string",
                                        "enum": ["Billing", "Bug", "Feature Request", "General"],
                                    },
                                    "priority": {
                                        "type": "string",
                                        "enum": ["Low", "Med", "High"],
                                    },
                                    "reply": {"type": "string"},
                                },
                                "required": ["category", "priority", "reply"],
                                "additionalProperties": False,
                            },
                        },
                    },
                )

                choice = response.choices[0]

                # if the model got cut off mid-JSON, treat it as a failure
                # so we retry instead of trying to parse broken output
                if choice.finish_reason == "length":
                    raise ValueError("Response was truncated before completion")

                raw = choice.message.content
                if not raw:
                    raise ValueError("Empty response from model")

                data = json.loads(raw)
                return TriageResult(**data)

            except (APITimeoutError, APIError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    # backoff briefly before retrying
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

        raise RuntimeError(f"LLM call failed after {MAX_RETRIES + 1} attempts: {last_error}")
