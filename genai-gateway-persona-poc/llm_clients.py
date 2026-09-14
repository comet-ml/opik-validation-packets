"""
Direct model-provider SDK clients for AcmeChat's persona answer generation —
no LiteLLM. Model strings are `"<provider>/<model>"` (e.g. "openai/gpt-4o-mini");
`generate()` dispatches on the prefix to a real `openai.OpenAI`/`anthropic.Anthropic`
client, each wrapped once at import time with Opik's native `track_openai`/
`track_anthropic` — so cost/token usage on the resulting LLM span is genuine,
computed by Opik from the model name, no manual stamping needed.

TODO(SE): confirm every provider the real customer routes to is covered here
(only OpenAI + Anthropic wired up). Three or more providers is probably where
LiteLLM becomes worth it again.
"""
import os
from typing import Optional

import anthropic
import openai
from dotenv import load_dotenv
from opik.integrations.anthropic import track_anthropic
from opik.integrations.openai import track_openai

load_dotenv()

# Secrets only — never hardcode these.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

_openai_client = (
    track_openai(openai.OpenAI(api_key=OPENAI_API_KEY))
    if OPENAI_API_KEY
    else None
)
_anthropic_client = (
    track_anthropic(anthropic.Anthropic(api_key=ANTHROPIC_API_KEY))
    if ANTHROPIC_API_KEY
    else None
)


def generate(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 500,
    temperature: float = 0.2,
) -> str:
    """Call the real OpenAI or Anthropic SDK based on the `<provider>/<model>` prefix."""
    provider, sep, model_name = model.partition("/")
    if not sep:
        raise ValueError(
            f"model={model!r} is missing a '<provider>/<model>' prefix "
            "(expected e.g. 'openai/gpt-4o-mini' or 'anthropic/claude-haiku-4-5')."
        )

    if provider == "openai":
        return _generate_openai(model_name, system_prompt, user_content, max_tokens, temperature)
    if provider == "anthropic":
        return _generate_anthropic(model_name, system_prompt, user_content, max_tokens, temperature)

    raise ValueError(
        f"Unsupported model provider prefix {provider!r} in model={model!r} "
        "(this PoC's llm_clients.py only wires up 'openai' and 'anthropic')."
    )


def _generate_openai(
    model_name: str, system_prompt: str, user_content: str, max_tokens: int, temperature: float
) -> str:
    if _openai_client is None:
        raise RuntimeError("OPENAI_API_KEY is not configured but an openai/* model was requested.")
    response = _openai_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def _generate_anthropic(
    model_name: str, system_prompt: str, user_content: str, max_tokens: int, temperature: float
) -> str:
    if _anthropic_client is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured but an anthropic/* model was requested.")
    response = _anthropic_client.messages.create(
        model=model_name,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
