"""Adaptive JSON extraction and repair for LLM responses.

LLM responses frequently contain JSON-parsing hazards: leading `<think>` blocks
from reasoning-mode models, markdown fences, smart quotes, trailing commas,
unescaped newlines, single-quoted Python-style strings, Python booleans
(`True`/`False`/`None`), stray BOM and invisible-unicode artifacts, leaked
prose after the closing brace, and control bytes that survived transport.
This module wraps `json.loads` with a cascade of sanitizers and rescue repairs
so callers get a dict back whenever the response is *structurally* JSON, even
if the surface is messy.

Public entry point: `extract_json(text: str) -> Optional[dict]`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional


_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*", re.IGNORECASE)

# Smart-quote and dash family — neutralized to their ASCII equivalents so the
# JSON in the model reply cannot accidentally start with curly-quote junk.
_SMART_QUOTE_MAP = {
    "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'", "‚": "'",
    "–": "-", "—": "-", " ": " ",
}
# Whitespace-ish characters that frequently leak into JSON strings.
_WHITESPACE_REPLACEMENTS = {
    " ": " ", "﻿": "", "​": "", "﻿": "",
    "‌": "", "‍": "",
}

# Python literals → JSON. Applied ONLY outside string literals (see _fix_python_literals).
_PY_LITERAL_TOKENS: tuple[tuple[str, str], ...] = (
    (": null", ": null"),
    (": None", ": null"),
    (": true", ": true"),
    (": True", ": true"),
    (": false", ": false"),
    (": False", ": false"),
    ("'null'", "null"),  # bare null tokens inside arrays etc.
)


# ---------------------------------------------------------------------------
# Universal text-level normalizations
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Apply universal, safe character-level normalizations."""
    for k, v in _SMART_QUOTE_MAP.items():
        text = text.replace(k, v)
    for k, v in _WHITESPACE_REPLACEMENTS.items():
        text = text.replace(k, v)
    # Strip BOM and other invisible leading characters that some transports prepend.
    while text and text[0] in "﻿​‌‍﻿":
        text = text[1:]
    return text


def _strip_think(text: str) -> str:
    """Remove LLM `<think>...</think>` reasoning blocks if present."""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    if cleaned != text:
        return cleaned.strip()
    if _THINK_OPEN_RE.search(text):
        # Orphan opening tag — strip it; the rest is sometimes (not always) clean JSON.
        return _THINK_OPEN_RE.sub("", text).strip()
    return text


def _strip_fences(text: str) -> str:
    """Remove markdown fences around the response."""
    cleaned = _FENCE_RE.sub("", text)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _strip_control_chars(text: str) -> str:
    """Remove stray ASCII control bytes (NUL, 0x01-0x08, 0x0B, 0x0C, 0x0E-0x1F)
    that occasionally survive serialization. \\n, \\r, \\t are NOT stripped — those
    are handled by the inside-string escaper."""
    return "".join(ch for ch in text if (ord(ch) >= 32 or ch in "\n\r\t") and ord(ch) != 127)


# ---------------------------------------------------------------------------
# JSON-slice extraction (string-aware)
# ---------------------------------------------------------------------------

def _balanced_json_slice(text: str) -> Optional[str]:
    """Return the first balanced top-level `{...}` or `[...]` substring, ignoring
    braces that occur inside string literals. Returns None if no balanced slice
    is found before end-of-text."""
    text = text.lstrip()
    candidates = []
    for opener in ("{", "["):
        idx = text.find(opener)
        if idx != -1:
            candidates.append((idx, opener))
    if not candidates:
        return None
    candidates.sort()
    start, opener = candidates[0]
    closer = "}" if opener == "{" else "]"

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ---------------------------------------------------------------------------
# Parsing primitives
# ---------------------------------------------------------------------------

def _try_loads(text: str) -> Optional[Any]:
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _coerce_dict(value: Any) -> Optional[dict]:
    if isinstance(value, dict):
        return value
    return None


# ---------------------------------------------------------------------------
# Repair strategies — each is a `str -> str` transform.
# ---------------------------------------------------------------------------

def _strip_trailing_commas(text: str) -> str:
    """`,` followed by `]` or `}` (possibly with whitespace), plus `, ,` repeats."""
    out = re.sub(r",(\s*[}\]])", r"\1", text)
    out = re.sub(r"(\s*),(\s*,)+", r"\1,", out)
    return out


def _strip_line_comments(text: str) -> str:
    """Remove `// ...` line comments outside string literals."""
    out_lines = []
    for line in text.splitlines():
        # Strip only when comment marker is OUTSIDE a JSON string.
        if "//" in line:
            in_str = False
            escaped = False
            cut = None
            for i, ch in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if ch == "\\" and in_str:
                    escaped = True
                    continue
                if ch == '"':
                    in_str = not in_str
                if ch == "/" and i + 1 < len(line) and line[i + 1] == "/" and not in_str:
                    cut = i
                    break
            if cut is not None:
                line = line[:cut]
        out_lines.append(line)
    return "\n".join(out_lines)


def _fix_unescaped_newlines(text: str) -> str:
    """Escape literal newlines / tabs / carriage-returns inside JSON string literals."""
    out = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_string = True
        out.append(ch)
    return "".join(out)


def _fix_python_literals(text: str) -> str:
    """Replace Python-style True/False/None tokens with JSON true/false/null.

    Only swaps tokens that look like VALUE positions (after `:`, in `[`, or at
    the very start) — never inside string literal contents.
    """
    out: list[str] = []
    in_string = False
    escape = False
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        # Token match — keyword must be in a value position.
        if not in_string and ch in ("T", "F", "N"):
            # Only consider replacing when preceded by a value-position delimiter.
            prev = out[-1] if out else ""
            if prev in (":", ",", "[", " ", "\t", "\n"):
                matched = False
                if text.startswith("True", i):
                    out.append("true")
                    i += 4
                    matched = True
                elif text.startswith("False", i):
                    out.append("false")
                    i += 5
                    matched = True
                elif text.startswith("None", i):
                    out.append("null")
                    i += 4
                    matched = True
                if matched:
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


def _quote_py_strings(text: str) -> str:
    """Convert Python-style single-quoted string literals to JSON double-quoted.
    Operates top-down on braces/brackets and walks each balanced substring."""
    result = []
    i = 0
    n = len(text)
    in_string = False
    quote = '"'
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                result.append(text[i:i + 2])
                i += 2
                continue
            if ch == quote:
                in_string = False
                result.append('"')
                i += 1
                continue
            if ch == '"':
                result.append('\\"')
                i += 1
                continue
            if ch == "\n":
                result.append("\\n")
                i += 1
                continue
            result.append(ch)
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            result.append('"')
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


# Repairs ranked by usefulness. Run *inside a candidate loop* — cascades
# compound them to cover edge-case combinations.
_STRATEGY_TEXT: tuple[Callable[[str], str], ...] = (
    _strip_trailing_commas,
    _strip_line_comments,
    _fix_unescaped_newlines,
    _fix_python_literals,
    lambda t: _fix_unescaped_newlines(_strip_trailing_commas(t)),
    lambda t: _fix_unescaped_newlines(_fix_python_literals(t)),
    lambda t: _strip_trailing_commas(_fix_python_literals(t)),
    lambda t: _fix_unescaped_newlines(_strip_trailing_commas(_fix_python_literals(t))),
    _quote_py_strings,
    lambda t: _quote_py_strings(_strip_trailing_commas(_fix_unescaped_newlines(t))),
)


def _scan_all_balanced(text: str) -> Optional[dict]:
    """Walk every `{` in the text and try to parse each balanced slice."""
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        sliced = _balanced_json_slice(text[i:])
        if not sliced:
            continue
        parsed = _try_loads(sliced)
        if isinstance(parsed, dict):
            return parsed
        for variant in _STRATEGY_TEXT:
            fixed = variant(sliced)
            parsed = _try_loads(fixed)
            if isinstance(parsed, dict):
                return parsed
    return None


def _regex_fallback(text: str) -> dict:
    """REGEX LAST-RESORT extractor.

    Scans the text for `"key": "value"` (or `"key": true`/`null`/`number`) patterns
    and returns whatever pairs can be unambiguously assembled. Used purely when
    *every* JSON strategy has failed. If at least one well-formed pair is found,
    callers get a partial dict instead of `{}`, with the caveat that some fields
    may be missing or truncated.

    Strings are captured from just inside an opening `"` to the next unescaped
    `"` followed by `,` or `}`. Embedded newlines are accepted (escaped on output).
    """
    out: dict[str, Any] = {}
    pattern = re.compile(
        r'"(?P<key>[A-Za-z_][A-Za-z_0-9]*)"\s*:\s*'
        r'(?:"(?P<value>(?:\\.|[^"\\])*)"|(?P<literal>true|false|null|-?\d+(?:\.\d+)?))',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        key = m.group("key")
        if m.group("value") is not None:
            try:
                # Decode escapes so the stored value is a real string.
                value = json.loads('"' + m.group("value") + '"')
            except Exception:
                value = m.group("value")
        else:
            literal = m.group("literal")
            if literal == "true":
                value = True
            elif literal == "false":
                value = False
            elif literal == "null":
                value = None
            else:
                try:
                    value = float(literal) if "." in literal else int(literal)
                except Exception:
                    continue
        out.setdefault(key, value)
    return out


# ---------------------------------------------------------------------------
# Diagnostic dump (used when ALL strategies fail — caller logs this).
# ---------------------------------------------------------------------------

def _diagnostic(report: str, text: str) -> str:
    """Compose a short diagnostic block. `report` is a short prefix line."""
    snippet = text if len(text) <= 600 else text[:300] + " ... (" + str(len(text) - 600) + " chars omitted) ... " + text[-300:]
    # Surface any control chars and the most-common surprising unicode points.
    control = [
        f"U+{ord(c):04X}" for c in text if ord(c) < 32 and c not in "\n\t"
    ][:20]
    smart = [
        f"U+{ord(c):04X}" for c in text if ord(c) in (
            0x2018, 0x2019, 0x201C, 0x201D, 0x2014, 0x2013, 0x00A0, 0x200B, 0x200C, 0x200D, 0xFEFF
        )
    ][:20]
    pieces = [
        report,
        f"text length: {len(text)}",
        f"control chars: {control or 'none'}",
        f"surprising unicode: {smart or 'none'}",
        f"first 300 chars: {text[:300]!r}",
        f"last 300 chars: {text[-300:]!r}",
    ]
    return "\n".join(pieces)


def diagnostic_for_unparseable(text: str) -> str:
    """Public helper for callers — produces a one-shot diagnostic string."""
    return _diagnostic("UNPARSEABLE — all JSON repair strategies failed", text)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _cascade(original: str) -> Optional[dict]:
    """Run strategies in order of increasing aggression."""
    if not original:
        return None

    text = _normalize(original)
    text = _strip_think(text)
    text = _strip_fences(text)
    text = _strip_control_chars(text)

    # 1. Try the cleaned text as-is.
    parsed = _try_loads(text)
    if parsed is not None:
        return _coerce_dict(parsed)

    # 2. Try parsing a balanced JSON slice.
    slice_ = _balanced_json_slice(text)
    if slice_:
        parsed = _try_loads(slice_)
        if parsed is not None:
            return _coerce_dict(parsed)

    # 3. Apply every repair variant to every candidate.
    candidates = [text]
    if slice_:
        candidates.append(slice_)
    for variant in _STRATEGY_TEXT:
        for base in candidates:
            fixed = variant(base)
            parsed = _try_loads(fixed)
            if parsed is not None:
                return _coerce_dict(parsed)

    # 4. Repairs on the *original* (pre-cleaned) text in case cleaning
    #    removed a critical fence character.
    cleaned_orig = _strip_think(original)
    cleaned_orig = _strip_fences(cleaned_orig)
    cleaned_orig = _strip_control_chars(cleaned_orig)
    parsed = _try_loads(cleaned_orig)
    if parsed is not None:
        return _coerce_dict(parsed)
    slice_ = _balanced_json_slice(cleaned_orig)
    if slice_:
        for variant in _STRATEGY_TEXT:
            fixed = variant(slice_)
            parsed = _try_loads(fixed)
            if parsed is not None:
                return _coerce_dict(parsed)

    # 5. Last-ditch: scan every `{` position.
    found = _scan_all_balanced(text)
    if found is not None:
        return found

    # 6. ABSOLUTE FALLBACK — regex-pair extraction. Even if the JSON is
    #    fundamentally broken, recover whatever `key": "value"` pairs we can.
    reg = _regex_fallback(text)
    if reg:
        return reg

    return None


def extract_json(text: str) -> Optional[dict]:
    """Best-effort JSON extraction. Returns the first parsed dict, or None."""
    if not text or not isinstance(text, str):
        return None
    return _cascade(text)


def safe_dumps(obj: Any, **kwargs) -> str:
    """Wrapper around `json.dumps` with safe defaults for prompt emission."""
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("separators", (", ", ": "))
    return json.dumps(obj, **kwargs)
