import json as _json
from config import LOGS_DIR

import os
import re
from game.state import GameState
from game.roles import ROLES_CONFIG, ALL_ROLES, EVIL_COORD_PHASES, GOOD_COORD_PHASES, PHASE_DESCRIPTIONS
from agents.llm_client import call_llm_json, call_llm_json_prefill
from memory.manager import (
    apply_lesson_delta,
    apply_evil_coord_delta,
    apply_good_coord_delta,
    get_lesson_stats,
    validate_lesson,
)

MAX_REFLECTION_RETRIES = 2

GOOD_ROLES = {"Merlin", "Percival", "LoyalServant"}
EVIL_ROLES = {"Assassin", "Morgana"}


def _validate_lesson_format(lesson: str, phase: str) -> tuple[bool, str]:
    """Thin wrapper — kept as a private name inside reflector.py for clarity, but
    delegates to the canonical validate_lesson in memory.manager."""
    return validate_lesson(lesson, phase)


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
    phases = config.get("phases", ["discussion", "proposal", "vote", "mission"])

    if faction == "evil":
        lines = [f"TARGETED QUESTIONS FOR {role.upper()} (by phase):"]
        lines.append(f"  You appeared on {len(my_missions)}/{total} quest teams.")
        if state.evil_wins == 0:
            lines.append("  Evil sabotaged zero quests. For each mission you played SUCCESS: was that the right call?")
            lines.append("  If you never had team access: why not, and what could you change in votes/discussion?")
        elif state.evil_wins < 3:
            lines.append(f"  Evil needed 3 quest fails but got {state.evil_wins}. What prevented the remaining fails?")
        return "\n".join(lines)

    elif role == "Merlin":
        lines = ["TARGETED QUESTIONS FOR MERLIN (by phase):"]
        if state.assassin_correct:
            lines.append("  ASSASSIN PHASE: You were assassinated. Which statements/votes could ONLY be explained by hidden knowledge?")
        else:
            lines.append("  ASSASSIN PHASE: You survived. What concealment choices protected you?")
        evil_proposals = [
            f"Q{v.quest_num}P{v.proposal_num}: included {[_n(state, s) for s in v.proposed_team if s in evil_slots]}"
            for v in state.vote_history
            if v.proposer_slot == slot_id and any(s in evil_slots for s in v.proposed_team)
        ]
        if evil_proposals:
            lines.append(f"  PROPOSAL: You proposed teams containing evil: {evil_proposals} — was this justified?")
        return "\n".join(lines)

    elif role == "Percival":
        merlin_slot = state.role_to_slot.get("Merlin")
        morgana_slot = state.role_to_slot.get("Morgana")
        lines = [
            "TARGETED QUESTIONS FOR PERCIVAL (by phase):",
            f"  Real Merlin was {_n(state, merlin_slot)}, Morgana was {_n(state, morgana_slot)}.",
            "  Did you correctly distinguish them? Did your behavior protect or expose Merlin?",
        ]
        return "\n".join(lines)

    else:
        evil_names = [_n(state, s) for s in evil_slots]
        lines = [
            f"TARGETED QUESTIONS FOR {role.upper()} (by phase):",
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

def _build_quality_bar() -> str:
    return (
        "\n=== LESSON QUALITY BAR (STRICT — ENFORCED) ===\n"
        "Each lesson MUST satisfy ALL of these:\n"
        "1. TRIGGER-ANCHORED: Names a concrete, observable game state (score, fail count, proposal number, "
        "repeated pattern, specific player behavior). No vague triggers ('when things go wrong', 'be careful').\n"
        "2. ACTIONABLE: States a specific decision or play (APPROVE/REJECT, include/exclude player, FAIL/SUCCESS, "
        "speech framing, guess target).\n"
        "3. CAUSAL REASON: Explains WHY this decision follows from the trigger using game mechanics.\n"
        "4. FORMAT: 'When X, do Y because Z. (observed on WIN|LOSS)' — ≤35 words.\n"
        "5. PHASE-CORRECT: The lesson belongs to the phase where the trigger appears and the action is taken.\n"
        "6. NO VAGUE FILLER: Reject 'trust steady players', 'watch everyone', 'be cautious', 'read the room'.\n"
        "7. GROUNDED: Each lesson must be traceable to a SPECIFIC MOMENT in THIS game (quote the turn/score/play).\n"
        "   You will privately identify that moment in a 'grounding' field (NOT persisted).\n\n"
        "POSITIVE EXAMPLE (vote phase):\n"
        "  'When score is 2-2 and a proposed team includes a player from a prior failed quest, "
        "vote REJECT because a single fail ends the game and clean teams are recoverable. (observed on LOSS)'\n"
        "NEGATIVE EXAMPLE (reject):\n"
        "  'Be careful when voting on late-game teams because evil might be on them. (observed on LOSS)'"
    )

def _build_reflection_prompt(role: str, state: GameState, slot_id: int) -> tuple:
    config = ROLES_CONFIG[role]
    faction = config["faction"]
    faction_won = (state.outcome == "GOOD_WINS") == (faction == "good")
    outcome_tag = "WIN" if faction_won else "LOSS"
    my_name = _n(state, slot_id)
    all_names = list(state.slot_to_name.values())
    phases = config.get("phases", ["discussion", "proposal", "vote", "mission"])

    full_role_reveal = "FULL ROLE REVEAL:\n" + "\n".join(
        f"  {_n(state, s)} → {r} ({'evil' if ROLES_CONFIG[r]['faction'] == 'evil' else 'good'})"
        for s, r in state.slot_to_role.items()
    )
    mission_log = "QUEST RESULTS:\n" + "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )
    vote_log = "ALL VOTES:\n" + "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state, v.proposer_slot)} → {[_n(state, s) for s in v.proposed_team]} "
        f"[{v.result}] | APPROVE: {[_n(state, s) for s, vt in v.votes.items() if vt == 'APPROVE']} "
        f"| REJECT: {[_n(state, s) for s, vt in v.votes.items() if vt == 'REJECT']}"
        for v in state.vote_history
    )
    discussion_log = "ALL DISCUSSION:\n" + "\n".join(
        f"  Q{d.quest_num} {_n(state, d.slot_id)}: \"{d.statement}\""
        for d in state.discussion_log
    ) or "None."

    agent_context = _format_agent_context(state, slot_id)
    strategic_summary = _build_strategic_summary(state)
    targeted_questions = _build_role_targeted_questions(role, state, slot_id)
    epistemic_constraints = _build_epistemic_constraints(role, state, slot_id)
    quality_bar = _build_quality_bar()

    # Few-shot examples per phase
    few_shots = """
FEW-SHOT EXAMPLES (format and quality):
DISCUSSION:
  Good: "When Percival asks 'who do you trust?', name your Morgana suspect to signal without claiming. (observed on WIN)"
  Bad:  "Be careful what you say in discussion because the Assassin is listening. (observed on LOSS)"
PROPOSAL:
  Good: "As Merlin on Q3+, include one uncertain player to test them; their vote reveals alignment. (observed on WIN)"
  Bad:  "Propose teams you think are good. (observed on LOSS)"
VOTE:
  Good: "When score is 2-2 and a proposed team includes a player from a prior failed quest, vote REJECT because a single fail ends the game. (observed on LOSS)"
  Bad:  "Vote carefully on late-game teams. (observed on LOSS)"
MISSION:
  Good: "As evil on a 3-person team with your ally, play exactly one FAIL — two fails exposes both of you. (observed on WIN)"
  Bad:  "Fail when you can. (observed on LOSS)"
ASSASSIN:
  Good: "When the Assassin guesses, target the player who approved suspicious teams and never questioned evil proposals. (observed on WIN)"
  Bad:  "Guess the quietest player. (observed on LOSS)"
"""

    phase_desc = "\n".join(f"  {p}: {PHASE_DESCRIPTIONS[p]}" for p in phases)

    system = (
        f"You are {role}, reflecting on a completed Avalon game. Outcome: {state.outcome} ({outcome_tag}).\n"
        f"Your task: extract phase-specific strategic lessons. Only phases you participated in: {phases}.\n"
        f"Phase definitions:\n{phase_desc}\n"
        f"{quality_bar}\n"
        f"{epistemic_constraints}\n\n"
        f"OUTPUT JSON SCHEMA (keys are EXACTLY these):\n"
        '{ "add_tentative": [ {"phase": "vote", "lesson": "...", "grounding": "specific moment in this game"}, ... ],\n'
        '  "confirm_active": [ {"phase": "...", "keyword": "..."} ],\n'
        '  "flag_deprecated": [ {"phase": "...", "keyword": "...", "reason": "..."} ] }'
    )

    user = (
        f"Game {state.game_id:03d} | Outcome: {state.outcome} ({outcome_tag}) | Your role: {role} ({my_name})\n\n"
        f"{full_role_reveal}\n\n"
        f"{mission_log}\n\n"
        f"{vote_log}\n\n"
        f"{discussion_log}\n\n"
        f"{strategic_summary}\n\n"
        f"{agent_context}\n\n"
        f"{targeted_questions}\n\n"
        f"{few_shots}\n"
        "Extract 0-1 lesson PER PHASE you acted in (skip phases where this game yielded no insight).\n"
        "Each lesson = trigger + action + causal reason + outcome tag. ≤35 words. "
        "Private 'grounding' field names the specific turn/score/play that anchors it.\n"
        'Return ONLY valid JSON starting with {"add_tentative": ['
    )

    return system, user, all_names

def _build_evil_coord_prompt(state: GameState) -> tuple:
    all_names = list(state.slot_to_name.values())
    phases = EVIL_COORD_PHASES
    phase_desc = "\n".join(f"  {p}: {PHASE_DESCRIPTIONS[p]}" for p in phases)
    assassin_slot = state.role_to_slot.get("Assassin")
    morgana_slot = state.role_to_slot.get("Morgana")

    vote_log = "VOTE HISTORY (A/M = Assassin/Morgana):\n" + "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state, v.proposer_slot)} → {[_n(state, s) for s in v.proposed_team]} "
        f"[{v.result}] | A: {v.votes.get(assassin_slot)} | M: {v.votes.get(morgana_slot)}"
        for v in state.vote_history
    )
    mission_log = "MISSIONS (evil on team marked *):\n" + "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s)+('*' if s in {assassin_slot,morgana_slot} else '') for s in m.team]} "
        f"→ {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )
    discussion_log = "DISCUSSION:\n" + "\n".join(
        f"  Q{d.quest_num} {_n(state, d.slot_id)}: \"{d.statement}\""
        for d in state.discussion_log
    ) or "None."

    system = (
        f"Extract coordination lessons for the EVIL TEAM (Assassin + Morgana). Outcome: {state.outcome}.\n"
        f"Phases: {phases}\n"
        f"Phase definitions:\n{phase_desc}\n"
        f"{_build_quality_bar()}\n\n"
        "Evil coordination lessons cover: signaling alignment without exposing both, "
        "vote coordination (split tickets, double-downs), proposal influence, fail discipline, "
        "and Merlin targeting the assassin phase.\n\n"
        "POSITIVE EXAMPLE (vote phase):\n"
        "  'When Assassin and Morgana both APPROVE a clean team at 0-0, split the next vote -- "
        "one REJECTs to test if good follows -- signaling confidence without lockstep. (observed on WIN)'\n"
        "POSITIVE EXAMPLE (mission phase):\n"
        "  'When both evil are on a 2-person team, EXACTLY ONE plays FAIL -- double-fail exposes both mathematically. (observed on LOSS)'\n"
        'OUTPUT JSON SCHEMA:\n'
        '{ "add_tentative": [ {"phase": "vote", "lesson": "...", "grounding": "..."} ],\n'
        '  "confirm_active": [ {"phase": "...", "keyword": "..."} ],\n'
        '  "flag_deprecated": [ {"phase": "...", "keyword": "...", "reason": "..."} ] }'
    )

    user = (
        f"Game {state.game_id:03d} | Evil outcome: {state.outcome}\n\n"
        f"{vote_log}\n\n"
        f"{mission_log}\n\n"
        f"{discussion_log}\n\n"
        "Extract 0-1 lesson PER PHASE where evil coordination was acted upon or revealed. "
        "Each lesson: trigger + action + reason + outcome tag. ≤35 words. "
        "Private 'grounding' field names the specific moment.\n"
        'Return ONLY valid JSON starting with {"add_tentative": ['
    )

    return system, user, all_names

def _build_good_coord_prompt(state: GameState) -> tuple:
    all_names = list(state.slot_to_name.values())
    phases = GOOD_COORD_PHASES
    phase_desc = "\n".join(f"  {p}: {PHASE_DESCRIPTIONS[p]}" for p in phases)
    merlin_slot = state.role_to_slot.get("Merlin")
    percival_slot = state.role_to_slot.get("Percival")
    loyal_slots = [s for s, r in state.slot_to_role.items() if r == "LoyalServant"]

    vote_log = "VOTE HISTORY (M/P/L = Merlin/Percival/LoyalServant):\n" + "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state, v.proposer_slot)} → {[_n(state, s) for s in v.proposed_team]} "
        f"[{v.result}] | M: {v.votes.get(merlin_slot)} | P: {v.votes.get(percival_slot)} | "
        f"L: {[v.votes.get(s) for s in loyal_slots]}"
        for v in state.vote_history
    )
    mission_log = "MISSIONS:\n" + "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )
    discussion_log = "DISCUSSION:\n" + "\n".join(
        f"  Q{d.quest_num} {_n(state, d.slot_id)}: \"{d.statement}\""
        for d in state.discussion_log
    ) or "None."

    system = (
        f"Extract coordination lessons for the GOOD TEAM (Merlin, Percival, LoyalServant). Outcome: {state.outcome}.\n"
        f"Phases: {phases}\n"
        f"Phase definitions:\n{phase_desc}\n"
        f"{_build_quality_bar()}\n\n"
        "Good coordination lessons cover: trusted cluster formation, Merlin protection via Percival, "
        "vote alignment without exposing Merlin, clean proposal support, fail-pattern reading, "
        "and consensus maintenance under pressure.\n\n"
        "POSITIVE EXAMPLE (vote phase):\n"
        "  'When score is 2-2 and a proposed team has no prior-fail players, Percival APPROVEs and "
        "signals Merlin to do the same -- clean teams must be passed at match point. (observed on WIN)'\n"
        "POSITIVE EXAMPLE (proposal phase):\n"
        "  'When Merlin is leader at 1-1, propose the 2 players you trust most -- Percival reads this "
        "as a trust signal and aligns. (observed on WIN)'\n"
        'OUTPUT JSON SCHEMA:\n'
        '{ "add_tentative": [ {"phase": "vote", "lesson": "...", "grounding": "..."} ],\n'
        '  "confirm_active": [ {"phase": "...", "keyword": "..."} ],\n'
        '  "flag_deprecated": [ {"phase": "...", "keyword": "...", "reason": "..."} ] }'
    )

    user = (
        f"Game {state.game_id:03d} | Good outcome: {state.outcome}\n\n"
        f"{vote_log}\n\n"
        f"{mission_log}\n\n"
        f"{discussion_log}\n\n"
        "Extract 0-1 lesson PER PHASE where good coordination was acted upon or revealed. "
        "Each lesson: trigger + action + reason + outcome tag. ≤35 words. "
        "Private 'grounding' field names the specific moment.\n"
        'Return ONLY valid JSON starting with {"add_tentative": ['
    )

    return system, user, all_names

def _log_reflection_debug(game_id: int, role: str, delta: dict, applied_counts: dict):
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, "reflection_debug.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"GAME {game_id:03d} | {role}\n")
        f.write(f"RAW DELTA: {_json.dumps(delta, ensure_ascii=False)}\n")
        tentative = delta.get("add_tentative", [])
        f.write(f"add_tentative ({len(tentative)} items):\n")
        for item in tentative:
            if not isinstance(item, dict):
                f.write(f"  INVALID ITEM: {item!r}\n")
                continue
            phase = item.get("phase", "MISSING")
            lesson = item.get("lesson", "MISSING")
            grounding = item.get("grounding", "MISSING")
            skipped = "<" in phase or "<" in lesson or not phase.strip() or not lesson.strip()
            f.write(f"  {'SKIP' if skipped else 'OK  '} phase={phase!r} lesson={lesson[:80]!r} grounding={grounding[:60]!r}\n")
        f.write(f"confirm_active: {len(delta.get('confirm_active', []))} items\n")
        f.write(f"flag_deprecated: {len(delta.get('flag_deprecated', []))} items\n")
        f.write(f"applied => tentative+{applied_counts.get('tentative',0)} "
                f"confirmed+{applied_counts.get('confirmed',0)} "
                f"deprecated+{applied_counts.get('deprecated',0)}\n")
        if not tentative:
            f.write("  !! LLM returned empty add_tentative\n")

def _log_coord_reflection_debug(label: str, game_id: int, delta: dict):
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
            phase = item.get("phase", "MISSING") if isinstance(item, dict) else "INVALID"
            lesson = item.get("lesson", "MISSING") if isinstance(item, dict) else str(item)
            grounding = item.get("grounding", "MISSING") if isinstance(item, dict) else "N/A"
            f.write(f"  phase={phase!r} lesson={lesson[:80]!r} grounding={grounding[:60]!r}\n")
        if not tentative:
            f.write("  !! LLM returned empty add_tentative for coord reflection\n")

def _rescue_toplevel_lesson(delta: dict) -> dict:
    """Rescue single top-level phase+lesson into add_tentative. Also handles wrong-key dicts."""
    if not isinstance(delta, dict):
        return delta

    existing = delta.get("add_tentative", [])

    # Case 1: single lesson at top level
    phase = delta.get("phase", "").strip()
    lesson = delta.get("lesson", "").strip()
    if phase and lesson and not existing:
        delta["add_tentative"] = [{"phase": phase, "lesson": lesson}]
        delta["_format_rescue"] = "toplevel"

    # Case 2: add_tentative is a dict instead of list (model wrapped it)
    if isinstance(existing, dict):
        rescued = []
        for k, v in existing.items():
            if isinstance(v, str) and v.strip():
                rescued.append({"phase": k, "lesson": v})
        if rescued:
            delta["add_tentative"] = rescued
            delta["_format_rescue"] = "dict_unwrap"

    # Case 3: items have 'dimension' instead of 'phase' (backward compat)
    for item in delta.get("add_tentative", []):
        if isinstance(item, dict) and "dimension" in item and "phase" not in item:
            item["phase"] = item.pop("dimension")

    # Clean up spurious top-level keys
    delta.pop("phase", None)
    delta.pop("lesson", None)
    delta.pop("grounding", None)
    delta.pop("dimension", None)
    return delta

def _has_sufficient_lessons(delta: dict) -> bool:
    """At least 1 lesson total; ideally one per acted phase. No hard minimum of 3."""
    tentative = delta.get("add_tentative", [])
    valid = [
        item for item in tentative
        if isinstance(item, dict)
        and item.get("phase", "").strip()
        and item.get("lesson", "").strip()
        and "<" not in item.get("phase", "")
        and "<" not in item.get("lesson", "")
        and _validate_lesson_format(item["lesson"], item["phase"])[0]
    ]
    return len(valid) >= 1

def _call_reflection_with_retry(llm, system: str, user: str, role: str, game_id: int, phases: list) -> dict:
    """Reflection call with format-aware retries. Two configurations:
       1) primary: prefilled JSON with per-phase lesson list;
       2) on validation fail, per-phase targeted retry for any missing/empty phases.
    Returns the best valid dict (with add_tentative populated), or {} on failure."""
    PREFILL = '{"add_tentative": ['

    def _validate_tentative(items):
        ok = []
        for item in items:
            if not isinstance(item, dict):
                continue
            phase = item.get("phase", "").strip()
            lesson = item.get("lesson", "").strip()
            if not phase or not lesson or "<" in phase or "<" in lesson:
                continue
            is_valid, reason = _validate_lesson_format(lesson, phase)
            if not is_valid:
                print(f"    [REFLECTION VALIDATION] Rejected {phase} lesson: {reason} — \"{lesson[:60]}...\"")
                continue
            ok.append({"phase": phase, "lesson": lesson, "grounding": item.get("grounding", "")})
        return ok

    def _backfill_missing(delta):
        """For any phase the LLM didn't fill, ask for it directly."""
        backfilled = list(delta.get("add_tentative", []))
        covered = {item["phase"] for item in backfilled}
        for phase in phases:
            if phase in covered:
                continue
            targeted_user = (
                f"{user}\n\nWrite ONLY the lesson for phase '{phase}'. "
                f'Return ONLY: {{"phase": "{phase}", "lesson": "When X, do Y because Z. (observed on WIN or LOSS)"}}'
            )
            targeted_system = (
                f"You are writing a single lesson for the '{phase}' phase. "
                f"Definition: {PHASE_DESCRIPTIONS.get(phase, phase)}. "
                f"Role: {role}. Max 35 words. Format: When X, do Y because Z. (observed on WIN|LOSS)"
            )
            extra = call_llm_json(
                llm, targeted_system, targeted_user,
                call_label=f"reflection {role} phase={phase}",
            )
            if not isinstance(extra, dict):
                continue
            lesson = (extra.get("lesson") or extra.get(phase) or "").strip()
            if not lesson or "<" in lesson:
                continue
            is_valid, reason = _validate_lesson_format(lesson, phase)
            if not is_valid:
                print(f"    [TARGETED RESCUE] Rejected {phase} lesson: {reason}")
                continue
            backfilled.append({"phase": phase, "lesson": lesson})
        delta["add_tentative"] = backfilled

    # Primary attempts — prefill-forced emission.
    for attempt in range(MAX_REFLECTION_RETRIES + 1):
        effective_user = user if attempt == 0 else (
            user + f"\n\n⚠️ RETRY {attempt}: Return 0-1 lesson per relevant phase: {phases}. "
                   f"The JSON must start with: {{\"add_tentative\": [{{\"phase\": \"{phases[0]}\""
        )
        delta = call_llm_json_prefill(
            llm, system, effective_user,
            prefill=PREFILL,
            call_label=f"reflection {role} (attempt {attempt + 1})",
        )
        if not isinstance(delta, dict):
            continue
        delta = _rescue_toplevel_lesson(delta)
        delta["add_tentative"] = _validate_tentative(delta.get("add_tentative", []))
        _backfill_missing(delta)

        if _has_sufficient_lessons(delta):
            return delta

    # Best-effort fallback: keep whatever validated so far, even if zero lessons.
    return delta if isinstance(delta, dict) else {}

def run_reflection(state: GameState, llm) -> dict:
    counts = {}

    for role in ALL_ROLES:
        slot_id = state.role_to_slot[role]
        system, user, names = _build_reflection_prompt(role, state, slot_id)
        phases = ROLES_CONFIG[role].get("phases", ["discussion", "proposal", "vote", "mission"])
        delta = _call_reflection_with_retry(llm, system, user, role, state.game_id, phases)

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
        applied_tentative = counts[role].get("tentative", 0)
        if applied_tentative > 0 and total_stored == 0:
            print(f"    [WARN] {role}: delta had lessons but file shows 0 stored — check _apply_delta")

    # Evil coordination reflection
    system, user, names = _build_evil_coord_prompt(state)
    coord_delta = call_llm_json(llm, system, user, call_label="evil coord reflection")
    coord_delta = coord_delta if isinstance(coord_delta, dict) else {}
    coord_delta = _rescue_toplevel_lesson(coord_delta)
    coord_delta = _sanitize_delta(coord_delta, names)
    _log_coord_reflection_debug("evil_coord", state.game_id, coord_delta)
    if coord_delta.get("add_tentative"):
        apply_evil_coord_delta(coord_delta, state.game_id)

    # Good coordination reflection
    system, user, names = _build_good_coord_prompt(state)
    good_coord_delta = call_llm_json(llm, system, user, call_label="good coord reflection")
    good_coord_delta = good_coord_delta if isinstance(good_coord_delta, dict) else {}
    good_coord_delta = _rescue_toplevel_lesson(good_coord_delta)
    good_coord_delta = _sanitize_delta(good_coord_delta, names)
    _log_coord_reflection_debug("good_coord", state.game_id, good_coord_delta)
    if good_coord_delta.get("add_tentative"):
        apply_good_coord_delta(good_coord_delta, state.game_id)

    return counts