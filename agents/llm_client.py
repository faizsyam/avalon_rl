import json
import re
import os
from datetime import datetime
from typing import Optional, Type, TypeVar, Dict, Any
from openai import OpenAI
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, MODEL_NAME, GAMEPLAY_MAX_TOKENS, REFLECTION_MAX_TOKENS, LOGS_DIR

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    ValidationError = Exception

T = TypeVar("T", bound="BaseModel")


def _make_client() -> OpenAI:
    return OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)


def create_llm() -> dict:
    return {
        "client": _make_client(),
        "model": MODEL_NAME,
        "temperature": 0.85,
        "max_tokens": GAMEPLAY_MAX_TOKENS,
    }


def create_reflection_llm() -> dict:
    return {
        "client": _make_client(),
        "model": MODEL_NAME,
        "temperature": 0.6,
        "max_tokens": REFLECTION_MAX_TOKENS,
    }


def _call(llm: dict, messages: list) -> str:
    try:
        response = llm["client"].chat.completions.create(
            model=llm["model"],
            messages=messages,
            temperature=llm["temperature"],
            max_tokens=llm["max_tokens"],
            extra_body={"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": True}},
            stream=False
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return ""


def _extract_json(text: str) -> str:
    """Extract first valid JSON object from text, handling markdown fences."""
    if not text:
        return ""
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    depth = 0
    in_string = False
    escape = False
    start = -1
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start:i+1]
    return ""


def _parse_json_strict(text: str) -> Optional[dict]:
    """Parse JSON strictly, return dict or None."""
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _validate_output(output: dict, schema: Optional[Type[T]] = None) -> bool:
    """Validate output dict against Pydantic schema if available."""
    if not PYDANTIC_AVAILABLE or schema is None:
        return True
    try:
        schema(**output)
        return True
    except ValidationError:
        return False


def _format_validation_error(e: ValidationError) -> str:
    """Format Pydantic validation error for retry prompt."""
    errors = []
    for err in e.errors():
        loc = " -> ".join(str(x) for x in err["loc"])
        errors.append(f"  {loc}: {err['msg']}")
    return "Validation errors:\n" + "\n".join(errors)


_JSON_SUFFIX = (
    "\n\nYour entire response must be a single valid JSON object. "
    "No prose before or after. No markdown fences. "
    "Do NOT write any analysis or reasoning outside the JSON. "
    "All thoughts belong inside JSON fields (e.g. private_note, reasoning, internal_note)."
)

_JSON_SYSTEM_ADDON = (
    "\n\n=== RESPONSE FORMAT (NON-NEGOTIABLE) ===\n"
    "Your ENTIRE response must be a single valid JSON object.\n"
    "Do NOT write any text, reasoning, or analysis outside the JSON object.\n"
    "Do NOT use markdown fences. Start your response with '{' and end with '}'.\n"
    "Put all your thinking inside the appropriate JSON fields "
    "(private_note, internal_note, reasoning, etc.)."
)

_FORMATTER_SYSTEM = (
    "You are a JSON repair assistant. You receive a malformed JSON attempt and must "
    "output ONLY a corrected, valid JSON object matching the implied schema. "
    "No explanations. No markdown. Start with '{' and end with '}'."
)


def call_llm_json(
    llm: dict,
    system: str,
    user: str,
    call_label: str = "",
    schema: Optional[Type[T]] = None,
    max_retries: int = 2
) -> dict:
    """Call LLM with JSON-enforced output. Validates against schema if provided."""
    augmented_system = system + _JSON_SYSTEM_ADDON
    augmented_user = user + _JSON_SUFFIX

    messages = [
        {"role": "system", "content": augmented_system},
        {"role": "user", "content": augmented_user},
        {"role": "assistant", "content": "{"},
    ]

    last_text = ""
    log_path = ""
    for attempt in range(max_retries + 1):
        text = _call(llm, messages)
        last_text = text
        if not text:
            continue

        json_str = _extract_json(text)
        if not json_str:
            continue

        result = _parse_json_strict(json_str)
        if result and _validate_output(result, schema):
            return result

        # Prepare retry with validation feedback
        label_str = f" for {call_label}" if call_label else ""
        warn = f"[WARN] Invalid JSON{label_str} (attempt {attempt+1}/{max_retries+1})"
        print(f"    {warn}")

        os.makedirs(LOGS_DIR, exist_ok=True)
        log_path = os.path.join(LOGS_DIR, "warns.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"Timestamp  : {datetime.utcnow().isoformat()} UTC\n")
            f.write(f"Warning    : {warn}\n")
            f.write(f"call_label : {call_label}\n")
            f.write(f"attempt    : {attempt+1}\n")
            f.write(f"response   : {text}\n")

        if attempt < max_retries:
            retry_user = augmented_user
            if schema and PYDANTIC_AVAILABLE:
                try:
                    model_instance = schema()
                    schema_json = model_instance.model_json_schema()
                    retry_user += f"\n\nPrevious output failed validation. Expected JSON schema:\n{json.dumps(schema_json, indent=2)}"
                except Exception:
                    pass

            messages = [
                {"role": "system", "content": _FORMATTER_SYSTEM},
                {"role": "user", "content": retry_user},
                {"role": "assistant", "content": "{"},
            ]

    # Final fallback: return empty dict
    final_label_str = f" for {call_label}" if call_label else ""
    retry_warn = f"[WARN] All retries failed{final_label_str} — using empty result"
    print(f"    {retry_warn}")
    if os.path.exists(log_path):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{retry_warn}\nlast_response: {last_text}\n")
    return {}


def call_llm_json_prefill(
    llm: dict,
    system: str,
    user: str,
    prefill: str,
    call_label: str = "",
    schema: Optional[Type[T]] = None
) -> dict:
    """Like call_llm_json but with a custom assistant prefill to force output structure."""
    augmented_system = system + _JSON_SYSTEM_ADDON
    augmented_user = user + _JSON_SUFFIX

    messages = [
        {"role": "system", "content": augmented_system},
        {"role": "user", "content": augmented_user},
        {"role": "assistant", "content": prefill},
    ]

    text = _call(llm, messages)
    # Strip the prefill from the response if model echoes it back
    if text.startswith(prefill[1:]):
        text = text[len(prefill) - 1:]
    json_str = _extract_json(text) if text else ""
    if json_str:
        result = _parse_json_strict(json_str)
        if result and _validate_output(result, schema):
            return result

    label_str = f" for {call_label}" if call_label else ""
    warn = f"[WARN] Invalid JSON prefill{label_str} — retrying with formatter"
    print(f"    {warn}")
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "warns.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"Timestamp  : {datetime.utcnow().isoformat()} UTC\n")
        f.write(f"Warning    : {warn}\n")
        f.write(f"call_label : {call_label}\n")
        f.write(f"response   : {text}\n")
    return {}


def log_llm_call(
    call_label: str,
    system: str,
    user: str,
    response: str,
    parsed: dict,
    game_id: Optional[int] = None,
    phase: Optional[str] = None,
    role: Optional[str] = None,
    slot_id: Optional[int] = None,
    temperature: float = 0.85,
    tokens_used: Optional[int] = None,
):
    """Log a complete LLM interaction for debugging/analysis."""
    import json
    from datetime import datetime
    from config import LOGS_DIR
    import re

    os.makedirs(os.path.join(LOGS_DIR, "llm_calls"), exist_ok=True)
    safe_label = re.sub(r'[^a-zA-Z0-9_-]', '_', call_label)
    suffix = f"_g{game_id:03d}" if game_id else ""
    filename = f"{safe_label}{suffix}_{slot_id if slot_id is not None else ''}.jsonl"
    path = os.path.join(LOGS_DIR, "llm_calls", filename)

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "call_label": call_label,
        "game_id": game_id,
        "phase": phase,
        "role": role,
        "slot_id": slot_id,
        "temperature": temperature,
        "tokens_used": tokens_used,
        "system_prompt": system,
        "user_prompt": user,
        "raw_response": response,
        "parsed_output": parsed,
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")