import os
from typing import Dict, List, Optional

from config import LESSONS_DIR, EVIL_COORD_FILE
from game.roles import ROLES_CONFIG, EVIL_COORD_DIMENSIONS, ALL_ROLES

# ---------------------------------------------------------------------------
# Good-team coordination file — mirrors evil_coordination for Merlin/Percival/LoyalServant
# ---------------------------------------------------------------------------
GOOD_COORD_FILE = os.path.join(LESSONS_DIR, "good_coord.txt")

GOOD_COORD_DIMENSIONS = [
    "merlin_signal_protection",       # How Merlin signals evil reads without exposing role
    "evil_identification_coordination", # How good players converge on evil reads via evidence
    "team_composition_alignment",     # Shared principles for building safe mission teams
    "vote_coordination",              # Coordinating reject/approve without revealing roles
    "merlin_concealment_support",     # How Percival/LoyalServant help shield Merlin's identity
]

# Per-dimension caps: kept here so consolidation and apply_delta enforce the same values.
TENTATIVE_CAP = 5   # max tentative lessons per dimension before forced consolidation
ACTIVE_CAP = 5      # max active lessons per dimension (enforced during consolidation)
CONSOLIDATION_THRESHOLD = 3  # tentative count that triggers consolidation check


def ensure_dirs():
    os.makedirs(LESSONS_DIR, exist_ok=True)


def get_lesson_path(role: str) -> str:
    return os.path.join(LESSONS_DIR, f"{role.lower()}.txt")


# ---------------------------------------------------------------------------
# File initialisation
# ---------------------------------------------------------------------------

def _init_lesson_file(role: str) -> str:
    dims = ROLES_CONFIG[role]["dimensions"]
    content = _serialize({
        "header": [f"=== {role.upper()} LESSONS ===", "version: 0", "last_updated: none"],
        "dimensions": {d: {"active": [], "tentative": [], "deprecated": []} for d in dims}
    }, dims)
    _write(get_lesson_path(role), content)
    return content


def _init_evil_coord() -> str:
    content = _serialize({
        "header": ["=== EVIL COORDINATION MEMORY ===", "version: 0", "last_updated: none"],
        "dimensions": {d: {"active": [], "tentative": [], "deprecated": []} for d in EVIL_COORD_DIMENSIONS}
    }, EVIL_COORD_DIMENSIONS)
    _write(EVIL_COORD_FILE, content)
    return content


def _init_good_coord() -> str:
    content = _serialize({
        "header": ["=== GOOD COORDINATION MEMORY ===", "version: 0", "last_updated: none"],
        "dimensions": {d: {"active": [], "tentative": [], "deprecated": []} for d in GOOD_COORD_DIMENSIONS}
    }, GOOD_COORD_DIMENSIONS)
    _write(GOOD_COORD_FILE, content)
    return content


# ---------------------------------------------------------------------------
# Low-level IO
# ---------------------------------------------------------------------------

def _write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _parse(content: str, dimensions: List[str]) -> Dict:
    parsed = {
        "header": [],
        "dimensions": {d: {"active": [], "tentative": [], "deprecated": []} for d in dimensions}
    }
    current_dim = None
    current_zone = None

    for line in content.split("\n"):
        stripped = line.strip()
        matched_dim = next((d for d in dimensions if stripped == f"[{d}]"), None)
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


def _serialize(parsed: Dict, dimensions: List[str]) -> str:
    lines = [l for l in parsed["header"] if l is not None]
    lines.append("")
    for dim in dimensions:
        d = parsed["dimensions"].get(dim, {"active": [], "tentative": [], "deprecated": []})
        lines += [f"[{dim}]", "ACTIVE:"] + d["active"] + \
                 ["TENTATIVE:"] + d["tentative"] + \
                 ["DEPRECATED:"] + d["deprecated"] + [""]
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


# ---------------------------------------------------------------------------
# Lesson loading (what agents read before acting)
# ---------------------------------------------------------------------------

def load_lessons(role: str) -> str:
    """
    Returns ACTIVE lessons (high confidence) and TENTATIVE lessons (provisional)
    as clearly separated sections. DEPRECATED lessons are never shown.

    Lesson lifecycle:
    - TENTATIVE: newly proposed from one game — injected with a caveat label so
      agents treat them as provisional hypotheses, not confirmed strategy.
    - ACTIVE: confirmed across multiple games via confirm_active deltas — injected
      as primary guidance. Outcome tags (WIN/LOSS) are preserved so agents can
      assess how reliable a lesson is across different game outcomes.
    - DEPRECATED: failed strategies — never injected. Kept in file for audit only.
    """
    path = get_lesson_path(role)
    if not os.path.exists(path):
        _init_lesson_file(role)
        return ""

    content = open(path, "r", encoding="utf-8").read()
    dims = ROLES_CONFIG[role]["dimensions"]
    parsed = _parse(content, dims)

    active_lines: List[str] = []
    tentative_lines: List[str] = []

    for dim in dims:
        d = parsed["dimensions"][dim]
        if d["active"]:
            active_lines.append(f"[{dim}]")
            active_lines.extend(d["active"])
        if d["tentative"]:
            tentative_lines.append(f"[{dim}]")
            tentative_lines.extend(d["tentative"])

    if not active_lines and not tentative_lines:
        return ""

    output: List[str] = []
    if active_lines:
        output.append("CONFIRMED LESSONS (high confidence — apply these):")
        output.extend(active_lines)
    if tentative_lines:
        if output:
            output.append("")
        output.append("PROVISIONAL LESSONS (observed once — treat as hypotheses, not rules):")
        output.extend(tentative_lines)

    return "\n".join(output)


def load_evil_coord() -> str:
    """Load evil coordination memory, separated by confidence tier."""
    if not os.path.exists(EVIL_COORD_FILE):
        _init_evil_coord()
        return ""

    content = open(EVIL_COORD_FILE, "r", encoding="utf-8").read()
    parsed = _parse(content, EVIL_COORD_DIMENSIONS)

    active_lines: List[str] = []
    tentative_lines: List[str] = []

    for dim in EVIL_COORD_DIMENSIONS:
        d = parsed["dimensions"][dim]
        if d["active"]:
            active_lines.append(f"[{dim}]")
            active_lines.extend(d["active"])
        if d["tentative"]:
            tentative_lines.append(f"[{dim}]")
            tentative_lines.extend(d["tentative"])

    output: List[str] = []
    if active_lines:
        output.append("CONFIRMED:")
        output.extend(active_lines)
    if tentative_lines:
        if output:
            output.append("")
        output.append("PROVISIONAL:")
        output.extend(tentative_lines)

    return "\n".join(output)


def load_good_coord() -> str:
    """Load good team coordination memory, separated by confidence tier."""
    if not os.path.exists(GOOD_COORD_FILE):
        _init_good_coord()
        return ""

    content = open(GOOD_COORD_FILE, "r", encoding="utf-8").read()
    parsed = _parse(content, GOOD_COORD_DIMENSIONS)

    active_lines: List[str] = []
    tentative_lines: List[str] = []

    for dim in GOOD_COORD_DIMENSIONS:
        d = parsed["dimensions"][dim]
        if d["active"]:
            active_lines.append(f"[{dim}]")
            active_lines.extend(d["active"])
        if d["tentative"]:
            tentative_lines.append(f"[{dim}]")
            tentative_lines.extend(d["tentative"])

    output: List[str] = []
    if active_lines:
        output.append("CONFIRMED:")
        output.extend(active_lines)
    if tentative_lines:
        if output:
            output.append("")
        output.append("PROVISIONAL:")
        output.extend(tentative_lines)

    return "\n".join(output)


# ---------------------------------------------------------------------------
# Delta application helpers
# ---------------------------------------------------------------------------

def _resolve_dim(parsed_dims: dict, raw_dim: str) -> Optional[str]:
    """Return the actual key in parsed_dims matching raw_dim after normalisation, or None."""
    normalized = raw_dim.strip().lower().replace(" ", "_")
    if normalized in parsed_dims:
        return normalized
    for key in parsed_dims:
        if key.strip().lower().replace(" ", "_") == normalized:
            return key
    return None


def _is_near_duplicate(new_lesson: str, existing_lessons: List[str], threshold: int = 6) -> bool:
    """
    Rough duplicate check: if a new lesson shares more than `threshold` words
    with any existing lesson, treat it as a near-duplicate.
    Prevents the tentative list from filling up with restatements of the same rule.
    """
    new_words = set(new_lesson.lower().split())
    for existing in existing_lessons:
        existing_words = set(existing.lower().split())
        overlap = len(new_words & existing_words)
        if overlap >= threshold:
            return True
    return False


def _apply_delta(parsed: Dict, delta: dict, game_id: int, dimensions: List[str]) -> Dict:
    tag = f"[g{game_id:03d}]"

    # ---- add_tentative ----
    for item in delta.get("add_tentative", []):
        if not isinstance(item, dict):
            continue
        raw_dim = item.get("dimension", "")
        lesson = item.get("lesson", "").strip()
        if "<" in raw_dim or "<" in lesson or not raw_dim.strip() or not lesson:
            continue
        dim = _resolve_dim(parsed["dimensions"], raw_dim)
        if not dim:
            continue

        # Enforce per-dimension tentative cap — do not add if already at limit.
        existing_tentative = parsed["dimensions"][dim]["tentative"]
        if len(existing_tentative) >= TENTATIVE_CAP:
            continue

        # Skip near-duplicate lessons to prevent restatement bloat.
        all_existing = existing_tentative + parsed["dimensions"][dim]["active"]
        if _is_near_duplicate(lesson, all_existing):
            continue

        parsed["dimensions"][dim]["tentative"].append(f"- {tag} {lesson}")

    # ---- confirm_active ----
    # Only move lessons that already exist in tentative (found by keyword).
    # Do NOT silently add to active if not found — this was the duplication bug.
    for item in delta.get("confirm_active", []):
        if not isinstance(item, dict):
            continue
        raw_dim = item.get("dimension", "")
        lesson = item.get("lesson", "").strip()
        keyword = item.get("keyword", "").lower().strip()
        dim = _resolve_dim(parsed["dimensions"], raw_dim)
        if not dim or not keyword:
            continue

        tentative = parsed["dimensions"][dim]["tentative"]
        for i, t in enumerate(tentative):
            if keyword in t.lower():
                # Promote: annotate with confirmation count if already in active (re-confirms).
                promoted = t  # preserve original tag + text
                parsed["dimensions"][dim]["active"].append(promoted)
                tentative.pop(i)
                break
        # If keyword not found in tentative, skip — do not add directly to active.
        # This prevents phantom lessons from appearing in the active list.

    # ---- flag_deprecated ----
    for item in delta.get("flag_deprecated", []):
        if not isinstance(item, dict):
            continue
        raw_dim = item.get("dimension", "")
        keyword = item.get("keyword", "").lower().strip()
        reason = item.get("reason", "").strip()
        dim = _resolve_dim(parsed["dimensions"], raw_dim)
        if not dim or not keyword:
            continue
        for zone in ("active", "tentative"):
            lst = parsed["dimensions"][dim][zone]
            for i, line in enumerate(lst):
                if keyword in line.lower():
                    deprecated_entry = (
                        f"- [DEPRECATED {tag}] {line.lstrip('- ')}"
                        + (f" — {reason}" if reason else "")
                    )
                    parsed["dimensions"][dim]["deprecated"].append(deprecated_entry)
                    lst.pop(i)
                    break

    return parsed


# ---------------------------------------------------------------------------
# Public apply functions
# ---------------------------------------------------------------------------

def apply_lesson_delta(role: str, delta: dict, game_id: int):
    dims = ROLES_CONFIG[role]["dimensions"]
    path = get_lesson_path(role)
    if not os.path.exists(path):
        _init_lesson_file(role)
    content = open(path, "r", encoding="utf-8").read()
    parsed = _parse(content, dims)
    parsed = _apply_delta(parsed, delta, game_id, dims)
    parsed = _bump_version(parsed, game_id)
    _write(path, _serialize(parsed, dims))


def apply_evil_coord_delta(delta: dict, game_id: int):
    if not os.path.exists(EVIL_COORD_FILE):
        _init_evil_coord()
    content = open(EVIL_COORD_FILE, "r", encoding="utf-8").read()
    parsed = _parse(content, EVIL_COORD_DIMENSIONS)
    parsed = _apply_delta(parsed, delta, game_id, EVIL_COORD_DIMENSIONS)
    parsed = _bump_version(parsed, game_id)
    _write(EVIL_COORD_FILE, _serialize(parsed, EVIL_COORD_DIMENSIONS))


def apply_good_coord_delta(delta: dict, game_id: int):
    """Apply a reflection delta to the good-team coordination memory file."""
    if not os.path.exists(GOOD_COORD_FILE):
        _init_good_coord()
    content = open(GOOD_COORD_FILE, "r", encoding="utf-8").read()
    parsed = _parse(content, GOOD_COORD_DIMENSIONS)
    parsed = _apply_delta(parsed, delta, game_id, GOOD_COORD_DIMENSIONS)
    parsed = _bump_version(parsed, game_id)
    _write(GOOD_COORD_FILE, _serialize(parsed, GOOD_COORD_DIMENSIONS))


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------

def consolidate_lessons(role: str, llm, game_id: int):
    """
    LLM-driven consolidation pass for a single role's lesson file.
    Merges near-duplicate tentative lessons, resolves contradictions,
    promotes stable patterns to active, removes vague entries, and
    enforces per-dimension caps.
    """
    from agents.llm_client import call_llm_json
    path = get_lesson_path(role)
    if not os.path.exists(path):
        return
    current = open(path, "r", encoding="utf-8").read()
    dims = ROLES_CONFIG[role]["dimensions"]

    system = (
        f"You are consolidating a strategic memory file for the {role} role in Avalon. "
        "Be strict. Preserve outcome tags (WIN/LOSS) in lessons — they are analytically valuable."
    )
    user = (
        f"Current lessons file for {role}:\n\n{current}\n\n"
        f"TASKS — apply all strictly:\n"
        f"1. MERGE: If 2+ TENTATIVE lessons in the same dimension share the same core rule "
        f"(even if worded differently), merge into one sharp 'When X, do Y because Z' rule "
        f"and PROMOTE it to ACTIVE. Combine any outcome tags (e.g. 'WIN x2, LOSS x1').\n"
        f"2. CONTRADICTIONS: If two lessons in the same dimension contradict each other, "
        f"keep the more specific/actionable one; deprecate the other with reason "
        f"'contradicts retained lesson'.\n"
        f"3. PROMOTE: Any TENTATIVE lesson confirmed across 2+ games (check [g00X] tags) "
        f"must be moved to ACTIVE.\n"
        f"4. REMOVE VAGUE: Delete any lesson that is vague (e.g. 'be careful', "
        f"'watch everyone'), role-inappropriate, or factually wrong about game mechanics.\n"
        f"5. CAPS: ACTIVE max {ACTIVE_CAP} per dimension. TENTATIVE max {TENTATIVE_CAP} per dimension. "
        f"Excess lessons go to DEPRECATED with reason 'cap exceeded — lower priority version'.\n"
        f"6. OUTCOME ANALYSIS: If a lesson is tagged only WIN or only LOSS across many games, "
        f"add a note in parentheses: e.g. '(reliable on WIN, untested on LOSS)'. "
        f"Lessons confirmed on BOTH outcomes get a '(robust)' tag.\n"
        f"7. Preserve exact file structure: header lines, [dimension] tags, "
        f"ACTIVE:/TENTATIVE:/DEPRECATED: zones.\n\n"
        'Return JSON only: {"updated_file": "complete updated file as a single string"}'
    )
    result = call_llm_json(llm, system, user)
    updated = result.get("updated_file", "")
    if updated and len(updated) > 100:
        parsed = _parse(updated, dims)
        parsed = _bump_version(parsed, game_id)
        _write(path, _serialize(parsed, dims))


def consolidate_evil_coord(llm, game_id: int):
    """LLM-driven consolidation for the evil coordination memory file."""
    from agents.llm_client import call_llm_json
    if not os.path.exists(EVIL_COORD_FILE):
        return
    current = open(EVIL_COORD_FILE, "r", encoding="utf-8").read()
    system = (
        "You are consolidating an evil team coordination memory file for Avalon. "
        "Be strict. Preserve outcome tags."
    )
    user = (
        f"{current}\n\n"
        f"TASKS:\n"
        f"1. Merge near-duplicate lessons into one sharp rule; promote merged result to ACTIVE.\n"
        f"2. Resolve contradictions — keep more specific/actionable, deprecate the other.\n"
        f"3. Remove vague lessons.\n"
        f"4. ACTIVE max 3 per dimension. TENTATIVE max 2 per dimension.\n"
        f"5. Add outcome reliability notes: (robust) if confirmed on both WIN and LOSS.\n"
        f"Preserve structure.\n\n"
        'Return JSON only: {"updated_file": "complete file content"}'
    )
    result = call_llm_json(llm, system, user)
    updated = result.get("updated_file", "")
    if updated and len(updated) > 100:
        parsed = _parse(updated, EVIL_COORD_DIMENSIONS)
        parsed = _bump_version(parsed, game_id)
        _write(EVIL_COORD_FILE, _serialize(parsed, EVIL_COORD_DIMENSIONS))


def consolidate_good_coord(llm, game_id: int):
    """LLM-driven consolidation for the good team coordination memory file."""
    from agents.llm_client import call_llm_json
    if not os.path.exists(GOOD_COORD_FILE):
        return
    current = open(GOOD_COORD_FILE, "r", encoding="utf-8").read()
    system = (
        "You are consolidating a good team coordination memory file for Avalon. "
        "Be strict. Preserve outcome tags."
    )
    user = (
        f"{current}\n\n"
        f"TASKS:\n"
        f"1. Merge near-duplicate lessons into one sharp rule; promote merged result to ACTIVE.\n"
        f"2. Resolve contradictions — keep more specific/actionable, deprecate the other.\n"
        f"3. Remove vague lessons.\n"
        f"4. ACTIVE max 3 per dimension. TENTATIVE max 2 per dimension.\n"
        f"5. Add outcome reliability notes: (robust) if confirmed on both WIN and LOSS.\n"
        f"Preserve structure.\n\n"
        'Return JSON only: {"updated_file": "complete file content"}'
    )
    result = call_llm_json(llm, system, user)
    updated = result.get("updated_file", "")
    if updated and len(updated) > 100:
        parsed = _parse(updated, GOOD_COORD_DIMENSIONS)
        parsed = _bump_version(parsed, game_id)
        _write(GOOD_COORD_FILE, _serialize(parsed, GOOD_COORD_DIMENSIONS))


# ---------------------------------------------------------------------------
# Consolidation trigger
# ---------------------------------------------------------------------------

def should_consolidate_now(tentative_threshold: int = CONSOLIDATION_THRESHOLD) -> bool:
    """
    Returns True if any role file OR either coordination file has a dimension
    that has hit the tentative cap.  Checks all files so consolidation is not
    missed due to a single slow-accumulating role.
    """
    # Individual role files
    for role in ALL_ROLES:
        path = get_lesson_path(role)
        if not os.path.exists(path):
            continue
        content = open(path, "r", encoding="utf-8").read()
        dims = ROLES_CONFIG[role]["dimensions"]
        parsed = _parse(content, dims)
        for dim in dims:
            if len(parsed["dimensions"][dim]["tentative"]) >= tentative_threshold:
                return True

    # Evil coordination file
    if os.path.exists(EVIL_COORD_FILE):
        content = open(EVIL_COORD_FILE, "r", encoding="utf-8").read()
        parsed = _parse(content, EVIL_COORD_DIMENSIONS)
        for dim in EVIL_COORD_DIMENSIONS:
            if len(parsed["dimensions"][dim]["tentative"]) >= tentative_threshold:
                return True

    # Good coordination file
    if os.path.exists(GOOD_COORD_FILE):
        content = open(GOOD_COORD_FILE, "r", encoding="utf-8").read()
        parsed = _parse(content, GOOD_COORD_DIMENSIONS)
        for dim in GOOD_COORD_DIMENSIONS:
            if len(parsed["dimensions"][dim]["tentative"]) >= tentative_threshold:
                return True

    return False


def get_lesson_stats() -> dict:
    """
    Returns a summary dict of lesson counts per role and coordination file,
    broken down by active / tentative / deprecated.
    Useful for monitoring learning health across games.
    """
    stats = {}

    for role in ALL_ROLES:
        path = get_lesson_path(role)
        if not os.path.exists(path):
            stats[role] = {"active": 0, "tentative": 0, "deprecated": 0}
            continue
        content = open(path, "r", encoding="utf-8").read()
        dims = ROLES_CONFIG[role]["dimensions"]
        parsed = _parse(content, dims)
        totals = {"active": 0, "tentative": 0, "deprecated": 0}
        for dim in dims:
            for zone in ("active", "tentative", "deprecated"):
                totals[zone] += len(parsed["dimensions"][dim][zone])
        stats[role] = totals

    for label, filepath, dimensions in [
        ("evil_coord", EVIL_COORD_FILE, EVIL_COORD_DIMENSIONS),
        ("good_coord", GOOD_COORD_FILE, GOOD_COORD_DIMENSIONS),
    ]:
        if not os.path.exists(filepath):
            stats[label] = {"active": 0, "tentative": 0, "deprecated": 0}
            continue
        content = open(filepath, "r", encoding="utf-8").read()
        parsed = _parse(content, dimensions)
        totals = {"active": 0, "tentative": 0, "deprecated": 0}
        for dim in dimensions:
            for zone in ("active", "tentative", "deprecated"):
                totals[zone] += len(parsed["dimensions"][dim][zone])
        stats[label] = totals

    return stats