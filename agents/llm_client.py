import json
import re

from crewai import LLM
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, MODEL_NAME, GAMEPLAY_MAX_TOKENS, REFLECTION_MAX_TOKENS


def create_llm() -> LLM:
    return LLM(
        model=f"openai/{MODEL_NAME}",
        base_url=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        temperature=0.85,
        max_tokens=GAMEPLAY_MAX_TOKENS,
    )


def create_reflection_llm() -> LLM:
    return LLM(
        model=f"openai/{MODEL_NAME}",
        base_url=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        temperature=0.6,
        max_tokens=REFLECTION_MAX_TOKENS,
    )


def _extract_text(raw) -> str:
    """Safely extract a plain string from whatever llm.call() returns."""
    if isinstance(raw, str):
        return raw
    # CrewAI / LiteLLM ModelResponse object
    if hasattr(raw, "choices") and raw.choices:
        choice = raw.choices[0]
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            return choice.message.content or ""
        if hasattr(choice, "text"):
            return choice.text or ""
    # Fallback: str() coercion
    return str(raw)


def parse_json(text: str) -> dict:
    if not text:
        return {}
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    return {}


def call_llm(llm: LLM, system: str, user: str) -> str:
    try:
        raw = llm.call([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        return _extract_text(raw)
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return ""


def call_llm_json(llm: LLM, system: str, user: str, call_label: str = "") -> dict:
    suffix = "\n\nYour entire response must be a single valid JSON object. No prose before or after. No markdown fences."
    response = call_llm(llm, system, user + suffix)
    result = parse_json(response)
    if not result:
        label_str = f" for {call_label}" if call_label else ""
        print(f"    [WARN] Invalid JSON{label_str} — retrying")
        retry = call_llm(llm, system,
            f"Your previous response was not valid JSON. Return ONLY a JSON object — nothing else.\n\n{user}{suffix}")
        result = parse_json(retry)
        if not result:
            print(f"    [WARN] Retry also failed{label_str} — using empty result")
    return result