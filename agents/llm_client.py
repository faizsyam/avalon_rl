import json
import re
import os
from datetime import datetime
from openai import OpenAI
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, MODEL_NAME, GAMEPLAY_MAX_TOKENS, REFLECTION_MAX_TOKENS, LOGS_DIR


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
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return ""


def parse_json(text: str) -> dict:
    if not text:
        return {}

    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    valid_candidates: list[dict] = []
    for start in (m.start() for m in re.finditer(r"\{", text)):
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start=start):
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
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start: i + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            valid_candidates.append(result)
                    except json.JSONDecodeError:
                        pass
                    break

    if valid_candidates:
        return valid_candidates[-1]

    return {}


def call_llm(llm: dict, system: str, user: str) -> str:
    return _call(llm, [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


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


def call_llm_json(llm: dict, system: str, user: str, call_label: str = "") -> dict:
    augmented_system = system + _JSON_SYSTEM_ADDON
    augmented_user = user + _JSON_SUFFIX

    messages = [
        {"role": "system", "content": augmented_system},
        {"role": "user", "content": augmented_user},
        {"role": "assistant", "content": "{"},
    ]

    text = _call(llm, messages)
    result = parse_json("{" + text) if text else {}
    if result:
        return result

    label_str = f" for {call_label}" if call_label else ""
    warn_message = f"[WARN] Invalid JSON{label_str} — retrying"
    print(f"    {warn_message}")

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "warns.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"Timestamp  : {datetime.utcnow().isoformat()} UTC\n")
        f.write(f"Warning    : {warn_message}\n")
        f.write(f"call_label : {call_label}\n")
        f.write(f"response   : {text}\n")

    retry_messages = [
        {
            "role": "system",
            "content": (
                "You are a JSON formatter. Your only job is to output a single valid JSON object. "
                "No prose. No markdown. No reasoning. Start with '{' and end with '}'."
            ),
        },
        {"role": "user", "content": f"Output ONLY the JSON object.\n\n{augmented_user}"},
        {"role": "assistant", "content": "{"},
    ]

    retry_text = _call(llm, retry_messages)
    retry_result = parse_json("{" + retry_text) if retry_text else {}

    if not retry_result:
        retry_warn = f"[WARN] Retry also failed{label_str} — using empty result"
        print(f"    {retry_warn}")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{retry_warn}\nretry_response: {retry_text}\n")

    return retry_result