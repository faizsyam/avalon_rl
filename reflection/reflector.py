import re
from game.state import GameState
from game.roles import ROLES_CONFIG, ALL_ROLES
from agents.llm_client import call_llm_json
from memory.manager import apply_lesson_delta, apply_evil_coord_delta


def _sanitize_names(text: str, names: list) -> str:
    """Replace all player names in lesson text with role-neutral placeholders."""
    result = text
    for name in names:
        # Whole-word match, case-insensitive
        result = re.sub(rf'\b{re.escape(name)}\b', 'a player', result, flags=re.IGNORECASE)
    return result


def _sanitize_delta(delta: dict, all_names: list) -> dict:
    """Walk every lesson string in a delta and strip player names."""
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
    my_name = _n(state, slot_id)

    statements = [(d.quest_num, d.statement) for d in state.discussion_log if d.slot_id == slot_id]
    if statements:
        lines.append(f"YOUR DISCUSSION STATEMENTS ({my_name}):")
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
            team_names = [_n(state, s) for s in v.proposed_team]
            lines.append(f"  Q{v.quest_num}P{v.proposal_num}: proposed {team_names} → {v.result}")

    missions = [m for m in state.mission_history if slot_id in m.team]
    if missions:
        lines.append("\nMISSIONS YOU WERE ON:")
        for m in missions:
            team_names = [_n(state, s) for s in m.team]
            lines.append(f"  Q{m.quest_num}: team={team_names} → {m.result} ({m.num_fails} fail(s))")

    notes = state.agent_notes.get(slot_id, [])
    if notes:
        lines.append("\nYOUR IN-GAME PRIVATE NOTES:")
        for n in notes:
            lines.append(f"  {n}")

    return "\n".join(lines)


def _build_reflection_prompt(role: str, state: GameState, slot_id: int) -> tuple:
    config = ROLES_CONFIG[role]
    faction = config["faction"]
    faction_won = (state.outcome == "GOOD_WINS") == (faction == "good")
    my_name = _n(state, slot_id)
    all_names = list(state.slot_to_name.values())

    assassin_reveal = ""
    if state.outcome == "GOOD_WINS" and state.assassin_guess_slot is not None:
        guess_name = _n(state, state.assassin_guess_slot)
        merlin_name = _n(state, state.role_to_slot.get("Merlin", -1))
        assassin_reveal = (
            f"\nASSASSIN PHASE: Assassin guessed {guess_name} as Merlin. "
            f"Merlin was {merlin_name}. Correct: {state.assassin_correct}"
        )

    full_role_reveal = "\nFULL ROLE REVEAL (post-game truth — use for reflection only, not in lessons):\n" + "\n".join(
        f"  {_n(state, s)} → {r} ({'evil' if ROLES_CONFIG[r]['faction'] == 'evil' else 'good'})"
        for s, r in state.slot_to_role.items()
    )

    all_mission_log = "\nQUEST RESULTS:\n" + "\n".join(
        f"  Q{m.quest_num}: team={[_n(state, s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )

    all_vote_log = "\nALL PROPOSALS AND VOTES:\n" + "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state, v.proposer_slot)} proposed "
        f"{[_n(state, s) for s in v.proposed_team]} → {v.result}\n"
        f"    APPROVE: {[_n(state, s) for s,vote in v.votes.items() if vote=='APPROVE']}  "
        f"REJECT: {[_n(state, s) for s,vote in v.votes.items() if vote=='REJECT']}"
        for v in state.vote_history
    )

    agent_decisions = _format_agent_decisions(state, slot_id)
    dims = config["dimensions"]

    system = (
        f"You are an AI agent who just played {role} in The Resistance: Avalon. "
        f"Extract SPECIFIC, ACTIONABLE lessons from this game.\n\n"
        f"LESSON FORMAT RULES — follow these exactly:\n"
        f"- Write each lesson as a concise strategic rule or heuristic (1-2 sentences max).\n"
        f"- Use trigger-action form where possible: 'When X, do Y' or 'If X, then Y is likely.' \n"
        f"- NO narrative. NO story. NO 'In Q2 I did X'. Write reusable rules, not game recaps.\n"
        f"- NO player names ({', '.join(all_names)}). Future games have different players.\n"
        f"- Reference roles (Merlin, Assassin, Morgana, Percival, Loyal Servant) or behavioral patterns.\n"
        f"- BAD: 'Trust Clara because she was steady.' \n"
        f"- GOOD: 'When a player consistently votes in alignment with quest outcomes across 3+ quests, treat them as likely good-aligned.' \n"
        f"- BAD: 'In Q4 I rejected the team because I was on two failed quests.' \n"
        f"- GOOD: 'As an evil player, voting against a team containing yourself draws attention — only do this if the alternative is an all-good team that would succeed.'"
    )

    user = f"""
=== POST-GAME REVIEW ===
Game {state.game_id} | Your role: {role} ({my_name}) | Faction: {faction} | YOU WON: {faction_won}
Outcome: {state.outcome}
{assassin_reveal}
{full_role_reveal}
{all_mission_log}
{all_vote_log}

=== YOUR DECISIONS THIS GAME ===
{agent_decisions}

=== REFLECTION TASK ===

PART 1 — DECISION REVIEW
For each key decision, evaluate: was it correct given what you knew at that moment (not hindsight)?
What was the consequence? What would you do differently?

PART 2 — COMMUNICATION REVIEW
- What emotional tone did you use? Did it help or hurt?
- Which rhetorical approaches (accusations, defenses, deflections, rapport-building) worked or backfired?
- What did other players' TONE reveal about them? What emotional or linguistic cues mattered?
- What would you communicate differently next time?

PART 3 — LESSON EXTRACTION
Extract 2-4 specific, actionable lessons. Use only these dimensions: {dims}
Include communication and tone insights under "communication_style_and_tone".
DO NOT use any player names in lesson text. Reference roles or describe behavior patterns.

Return ONLY valid JSON:
{{
  "add_tentative": [
    {{"dimension": "<dimension_name>", "lesson": "<specific actionable lesson — no player names>"}}
  ],
  "confirm_active": [
    {{"dimension": "<dimension_name>", "lesson": "<lesson confirmed again>", "keyword": "<phrase from existing lesson>"}}
  ],
  "flag_deprecated": [
    {{"dimension": "<dimension_name>", "keyword": "<phrase from existing lesson that failed>", "reason": "<what happened — no player names>"}}
  ]
}}
"""
    return system, user, all_names


def _build_evil_coord_prompt(state: GameState) -> tuple:
    assassin_slot = state.role_to_slot.get("Assassin", -1)
    morgana_slot = state.role_to_slot.get("Morgana", -1)
    all_names = list(state.slot_to_name.values())

    vote_summary = "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {[_n(state,s) for s in v.proposed_team]} → {v.result}\n"
        f"    Assassin ({_n(state, assassin_slot)}): {v.votes.get(assassin_slot,'?')}  "
        f"Morgana ({_n(state, morgana_slot)}): {v.votes.get(morgana_slot,'?')}"
        for v in state.vote_history
    )
    mission_summary = "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )

    system = (
        "You are analyzing evil team coordination in a completed Avalon game. "
        "Extract specific coordination lessons for Assassin and Morgana to use in future games. "
        f"DO NOT use player names ({', '.join(all_names)}) in lessons — future games will have different players. "
        "Reference roles (Assassin, Morgana) or describe patterns instead."
    )

    user = f"""
Outcome: {state.outcome} | Assassin: {_n(state, assassin_slot)} | Morgana: {_n(state, morgana_slot)}

VOTE COORDINATION:
{vote_summary}

QUEST RESULTS:
{mission_summary}

Analyze coordination quality and extract lessons. Reference roles, not names.
Dimensions: covering_for_each_other, vote_synchronization, mission_sabotage_timing, blame_deflection

Return ONLY valid JSON:
{{
  "add_tentative": [
    {{"dimension": "<dimension_name>", "lesson": "<lesson — no player names>"}}
  ],
  "confirm_active": [],
  "flag_deprecated": []
}}
"""
    return system, user, all_names


def run_reflection(state: GameState, llm) -> dict:
    counts = {}
    all_names = list(state.slot_to_name.values())

    for role in ALL_ROLES:
        slot_id = state.role_to_slot[role]
        system, user, names = _build_reflection_prompt(role, state, slot_id)
        delta = call_llm_json(llm, system, user, call_label=f"reflection {role}")

        if delta and isinstance(delta, dict):
            delta = _sanitize_delta(delta, names)
            tentative = delta.get("add_tentative", [])
            if not isinstance(tentative, list):
                tentative = []
            delta["add_tentative"] = tentative
            delta.setdefault("confirm_active", [])
            delta.setdefault("flag_deprecated", [])
            apply_lesson_delta(role, delta, state.game_id)
            counts[role] = len(tentative)
        else:
            counts[role] = 0

    system, user, names = _build_evil_coord_prompt(state)
    coord_delta = call_llm_json(llm, system, user, call_label="evil coord reflection")
    if coord_delta and isinstance(coord_delta, dict):
        coord_delta = _sanitize_delta(coord_delta, names)
        apply_evil_coord_delta(coord_delta, state.game_id)

    return counts