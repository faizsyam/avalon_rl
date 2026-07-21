import os
import re
from typing import Dict, List, Optional

from config import LESSONS_DIR, EVIL_COORD_FILE, GOOD_COORD_FILE
from game.roles import ROLES_CONFIG, EVIL_COORD_PHASES, GOOD_COORD_PHASES, ALL_ROLES, PHASE_DESCRIPTIONS
from agents.llm_client import call_llm_json

# Per-phase caps: shared by lesson files and coordination files alike.
TENTATIVE_CAP = 5
ACTIVE_CAP = 5
CONSOLIDATION_THRESHOLD = 3

# All phase names that may appear in lesson files (validation / debugging).
PHASES_ALL = ("discussion", "proposal", "vote", "mission", "assassin")

# Phase-specific required action words (word stems, matched with word boundaries).
# Discussion stems are kept broad because the phase covers many verbal moves
# (challenge, demand, press, etc.) — restricting to act-of-speaking verbs alone
# produced false rejections on otherwise high-quality lessons.
# Proposal stems also extended with composition verbs (add, drop, remove, pair)
# that the LLM reaches for when no other word fits. Mission stems admit the
# observational verbs good players need ("note", "observe", "evaluate") since
# only evil actually plays cards; the FAIL/SUCCESS substring check below
# enforces that a *decision* or *outcome* is named regardless.
PHASE_ACTION_STEMS = {
    "discussion": [
        # Speech acts & verbal moves
        "say", "frame", "ask", "accuse", "deflect", "signal", "name", "propose", "steer",
        "demand", "challenge", "press", "question", "probe", "warn", "blame",
        "attack", "defend", "counter", "support", "agree", "disagree",
        "express", "withhold", "doubt", "claim", "downplay", "disclose",
        "interpret", "spot", "notice", "call", "suggest",
        "skip", "veto", "second", "echo", "parrot", "mirror",
        # Strategic-speech moves the LLM reaches for that previously dropped lessons
        "avoid", "expose", "reveal", "raise", "highlight", "flag", "lobby",
        "speculate", "predict", "anticipate", "address",
    ],
    "proposal": [
        # Team composition verbs
        "propose", "pick", "choose", "select", "include", "exclude", "team", "test",
        "add", "drop", "remove", "pair", "put", "extend", "reform", "draft",
        "build", "shape", "form", "size", "carry", "trust", "restructure",
        # Strategic moves that should land in proposal rather than other phases
        "avoid", "veto", "block", "lead", "anchor",
    ],
    "vote": ["approve", "reject", "vote"],
    "mission": [
        "fail", "success", "play",
        "succeed", "pass", "note", "observe", "track", "evaluate", "judge",
        "weight", "assess", "treat", "complete", "submit", "decline",
    ],
    "assassin": ["guess", "target", "identify", "name", "select", "pick", "decide", "choose", "eliminate", "rule", "narrow", "evaluate", "judge"],
}

_GENERIC_ACTION_VERBS = frozenset({
    "use", "make", "take", "give", "show", "keep", "find", "try", "need",
    "let", "get", "set", "put", "look", "watch", "tell", "speak", "talk",
    "listen", "hear", "think", "believe", "consider", "decide", "determine",
    "confirm", "suspect", "doubt", "figure", "check", "verify", "weigh",
    "balance", "compare", "identify", "track", "recognize", "distinguish",
    "separate", "sort", "count", "note", "record", "mark", "remember",
    "focus", "concentrate", "prioritize", "rank", "order", "manage",
    "control", "handle", "direct", "guide", "lead", "follow", "pursue",
    "avoid", "prevent", "protect", "guard", "cover", "hide", "conceal",
    "mask", "disguise", "bluff", "lie", "mislead", "distract", "confuse",
    "pressure", "force", "push", "pull", "draw", "attract", "divert",
    "shift", "change", "adjust", "adapt", "modify", "correct", "fix",
    "resolve", "settle", "commit", "execute", "perform", "deliver",
    "produce", "cause", "trigger", "arrange", "plan", "prepare",
    "signal", "communicate", "indicate", "imply", "hint", "suggest",
    "reveal", "expose", "uncover", "demonstrate", "prove",
    "disprove", "narrow",
})

VAGUE_PHRASES = (
    "be careful", "watch everyone", "be cautious", "read the room",
    "trust steady players", "pay attention", "stay alert", "be aware",
    "be smart", "play well", "make good choices",
)


def validate_lesson(lesson: str, phase: str) -> tuple[bool, str]:
    """Canonical lesson validator. Returns (is_valid, reason_if_invalid).
    Used by both the reflector (to reject malformed LLM emissions) and by
    consolidate_lessons (to filter anything that slipped past the LLM)."""
    if not lesson or not lesson.strip():
        return False, "empty lesson"

    body = normalize_lesson_body(lesson)
    return validate_lesson_body(body, phase)


def validate_coordination_lesson(lesson: str, phase: str) -> tuple[bool, str]:
    """Coordination files (evil/good coordination) describe cross-game team-coordination
    rules, not single-game outcomes. They are allowed to omit the literal outcome tag
    the role-validator demands, because reliability-style tags like "(reliable on WIN,
    untested on LOSS)" carry the same commitment. The structural requirements that
    *cannot* be falsified — "When ", "because ", phase-appropriate action verb, length
    — still hold for coord files so the file stays machine-readable."""
    if not lesson or not lesson.strip():
        return False, "empty lesson"
    body = normalize_lesson_body(lesson)
    return validate_lesson_body(body, phase, require_outcome_tag=False)


def normalize_lesson_body(lesson: str) -> str:
    """Strip the leading "- [gXXX]" / "- [DEPRECATED gXXX]" prefix and any
    leading dash, and any trailing {grounding: ...} suffix,
    so the body can be validated on its own."""
    s = lesson.strip()
    s = re.sub(r'^-\s*\[(?:DEPRECATED\s+)?g\d+\]\s*', '', s)
    s = re.sub(r'^-\s*', '', s).strip()
    s = re.sub(r'\s+', ' ', s)
    # Strip grounding metadata suffix
    s = re.sub(r'\s*\{grounding:\s*[^}]+\}\s*$', '', s).strip()
    return s


def validate_lesson_body(body: str, phase: str, require_outcome_tag: bool = True) -> tuple[bool, str]:
    """Validate an already-normalized lesson body (marker prefix + dash stripped,
    whitespace collapsed). Returns (is_valid, reason_if_invalid).

    `require_outcome_tag` defaults True (role files). Coordination files pass False
    — their rules aggregate across many games and don't admit a single-game outcome
    tag."""
    if not body:
        return False, "empty lesson"

    words = body.split()
    if len(words) > 35:
        return False, f"exceeds 35 words ({len(words)})"
    if not body.startswith("When "):
        return False, "must start with 'When '"

    # The phase-specific action-stem check below enforces the "do Y" verb;
    # treating bare REJECT/FAIL-style tokens as equivalent. Skipping an
    # extra " do " substring check avoids rejecting lessons that lead with
    # the action verb directly ("When X, REJECT because...").
    if " because " not in body and " Because " not in body and not re.search(r"\bbecause\b", body, re.IGNORECASE):
        return False, "must contain ' because ' (causal reason)"

    has_win = "(observed on WIN)" in body
    has_loss = "(observed on LOSS)" in body
    if require_outcome_tag:
        if not (has_win or has_loss):
            return False, "must end with '(observed on WIN)' or '(observed on LOSS)'"
        if has_win and has_loss:
            return False, "cannot have both WIN and LOSS tags"

    # Phase-specific required action content.
    if phase == "vote":
        if not re.search(r"\bAPPROVE\b|\bREJECT\b", body):
            return False, "vote lesson must specify APPROVE or REJECT"
    elif phase == "mission":
        # Lessons concern the OUTCOME (success/fail) of a quest — for card-players
        # who decide FAIL vs SUCCESS, and for good roles who observe outcomes.
        # Accept any case and verb form ('SUCCESS', 'succeeds', '0-fail', 'failed',
        # 'passed', 'clean pass', etc.). The case-sensitive FAIL/SUCCESS check
        # rejected otherwise-solid lessons for stylistic wording.
        outcome_signal = re.search(
            r"\bSUCCESS\b|\bFAIL(?:S|ED|URE)?\b|\bSUCCEED(?:S|ED|ING)?\b|"
            r"\bPASS(?:ES|ED|ING)?\b|0\s*-\s*fail|0\s*-\s*pass|clean\s+pass",
            body,
            re.IGNORECASE,
        )
        if not outcome_signal:
            return False, "mission lesson must specify FAIL or SUCCESS"
    elif phase == "assassin":
        if "guess" not in body.lower() and "target" not in body.lower():
            return False, "assassin lesson must mention guess or target"

    # Phase-specific required action stem (word-boundary, case-insensitive).
    # Cascading check: first try phase-specific stems, then fall back to
    # generic action verbs. Only reject if NEITHER matches — this catches
    # obvious non-action lessons like "When X, the game is hard because Y"
    # while accepting valid lessons whose verbs happen to be outside the
    # phase-specific list.
    action_stems = PHASE_ACTION_STEMS.get(phase, [])
    if action_stems:
        if not any(re.search(rf'\b{re.escape(stem)}\w*\b', body, re.IGNORECASE) for stem in action_stems):
            if not any(re.search(rf'\b{re.escape(v)}\w*\b', body, re.IGNORECASE) for v in _GENERIC_ACTION_VERBS):
                return False, f"phase '{phase}' lesson must contain a phase-appropriate action verb"

    lower_body = body.lower()
    for vague in VAGUE_PHRASES:
        if vague in lower_body:
            return False, f"contains vague filler: '{vague}'"

    return True, ""


def _filter_valid_lessons(parsed: dict, phases: list, game_id: int, *,
                         validator=validate_lesson) -> dict:
    """Remove any invalid lessons from active/tentative zones after LLM consolidation.
    `validator` defaults to the strict role validator; coord callers pass
    `validate_coordination_lesson` so coord lessons without a literal outcome tag
    are kept."""
    for phase in phases:
        for zone in ("active", "tentative"):
            lst = parsed["dimensions"][phase][zone]
            valid = []
            for lesson in lst:
                ok, _ = validator(lesson, phase)
                if ok:
                    valid.append(lesson)
                else:
                    # Move invalid to deprecated
                    deprecated_entry = (
                        f"- [DEPRECATED g{game_id:03d}] {lesson.lstrip('- ')}"
                        f" — auto-deprecated: invalid format"
                    )
                    parsed["dimensions"][phase]["deprecated"].append(deprecated_entry)
            parsed["dimensions"][phase][zone] = valid
    return parsed


def _auto_promote_aged_tentative(parsed: dict, current_game_id: int) -> dict:
    """Promote any tentative entry whose [gXXX] tag list does NOT include the
    current game into ACTIVE.

    Why this exists: the consolidator's LLM call rarely merges two near-duplicate
    tentative entries across games (it varies wording round-to-round). Without a
    mechanical promotion path, tentative zones fill the cap, new insights are
    silently dropped on _apply_delta, and lesson learning stalls. Any lesson that
    has survived at least one round without being deprecated has, by definition,
    accumulated enough evidence to enter ACTIVE."""
    for phase in parsed["dimensions"]:
        tentative = list(parsed["dimensions"][phase].get("tentative", []))
        still_tentative = []
        for entry in tentative:
            tag_ids = [int(m) for m in re.findall(r"\[g(\d+)\]", entry) if m.isdigit()]
            if tag_ids and all(t < current_game_id for t in tag_ids):
                parsed["dimensions"][phase].setdefault("active", []).append(entry)
            else:
                still_tentative.append(entry)
        parsed["dimensions"][phase]["tentative"] = still_tentative
    return parsed


def repair_lesson(lesson: str, phase: str, faction_won=None) -> str | None:
    """Deterministic best-effort repair of a malformed lesson.

    Repairs:
      1. Strip leading "- [gXXX]" / "- [DEPRECATED gXXX]" prefix and dash.
      2. Collapse runs of whitespace.
      3. Append a missing outcome tag (only if `faction_won` is known — exit
         code is observable from the game, not fabricated from thin air).
      4. Truncate to ≤35 words while preserving the trailing outcome tag.

    After repair we re-run `validate_lesson_body`. If validation still
    fails (typically because the body is missing `because` or doesn't
    start with `When ` — content we cannot fabricate) we return `None`
    so the caller drops the lesson instead of silently writing bad data.

    Parameters
    ----------
    lesson : str
        Raw lesson text emitted by the LLM.
    phase : str
        Phase bucket the lesson belongs to. Drives the action-stem check
        in validation.
    faction_won : Optional[bool]
        Whether the lesson's faction won the game. Used to attach a
        missing outcome tag. If `None` and the tag is absent, no repair
        is attempted for that issue.
    """
    body = normalize_lesson_body(lesson)
    if not body:
        return None

    has_win = "(observed on WIN)" in body
    has_loss = "(observed on LOSS)" in body
    outcome_tag = None
    if has_win and not has_loss:
        outcome_tag = "(observed on WIN)"
    elif has_loss and not has_win:
        outcome_tag = "(observed on LOSS)"
    elif faction_won is not None:
        outcome_tag = "(observed on WIN)" if faction_won else "(observed on LOSS)"
        if not body.endswith("."):
            body = body + "."
        body = body + " " + outcome_tag

    words = body.split()
    if len(words) > 35:
        if outcome_tag:
            tag_words = outcome_tag.split()
            non_tag_words = [w for w in words if w not in tag_words]
            head_budget = 35 - len(tag_words)
            non_tag_words = non_tag_words[: max(head_budget, 1)]
            body = " ".join(non_tag_words) + " " + outcome_tag
        else:
            body = " ".join(words[:35])

    ok, _ = validate_lesson_body(body, phase)
    return body if ok else None


def ensure_dirs():
    os.makedirs(LESSONS_DIR, exist_ok=True)


def get_lesson_path(role: str) -> str:
    return os.path.join(LESSONS_DIR, f"{role.lower()}.txt")


def _init_lesson_file(role: str) -> str:
    phases = ROLES_CONFIG[role]["phases"]
    path = get_lesson_path(role)
    _init_file(path, role.upper(), phases)
    return open(path).read()


def _init_evil_coord() -> str:
    _init_file(EVIL_COORD_FILE, "EVIL COORDINATION MEMORY", EVIL_COORD_PHASES)
    return open(EVIL_COORD_FILE).read()


def _init_good_coord() -> str:
    _init_file(GOOD_COORD_FILE, "GOOD COORDINATION MEMORY", GOOD_COORD_PHASES)
    return open(GOOD_COORD_FILE).read()


def _parse(content: str, phases: List[str]) -> Dict:
    """Parse a lesson file keyed by phase. The internal dict key stays 'dimensions'
    for minimal churn — its keys ARE phase names. ACTIVE/TENTATIVE/DEPRECATED zones."""
    parsed = {
        "header": [],
        "dimensions": {p: {"active": [], "tentative": [], "deprecated": []} for p in phases}
    }
    current_dim = None
    current_zone = None

    for line in content.split("\n"):
        stripped = line.strip()
        matched_dim = next((p for p in phases if stripped == f"[{p}]"), None)
        if matched_dim:
            current_dim = matched_dim
            current_zone = None
        elif stripped == "ACTIVE:":
            current_zone = "active"
        elif stripped == "TENTATIVE:":
            current_zone = "tentative"
        elif stripped == "DEPRECATED:":
            current_zone = "deprecated"
        elif current_dim and current_zone and stripped.startswith("-"):
            parsed["dimensions"][current_dim][current_zone].append(stripped)
        elif not current_dim:
            parsed["header"].append(line)

    return parsed


def _serialize(parsed: Dict, phases: List[str]) -> str:
    lines = [l for l in parsed["header"] if l is not None]
    lines.append("")
    for phase in phases:
        p = parsed["dimensions"].get(phase, {"active": [], "tentative": [], "deprecated": []})
        lines += [f"[{phase}]", "ACTIVE:"] + p["active"] + \
                 ["TENTATIVE:"] + p["tentative"] + \
                 ["DEPRECATED:"] + p["deprecated"] + [""]
    return "\n".join(lines)


def _bump_version(parsed: Dict, game_id: int) -> Dict:
    new_header = []
    for line in parsed["header"]:
        if line.startswith("version:"):
            try:
                v = int(line.split(":")[1].strip()) + 1
            except Exception:
                v = 1
            new_header.append(f"version: {v}")
        elif line.startswith("last_updated:"):
            new_header.append(f"last_updated: game_{game_id:03d}")
        else:
            new_header.append(line)
    parsed["header"] = new_header
    return parsed


def _parse_file(path: str, phases: List[str]) -> Dict:
    content = open(path, "r", encoding="utf-8").read()
    return _parse(content, phases)


def _phase_block(parsed: Dict, phase: str) -> Dict:
    """The lesson entries for one phase, keyed by zone."""
    return parsed["dimensions"].get(phase, {"active": [], "tentative": [], "deprecated": []})


def _resolve_phase(dimensions: Dict, raw_phase: str) -> Optional[str]:
    """Resolve a raw phase string to a valid phase key in the dimensions dict."""
    raw = raw_phase.strip().lower()
    if raw in dimensions:
        return raw
    # Try common abbreviations/typos
    aliases = {
        "discuss": "discussion",
        "prop": "proposal",
        "props": "proposal",
        "voting": "vote",
        "missions": "mission",
        "kill": "assassin",
        "guess": "assassin",
    }
    return aliases.get(raw)


def _format_phase(entries: Dict, phase: str) -> str:
    """Compact rendering of one phase's active + tentative lessons for injection."""
    active = entries.get("active", [])
    tentative = entries.get("tentative", [])
    if not active and not tentative:
        return ""
    out = [f"[{phase}]"]
    if active:
        out.append("CONFIRMED:")
        out.extend(active)
    if tentative:
        if active:
            out.append("")
        out.append("PROVISIONAL:")
        out.extend(tentative)
    return "\n".join(out)


def load_lessons(role: str, phase: str) -> str:
    """Return ONLY this phase's confirmed+tentative lessons for a role, compactly formatted.
    Empty string if the role has no lessons for this phase. Phase lessons are injected into
    the per-phase user prompt (NOT the cached system prompt)."""
    path = get_lesson_path(role)
    if not os.path.exists(path):
        return ""
    parsed = _parse_file(path, ROLES_CONFIG[role]["phases"])
    if phase not in parsed["dimensions"]:
        return ""
    return _format_phase(parsed["dimensions"][phase], phase)


def load_evil_coord(phase: str) -> str:
    if not os.path.exists(EVIL_COORD_FILE):
        return ""
    parsed = _parse_file(EVIL_COORD_FILE, EVIL_COORD_PHASES)
    if phase not in parsed["dimensions"]:
        return ""
    return _format_phase(parsed["dimensions"][phase], phase)


def load_good_coord(phase: str) -> str:
    if not os.path.exists(GOOD_COORD_FILE):
        return ""
    parsed = _parse_file(GOOD_COORD_FILE, GOOD_COORD_PHASES)
    if phase not in parsed["dimensions"]:
        return ""
    return _format_phase(parsed["dimensions"][phase], phase)


def snapshot_all_lessons(role: str) -> str:
    """Full file content across all phases — used for the evaluator's lesson-stability
    metric (compares consecutive whole-files line-by-line). Independent of phase."""
    path = get_lesson_path(role)
    if not os.path.exists(path):
        return ""
    return open(path, "r", encoding="utf-8").read()


def snapshot_all_coord(kind: str) -> str:
    """Full content of a coordination file. kind: 'evil' or 'good'."""
    path = EVIL_COORD_FILE if kind == "evil" else GOOD_COORD_FILE
    if not os.path.exists(path):
        return ""
    return open(path, "r", encoding="utf-8").read()


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts."""
    w1 = _content_words(text1)
    w2 = _content_words(text2)
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def _normalize_lesson(lesson: str) -> str:
    """Strip the [gXXX]/[DEPRECATED ...]/ leading-dash metadata so the lesson body
    can be matched on its own. Used for both near-dup detection and keyword-based
    promotion/deprecation so we compare apples to apples."""
    s = lesson.strip()
    s = re.sub(r'^-\s*\[(?:DEPRECATED\s+)?g\d+\]\s*', '', s)
    s = re.sub(r'^-\s*', '', s)
    return s.strip().lower()


def _is_near_duplicate(lesson: str, existing: List[str], threshold: float = 0.7) -> bool:
    """True if `lesson` has ≥`threshold` Jaccard similarity to any existing lesson
    in the same phase's active+tentative zone. Returns False when existing is empty."""
    target_words = set(_normalize_lesson(lesson).split()) - _STOPWORDS
    if not target_words:
        return False
    for prior in existing:
        prior_words = set(_normalize_lesson(prior).split()) - _STOPWORDS
        if not prior_words:
            continue
        union = target_words | prior_words
        if len(union) == 0:
            continue
        overlap = len(target_words & prior_words) / len(union)
        if overlap >= threshold:
            return True
    return False


_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "is", "are", "was", "were",
    "to", "of", "in", "on", "at", "for", "with", "by", "as", "be", "do",
    "does", "did", "has", "have", "had", "this", "that", "these", "those",
    "i", "we", "you", "they", "he", "she", "it",
})


def _match_lesson_phrase(lesson: str, keyword: str) -> bool:
    """Match a reflector's `keyword` to a stored lesson entry.

    Three-tier matching, in order of decreasing strictness:
      1. Whole substring containment (most precise: "team composition signal"
         matches only lessons literally containing that phrase).
      2. Word-boundary containment with ALL keyword tokens in any order
         (catches "team composition" and "composition of the team" but rejects
         the single-word "fail" matching every lesson mentioning fails).
      3. As a final fallback, hard floor: keywords of <4 chars or that
         match a too-common word are rejected outright.

    Generic words like 'evil', 'fail', 'team' can no longer accidentally
    promote unrelated lessons because they must either appear as a literal
    substring OR all appear as standalone tokens (each ≥4 chars or with the
    stopword filter applied).
    """
    norm = _normalize_lesson(lesson)
    key = keyword.strip().lower()
    if not key:
        return False
    if key in norm:
        return True
    # Tier 2: all keyword tokens must appear as tokens (with the stopword
    # filter excluding the most common function-words). Reject when key is
    # clearly too short or generic to be a reliable selector.
    key_tokens = [t for t in re.findall(r"[a-z]+", key) if t not in _STOPWORDS and len(t) >= 3]
    if not key_tokens or len(key_tokens) == 0:
        # All tokens filtered out as stopwords/too-short — refuse ambiguous match.
        return False
    norm_word_set = set(re.findall(r"[a-z]+", norm)) - _STOPWORDS
    return all(t in norm_word_set for t in key_tokens)


def _words_in_order(haystack: str, words: List[str]) -> bool:
    pos = 0
    for w in words:
        idx = haystack.find(w, pos)
        if idx < 0:
            return False
        pos = idx + len(w)
    return True
# Backward-compat re-export — older callers may still import `_words_in_order`.
__all__ = ("_words_in_order",)


def _write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    written = open(path, "r", encoding="utf-8").read()
    if len(written) < 50:
        raise RuntimeError(f"_write to {path} produced suspiciously short file ({len(written)} chars)")


def _apply_delta(parsed: Dict, delta: dict, game_id: int) -> tuple[Dict, set]:
    tag = f"[g{game_id:03d}]"
    skipped_phases = set()

    # ---- add_tentative ----
    for item in delta.get("add_tentative", []):
        if not isinstance(item, dict):
            continue
        raw_phase = item.get("phase", "") or item.get("dimension", "")
        lesson = item.get("lesson", "").strip()
        if "<" in raw_phase or "<" in lesson or not raw_phase.strip() or not lesson:
            continue
        phase = _resolve_phase(parsed["dimensions"], raw_phase)
        if not phase:
            continue

        existing_tentative = parsed["dimensions"][phase]["tentative"]
        if len(existing_tentative) >= TENTATIVE_CAP:
            skipped_phases.add(phase)
            continue

        all_existing = existing_tentative + parsed["dimensions"][phase]["active"]
        if _is_near_duplicate(lesson, all_existing):
            continue

        grounding = item.get("grounding", "").strip()
        grounding_suffix = f" {{grounding: {grounding}}}" if grounding else ""
        parsed["dimensions"][phase]["tentative"].append(f"- {tag} {lesson}{grounding_suffix}")

    for item in delta.get("confirm_active", []):
        if not isinstance(item, dict):
            continue
        raw_phase = item.get("phase", "") or item.get("dimension", "")
        lesson_text = item.get("lesson", "").strip()
        keyword = item.get("keyword", "").lower().strip()
        phase = _resolve_phase(parsed["dimensions"], raw_phase)
        if not phase:
            continue
        if not lesson_text and not keyword:
            continue

        tentative = parsed["dimensions"][phase]["tentative"]
        for i, t in enumerate(tentative):
            match = False
            if lesson_text:
                norm_target = _normalize_lesson(lesson_text)
                norm_stored = _normalize_lesson(t)
                match = lesson_text in t or norm_target in norm_stored
            elif keyword:
                match = _match_lesson_phrase(t, keyword)
            if match:
                parsed["dimensions"][phase]["active"].append(t)
                tentative.pop(i)
                break

    for item in delta.get("flag_deprecated", []):
        if not isinstance(item, dict):
            continue
        raw_phase = item.get("phase", "") or item.get("dimension", "")
        lesson_text = item.get("lesson", "").strip()
        keyword = item.get("keyword", "").lower().strip()
        reason = item.get("reason", "").strip()
        phase = _resolve_phase(parsed["dimensions"], raw_phase)
        if not phase:
            continue
        if not lesson_text and not keyword:
            continue
        for zone in ("active", "tentative"):
            lst = parsed["dimensions"][phase][zone]
            for i, line in enumerate(lst):
                match = False
                if lesson_text:
                    norm_target = _normalize_lesson(lesson_text)
                    norm_stored = _normalize_lesson(line)
                    match = lesson_text in line or norm_target in norm_stored
                elif keyword:
                    match = _match_lesson_phrase(line, keyword)
                if match:
                    deprecated_entry = (
                        f"- [DEPRECATED {tag}] {line.lstrip('- ')}"
                        + (f" — {reason}" if reason else "")
                    )
                    parsed["dimensions"][phase]["deprecated"].append(deprecated_entry)
                    lst.pop(i)
                    break

    return parsed, skipped_phases

def apply_lesson_delta(role: str, delta: dict, game_id: int) -> set:
    return _apply_delta_to_path(get_lesson_path(role), ROLES_CONFIG[role]["phases"], delta, game_id)


def apply_evil_coord_delta(delta: dict, game_id: int) -> set:
    return _apply_delta_to_path(EVIL_COORD_FILE, EVIL_COORD_PHASES, delta, game_id)


def apply_good_coord_delta(delta: dict, game_id: int) -> set:
    return _apply_delta_to_path(GOOD_COORD_FILE, GOOD_COORD_PHASES, delta, game_id)


def _apply_delta_to_path(path: str, phases: List[str], delta: dict, game_id: int) -> set:
    """Single apply path for role lesson files AND coordination files.
    Returns the set of phases where lessons were skipped due to tentative cap."""
    if not os.path.exists(path):
        # Initialize with the right headers and phase structure on first write.
        header_label = os.path.basename(path).replace(".txt", "").upper().replace("_", " ")
        _init_file(path, header_label, phases)
    parsed = _parse_file(path, phases)
    parsed, skipped_phases = _apply_delta(parsed, delta, game_id)
    parsed = _bump_version(parsed, game_id)
    _write(path, _serialize(parsed, phases))
    return skipped_phases


def _init_file(path: str, header_label: str, phases: List[str]):
    """Initialize any lesson file (per-role or per-faction coordination) with the
    canonical empty structure."""
    content = _serialize({
        "header": [f"=== {header_label} LESSONS ===", "version: 0", "last_updated: none"],
        "dimensions": {p: {"active": [], "tentative": [], "deprecated": []} for p in phases}
    }, phases)
    _write(path, content)


def _consolidate_system(role_or_label: str, dim_desc: str, active_max: int, tentative_max: int) -> str:
    return (
        f"You are consolidating the strategic memory file for the {role_or_label} role in Avalon.\n"
        f"This file is organized by GAME PHASE. Phase meanings:\n{dim_desc}\n"
        f"Each lesson MUST follow the exact format: 'When X, do Y because Z. (observed on WIN|LOSS)' — ≤35 words.\n"
        f"Rules:\n"
        f"- Trigger (When X) must be a concrete, observable game state (score, fail count, proposal number, specific player behavior)\n"
        f"- Action (do Y) must be a specific decision: APPROVE/REJECT, include/exclude player, FAIL/SUCCESS, speech framing, guess target\n"
        f"- Reason (because Z) must cite game mechanics\n"
        f"- Phase must match where the trigger occurs and action is taken\n"
        f"- NO vague filler: reject 'be careful', 'watch everyone', 'trust steady players', 'read the room'\n"
        f"Ensure each lesson is under 35 words and placed in the correct phase. Be strict."
    )


def _consolidate_user(current: str, active_max: int, tentative_max: int) -> str:
    return (
        f"Current lessons file:\n\n{current}\n\n"
        f"TASKS — apply all strictly:\n"
        f"1. MERGE & PROMOTE: If 2+ TENTATIVE lessons in the same phase share the same core rule "
        f"(even if worded differently), merge into ONE sharp 'When X, do Y because Z' rule "
        f"and PROMOTE to ACTIVE. Combine outcome tags (e.g. 'WIN x2, LOSS x1').\n"
        f"2. CONTRADICTIONS: If two lessons in the same phase contradict, "
        f"keep the more specific/actionable one; deprecate the other with reason "
        f"'contradicts retained lesson'.\n"
        f"3. PROMOTE BY EVIDENCE: Any TENTATIVE lesson with [gXXX] tags from 2+ distinct games "
        f"MUST be moved to ACTIVE.\n"
        f"4. PURGE VAGUE: DELETE any lesson that is vague ('be careful', 'watch everyone'), "
        f"phase-inappropriate, or factually wrong about game mechanics.\n"
        f"5. ENFORCE CAPS: ACTIVE max {active_max} per phase. TENTATIVE max {tentative_max} per phase. "
        f"Excess → DEPRECATED with reason 'cap exceeded — lower priority version'.\n"
        f"6. OUTCOME RELIABILITY TAGS: Add in parentheses after outcome tag:\n"
        f"   - '(reliable on WIN, untested on LOSS)' if only WIN tags\n"
        f"   - '(reliable on LOSS, untested on WIN)' if only LOSS tags\n"
        f"   - '(robust)' if confirmed on BOTH outcomes\n"
        f"7. PRESERVE STRUCTURE: Exact file structure — header lines, [phase] tags, "
        f"ACTIVE:/TENTATIVE:/DEPRECATED: zones.\n\n"
        'Return JSON only: {"updated_file": "complete updated file as a single string"}'
    )


def _restore_dropped_active(updated_parsed, original_parsed, phases):
    """Never silently drop pre-existing active lessons during consolidation."""
    for phase in phases:
        orig_active = set(original_parsed["dimensions"][phase]["active"])
        new_active = set(updated_parsed["dimensions"][phase]["active"])
        new_deprecated = set(updated_parsed["dimensions"][phase]["deprecated"])
        for lesson in orig_active:
            if lesson not in new_active and lesson not in new_deprecated:
                updated_parsed["dimensions"][phase]["active"].append(lesson)
    return updated_parsed


def consolidate_lessons(role: str, llm, game_id: int):
    """LLM-driven consolidation pass for a single role's phase-bucketed lesson file."""
    consolidate_file(get_lesson_path(role), ROLES_CONFIG[role]["phases"], role, llm, game_id,
                     active_cap=ACTIVE_CAP, tentative_cap=TENTATIVE_CAP,
                     validator=validate_lesson)


def consolidate_evil_coord(llm, game_id: int):
    consolidate_file(EVIL_COORD_FILE, EVIL_COORD_PHASES, "evil coordination", llm, game_id,
                     active_cap=3, tentative_cap=2,
                     validator=validate_coordination_lesson)


def consolidate_good_coord(llm, game_id: int):
    consolidate_file(GOOD_COORD_FILE, GOOD_COORD_PHASES, "good coordination", llm, game_id,
                     active_cap=3, tentative_cap=2,
                     validator=validate_coordination_lesson)


def consolidate_file(path: str, phases, label: str, llm, game_id: int,
                     active_cap: int, tentative_cap: int,
                     validator=validate_lesson):
    """Single consolidation entry point shared by role and coordination files.

    `validator` is the lesson-shape validator; coord callers pass
    `validate_coordination_lesson` so coord rules without a literal outcome tag
    survive the filter pass. Use of `_auto_promote_aged_tentative` ensures that
    lessons that have aged past the current round move to ACTIVE, even when the
    LLM-driven merger step does not produce a duplicate."""
    if not os.path.exists(path):
        return
    current = open(path, "r", encoding="utf-8").read()
    dim_desc = "\n".join(f"  {p}: {PHASE_DESCRIPTIONS[p]}" for p in phases)
    system = _consolidate_system(label, dim_desc, active_cap, tentative_cap)
    user = _consolidate_user(current, active_cap, tentative_cap)
    result = call_llm_json(llm, system, user)
    updated = result.get("updated_file", "")
    if not updated or len(updated) < 100:
        return

    updated_parsed = _parse(updated, phases)
    original_parsed = _parse(current, phases)
    updated_parsed = _restore_dropped_active(updated_parsed, original_parsed, phases)
    # Mechanical promotion FIRST so LLM consolidation cannot accidentally
    # re-promote (or lose) an already-stable rule into the deprecated pile.
    updated_parsed = _auto_promote_aged_tentative(updated_parsed, game_id)
    updated_parsed = _filter_valid_lessons(updated_parsed, phases, game_id, validator=validator)
    updated_parsed = _bump_version(updated_parsed, game_id)
    _write(path, _serialize(updated_parsed, phases))


def should_consolidate_now(tentative_threshold: int = CONSOLIDATION_THRESHOLD) -> bool:
    """True if any role file OR either coordination file has a phase whose tentative
    count has hit the threshold. Checks all files so consolidation isn't missed."""
    for role in ALL_ROLES:
        path = get_lesson_path(role)
        if not os.path.exists(path):
            continue
        parsed = _parse_file(path, ROLES_CONFIG[role]["phases"])
        for p in ROLES_CONFIG[role]["phases"]:
            if len(parsed["dimensions"][p]["tentative"]) >= tentative_threshold:
                return True

    for label, filepath, phases in [
        ("evil", EVIL_COORD_FILE, EVIL_COORD_PHASES),
        ("good", GOOD_COORD_FILE, GOOD_COORD_PHASES),
    ]:
        if not os.path.exists(filepath):
            continue
        parsed = _parse_file(filepath, phases)
        for p in phases:
            if len(parsed["dimensions"][p]["tentative"]) >= tentative_threshold:
                return True

    return False


def get_lesson_stats() -> dict:
    """Per-phase lesson counts (active / tentative / deprecated) for every role and
    coordination file, plus phase totals. Used for monitoring learning health."""
    stats = {}

    for role in ALL_ROLES:
        path = get_lesson_path(role)
        phases = ROLES_CONFIG[role]["phases"]
        if not os.path.exists(path):
            stats[role] = {"active": 0, "tentative": 0, "deprecated": 0, "by_phase": {}}
            continue
        parsed = _parse_file(path, phases)
        totals = {"active": 0, "tentative": 0, "deprecated": 0}
        by_phase = {}
        for p in phases:
            zone_counts = {z: len(parsed["dimensions"][p][z]) for z in ("active", "tentative", "deprecated")}
            by_phase[p] = zone_counts
            for z in ("active", "tentative", "deprecated"):
                totals[z] += zone_counts[z]
        stats[role] = {**totals, "by_phase": by_phase}

    for label, filepath, phases in [
        ("evil_coord", EVIL_COORD_FILE, EVIL_COORD_PHASES),
        ("good_coord", GOOD_COORD_FILE, GOOD_COORD_PHASES),
    ]:
        if not os.path.exists(filepath):
            stats[label] = {"active": 0, "tentative": 0, "deprecated": 0, "by_phase": {}}
            continue
        parsed = _parse_file(filepath, phases)
        totals = {"active": 0, "tentative": 0, "deprecated": 0}
        by_phase = {}
        for p in phases:
            zone_counts = {z: len(parsed["dimensions"][p][z]) for z in ("active", "tentative", "deprecated")}
            by_phase[p] = zone_counts
            for z in ("active", "tentative", "deprecated"):
                totals[z] += zone_counts[z]
        stats[label] = {**totals, "by_phase": by_phase}

    return stats
