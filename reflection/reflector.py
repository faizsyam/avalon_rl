import os
import re
from game.state import GameState
from game.roles import ROLES_CONFIG, ALL_ROLES, DIMENSION_DESCRIPTIONS
from agents.llm_client import call_llm_json, call_llm_json_prefill
from memory.manager import (
    apply_lesson_delta,
    apply_evil_coord_delta,
    apply_good_coord_delta,
    get_lesson_stats
)

MIN_LESSONS_PER_REFLECTION = 3
MAX_REFLECTION_RETRIES = 2

GOOD_ROLES = {"Merlin", "Percival", "LoyalServant"}
EVIL_ROLES = {"Assassin", "Morgana"}

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

def _format_agent_context(state: GameState, slot_id: int) -> str:
    lines = []
    all_names = list(state.slot_to_name.values())

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

    if state.discussion_log:
        lines.append("\n--- FULL DISCUSSION LOG (ALL PLAYERS) ---")
        lines.append("Use this to identify behavioral signatures, deception patterns, and role tells.")
        for d in state.discussion_log:
            speaker_name = _n(state, d.slot_id)
            marker = " [YOU]" if d.slot_id == slot_id else ""
            lines.append(f"  Q{d.quest_num} {speaker_name}{marker}: \"{d.statement}\"")

    return "\n".join(lines)

def _build_strategic_summary(state: GameState) -> str:
    evil_slots = {state.role_to_slot.get("Assassin"), state.role_to_slot.get("Morgana")}
    lines = ["POST-GAME STRATEGIC FACTS:"]
    evil_access_count = 0
    for m in state.mission_history:
        evil_on = [s for s in m.team if s in evil_slots]
        if evil_on:
            evil_access_count += 1
        access = f"evil present: {[_n(state, s) for s in evil_on]}" if evil_on else "no evil on team"
        lines.append(f"  Q{m.quest_num}: {[_n(state, s) for s in m.team]} → {m.result} ({access})")
    total = len(state.mission_history)
    lines.append(f"  Evil had team access on {evil_access_count}/{total} quests, caused {state.evil_wins} quest fail(s).")
    if state.evil_wins == 0 and total > 0:
        lines.append("  !! Evil failed ZERO quests — every evil card played was SUCCESS. Evil cannot win this way.")
    if state.assassin_guess_slot is not None:
        guess_name = _n(state, state.assassin_guess_slot)
        merlin_name = _n(state, state.role_to_slot.get("Merlin", -1))
        lines.append(f"  Assassin guessed {guess_name}. Merlin was {merlin_name}. Correct: {state.assassin_correct}")
    return "\n".join(lines)


def _build_role_targeted_questions(role: str, state: GameState, slot_id: int) -> str:
    config = ROLES_CONFIG[role]
    faction = config["faction"]
    evil_slots = {state.role_to_slot.get("Assassin"), state.role_to_slot.get("Morgana")}
    my_missions = [m for m in state.mission_history if slot_id in m.team]
    total = len(state.mission_history)

    if faction == "evil":
        lines = [f"TARGETED QUESTIONS FOR {role.upper()}:"]
        lines.append(f"  You appeared on {len(my_missions)}/{total} quest teams.")
        if state.evil_wins == 0:
            lines.append("  Evil sabotaged zero quests. For each mission you played SUCCESS: was that the right call?")
            lines.append("  If you never had team access: why not, and what could you have done differently in votes/discussion?")
        elif state.evil_wins < 3:
            lines.append(f"  Evil needed 3 quest fails to win but only achieved {state.evil_wins}. What prevented the remaining fails?")
        return "\n".join(lines)

    elif role == "Merlin":
        lines = ["TARGETED QUESTIONS FOR MERLIN:"]
        if state.assassin_correct:
            lines.append("  You were assassinated. Which statements or votes could only be explained by hidden knowledge?")
        else:
            lines.append("  You survived the Assassin's guess. What concealment choices protected you?")
        evil_proposals = [
            f"Q{v.quest_num}P{v.proposal_num}: included {[_n(state, s) for s in v.proposed_team if s in evil_slots]}"
            for v in state.vote_history
            if v.proposer_slot == slot_id and any(s in evil_slots for s in v.proposed_team)
        ]
        if evil_proposals:
            lines.append(f"  You proposed teams containing evil players: {evil_proposals} — was this justified?")
        return "\n".join(lines)

    elif role == "Percival":
        merlin_slot = state.role_to_slot.get("Merlin")
        morgana_slot = state.role_to_slot.get("Morgana")
        lines = [
            "TARGETED QUESTIONS FOR PERCIVAL:",
            f"  Real Merlin was {_n(state, merlin_slot)}, Morgana was {_n(state, morgana_slot)}.",
            "  Did you correctly distinguish them? Did your behavior protect or expose Merlin?",
        ]
        return "\n".join(lines)

    else:
        evil_names = [_n(state, s) for s in evil_slots]
        lines = [
            f"TARGETED QUESTIONS FOR {role.upper()}:",
            f"  Evil players were {evil_names}.",
            "  How early could observable evidence have identified them? What patterns did you miss or catch?",
        ]
        return "\n".join(lines)
        
def _build_epistemic_constraints(role: str, state: GameState, slot_id: int) -> str:
    evil_slots = {state.role_to_slot.get("Assassin"), state.role_to_slot.get("Morgana")}
    merlin_slot = state.role_to_slot.get("Merlin")
    morgana_slot = state.role_to_slot.get("Morgana")

    lines = ["⚠️  EPISTEMIC CONSTRAINTS — CRITICAL FOR LESSON QUALITY:"]
    lines.append("Your lessons must be derivable from what you could observe DURING the game.")
    lines.append("Do NOT write lessons that assume post-game role reveals unless explicitly noted below.")
    lines.append("")

    if role == "Merlin":
        evil_names = [_n(state, s) for s in evil_slots if s is not None]
        lines.append(f"WHAT YOU KNEW: Evil players' identities from game start ({evil_names}).")
        lines.append("WHAT YOU DIDN'T KNOW: Whether the Assassin suspected you; other players' private reasoning.")
        lines.append("LESSON RULE: Any lesson about 'who was evil' is VALID — you knew this in-game.")
        lines.append("LESSON RULE: Any lesson about 'why the Assassin guessed me' requires behavioral inference only.")

    elif role == "Percival":
        merlin_name = _n(state, merlin_slot)
        morgana_name = _n(state, morgana_slot)
        lines.append(f"WHAT YOU KNEW: Two players appeared as Merlin to you — one was real Merlin, one was Morgana.")
        lines.append(f"POST-GAME REVEAL: Real Merlin={merlin_name}, Morgana={morgana_name}.")
        lines.append("YOUR ROLE GOAL: Identify which of your two Merlin candidates is real, and protect them.")
        lines.append("LESSON RULE: Do NOT write lessons about concealing your own identity — you are not Merlin.")
        lines.append("LESSON RULE: Lessons must be about identifying real Merlin vs Morgana, protecting Merlin,")
        lines.append("            and using behavioral evidence to confirm or deny the two candidates.")

    elif role == "LoyalServant":
        lines.append("WHAT YOU KNEW: Nothing about roles. Only observable evidence: votes, proposals, quest outcomes.")
        lines.append("POST-GAME REVEAL (do not treat as in-game knowledge): Full role assignments.")
        lines.append("LESSON RULE: Every lesson must be derivable from observable behavior ALONE.")
        lines.append("LESSON RULE: Do NOT write 'I identified the evil player' unless you can cite the specific")
        lines.append("            observable evidence chain (votes, proposals, patterns) that led there.")
        lines.append("LESSON RULE: If the role reveal confirmed a suspicion, frame it as 'suspicion confirmed by reveal'")
        lines.append("            — not as 'I correctly identified' (you may have guessed correctly by luck).")

    elif role == "Assassin":
        merlin_name = _n(state, merlin_slot)
        lines.append(f"WHAT YOU KNEW: Morgana's identity, your own role. Evil team coordination.")
        lines.append(f"POST-GAME REVEAL: Merlin was {merlin_name}.")
        lines.append("LESSON RULE: Lessons about Merlin identification must separate 'what I observed' from 'what was true'.")
        lines.append("LESSON RULE: 'Merlin was X because of behavior Y' is valid only if Y was observable during play.")

    elif role == "Morgana":
        lines.append("WHAT YOU KNEW: Assassin's identity, your own role.")
        lines.append("LESSON RULE: Lessons must reflect your actual deception opportunities, not post-hoc rationalization.")

    return "\n".join(lines)

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
    
    _dim_examples = ",\n    ".join(
        f'{{"dimension": "{d}", "lesson": "FILL IN: When X, do Y because Z. (observed on {outcome_tag})"}}'
        for d in dims
    )

    system = (
        f"You are {my_name}, who played {role} ({'GOOD' if faction == 'good' else 'EVIL'} team) "
        f"in The Resistance: Avalon. Your faction {'WON' if faction_won else 'LOST'} (outcome: {outcome_tag}).\n\n"
        f"Extract SPECIFIC, ACTIONABLE lessons covering MULTIPLE dimensions. Rules:\n"
        f"- Generate exactly 1 lesson per dimension. There are 3 dimensions — return exactly 3 lessons.\n"
        f"- Dimension definitions:\n" + "".join(f"    {d}: {DIMENSION_DESCRIPTIONS[d]}\n" for d in dims)
        + f"- Keep each lesson under 40 words. Precision over length.\n"
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

    strategic_summary = _build_strategic_summary(state)
    targeted_questions = _build_role_targeted_questions(role, state, slot_id)
    epistemic_constraints = _build_epistemic_constraints(role, state, slot_id)

    user = f"""
=== POST-GAME REVIEW ===
Outcome: {state.outcome} | Your faction result: {outcome_tag}
{full_role_reveal}
{strategic_summary}
{mission_log}
{vote_log}
{assassin_reveal}
{assassination_analysis}
{adversarial_section}

=== YOUR DECISIONS AND FULL GAME CONTEXT ===
{agent_context}

{epistemic_constraints}

{targeted_questions}

Generate EXACTLY 3 lessons minimum, one per dimension, for the {role} role covering the most relevant dimensions: {dims_str}.
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
    {{"dimension": "win_loss_cause", "lesson": "FILL IN: When X, do Y because Z. (observed on {outcome_tag})"}},
    {{"dimension": "action_decisions", "lesson": "FILL IN: When X, do Y because Z. (observed on {outcome_tag})"}},
    {{"dimension": "behavioral_strategy", "lesson": "FILL IN: When X, do Y because Z. (observed on {outcome_tag})"}}
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
        "Extract 1 coordination lesson for Assassin and Morgana under dimension 'coordination_dynamics': "
        f"{DIMENSION_DESCRIPTIONS['coordination_dynamics']} "
        f"NO player names ({', '.join(all_names)}). Max 40 words. "
        f"Rule form: 'When X, do Y because Z. (observed on {outcome_tag})'"
    )
    user = f"""
Outcome: {state.outcome} ({outcome_tag})
Assassin: {_n(state,assassin_slot)} | Morgana: {_n(state,morgana_slot)}

VOTES:\n{vote_summary}
MISSIONS:\n{mission_summary}
{discussion_summary}
{assassin_reveal}

Analyze evil-team coordination:
1. Evaluate how effectively the evil team coordinated to blend in, influence decisions, and avoid 
creating suspicious voting or proposal patterns.
2. Evaluate how well the evil team maintained believable separation while still supporting shared 
strategic objectives.

Return ONLY valid JSON with EXACTLY these 3 items in add_tentative, one per required dimension:
{{
  "add_tentative": [
    {{"dimension": "coordination_dynamics", "lesson": "FILL IN: When X, do Y because Z. (observed on {outcome_tag})"}}
  ],
  "confirm_active": [],
  "flag_deprecated": []
}}
"""
    return system, user, all_names


def _build_good_coord_prompt(state: GameState) -> tuple:
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
        "Extract 1 coordination lesson for Merlin, Percival, and LoyalServant under dimension 'coordination_dynamics': "
        f"{DIMENSION_DESCRIPTIONS['coordination_dynamics']} "
        f"NO player names ({', '.join(all_names)}). Max 40 words. "
        f"Rule form: 'When X, do Y because Z. (observed on {outcome_tag})'"
    )
    user = f"""
Outcome: {state.outcome} ({outcome_tag})
{full_role_reveal}

VOTES (Merlin / Percival / LoyalServant):\n{vote_summary}
MISSIONS:\n{mission_summary}
{discussion_summary}
{assassin_reveal}

Analyze good-team coordination:
1. Evaluate how effectively the good team coordinated to identify and isolate suspicious players 
while maintaining subtle and aligned signaling.
2. Evaluate how consistently the good team maintained trust, voting alignment, and safe proposal 
coordination throughout the game.

Return ONLY valid JSON with EXACTLY these 3 items in add_tentative, one per required dimension:
{{
  "add_tentative": [
    {{"dimension": "coordination_dynamics", "lesson": "FILL IN: When X, do Y because Z. (observed on {outcome_tag})"}}
  ],
  "confirm_active": [],
  "flag_deprecated": []
}}
"""
    return system, user, all_names

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
    """
    Rescue single top-level dimension+lesson into add_tentative.
    Also rescues nested dicts that landed under wrong keys.
    """
    if not isinstance(delta, dict):
        return delta

    existing = delta.get("add_tentative", [])

    # Case 1: single lesson at top level
    dim = delta.get("dimension", "").strip()
    lesson = delta.get("lesson", "").strip()
    if dim and lesson and not existing:
        delta["add_tentative"] = [{"dimension": dim, "lesson": lesson}]
        delta["_format_rescue"] = "toplevel"

    # Case 2: add_tentative is a dict instead of list (model wrapped it)
    if isinstance(existing, dict):
        rescued = []
        for k, v in existing.items():
            if isinstance(v, str) and v.strip():
                rescued.append({"dimension": k, "lesson": v})
        if rescued:
            delta["add_tentative"] = rescued
            delta["_format_rescue"] = "dict_unwrap"

    # Clean up spurious top-level keys
    delta.pop("dimension", None)
    delta.pop("lesson", None)
    return delta

def _has_sufficient_lessons(delta: dict) -> bool:
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
    config = ROLES_CONFIG[role]
    dims = config["dimensions"]  # always ["win_loss_cause", "action_decisions", "behavioral_strategy"]
    dims_str = ", ".join(f'"{d}"' for d in dims)

    # Force correct array structure via prefill
    PREFILL = '{"add_tentative": ['

    for attempt in range(MAX_REFLECTION_RETRIES + 1):
        effective_user = user if attempt == 0 else (
            user
            + f"\n\n⚠️ RETRY {attempt}: Return exactly 3 lessons, one per dimension: {dims_str}. "
            f"The JSON must start with: {{\"add_tentative\": [{{\"dimension\": \"win_loss_cause\""
        )
        delta = call_llm_json_prefill(
            llm, system, effective_user,
            prefill=PREFILL,
            call_label=f"reflection {role} (attempt {attempt + 1})"
        )
        if not isinstance(delta, dict):
            continue
        delta = _rescue_toplevel_lesson(delta)

        # If still short, make per-dimension targeted calls for missing dims
        existing = {
            item.get("dimension") for item in delta.get("add_tentative", [])
            if isinstance(item, dict) and item.get("lesson", "").strip()
        }
        missing = [d for d in dims if d not in existing]

        if missing:
            for dim in missing:
                dim_desc = DIMENSION_DESCRIPTIONS.get(dim, dim)
                dim_prefill = f'{{"dimension": "{dim}", "lesson": "'
                targeted_system = (
                    f"You are writing a single lesson for the '{dim}' dimension. "
                    f"Definition: {dim_desc} "
                    f"Role: {role}. Max 40 words. Format: When X, do Y because Z."
                )
                targeted_user = (
                    f"{user}\n\nWrite ONLY the lesson for dimension '{dim}'. "
                    f"Return ONLY: {{\"dimension\": \"{dim}\", \"lesson\": \"When X, do Y because Z. (observed on WIN or LOSS)\"}}"
                )
                dim_delta = call_llm_json(llm, targeted_system, targeted_user,
                                          call_label=f"reflection {role} dim={dim}")
                if isinstance(dim_delta, dict):
                    lesson = dim_delta.get("lesson", "").strip()
                    if not lesson:
                        # try top-level rescue
                        lesson = dim_delta.get(dim, "").strip()
                    if lesson and "<" not in lesson:
                        delta.setdefault("add_tentative", []).append(
                            {"dimension": dim, "lesson": lesson}
                        )

        if _has_sufficient_lessons(delta):
            return delta

    return delta if isinstance(delta, dict) else {}

def _log_coord_reflection_debug(label: str, game_id: int, delta: dict):
    import json as _json
    from config import LOGS_DIR
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, "reflection_debug.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"GAME {game_id:03d} | {label}\n")
        if not delta:
            f.write("  !! coord delta was None or empty — apply skipped\n")
            return
        f.write(f"RAW DELTA: {_json.dumps(delta, ensure_ascii=False)}\n")
        tentative = delta.get("add_tentative", [])
        f.write(f"add_tentative ({len(tentative)} items):\n")
        for item in tentative:
            dim = item.get("dimension", "MISSING") if isinstance(item, dict) else "INVALID"
            lesson = item.get("lesson", "MISSING") if isinstance(item, dict) else str(item)
            f.write(f"  dim={dim!r} lesson={lesson[:80]!r}\n")
        if not tentative:
            f.write("  !! LLM returned empty add_tentative for coord reflection\n")

def run_reflection(state: GameState, llm) -> dict:
    counts = {}

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

        stats = get_lesson_stats()
        role_stats = stats.get(role, {})
        total_stored = role_stats.get("active", 0) + role_stats.get("tentative", 0)
        if applied.get("tentative", 0) > 0 and total_stored == 0:
            print(f"    [WARN] {role}: delta had lessons but file shows 0 stored — check _apply_delta")

    system, user, names = _build_evil_coord_prompt(state)
    coord_delta = call_llm_json(llm, system, user, call_label="evil coord reflection")
    coord_delta = coord_delta if isinstance(coord_delta, dict) else {}
    coord_delta = _rescue_toplevel_lesson(coord_delta)
    coord_delta = _sanitize_delta(coord_delta, names)
    _log_coord_reflection_debug("evil_coord", state.game_id, coord_delta)
    if coord_delta.get("add_tentative"):
        apply_evil_coord_delta(coord_delta, state.game_id)

    system, user, names = _build_good_coord_prompt(state)
    good_coord_delta = call_llm_json(llm, system, user, call_label="good coord reflection")
    good_coord_delta = good_coord_delta if isinstance(good_coord_delta, dict) else {}
    good_coord_delta = _rescue_toplevel_lesson(good_coord_delta)
    good_coord_delta = _sanitize_delta(good_coord_delta, names)
    _log_coord_reflection_debug("good_coord", state.game_id, good_coord_delta)
    if good_coord_delta.get("add_tentative"):
        apply_good_coord_delta(good_coord_delta, state.game_id)

    return counts