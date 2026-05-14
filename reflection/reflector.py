import os
import re
from game.state import GameState
from game.roles import ROLES_CONFIG, ALL_ROLES
from agents.llm_client import call_llm_json
from memory.manager import (
    apply_lesson_delta,
    apply_evil_coord_delta,
    apply_good_coord_delta,
)
# Minimum lessons required per reflection call before accepting the response.
MIN_LESSONS_PER_REFLECTION = 3
MAX_REFLECTION_RETRIES = 2

GOOD_ROLES = {"Merlin", "Percival", "LoyalServant"}
EVIL_ROLES = {"Assassin", "Morgana"}


# ---------------------------------------------------------------------------
# Sanitisation helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def _format_agent_context(state: GameState, slot_id: int) -> str:
    """
    Build a rich context block for the reflecting agent that includes:
    - The agent's own statements, votes, proposals, and mission results.
    - ALL other players' statements and votes so the agent can observe
      behavioral patterns across the full game — essential for learning
      deception signatures, Merlin tells, and coordination patterns.
    """
    lines = []
    all_names = list(state.slot_to_name.values())

    # ---- Own decisions ----
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

    # ---- Full discussion log (all players) — critical for behavioral pattern learning ----
    if state.discussion_log:
        lines.append("\n--- FULL DISCUSSION LOG (ALL PLAYERS) ---")
        lines.append("Use this to identify behavioral signatures, deception patterns, and role tells.")
        for d in state.discussion_log:
            speaker_name = _n(state, d.slot_id)
            marker = " [YOU]" if d.slot_id == slot_id else ""
            lines.append(f"  Q{d.quest_num} {speaker_name}{marker}: \"{d.statement}\"")

    # ---- All players' vote breakdown ----
    lines.append("\n--- FULL VOTE BREAKDOWN (ALL PLAYERS) ---")
    for v in state.vote_history:
        lines.append(f"  Q{v.quest_num}P{v.proposal_num} — {_n(state, v.proposer_slot)} proposed "
                     f"{[_n(state, s) for s in v.proposed_team]} → {v.result}")
        for s, vt in v.votes.items():
            marker = " [YOU]" if s == slot_id else ""
            lines.append(f"    {_n(state, s)}{marker}: {vt}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_reflection_prompt(role: str, state: GameState, slot_id: int) -> tuple:
    config = ROLES_CONFIG[role]
    faction = config["faction"]
    faction_won = (state.outcome == "GOOD_WINS") == (faction == "good")
    outcome_tag = "WIN" if faction_won else "LOSS"
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
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state,v.proposer_slot)}→{[_n(state,s) for s in v.proposed_team]} "
        f"{v.result}\n"
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

    # ---- Role-specific deep analysis blocks ----
    assassination_analysis = ""

    if role == "Merlin":
        if state.outcome == "EVIL_WINS" and state.assassin_correct:
            assassination_analysis = """
CRITICAL — YOU WERE ASSASSINATED:
The Assassin correctly identified you. Analyze precisely:
- Which statements or votes could ONLY be explained by hidden knowledge of evil players?
- Were your objections to specific players too consistent, too accurate, or too early?
- Did you block the same players repeatedly in a detectable pattern?
- What would a Loyal Servant with NO hidden knowledge have said differently at each moment?
- At which exact quest/proposal did you become identifiable? What triggered it?
Identity concealment must improve more than team selection — assassination ends good wins instantly.
"""
        else:
            assassination_analysis = """
MERLIN IDENTITY AUDIT (even though you survived):
Review each statement and vote you made:
- Could any be explained ONLY by Merlin's hidden knowledge? List them.
- Which behaviors were indistinguishable from a Loyal Servant?
- Did you ever reveal accurate reads on evil without a plausible non-Merlin explanation?
- What behavioral signature, if any, did the Assassin seem to track? Did they focus on you?
Building this self-audit habit prevents assassination in future games.
"""

    if role == "Assassin":
        if state.assassin_guess_slot is not None:
            guess_name = _n(state, state.assassin_guess_slot)
            merlin_name = _n(state, state.role_to_slot.get("Merlin", -1))
            correct = state.assassin_correct
            assassination_analysis = f"""
ASSASSINATION DEBRIEF — Guess: {guess_name}, Actual Merlin: {merlin_name}, Correct: {correct}

Conduct a full behavioral comparison across all players:

FOR YOUR GUESS ({guess_name}):
- List every statement or vote that made them appear Merlin-like.
- For each tell, ask: could a Loyal Servant or Percival explain this behavior without hidden knowledge?
- If yes → it was a false tell. If no → it was a genuine tell.

FOR ACTUAL MERLIN ({merlin_name}):
- Now review their actual statements and votes with hindsight.
- Which patterns, in retrospect, indicated hidden knowledge of evil?
- Were their team objections accurate beyond chance? Were endorsements consistently safe?
- Did they avoid or redirect questions about their alignment unusually?
- What distinguishes their behavior from a normal Loyal Servant's play?

FINGERPRINT EXTRACTION:
Identify the 1-2 most reliable behavioral signals that distinguish Merlin from good non-Merlins.
These become your identification heuristics in future games.
"""

    # ---- Adversarial learning block ----
    if faction == "good":
        adversarial_section = """
ADVERSARIAL LEARNING — What evil looks for in your behavior:
- Assassin tracks: consistent accurate objections to evil-containing teams, unexplained exclusion of evil players, pattern of endorsing only safe teams, visible reactions when evil is discussed.
- Morgana tracks: which good players are most persuasive so she can mimic or discredit them.
- Consider: which of YOUR behaviors in this game would look suspicious to a watching Assassin?
- Add at least one lesson about minimizing your behavioral signature as a good player.
"""
    else:
        adversarial_section = """
ADVERSARIAL LEARNING — What good players track in your behavior:
- Merlin watches: who proposes or approves evil-heavy teams, who objects to clean teams without reason.
- Percival watches: who mimics Merlin's reasoning style (Morgana tell), voting inconsistencies.
- LoyalServant watches: vote patterns vs quest outcomes, team composition consistency.
- Consider: which of YOUR behaviors in this game were most detectable by good players?
- Add at least one lesson about reducing detection risk as an evil player.
"""

    agent_context = _format_agent_context(state, slot_id)
    dims = config["dimensions"]
    dims_str = ", ".join(f'"{d}"' for d in dims)
    d0 = dims[0]
    d_last = dims[-1] if len(dims) > 1 else dims[0]

    system = (
        f"You are {my_name}, who played {role} ({'GOOD' if faction == 'good' else 'EVIL'} team) "
        f"in The Resistance: Avalon. Your faction {'WON' if faction_won else 'LOST'} (outcome: {outcome_tag}).\n\n"
        f"Extract SPECIFIC, ACTIONABLE lessons covering MULTIPLE dimensions. Rules:\n"
        f"- Minimum {MIN_LESSONS_PER_REFLECTION} lessons total, ideally covering all dimensions: {dims_str}\n"
        f"- Write each lesson as a concrete reusable rule: 'When X, do Y because Z.'\n"
        f"- NO narrative. NO 'In Q2 I did X'. Write reusable rules, not game recaps.\n"
        f"- NO player names ({', '.join(all_names)}). Reference roles or behavioral patterns.\n"
        f"- Each lesson must include enough specificity to apply in a future game with different players.\n"
        f"- BAD: 'Trust steady players.' GOOD: 'When a player consistently votes with quest outcomes "
        f"across 3+ quests and demands reasoning before approving teams, treat them as likely good-aligned "
        f"because this behavior is difficult to fake without knowing outcomes in advance.'\n"
        f"- Good team reminder: Assassin identifying Merlin = evil wins even after 3 quest successes.\n"
        f"- Evil team reminder: approving a quest with no evil players guarantees a good quest win."
    )

    user = f"""
=== POST-GAME REVIEW ===
Outcome: {state.outcome} | Your faction result: {outcome_tag}
{full_role_reveal}
{mission_log}
{vote_log}
{assassin_reveal}
{assassination_analysis}
{adversarial_section}

=== YOUR DECISIONS AND FULL GAME CONTEXT ===
{agent_context}

Write {MIN_LESSONS_PER_REFLECTION}-5 strategic lessons for the {role} role, split across these dimensions: {dims_str}.
Use the FULL DISCUSSION LOG above to identify behavioral patterns and tells — not just quest outcomes.

Each lesson must be "When X, do Y because Z." and be reusable in any future game.
Tag each lesson with the game outcome: include "(observed on {outcome_tag})" at the end.

Fill in "confirm_active" if any existing TENTATIVE lesson was clearly validated in this game
(provide the keyword from that lesson and its dimension).
Fill in "flag_deprecated" if any existing TENTATIVE or ACTIVE lesson was clearly contradicted
(provide the keyword and dimension, and a reason).

Return ONLY valid JSON:
{{
  "reasoning": "for each key decision: was it correct and what was the consequence",
  "add_tentative": [
    {{"dimension": "{d0}", "lesson": "When X, do Y because Z. (observed on {outcome_tag})"}},
    {{"dimension": "{d_last}", "lesson": "When X, do Y because Z. (observed on {outcome_tag})"}}
  ],
  "confirm_active": [
    {{"dimension": "dimension_name", "lesson": "restated merged lesson", "keyword": "unique word from existing tentative lesson"}}
  ],
  "flag_deprecated": [
    {{"dimension": "dimension_name", "keyword": "unique word from lesson to deprecate", "reason": "why it failed"}}
  ]
}}
"""
    return system, user, all_names


def _build_evil_coord_prompt(state: GameState) -> tuple:
    assassin_slot = state.role_to_slot.get("Assassin", -1)
    morgana_slot = state.role_to_slot.get("Morgana", -1)
    all_names = list(state.slot_to_name.values())
    outcome_tag = "WIN" if state.outcome == "EVIL_WINS" else "LOSS"

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

    discussion_summary = ""
    if state.discussion_log:
        ass_name = _n(state, assassin_slot)
        morg_name = _n(state, morgana_slot)
        discussion_summary = "\nEVIL PLAYERS' DISCUSSION STATEMENTS:\n"
        for d in state.discussion_log:
            if d.slot_id in (assassin_slot, morgana_slot):
                role_label = "Assassin" if d.slot_id == assassin_slot else "Morgana"
                discussion_summary += f"  Q{d.quest_num} [{role_label}]: \"{d.statement}\"\n"

    assassin_reveal = ""
    if state.assassin_guess_slot is not None:
        guess_name = _n(state, state.assassin_guess_slot)
        merlin_name = _n(state, state.role_to_slot.get("Merlin", -1))
        assassin_reveal = (
            f"\nASSASSIN GUESS: guessed {guess_name}, Merlin was {merlin_name}. "
            f"Correct: {state.assassin_correct}"
        )

    system = (
        "Extract specific coordination lessons for Assassin and Morgana to use in future games. "
        f"NO player names ({', '.join(all_names)}). Reference roles or behavioral patterns only. "
        "Write rule-form lessons ('When X, do Y because Z'), not game recaps. "
        f"Minimum 2 lessons. Tag each with outcome: (observed on {outcome_tag})."
    )
    user = f"""
Outcome: {state.outcome} ({outcome_tag})
Assassin: {_n(state,assassin_slot)} | Morgana: {_n(state,morgana_slot)}

VOTES:\n{vote_summary}
MISSIONS:\n{mission_summary}
{discussion_summary}
{assassin_reveal}

Analyze:
1. Did their vote patterns expose the alliance? Look for synchronized APPROVE/REJECT.
2. Was sabotage timing optimal? If no fails occurred, was that the right call?
3. Were their discussion statements complementary or redundant? Did either player reveal the alliance?
4. Did Morgana successfully mimic Merlin's reasoning style, or were there detectable differences?
5. How could the Assassin have better identified Merlin from behavioral signals?

Dimensions: covering_for_each_other, vote_synchronization, mission_sabotage_timing, blame_deflection

Return ONLY valid JSON:
{{
  "add_tentative": [
    {{"dimension": "vote_synchronization", "lesson": "When [situation], do [action] because [reason]. (observed on {outcome_tag})"}},
    {{"dimension": "mission_sabotage_timing", "lesson": "When [situation], do [action] because [reason]. (observed on {outcome_tag})"}}
  ],
  "confirm_active": [],
  "flag_deprecated": []
}}
"""
    return system, user, all_names


def _build_good_coord_prompt(state: GameState) -> tuple:
    """
    Build a reflection prompt for good-team coordination patterns.
    Mirrors evil_coordination but for Merlin/Percival/LoyalServant.
    """
    merlin_slot = state.role_to_slot.get("Merlin", -1)
    percival_slot = state.role_to_slot.get("Percival", -1)
    loyal_slot = state.role_to_slot.get("LoyalServant", -1)
    all_names = list(state.slot_to_name.values())
    outcome_tag = "WIN" if state.outcome == "GOOD_WINS" else "LOSS"

    vote_summary = "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {[_n(state,s) for s in v.proposed_team]} → {v.result}\n"
        f"    Merlin: {v.votes.get(merlin_slot,'?')}  "
        f"Percival: {v.votes.get(percival_slot,'?')}  "
        f"LoyalServant: {v.votes.get(loyal_slot,'?')}"
        for v in state.vote_history
    )
    mission_summary = "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )

    discussion_summary = ""
    if state.discussion_log:
        good_slots = {merlin_slot, percival_slot, loyal_slot}
        slot_to_role = {merlin_slot: "Merlin", percival_slot: "Percival", loyal_slot: "LoyalServant"}
        discussion_summary = "\nGOOD PLAYERS' DISCUSSION STATEMENTS:\n"
        for d in state.discussion_log:
            if d.slot_id in good_slots:
                role_label = slot_to_role.get(d.slot_id, "Good")
                discussion_summary += f"  Q{d.quest_num} [{role_label}]: \"{d.statement}\"\n"

    full_role_reveal = "FULL ROLE REVEAL:\n" + "\n".join(
        f"  {_n(state, s)} → {r}"
        for s, r in state.slot_to_role.items()
    )

    assassin_reveal = ""
    if state.assassin_guess_slot is not None:
        guess_name = _n(state, state.assassin_guess_slot)
        merlin_name = _n(state, merlin_slot)
        assassin_reveal = (
            f"\nASSASSIN PHASE: guessed {guess_name}, Merlin was {merlin_name}. "
            f"Correct: {state.assassin_correct}"
        )

    system = (
        "Extract good-team coordination lessons for Merlin, Percival, and LoyalServant. "
        f"NO player names ({', '.join(all_names)}). Reference roles and behavioral patterns only. "
        "Write rule-form lessons ('When X, do Y because Z'), not game recaps. "
        f"Minimum 2 lessons. Tag each with outcome: (observed on {outcome_tag})."
    )
    user = f"""
Outcome: {state.outcome} ({outcome_tag})
{full_role_reveal}

VOTES (Merlin / Percival / LoyalServant):\n{vote_summary}
MISSIONS:\n{mission_summary}
{discussion_summary}
{assassin_reveal}

Analyze good-team coordination:
1. Did Merlin successfully signal evil reads to Percival without revealing their role?
2. Did Percival protect Merlin's identity while still acting on Merlin's signals?
3. Did LoyalServant correctly identify and align with good players through observable evidence?
4. Were good team vote patterns coordinated enough to block evil proposals?
5. Did Merlin's behavior reveal their identity to the Assassin? What specifically?
6. How could good team have coordinated more safely without exposing Merlin?

Dimensions: merlin_signal_protection, evil_identification_coordination,
            team_composition_alignment, vote_coordination, merlin_concealment_support

Return ONLY valid JSON:
{{
  "add_tentative": [
    {{"dimension": "merlin_signal_protection", "lesson": "When X, do Y because Z. (observed on {outcome_tag})"}},
    {{"dimension": "evil_identification_coordination", "lesson": "When X, do Y because Z. (observed on {outcome_tag})"}}
  ],
  "confirm_active": [],
  "flag_deprecated": []
}}
"""
    return system, user, all_names


# ---------------------------------------------------------------------------
# Debugging and rescue helpers
# ---------------------------------------------------------------------------

def _log_reflection_debug(game_id: int, role: str, delta: dict, applied_counts: dict):
    import json as _json
    from config import LOGS_DIR
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, "reflection_debug.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"GAME {game_id:03d} | {role}\n")
        f.write(f"RAW DELTA: {_json.dumps(delta, ensure_ascii=False)}\n")
        tentative = delta.get("add_tentative", [])
        f.write(f"add_tentative ({len(tentative)} items):\n")
        for item in tentative:
            dim = item.get("dimension", "MISSING")
            lesson = item.get("lesson", "MISSING")
            skipped = "<" in dim or "<" in lesson or not dim.strip() or not lesson.strip()
            f.write(f"  {'SKIP' if skipped else 'OK  '} dim={dim!r} lesson={lesson[:80]!r}\n")
        f.write(f"confirm_active: {len(delta.get('confirm_active', []))} items\n")
        f.write(f"flag_deprecated: {len(delta.get('flag_deprecated', []))} items\n")
        f.write(f"applied => tentative+{applied_counts.get('tentative',0)} "
                f"confirmed+{applied_counts.get('confirmed',0)} "
                f"deprecated+{applied_counts.get('deprecated',0)}\n")
        if not tentative:
            f.write("  !! LLM returned empty add_tentative\n")
        elif len(tentative) < MIN_LESSONS_PER_REFLECTION:
            f.write(f"  !! Only {len(tentative)} lessons returned (minimum is {MIN_LESSONS_PER_REFLECTION})\n")


def _rescue_toplevel_lesson(delta: dict) -> dict:
    """LLM sometimes puts dimension+lesson at top level instead of inside add_tentative."""
    if not isinstance(delta, dict):
        return delta
    dim = delta.get("dimension", "").strip()
    lesson = delta.get("lesson", "").strip()
    existing = delta.get("add_tentative", [])
    if dim and lesson and not existing:
        delta["add_tentative"] = [{"dimension": dim, "lesson": lesson}]
    return delta


def _has_sufficient_lessons(delta: dict) -> bool:
    """Return True if the delta contains the minimum required number of valid lessons."""
    tentative = delta.get("add_tentative", [])
    valid = [
        item for item in tentative
        if isinstance(item, dict)
        and item.get("dimension", "").strip()
        and item.get("lesson", "").strip()
        and "<" not in item.get("dimension", "")
        and "<" not in item.get("lesson", "")
    ]
    return len(valid) >= MIN_LESSONS_PER_REFLECTION


def _call_reflection_with_retry(llm, system: str, user: str, role: str, game_id: int) -> dict:
    """
    Call the LLM for reflection with retry logic if the response contains
    fewer than MIN_LESSONS_PER_REFLECTION valid lessons.
    """
    for attempt in range(MAX_REFLECTION_RETRIES + 1):
        delta = call_llm_json(llm, system, user, call_label=f"reflection {role} (attempt {attempt+1})")
        if not isinstance(delta, dict):
            continue
        delta = _rescue_toplevel_lesson(delta)
        if _has_sufficient_lessons(delta):
            return delta
        # Retry with explicit reminder
        retry_note = (
            f"\n\nIMPORTANT: Your previous response only contained "
            f"{len(delta.get('add_tentative', []))} lesson(s). "
            f"You must provide at least {MIN_LESSONS_PER_REFLECTION} lessons across different dimensions. "
            "Every dimension listed must have at least one lesson."
        )
        user = user + retry_note

    # Return whatever we have after exhausting retries
    return delta if isinstance(delta, dict) else {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_reflection(state: GameState, llm) -> dict:
    counts = {}

    # ------------------------------------------------------------------
    # Phase 1: Individual role reflections
    # ------------------------------------------------------------------
    for role in ALL_ROLES:
        slot_id = state.role_to_slot[role]
        system, user, names = _build_reflection_prompt(role, state, slot_id)
        delta = _call_reflection_with_retry(llm, system, user, role, state.game_id)

        if isinstance(delta, dict):
            delta = _sanitize_delta(delta, names)
            delta.setdefault("add_tentative", [])
            delta.setdefault("confirm_active", [])
            delta.setdefault("flag_deprecated", [])
            apply_lesson_delta(role, delta, state.game_id)
            applied = {
                "tentative": len(delta.get("add_tentative", [])),
                "confirmed": len(delta.get("confirm_active", [])),
                "deprecated": len(delta.get("flag_deprecated", [])),
            }
            counts[role] = applied
            _log_reflection_debug(state.game_id, role, delta, applied)
        else:
            counts[role] = {"tentative": 0, "confirmed": 0, "deprecated": 0}
            _log_reflection_debug(state.game_id, role, {}, {})

    # ------------------------------------------------------------------
    # Phase 2: Evil faction coordination reflection (Assassin + Morgana only)
    # ------------------------------------------------------------------
    system, user, names = _build_evil_coord_prompt(state)
    coord_delta = call_llm_json(llm, system, user, call_label="evil coord reflection")
    if coord_delta and isinstance(coord_delta, dict):
        coord_delta = _sanitize_delta(coord_delta, names)
        apply_evil_coord_delta(coord_delta, state.game_id)

    # ------------------------------------------------------------------
    # Phase 3: Good faction coordination reflection (Merlin + Percival + LoyalServant only)
    # ------------------------------------------------------------------
    system, user, names = _build_good_coord_prompt(state)
    good_coord_delta = call_llm_json(llm, system, user, call_label="good coord reflection")
    if good_coord_delta and isinstance(good_coord_delta, dict):
        good_coord_delta = _sanitize_delta(good_coord_delta, names)
        apply_good_coord_delta(good_coord_delta, state.game_id)

    return counts