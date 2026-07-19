import json
import re
import os
import threading
from datetime import datetime
from typing import Optional, Type, TypeVar, Dict, Any
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError, RateLimitError
from config import (
    NVIDIA_API_KEYS,
    NVIDIA_BASE_URL,
    MODEL_NAME,
    GAMEPLAY_MAX_TOKENS,
    REFLECTION_MAX_TOKENS,
    LOGS_DIR,
)
from agents.json_repair import extract_json as _extract_json
from agents.json_repair import diagnostic_for_unparseable as _diagnostic_for_unparseable

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    ValidationError = Exception

T = TypeVar("T", bound="BaseModel")


_RETRIABLE_EXC = (RateLimitError, APIConnectionError, APITimeoutError)


def _is_retriable(exc: Exception) -> bool:
    """Return True for errors that another key (or another attempt) might recover from."""
    if isinstance(exc, _RETRIABLE_EXC):
        return True
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status is None:
            return True
        # 408 request timeout, 429 too many requests, 5xx server errors
        return status == 408 or status == 429 or status >= 500
    return False


class KeyRotator:
    """Cycles through a pool of NVIDIA API keys.

    `current` yields the active OpenAI client. `rotate()` advances to the next
    key and returns its client, wrapping back to the first after the last.
    The rotator is process-wide (one instance per process) so callers share
    state: when gameplay hits a rate limit on key1, reflection's next call
    starts on key2 instead of burning key1 again.
    """

    def __init__(self, keys, base_url, label_prefix="key"):
        self._keys = list(keys)
        if not self._keys:
            raise RuntimeError(
                "No NVIDIA API keys configured. Set NVIDIA_API_KEY1/2/3 in .env."
            )
        self._clients = [OpenAI(api_key=k, base_url=base_url) for k in self._keys]
        self._index = 0
        self._lock = threading.Lock()
        # Stable labels per key for logging ("key1", "key2", ...)
        self._labels = [f"{label_prefix}{i + 1}" for i in range(len(self._keys))]

    def __len__(self) -> int:
        return len(self._clients)

    def _label(self, idx: int) -> str:
        return self._labels[idx]

    def current(self):
        with self._lock:
            return self._clients[self._index], self._label(self._index)

    def rotate(self):
        with self._lock:
            self._index = (self._index + 1) % len(self._clients)
            return self._clients[self._index], self._label(self._index)

    def reset(self):
        with self._lock:
            self._index = 0


# Shared across gameplay + reflection clients so quota pressure on one pool
# is visible to the other.
_ROTATOR = KeyRotator(NVIDIA_API_KEYS, NVIDIA_BASE_URL) if NVIDIA_API_KEYS else None


def create_llm() -> dict:
    if _ROTATOR is None:
        raise RuntimeError(
            "No NVIDIA API keys configured. Set NVIDIA_API_KEY1/2/3 in .env."
        )
    return {
        "rotator": _ROTATOR,
        "model": MODEL_NAME,
        "temperature": 0.85,
        "max_tokens": GAMEPLAY_MAX_TOKENS,
    }


def create_reflection_llm() -> dict:
    if _ROTATOR is None:
        raise RuntimeError(
            "No NVIDIA API keys configured. Set NVIDIA_API_KEY1/2/3 in .env."
        )
    return {
        "rotator": _ROTATOR,
        "model": MODEL_NAME,
        "temperature": 0.6,
        "max_tokens": REFLECTION_MAX_TOKENS,
    }


def _call(llm: dict, messages: list) -> str:
    rotator: KeyRotator = llm["rotator"]
    request_kwargs = dict(
        model=llm["model"],
        messages=messages,
        temperature=llm["temperature"],
        max_tokens=llm["max_tokens"],
        extra_body={"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": True}},
        stream=False,
    )

    # Two full sweeps across the key pool before giving up on this call.
    # Each retriable error advances the rotator; the next call resumes where
    # the previous one left off, and keeps looping around indefinitely.
    max_attempts = max(1, 2 * len(rotator))
    last_exc = None
    for attempt in range(max_attempts):
        if attempt == 0:
            client, label = rotator.current()
        else:
            client, label = rotator.rotate()
        try:
            response = client.chat.completions.create(**request_kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            last_exc = e
            if not _is_retriable(e):
                print(f"    [LLM ERROR] [{label}] non-retriable: {e}")
                return ""
            next_label = (
                rotator._labels[(rotator._index + 1) % len(rotator)]
                if attempt + 1 < max_attempts
                else None
            )
            err_name = type(e).__name__
            if next_label is not None:
                print(
                    f"    [LLM RETRY] [{label}] {err_name}: {e} -> rotating to {next_label}"
                )
            else:
                print(
                    f"    [LLM RETRY] [{label}] {err_name}: {e} -> wrapping back to first key"
                )

    print(
        f"    [LLM ERROR] Exhausted {max_attempts} attempts across {len(rotator)} keys: {last_exc}"
    )
    return ""


# Adapter that re-exports json_repair.extract_json under the historical name
# used elsewhere in this file. `_extract_json` returns a dict or None.
__all__ = ["call_llm_json", "call_llm_json_prefill", "log_llm_call", "_extract_json"]


def _try_parse_dict(value: Any) -> Optional[dict]:
    """Coerce arbitrary JSON-decoded output to a dict (lists, scalars rejected)."""
    return value if isinstance(value, dict) else None


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
    "\n\nOUTPUT CONTRACT — read carefully:\n"
    "- Your entire reply must be ONE JSON object. Nothing else.\n"
    "- The very first character of your reply must be '{'. The very last must be '}'.\n"
    "- No prose, no greetings, no analysis, no <think> blocks, no markdown fences "
    "(```), no trailing prose after the closing brace.\n"
    "- All your reasoning goes INSIDE the JSON fields (private_note, internal_note, reasoning).\n"
    "- Use only standard ASCII double-quotes for JSON strings. No smart quotes.\n"
    "- Escape any internal quotes with \\\". Escape any literal newline as \\n.\n"
    "- Do NOT add fields not in the schema. Do NOT omit required fields."
)

_JSON_SYSTEM_ADDON = (
    "\n\n=== OUTPUT FORMAT (NON-NEGOTIABLE) ===\n"
    "Respond with EXACTLY ONE valid JSON object and nothing else.\n"
    "Rules:\n"
    "  1. First character = '{', last character = '}'.\n"
    "  2. NO prose before the '{' or after the '}'. No greetings, no sign-offs.\n"
    "  3. NO markdown code fences (```). NO <think>...</think> blocks.\n"
    "  4. NO analysis or reasoning outside JSON fields — internal thinking\n"
    "     belongs in private_note / internal_note / reasoning fields.\n"
    "  5. Use straight ASCII double quotes only. No smart quotes.\n"
    "  6. Escape inner quotes with \\\" and inner newlines as \\n.\n"
    "  7. Include every required field shown in the user prompt's JSON template.\n"
    "Failure to comply will be discarded and retried — replies cost the table time."
)

_FORMATTER_SYSTEM = (
    "You are a strict JSON formatter. The previous reply failed JSON validation.\n"
    "Return ONLY the corrected JSON object, matching the user prompt's template.\n"
    "Hard rules:\n"
    "  - First character = '{', last character = '}'. No fences. No prose.\n"
    "  - Straight double quotes only. Escape inner newlines as \\n.\n"
    "  - Output the JSON, period."
)


def call_llm_json(
    llm: dict,
    system: str,
    user: str,
    call_label: str = "",
    schema: Optional[Type[T]] = None,
    max_retries: int = 2
) -> dict:
    """Call LLM with JSON-enforced output. Validates against schema if provided.

    Uses a repair-tolerant parser (`agents.json_repair`) before declaring a JSON
    failure, so think-block leakage, smart quotes, stray fences, trailing
    commas, etc. are silently normalized on attempt 1.
    """
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

        result = _try_parse_dict(_extract_json(text))
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

    # Final fallback: append a *full diagnostic* to warns.txt so future
    # parse failures can be diagnosed without rerunning the experiment.
    final_label_str = f" for {call_label}" if call_label else ""
    retry_warn = f"[WARN] All retries failed{final_label_str} — using empty result"
    print(f"    {retry_warn}")
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "warns.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{retry_warn}\n")
        f.write(_diagnostic_for_unparseable(last_text or "") + "\n")
        f.write("---\n")
    return {}


def call_llm_json_prefill(
    llm: dict,
    system: str,
    user: str,
    prefill: str,
    call_label: str = "",
    schema: Optional[Type[T]] = None
) -> dict:
    """Like `call_llm_json` but with a custom assistant prefill to force output structure.
    Falls back to repair-tolerant parsing before declaring a JSON failure, and
    retries once with the strict formatter system prompt if that fails too."""
    augmented_system = system + _JSON_SYSTEM_ADDON
    augmented_user = user + _JSON_SUFFIX

    messages = [
        {"role": "system", "content": augmented_system},
        {"role": "user", "content": augmented_user},
        {"role": "assistant", "content": prefill},
    ]

    text = _call(llm, messages)
    # Strip the prefill from the response if model echoes it back
    if prefill and text.startswith(prefill[1:]):
        text = text[len(prefill) - 1:]

    result = _try_parse_dict(_extract_json(text)) if text else None
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

    # One formatter retry — same pattern as `call_llm_json` but bounded to one shot.
    try:
        messages = [
            {"role": "system", "content": _FORMATTER_SYSTEM},
            {"role": "user", "content": augmented_user},
            {"role": "assistant", "content": prefill or "{"},
        ]
        text = _call(llm, messages)
        if prefill and text.startswith(prefill[1:]):
            text = text[len(prefill) - 1:]
        result = _try_parse_dict(_extract_json(text)) if text else None
        if result and _validate_output(result, schema):
            return result
    except Exception:
        pass

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