import os
import re
from game.state import GameState
from game.roles import ROLES_CONFIG, ALL_ROLES
from agents.llm_client import call_llm_json
from memory.manager import apply_lesson_delta, apply_evil_coord_delta
from config import PUBLIC_LESSONS_DIR


def _sanitize_names(text: str, names: list) -> str:
    result = text
    for name in names:
        result = re.sub(rf'\b{re.escape(name)}\b', 'a player', result, flags=re.IGNORECASE)
    return result


def _sanitize_delta(delta: dict, all_names: list) -> dict:
    for section in ("add_tentative", "confirm_active", "flag_deprecated"):
        for item in delta.get(section, []):
            if isinstance(item, dict):
                for key in ("lesson", "reason", "keyword"):
                    if key in item and isinstance(item[key], str):
                        item[key] = _sanitize_names(item[key], all_names)
    return delta


def _n(state: GameState, slot: int) -> str:
    return state.slot_to_name.get(slot, f"Slot{slot}")


def _format_agent_decisions(state: GameState, slot_id: int) -> str:
    lines = []
    statements = [(d.quest_num, d.statement) for d in state.discussion_log if d.slot_id == slot_id]
    if statements:
        lines.append("YOUR STATEMENTS:")
        for q, s in statements:
            lines.append(f"  Q{q}: \"{s}\"")
    lines.append("\nYOUR VOTES:")
    for v in state.vote_history:
        my_vote = v.votes.get(slot_id, "?")
        proposer = _n(state, v.proposer_slot)
        team_names = [_n(state, s) for s in v.proposed_team]
        lines.append(f"  Q{v.quest_num}P{v.proposal_num}: {my_vote} on {team_names} (by {proposer}) → {v.result}")
    proposals = [v for v in state.vote_history if v.proposer_slot == slot_id]
    if proposals:
        lines.append("\nYOUR PROPOSALS:")
        for v in proposals:
            lines.append(f"  Q{v.quest_num}P{v.proposal_num}: proposed {[_n(state,s) for s in v.proposed_team]} → {v.result}")
    missions = [m for m in state.mission_history if slot_id in m.team]
    if missions:
        lines.append("\nMISSIONS YOU WERE ON:")
        for m in missions:
            lines.append(f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))")
    notes = state.agent_notes.get(slot_id, [])
    if notes:
        lines.append("\nYOUR IN-GAME NOTES:")
        for n in notes:
            lines.append(f"  {n}")
    return "\n".join(lines)


def _build_reflection_prompt(role: str, state: GameState, slot_id: int) -> tuple:
    config = ROLES_CONFIG[role]
    faction = config["faction"]
    faction_won = (state.outcome == "GOOD_WINS") == (faction == "good")
    my_name = _n(state, slot_id)
    all_names = list(state.slot_to_name.values())

    full_role_reveal = "FULL ROLE REVEAL:\n" + "\n".join(
        f"  {_n(state, s)} → {r} ({'evil' if ROLES_CONFIG[r]['faction'] == 'evil' else 'good'})"
        for s, r in state.slot_to_role.items()
    )
    mission_log = "QUEST RESULTS:\n" + "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )
    vote_log = "ALL VOTES:\n" + "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state,v.proposer_slot)}→{[_n(state,s) for s in v.proposed_team]} {v.result}\n"
        f"    APPROVE:{[_n(state,s) for s,vt in v.votes.items() if vt=='APPROVE']} "
        f"REJECT:{[_n(state,s) for s,vt in v.votes.items() if vt=='REJECT']}"
        for v in state.vote_history
    )

    assassin_reveal = ""
    if state.assassin_guess_slot is not None:
        guess_name = _n(state, state.assassin_guess_slot)
        merlin_name = _n(state, state.role_to_slot.get("Merlin", -1))
        assassin_reveal = (
            f"\nASSASSIN PHASE: Assassin guessed {guess_name} as Merlin. "
            f"Merlin was {merlin_name}. Correct: {state.assassin_correct}"
        )

    assassination_analysis = ""
    if role == "Merlin" and state.outcome == "EVIL_WINS" and state.assassin_correct:
        assassination_analysis = """
CRITICAL ANALYSIS REQUIRED — YOU WERE ASSASSINATED:
The Assassin correctly identified you. This means your behavior during the game was distinctive enough
to reveal your role despite your efforts. Answer these specifically:
- Which of your statements or votes could ONLY be explained by someone with hidden knowledge of evil players?
- Were your objections to specific players too consistent, too accurate, or too early in the game?
- Did you always block the same players? Did you react too visibly when evil was discussed?
- What would a Loyal Servant with NO hidden knowledge have said or done differently at those moments?
Being assassinated is the most common way the good team loses despite winning all quests. Your identity
concealment must improve more than your team selection.
"""

    agent_decisions = _format_agent_decisions(state, slot_id)
    dims = config["dimensions"]

    system = (
        f"You are {my_name}, who played {role} ({'GOOD' if faction == 'good' else 'EVIL'} team) "
        f"in The Resistance: Avalon. Your faction {'WON' if faction_won else 'LOST'}.\n\n"
        f"Extract SPECIFIC, ACTIONABLE lessons. Follow these format rules exactly:\n"
        f"- Write each lesson as a concise strategic rule: 'When X, do Y' or 'If X, then Y is likely.'\n"
        f"- NO narrative. NO 'In Q2 I did X'. Write reusable rules, not game recaps.\n"
        f"- NO player names ({', '.join(all_names)}). Reference roles or behavioral patterns.\n"
        f"- BAD: 'Trust a player because they were steady.' GOOD: 'When a player consistently votes "
        f"with quest outcomes across 3+ quests, treat them as likely good-aligned.'\n"
        f"- Good team must understand: the Assassin identifying Merlin = evil wins even after 3 quest wins.\n"
        f"- Evil team must understand: approving a team with no evil players guarantees a good quest win."
    )

    user = f"""
=== POST-GAME REVIEW ===
{full_role_reveal}
{mission_log}
{vote_log}
{assassin_reveal}
{assassination_analysis}

=== YOUR DECISIONS ===
{agent_decisions}

=== REFLECTION TASKS ===

PART 1 — DECISION REVIEW
For each key decision: was it correct given what you knew at the time? What was the consequence?

PART 2 — COMMUNICATION REVIEW
What tone worked? What backfired? What did others' tone and word choice reveal?

PART 3 — LESSON EXTRACTION
Extract 2-4 specific rule-form lessons. Use only these dimensions: {dims}
NO player names. Reference roles or behavioral patterns only.

Return ONLY valid JSON:
{{
  "add_tentative": [{{"dimension": "<dim>", "lesson": "<rule-form lesson>"}}],
  "confirm_active": [{{"dimension": "<dim>", "lesson": "<confirmed lesson>", "keyword": "<phrase from existing lesson>"}}],
  "flag_deprecated": [{{"dimension": "<dim>", "keyword": "<phrase from failed lesson>", "reason": "<what happened>"}}]
}}
"""
    return system, user, all_names


def _build_evil_coord_prompt(state: GameState) -> tuple:
    assassin_slot = state.role_to_slot.get("Assassin", -1)
    morgana_slot = state.role_to_slot.get("Morgana", -1)
    all_names = list(state.slot_to_name.values())
    vote_summary = "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {[_n(state,s) for s in v.proposed_team]} → {v.result}\n"
        f"    Assassin ({_n(state,assassin_slot)}): {v.votes.get(assassin_slot,'?')}  "
        f"Morgana ({_n(state,morgana_slot)}): {v.votes.get(morgana_slot,'?')}"
        for v in state.vote_history
    )
    mission_summary = "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )
    system = (
        "Extract specific coordination lessons for Assassin and Morgana to use in future games. "
        f"NO player names ({', '.join(all_names)}). Reference roles or behavioral patterns. "
        "Write rule-form lessons, not game recaps."
    )
    user = f"""
Outcome: {state.outcome} | Assassin: {_n(state,assassin_slot)} | Morgana: {_n(state,morgana_slot)}
VOTES:\n{vote_summary}
MISSIONS:\n{mission_summary}

Analyze coordination quality. Did their votes expose the alliance? Was sabotage timing smart?
Dimensions: covering_for_each_other, vote_synchronization, mission_sabotage_timing, blame_deflection

Return ONLY valid JSON:
{{"add_tentative": [{{"dimension": "<dim>", "lesson": "<rule-form lesson>"}}], "confirm_active": [], "flag_deprecated": []}}
"""
    return system, user, all_names


def _collect_public_lessons(state: GameState, llm) -> dict:
    from agents.prompts import get_public_lesson_prompt
    public_lessons = {}
    for role in ALL_ROLES:
        slot_id = state.role_to_slot[role]
        prompt = get_public_lesson_prompt(state, slot_id, role)
        system = "You are writing a 1-2 sentence public lesson for all players to read. Be direct and role-specific."
        result = call_llm_json(llm, system, prompt, call_label=f"public-lesson {role}")
        lesson = result.get("public_lesson", "").strip()
        if lesson:
            public_lessons[role] = lesson
    return public_lessons


def _save_public_lessons(public_lessons: dict, game_id: int):
    os.makedirs(PUBLIC_LESSONS_DIR, exist_ok=True)
    path = os.path.join(PUBLIC_LESSONS_DIR, f"game_{game_id:03d}.txt")
    lines = [f"=== PUBLIC LESSONS - GAME {game_id:03d} ===\n"]
    for role, lesson in public_lessons.items():
        lines.append(f"{role}: \"{lesson}\"")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _apply_cross_lessons(state: GameState, public_lessons: dict, llm, all_names: list):
    from agents.prompts import get_cross_lesson_prompt
    for role in ALL_ROLES:
        slot_id = state.role_to_slot[role]
        prompt = get_cross_lesson_prompt(state, slot_id, role, public_lessons)
        system = "Extract cross-role lessons relevant to your specific role. Rule-form only. No player names."
        result = call_llm_json(llm, system, prompt, call_label=f"cross-lesson {role}")
        if result and isinstance(result, dict):
            result = _sanitize_delta(result, all_names)
            tentative = result.get("add_tentative", [])
            if isinstance(tentative, list) and tentative:
                apply_lesson_delta(role, {"add_tentative": tentative, "confirm_active": [], "flag_deprecated": []}, state.game_id)


def run_reflection(state: GameState, llm) -> dict:
    counts = {}
    all_names = list(state.slot_to_name.values())

    # Phase 1: Individual reflection + lesson updates
    for role in ALL_ROLES:
        slot_id = state.role_to_slot[role]
        system, user, names = _build_reflection_prompt(role, state, slot_id)
        delta = call_llm_json(llm, system, user, call_label=f"reflection {role}")
        if delta and isinstance(delta, dict):
            delta = _sanitize_delta(delta, names)
            delta.setdefault("add_tentative", [])
            delta.setdefault("confirm_active", [])
            delta.setdefault("flag_deprecated", [])
            apply_lesson_delta(role, delta, state.game_id)
            counts[role] = len(delta.get("add_tentative", []))
        else:
            counts[role] = 0

    # Phase 2: Evil coordination reflection
    system, user, names = _build_evil_coord_prompt(state)
    coord_delta = call_llm_json(llm, system, user, call_label="evil coord reflection")
    if coord_delta and isinstance(coord_delta, dict):
        coord_delta = _sanitize_delta(coord_delta, names)
        apply_evil_coord_delta(coord_delta, state.game_id)

    # Phase 3: Public lessons — each agent writes one sentence, then all read them
    print("  Collecting public lessons...")
    public_lessons = _collect_public_lessons(state, llm)
    if public_lessons:
        _save_public_lessons(public_lessons, state.game_id)
        print(f"  Applying cross-role lessons ({len(public_lessons)} public lessons)...")
        _apply_cross_lessons(state, public_lessons, llm, all_names)

    return counts