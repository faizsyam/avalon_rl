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

# Phase-specific required action words (word stems, matched with word boundaries)
PHASE_ACTION_STEMS = {
    "discussion": ["say", "frame", "ask", "accuse", "deflect", "signal", "name", "propose", "steer"],
    "proposal": ["propose", "pick", "choose", "select", "include", "exclude", "team", "test"],
    "vote": ["approve", "reject", "vote"],
    "mission": ["fail", "success", "play"],
    "assassin": ["guess", "target", "identify", "name"]
}

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

    stripped = lesson.strip()
    # Strip leading "- [gXXX] "-style marker so the body can be matched.
    body = re.sub(r'^-\s*\[(?:DEPRECATED\s+)?g\d+\]\s*', '', stripped)
    body = re.sub(r'^-\s*', '', body).strip()

    words = body.split()
    if len(words) > 35:
        return False, f"exceeds 35 words ({len(words)})"
    if not body.startswith("When "):
        return False, "must start with 'When '"
    if " do " not in body and " Do " not in body:
        # Action phrase; recasts of action verbs (REJECT/FAIL/etc.) at
        # the top of the rule are handled by the phase stem check below.
        pass  # Phase-action-stem check below catches the same cases.
    if " because " not in body:
        return False, "must contain ' because ' (causal reason)"

    has_win = "(observed on WIN)" in body
    has_loss = "(observed on LOSS)" in body
    if not (has_win or has_loss):
        return False, "must end with '(observed on WIN)' or '(observed on LOSS)'"
    if has_win and has_loss:
        return False, "cannot have both WIN and LOSS tags"

    # Phase-specific required action content.
    if phase == "vote":
        if "APPROVE" not in body and "REJECT" not in body:
            return False, "vote lesson must specify APPROVE or REJECT"
    elif phase == "mission":
        if "FAIL" not in body and "SUCCESS" not in body:
            return False, "mission lesson must specify FAIL or SUCCESS"
    elif phase == "assassin":
        if "guess" not in body.lower() and "target" not in body.lower():
            return False, "assassin lesson must mention guess or target"

    # Phase-specific required action stem (word-boundary, case-insensitive).
    action_stems = PHASE_ACTION_STEMS.get(phase, [])
    if action_stems:
        if not any(re.search(rf'\b{re.escape(stem)}\w*\b', body, re.IGNORECASE) for stem in action_stems):
            return False, f"phase '{phase}' lesson must contain a phase-appropriate action verb"

    lower_body = body.lower()
    for vague in VAGUE_PHRASES:
        if vague in lower_body:
            return False, f"contains vague filler: '{vague}'"

    return True, ""


def _filter_valid_lessons(parsed: dict, phases: list, game_id: int) -> dict:
    """Remove any invalid lessons from active/tentative zones after LLM consolidation."""
    for phase in phases:
        for zone in ("active", "tentative"):
            lst = parsed["dimensions"][phase][zone]
            valid = []
            for lesson in lst:
                ok, _ = validate_lesson(lesson, phase)
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
    """Tight match for confirm_active/flag_deprecated. The keyword must either be a
    substring of the normalized lesson body, or have all its words appear in order.
    Generic words like 'evil' or 'fail' cannot accidentally promote unrelated
    lessons because the substring check requires the literal phrase."""
    norm = _normalize_lesson(lesson)
    key = keyword.strip().lower()
    if not key:
        return False
    if key in norm:
        return True
    words = key.split()
    return _words_in_order(norm, words)


def _words_in_order(haystack: str, words: List[str]) -> bool:
    pos = 0
    for w in words:
        idx = haystack.find(w, pos)
        if idx < 0:
            return False
        pos = idx + len(w)
    return True


def _write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    written = open(path, "r", encoding="utf-8").read()
    if len(written) < 50:
        raise RuntimeError(f"_write to {path} produced suspiciously short file ({len(written)} chars)")


def _apply_delta(parsed: Dict, delta: dict, game_id: int) -> Dict:
    tag = f"[g{game_id:03d}]"

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
            continue

        all_existing = existing_tentative + parsed["dimensions"][phase]["active"]
        if _is_near_duplicate(lesson, all_existing):
            continue

        parsed["dimensions"][phase]["tentative"].append(f"- {tag} {lesson}")

    for item in delta.get("confirm_active", []):
        if not isinstance(item, dict):
            continue
        raw_phase = item.get("phase", "") or item.get("dimension", "")
        keyword = item.get("keyword", "").lower().strip()
        phase = _resolve_phase(parsed["dimensions"], raw_phase)
        if not phase or not keyword:
            continue

        tentative = parsed["dimensions"][phase]["tentative"]
        for i, t in enumerate(tentative):
            if _match_lesson_phrase(t, keyword):
                parsed["dimensions"][phase]["active"].append(t)
                tentative.pop(i)
                break

    for item in delta.get("flag_deprecated", []):
        if not isinstance(item, dict):
            continue
        raw_phase = item.get("phase", "") or item.get("dimension", "")
        keyword = item.get("keyword", "").lower().strip()
        reason = item.get("reason", "").strip()
        phase = _resolve_phase(parsed["dimensions"], raw_phase)
        if not phase or not keyword:
            continue
        for zone in ("active", "tentative"):
            lst = parsed["dimensions"][phase][zone]
            for i, line in enumerate(lst):
                if _match_lesson_phrase(line, keyword):
                    deprecated_entry = (
                        f"- [DEPRECATED {tag}] {line.lstrip('- ')}"
                        + (f" — {reason}" if reason else "")
                    )
                    parsed["dimensions"][phase]["deprecated"].append(deprecated_entry)
                    lst.pop(i)
                    break

    return parsed

def apply_lesson_delta(role: str, delta: dict, game_id: int):
    _apply_delta_to_path(get_lesson_path(role), ROLES_CONFIG[role]["phases"], delta, game_id)


def apply_evil_coord_delta(delta: dict, game_id: int):
    _apply_delta_to_path(EVIL_COORD_FILE, EVIL_COORD_PHASES, delta, game_id)


def apply_good_coord_delta(delta: dict, game_id: int):
    _apply_delta_to_path(GOOD_COORD_FILE, GOOD_COORD_PHASES, delta, game_id)


def _apply_delta_to_path(path: str, phases: List[str], delta: dict, game_id: int):
    """Single apply path for role lesson files AND coordination files."""
    if not os.path.exists(path):
        # Initialize with the right headers and phase structure on first write.
        header_label = os.path.basename(path).replace(".txt", "").upper().replace("_", " ")
        _init_file(path, header_label, phases)
    parsed = _parse_file(path, phases)
    parsed = _apply_delta(parsed, delta, game_id)
    parsed = _bump_version(parsed, game_id)
    _write(path, _serialize(parsed, phases))


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
                     active_cap=ACTIVE_CAP, tentative_cap=TENTATIVE_CAP)


def consolidate_evil_coord(llm, game_id: int):
    consolidate_file(EVIL_COORD_FILE, EVIL_COORD_PHASES, "evil coordination", llm, game_id,
                     active_cap=3, tentative_cap=2)


def consolidate_good_coord(llm, game_id: int):
    consolidate_file(GOOD_COORD_FILE, GOOD_COORD_PHASES, "good coordination", llm, game_id,
                     active_cap=3, tentative_cap=2)


def consolidate_file(path: str, phases, label: str, llm, game_id: int, active_cap: int, tentative_cap: int):
    """Single consolidation entry point shared by role and coordination files."""
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
    updated_parsed = _filter_valid_lessons(updated_parsed, phases, game_id)
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
