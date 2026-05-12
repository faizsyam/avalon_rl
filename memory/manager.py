import os
from typing import Dict, List

from config import LESSONS_DIR, EVIL_COORD_FILE
from game.roles import ROLES_CONFIG, EVIL_COORD_DIMENSIONS, ALL_ROLES


def ensure_dirs():
    os.makedirs(LESSONS_DIR, exist_ok=True)


def get_lesson_path(role: str) -> str:
    return os.path.join(LESSONS_DIR, f"{role.lower()}.txt")


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


def load_lessons(role: str) -> str:
    """
    Returns only the ACTIVE lessons, with TENTATIVE lessons appended
    under a clearly marked section. DEPRECATED lessons are never shown.

    Lesson lifecycle:
    - TENTATIVE: newly proposed from one game; injected with a caveat label
      so agents treat them as provisional hypotheses, not confirmed strategy.
    - ACTIVE: confirmed across multiple games via confirm_active deltas;
      injected as primary guidance.
    - DEPRECATED: failed strategies; never injected. Kept in file for audit only.
    """
    path = get_lesson_path(role)
    if not os.path.exists(path):
        _init_lesson_file(role)
        return ""

    content = open(path, "r", encoding="utf-8").read()
    dims = ROLES_CONFIG[role]["dimensions"]
    parsed = _parse(content, dims)

    active_lines = []
    tentative_lines = []

    for dim in dims:
        d = parsed["dimensions"][dim]
        active = d["active"]
        tentative = d["tentative"]
        if active:
            active_lines.append(f"[{dim}]")
            active_lines.extend(active)
        if tentative:
            tentative_lines.append(f"[{dim}]")
            tentative_lines.extend(tentative)

    if not active_lines and not tentative_lines:
        return ""

    output = []
    if active_lines:
        output.append("CONFIRMED LESSONS (high confidence — apply these):")
        output.extend(active_lines)
    if tentative_lines:
        output.append("")
        output.append("PROVISIONAL LESSONS (observed once — treat as hypotheses, not rules):")
        output.extend(tentative_lines)

    return "\n".join(output)


def load_evil_coord() -> str:
    """Same filtered loading for evil coordination memory."""
    if not os.path.exists(EVIL_COORD_FILE):
        _init_evil_coord()
        return ""

    content = open(EVIL_COORD_FILE, "r", encoding="utf-8").read()
    parsed = _parse(content, EVIL_COORD_DIMENSIONS)

    active_lines = []
    tentative_lines = []

    for dim in EVIL_COORD_DIMENSIONS:
        d = parsed["dimensions"][dim]
        if d["active"]:
            active_lines.append(f"[{dim}]")
            active_lines.extend(d["active"])
        if d["tentative"]:
            tentative_lines.append(f"[{dim}]")
            tentative_lines.extend(d["tentative"])

    output = []
    if active_lines:
        output.append("CONFIRMED:")
        output.extend(active_lines)
    if tentative_lines:
        output.append("")
        output.append("PROVISIONAL:")
        output.extend(tentative_lines)

    return "\n".join(output)


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


def _apply_delta(parsed: Dict, delta: dict, game_id: int, dimensions: List[str]) -> Dict:
    tag = f"[g{game_id:03d}]"

    for item in delta.get("add_tentative", []):
        if not isinstance(item, dict):
            continue
        dim = item.get("dimension", "")
        lesson = item.get("lesson", "").strip()
        if dim in parsed["dimensions"] and lesson:
            parsed["dimensions"][dim]["tentative"].append(f"- {tag} {lesson}")

    for item in delta.get("confirm_active", []):
        if not isinstance(item, dict):
            continue
        dim = item.get("dimension", "")
        lesson = item.get("lesson", "").strip()
        keyword = item.get("keyword", "").lower()
        if dim not in parsed["dimensions"] or not lesson:
            continue
        tentative = parsed["dimensions"][dim]["tentative"]
        moved = False
        if keyword:
            for i, t in enumerate(tentative):
                if keyword in t.lower():
                    parsed["dimensions"][dim]["active"].append(t)
                    tentative.pop(i)
                    moved = True
                    break
        if not moved:
            parsed["dimensions"][dim]["active"].append(f"- {tag} {lesson}")

    for item in delta.get("flag_deprecated", []):
        if not isinstance(item, dict):
            continue
        dim = item.get("dimension", "")
        keyword = item.get("keyword", "").lower()
        reason = item.get("reason", "")
        if dim not in parsed["dimensions"] or not keyword:
            continue
        for zone in ("active", "tentative"):
            lst = parsed["dimensions"][dim][zone]
            for i, line in enumerate(lst):
                if keyword in line.lower():
                    parsed["dimensions"][dim]["deprecated"].append(
                        f"- [DEPRECATED {tag}] {line.lstrip('- ')} — {reason}"
                    )
                    lst.pop(i)
                    break

    return parsed


def consolidate_lessons(role: str, llm, game_id: int):
    from agents.llm_client import call_llm_json
    path = get_lesson_path(role)
    if not os.path.exists(path):
        return
    current = open(path, "r", encoding="utf-8").read()
    dims = ROLES_CONFIG[role]["dimensions"]
    system = (
        f"You are consolidating a strategic memory file for the {role} role in Avalon. "
        "Clean, deduplicate, and promote lessons. Be strict."
    )
    user = (
        f"Current lessons file for {role}:\n\n{current}\n\n"
        "TASKS — apply all:\n"
        "1. MERGE: If 2+ TENTATIVE lessons in the same dimension say essentially the same thing, "
        "merge them into one sharp rule and PROMOTE it to ACTIVE.\n"
        "2. CONTRADICTIONS: If two lessons in the same dimension contradict each other, "
        "keep the more specific/actionable one and deprecate the other with reason 'contradicts retained lesson'.\n"
        "3. PROMOTE: Any TENTATIVE lesson that appears 2+ times (same concept, different wording) "
        "across the file must be merged and moved to ACTIVE.\n"
        "4. REMOVE: Delete any lesson that is vague (e.g. 'be careful', 'watch everyone'), "
        "role-inappropriate (advice for a different role), or factually wrong about game mechanics.\n"
        "5. CAPS: ACTIVE max 5 per dimension. TENTATIVE max 3 per dimension.\n"
        "6. Preserve exact file structure: header lines, [dimension] tags, ACTIVE:/TENTATIVE:/DEPRECATED: zones.\n\n"
        'Return JSON only: {"updated_file": "complete updated file as a single string"}'
    )
    result = call_llm_json(llm, system, user)
    updated = result.get("updated_file", "")
    if updated and len(updated) > 100:
        parsed = _parse(updated, dims)
        parsed = _bump_version(parsed, game_id)
        _write(path, _serialize(parsed, dims))


def consolidate_evil_coord(llm, game_id: int):
    from agents.llm_client import call_llm_json
    if not os.path.exists(EVIL_COORD_FILE):
        return
    current = open(EVIL_COORD_FILE, "r", encoding="utf-8").read()
    system = "You are consolidating an evil team coordination memory file for Avalon. Be strict."
    user = (
        f"{current}\n\n"
        "TASKS:\n"
        "1. Merge near-duplicate lessons into one sharp rule and PROMOTE merged result to ACTIVE.\n"
        "2. Resolve contradictions — keep the more specific/actionable one, deprecate the other.\n"
        "3. Remove vague lessons.\n"
        "4. ACTIVE max 3 per dimension. TENTATIVE max 2 per dimension.\n"
        "Preserve structure.\n\n"
        'Return JSON only: {"updated_file": "complete file content"}'
    )
    result = call_llm_json(llm, system, user)
    updated = result.get("updated_file", "")
    if updated and len(updated) > 100:
        parsed = _parse(updated, EVIL_COORD_DIMENSIONS)
        parsed = _bump_version(parsed, game_id)
        _write(EVIL_COORD_FILE, _serialize(parsed, EVIL_COORD_DIMENSIONS))