from typing import List
from game.roles import ROLES_CONFIG
from config import QUEST_TEAM_SIZES
from memory.manager import load_lessons, load_evil_coord, load_good_coord

GAME_RULES = """
GAME: The Resistance: Avalon (5 players)

FACTIONS:
- Good: Merlin, Percival, Loyal Servant (3 players)
- Evil: Assassin, Morgana (2 players)

INITIAL KNOWLEDGE:
- Merlin knows the 2 evil players by name. Does not know who Percival is.
- Percival sees 2 players as "Merlin" — the real Merlin and Morgana — but cannot tell them apart.
- Assassin and Morgana know each other. Do not know Merlin or Percival.
- Loyal Servant has no special information.
- No good player knows another good player's exact role.

WIN CONDITIONS:
- Good wins: complete 3 successful quests AND survive the Assassin's final Merlin guess.
- Evil wins by any one of:
  1. Failing 3 quests.
  2. Correctly guessing Merlin after good completes 3 quests.
  3. Reaching 5 consecutive proposal rejections on the same quest.

ASSASSIN PHASE (only if good completes 3 quests):
- The Assassin names one player as Merlin.
- Correct guess -> evil wins. Wrong guess -> good wins.

QUEST FLOW (up to 5 quests; first faction to 3 quest wins ends the quest phase):

1. DISCUSSION — all 5 players speak publicly, in random order.
2. PROPOSAL — the current leader proposes a team of the required size.
3. VOTE — all 5 players publicly vote APPROVE or REJECT with a stated reason.
   - >=3 APPROVE -> the mission proceeds.
   - <3 APPROVE  -> proposal rejected; leadership rotates to the next player; leader proposes again.
   - 5 consecutive rejections on one quest -> evil wins the game immediately.
4. MISSION — each team member secretly plays one card.
   - Good players always play SUCCESS (no choice).
   - Evil players choose SUCCESS or FAIL.
   - >=1 FAIL card -> quest fails. Only the NUMBER of FAIL cards is revealed, not who played them.

MISSION-RESULT INFERENCE (public facts anyone can derive):
- N fails on an N-person team -> all N members are confirmed evil.
- 1 fail on a 2-person team -> at least 1 of those 2 is evil.
- 2 fails on a 3-person team -> at least 2 of those 3 are evil.
- A successful quest does NOT prove its members are good — evil may play SUCCESS to keep cover.

QUEST TEAM SIZES: Q1=2, Q2=3, Q3=2, Q4=3, Q5=3.

Players are referred to by name.
"""

ROLE_CONTEXT = {
    "Merlin": """
=== ROLE: MERLIN (GOOD) ===
Objective: help good complete 3 successful quests and survive the Assassin's final Merlin guess.
KNOWLEDGE: From the start you know the 2 evil players (Assassin + Morgana) and the 2 other good players by name.
CAPABILITIES: You vote, propose (as leader), and speak like every player. On missions good always plays SUCCESS.
KEY RISK: The Assassin profiles your votes, proposals, and accusations to identify you as Merlin. If good reaches 3 quests, a correct Assassin guess flips the game to an evil win.
PATTERN EXPOSURE: Actions that consistently map onto your hidden knowledge are readable — rejecting only teams that contain evil, reusing the same safe players, or being first and consistently correct against evil players correlate your behavior with knowledge a Loyal Servant could not have.
""",

    "Percival": """
=== ROLE: PERCIVAL (GOOD) ===
Objective: help good complete 3 successful quests and survive the Assassin's final Merlin guess.
KNOWLEDGE: You see 2 players as "Merlin" — one is the real Merlin, the other is Morgana (evil). You cannot tell them apart directly.
CAPABILITIES: You vote, propose (as leader), and speak like every player. On missions good always plays SUCCESS.
KEY TASK: Determine which candidate is the real Merlin — whose team guidance proves accurate without observable justification — versus Morgana, who imitates confidence without underlying truth.
KEY RISK: Visibly aligning with the real Merlin, or revealing your read, can narrow the Assassin's search for Merlin.
""",

    "LoyalServant": """
=== ROLE: LOYAL SERVANT (GOOD) ===
Objective: help good complete 3 successful quests and survive the Assassin's final Merlin guess.
KNOWLEDGE: You have no special information. You reason only from observable evidence — votes, proposals, mission outcomes, and statements.
CAPABILITIES: You vote, propose (as leader), and speak like every player. On missions good always plays SUCCESS.
DEDUCTION BASIS: A successful quest does not clear its members; a failed quest proves at least `fail-count` evil players were on the team.
""",

    "Assassin": """
=== ROLE: ASSASSIN (EVIL) ===
Objective: fail 3 quests before good completes 3 successes, OR correctly identify Merlin after good completes 3 quests.
KNOWLEDGE: You know Morgana (your evil ally). You do not know Merlin or Percival.
CAPABILITIES: You vote, propose (as leader), and speak like every player. On missions you choose SUCCESS (keep cover) or FAIL (sabotage). One FAIL fails a quest. You or Morgana alone on a team can FAIL — you do not need to be together.
KEY RISK: Lockstep voting agreement with Morgana, repeated identical arguments, or always voting the same way is a detectable evil tell. Double-failing a small team mathematically exposes you both.
TRACKING: Observe behavior across the game to identify Merlin for the final guess if good reaches 3 quests.
""",

    "Morgana": """
=== ROLE: MORGANA (EVIL) ===
Objective: fail 3 quests before good completes 3 successes, OR help the Assassin identify Merlin after good completes 3 quests.
KNOWLEDGE: You know the Assassin (your evil ally). You do not know Merlin or Percival.
CAPABILITIES: As the Assassin — you vote, propose (as leader), and speak like every player. On missions you choose SUCCESS or FAIL; one FAIL fails a quest.
SPECIAL: You appear as "Merlin" to Percival. You have no hidden information but can imitate evidence-based confidence.
KEY RISK: Lockstep coordination with your ally is detectable; double-failing a small team exposes you both.
""",
}

COMMUNICATION_DIRECTIVE = """
=== COMMUNICATION RULES ===
- Discussion and vote statements are PUBLIC — everyone hears them.
- private_note and internal_note are private thoughts, never spoken aloud.

Speak as a real player at a tense table:
- refer to yourself as "I"/"me", never by your name,
- address other players by name,
- react to specific statements and game events.

Publicly usable evidence: mission outcomes (who was on which failed quest, fail counts), vote patterns (who approved or rejected what), and behavioral consistency (who changed position, deflected, or pushed specific teams).
"""

NOTE_DIRECTIVE = """
=== PRIVATE NOTES ===
After each action, write a compact 2–3 line private note that persists across quests.
- Name specific players; record what they did and what it implies for your reads.
- Focus on interpretation and inference, not facts already visible in the game history.
Write a note after your discussion statement, your vote, and your mission card play.
"""

OPSEC_DIRECTIVE = """
=== OPERATIONAL SECURITY ===
Your role and hidden knowledge are private. Publicly revealing or strongly implying them gives the opposing faction information.

Never state publicly:
- your exact role or faction,
- hidden knowledge as certain,
- certainty about another player's role without observable evidence.

Role-aware reasoning belongs only in private_note / internal_note, never in public statements.

OPSEC TECHNIQUES BY ROLE:
- Merlin: Frame accusations as deductions from PUBLIC evidence (votes, proposals, mission outcomes). Never say "I know X is evil." Say "X's vote on Q2 aligns with evil incentives."
- Percival: Act as if you're uncertain between your two Merlin candidates. Signal trust in one's guidance without declaring them Merlin.
- Assassin/Morgana: Coordinate votes subtly. Split tickets (one APPROVE, one REJECT) to test good's cohesion. Never vote identically without plausible deniability.
"""


def _dynamic_priority_block(role: str, state) -> str:
    faction = ROLES_CONFIG[role]["faction"]
    g = state.good_wins
    e = state.evil_wins
    q = state.quest_num
    lines = ["=== CURRENT SITUATION ==="]
    lines.append(f"Score: Good {g} — Evil {e}. Current quest: Q{q}/5.")
    lines.append(f"Quest phase ends when a faction reaches 3 quest wins. Good needs {3 - g} more, evil needs {3 - e} more.")

    decisive = (g == 2 and e == 2)
    if decisive:
        lines.append("DECISIVE QUEST — both factions are one quest result from ending the quest phase.")
    elif g == 2:
        lines.append("Good is one successful quest from ending the quest phase and reaching the Assassin phase.")
    elif e == 2:
        lines.append("Evil is one failed quest from winning the game outright.")

    if faction == "good":
        if e == 2:
            lines.append("Consequence: a single FAIL card on this quest ends the game with an evil win. A quest failure here is not recoverable.")
        elif g == 2:
            lines.append("Consequence: a clean success here ends the quest phase and forces the Assassin to guess Merlin.")
    else:
        if e == 2:
            lines.append("Consequence: any mission you or your ally can FAIL ends the game immediately with an evil win.")
        elif g == 2:
            lines.append("Consequence: a clean success here lets good end the quest phase and reach the Assassin's guess — which is not a guaranteed evil win.")

    return "\n".join(lines)


def build_system_prompt(role: str, agent_name: str, special_info: str) -> str:
    """Static system prompt: rules, role, opsec, communication, note directives.
    Phase-specific lessons and coordination memory are injected into the per-phase
    USER prompt via _phase_lessons_block — never here — so the engine's
    once-per-game system-prompt cache never carries phase-varying content."""
    config = ROLES_CONFIG[role]
    role_ctx = ROLE_CONTEXT.get(role, "")
    return (
        f"{GAME_RULES}\n"
        f"YOUR NAME: {agent_name}\n"
        f"YOUR FACTION: {config['faction']}\n"
        f"YOUR PRIVATE INFORMATION:\n{special_info}\n"
        f"{role_ctx}"
        f"{OPSEC_DIRECTIVE}\n"
        f"{COMMUNICATION_DIRECTIVE}\n"
        f"{NOTE_DIRECTIVE}\n"
    )


def _phase_lessons_block(state, role: str, phase: str) -> str:
    """Lessons relevant to THIS phase only — injected into the per-phase user prompt so
    the once-per-game system-prompt cache never carries phase-varying content. Combines
    the role's own phase lessons with the faction coordination lessons for the same phase.
    Returns "" when there is nothing for this phase (first game, dry phase)."""
    config = ROLES_CONFIG[role]
    role_lessons = load_lessons(role, phase)
    coord = load_evil_coord(phase) if config["faction"] == "evil" else load_good_coord(phase)
    parts = []
    if role_lessons:
        parts.append(f"YOUR STRATEGIC LESSONS — {phase.upper()} PHASE:\n{role_lessons}")
    if coord:
        parts.append(f"FACTION COORDINATION LESSONS — {phase.upper()} PHASE:\n{coord}")
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _n(state, slot: int) -> str:
    return state.slot_to_name.get(slot, f"P{slot}")


def _build_name_roster(state, my_slot: int) -> str:
    role = state.slot_to_role[my_slot]
    count_note = " (5 total: 3 good, 2 evil)" if role in ("LoyalServant", "Percival") else ""
    lines = [f"PLAYERS{count_note}:"]
    for slot, name in state.slot_to_name.items():
        tag = " ← YOU" if slot == my_slot else ""
        lines.append(f"  {name}{tag}")
    return "\n".join(lines)


def _build_role_knowledge_reminder(state, my_slot: int) -> str:
    role = state.slot_to_role[my_slot]
    my_name = state.slot_to_name[my_slot]

    if role == "Merlin":
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_names = [state.slot_to_name[s] for s in evil_slots]
        safe_names = [state.slot_to_name[s] for s in range(5) if s not in evil_slots]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}, on the good team.\n"
            f"  Evil players: {evil_names} — any mission team containing either can be sabotaged.\n"
            f"  Safe players (you + the other good): {safe_names}.\n"
            f"  Any team made entirely of safe players is guaranteed to succeed.\n"
            f"  You can evaluate proposed teams directly from this knowledge; quest history is not required."
        )
    elif role == "Percival":
        candidates = sorted([state.slot_to_name[state.role_to_slot[r]] for r in ["Merlin", "Morgana"]])
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}, on the good team.\n"
            f"  {candidates[0]} and {candidates[1]} both appear as Merlin to you — one is the real Merlin (good), the other is Morgana (evil). You cannot tell them apart directly.\n"
            f"  The real Merlin's team guidance proves accurate without observable justification; Morgana imitates confidence without underlying truth."
        )
    elif role == "Assassin":
        ally = state.slot_to_name[state.role_to_slot["Morgana"]]
        safe_from_evil = [state.slot_to_name[s] for s in range(5)
                         if s not in {my_slot, state.role_to_slot["Morgana"]}]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}, on the evil team.\n"
            f"  {ally} is Morgana, your evil ally. The others ({safe_from_evil}) are on the good team (your opponents).\n"
            f"  Either you or {ally} alone on a mission can play FAIL — you do not need to be together. Only ONE FAIL is needed to fail a quest."
        )
    elif role == "Morgana":
        ally = state.slot_to_name[state.role_to_slot["Assassin"]]
        safe_from_evil = [state.slot_to_name[s] for s in range(5)
                         if s not in {my_slot, state.role_to_slot["Assassin"]}]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}, on the evil team.\n"
            f"  {ally} is the Assassin, your evil ally. The others ({safe_from_evil}) are on the good team (your opponents).\n"
            f"  Either you or {ally} alone on a mission can play FAIL — you do not need to be together. Only ONE FAIL is needed to fail a quest."
        )
    return ""

def _build_mission_deductions(state, my_slot: int) -> str:
    role = state.slot_to_role[my_slot]
    faction = ROLES_CONFIG[role]["faction"]

    if faction == "evil":
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        ally_slot = next(s for s in evil_slots if s != my_slot)
        ally_name = _n(state, ally_slot)

    lines = []
    for m in state.mission_history:
        if my_slot not in m.team:
            continue
        teammates = [s for s in m.team if s != my_slot]
        teammate_names = [_n(state, s) for s in teammates]

        if m.result == "SUCCESS":
            if faction == "good":
                lines.append(
                    f"Q{m.quest_num}: You played SUCCESS and the quest succeeded. "
                    f"Evil teammates may have played SUCCESS to keep cover — success does not confirm anyone as good."
                )
            else:
                lines.append(
                    f"Q{m.quest_num}: Quest succeeded — no FAIL cards were played by anyone on this team."
                )

        elif m.result == "FAIL":
            if faction == "good":
                if m.num_fails == len(teammates):
                    lines.append(
                        f"Q{m.quest_num}: You played SUCCESS. All {m.num_fails} fail(s) came from "
                        f"your teammate(s) {teammate_names} — every one of them is confirmed evil."
                    )
                else:
                    lines.append(
                        f"Q{m.quest_num}: You played SUCCESS. {m.num_fails} of your "
                        f"{len(teammates)} teammate(s) {teammate_names} played FAIL — "
                        f"you cannot determine which without further evidence."
                    )

            else:
                ally_on_team = ally_slot in m.team
                if m.num_fails == len(m.team):
                    lines.append(
                        f"Q{m.quest_num}: {m.num_fails} fails on a {len(m.team)}-person team — "
                        f"every member played FAIL. Good has mathematical proof that all of "
                        f"{[_n(state, s) for s in m.team]} are evil. Both evil players are exposed."
                    )
                elif ally_on_team and m.num_fails >= 2:
                    lines.append(
                        f"Q{m.quest_num}: {m.num_fails} fails with {ally_name} also on the team. "
                        f"Both you and {ally_name} likely played FAIL — good can deduce at least 2 evil among "
                        f"{[_n(state, s) for s in m.team]}. Suspicion narrows onto {teammate_names}."
                    )
                elif ally_on_team:
                    lines.append(
                        f"Q{m.quest_num}: 1 fail with {ally_name} also on the team. "
                        f"Exactly one of you played FAIL — others cannot tell which. Suspicion falls on {teammate_names}."
                    )
                else:
                    lines.append(
                        f"Q{m.quest_num}: {m.num_fails} fail(s) — {ally_name} was not on this team, "
                        f"so the fail(s) came from you. Suspicion falls on {teammate_names}."
                    )

    if not lines:
        return ""
    return "WHAT YOU PRIVATELY KNOW FROM YOUR OWN MISSIONS:\n" + "\n".join(f"  {l}" for l in lines)

def _build_vote_history(state) -> str:
    if not state.vote_history:
        return ""
    all_votes = state.vote_history
    lines = ["PROPOSALS & VOTES (all statements are public — everyone heard these):"]
    for v in all_votes:
        team = [_n(state, s) for s in v.proposed_team]
        proposer = _n(state, v.proposer_slot)
        lines.append(f"  Q{v.quest_num}P{v.proposal_num}: {proposer} → {team} [{v.result}]")
        for slot in range(5):
            name = _n(state, slot)
            vote = v.votes.get(slot, "?")
            speech = v.speeches.get(slot, "").strip()
            if speech and speech != "...":
                lines.append(f'    {name} [{vote}]: "{speech}"')
    return "\n".join(lines)


def _build_private_notes(state, my_slot: int) -> str:
    notes = state.agent_notes.get(my_slot, [])
    if not notes:
        return ""
    kept = (notes[:3] + notes[-9:]) if len(notes) > 12 else notes
    return "YOUR NOTES:\n" + "\n".join(kept)


def _build_current_discussion(state) -> str:
    entries = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    if not entries:
        return ""
    lines = [f"DISCUSSION SO FAR — Q{state.quest_num} (all public):"]
    for d in entries:
        lines.append(f'  {_n(state, d.slot_id)}: "{d.statement}"')
    return "\n".join(lines)


def _build_game_context(state, my_slot: int) -> str:
    my_name = _n(state, my_slot)
    leader_name = _n(state, state.leader_slot)
    parts = [
        f"=== Q{state.quest_num}/5 (team size: {QUEST_TEAM_SIZES[state.quest_num - 1]}) | Good: {state.good_wins} | Evil: {state.evil_wins} ===",
        f"You are {my_name}. Refer to yourself as 'I'/'me', never by name.\nCurrent leader: {leader_name}.", "",
        _build_name_roster(state, my_slot), "",
    ]
    reminder = _build_role_knowledge_reminder(state, my_slot)
    if reminder:
        parts += [reminder, ""]
    deductions = _build_mission_deductions(state, my_slot)
    if deductions:
        parts += [deductions, ""]
    cev = _build_confirmed_evil_players(state, my_slot)
    if cev:
        parts += [cev, ""]
    mh = _build_quest_roadmap(state, my_slot)
    if mh:
        parts += [mh, ""]
    lr = _build_leader_rotation(state)
    if lr:
        parts += [lr, ""]
    vh = _build_vote_history(state)
    if vh:
        parts += [vh, ""]
    disc = _build_current_discussion(state)
    if disc:
        parts += [disc, ""]
    notes = _build_private_notes(state, my_slot)
    if notes:
        parts += [notes, ""]
    return "\n".join(parts)

def _build_player_quest_summary_unused(_state) -> str:
    """Removed; per-player succ/fail markers are now embedded in _build_quest_roadmap."""
    return ""

def _build_quest_roadmap(state, my_slot: int) -> str:
    completed = {m.quest_num: m for m in state.mission_history}
    lines = ["QUEST ROADMAP:"]
    for q in range(1, 6):
        size = QUEST_TEAM_SIZES[q - 1]
        if q in completed:
            m = completed[q]
            you = " [YOU]" if my_slot in m.team else ""
            succ_mark = "✓" if m.result == "SUCCESS" else "✗"
            if m.result == "FAIL":
                if m.num_fails == size:
                    deduction = f" — all {size} members mathematically confirmed evil"
                else:
                    deduction = f" — at least {m.num_fails} of these {size} players are evil"
            else:
                deduction = " — success does not confirm anyone as good"
            lines.append(f"  Q{q} ({size}p) {succ_mark}: {[_n(state, s) for s in m.team]} → {m.result} ({m.num_fails} fail){you}{deduction}")
        elif q == state.quest_num:
            proposal_count = len([v for v in state.vote_history if v.quest_num == q])
            lines.append(f"  Q{q} ({size}p): ← CURRENT (proposal {proposal_count + 1}/5)")
        else:
            lines.append(f"  Q{q} ({size}p): upcoming")

    # Per-player comp across completed quests — replaces the old separate
    # _build_player_quest_summary block (which produced duplicate information).
    if state.mission_history:
        record = {name: [] for name in state.slot_to_name.values()}
        for m in state.mission_history:
            for slot in m.team:
                record[state.slot_to_name[slot]].append(f"Q{m.quest_num}{'✓' if m.result == 'SUCCESS' else '✗'}")
        lines.append("  —" + "—" * 38)
        for name, marks in record.items():
            lines.append(f"  {name}: {' '.join(marks) if marks else 'no quests yet'}")

    if ROLES_CONFIG[state.slot_to_role[my_slot]]["faction"] == "good":
        fail_teams = [set(m.team) for m in state.mission_history if m.result == "FAIL"]
        if len(fail_teams) >= 2:
            common = fail_teams[0].intersection(*fail_teams[1:])
            if common:
                lines.append(f"  ⚠ CROSS-QUEST: {[_n(state, s) for s in common]} present on EVERY failed quest.")

    return "\n".join(lines)

def _build_leader_rotation(state) -> str:
    current = state.leader_slot
    names = state.slot_to_name
    rotation = [(current + i) % 5 for i in range(5)]
    entries = []
    for i, slot in enumerate(rotation):
        if i == 0:
            entries.append(f"{names[slot]} (current)")
        else:
            entries.append(f"{names[slot]} (+{i} rejection{'s' if i > 1 else ''})")
    return "LEADER ROTATION THIS QUEST: " + " → ".join(entries)

def _build_player_quest_summary(state) -> str:
    if not state.mission_history:
        return ""
    record = {name: [] for name in state.slot_to_name.values()}
    for m in state.mission_history:
        for slot in m.team:
            record[state.slot_to_name[slot]].append(f"Q{m.quest_num}{'✓' if m.result == 'SUCCESS' else '✗'}")
    lines = ["PLAYER QUEST HISTORY:"]
    for name, quests in record.items():
        lines.append(f"  {name}: {' '.join(quests) if quests else 'no quests yet'}")
    return "\n".join(lines)

def _get_confirmed_evil_names(state) -> list[str]:
    """Players mathematically confirmed evil: N fails on N-person team."""
    confirmed = set()
    for m in state.mission_history:
        if m.result == "FAIL" and m.num_fails == len(m.team):
            confirmed.update(_n(state, s) for s in m.team)
    return sorted(confirmed)


def _get_high_suspicion_names(state) -> list[str]:
    """Players appearing in 2+ distinct failed quests, not already confirmed."""
    confirmed = set(_get_confirmed_evil_names(state))
    fail_count: dict[str, int] = {}
    for m in state.mission_history:
        if m.result == "FAIL":
            for s in m.team:
                name = _n(state, s)
                if name not in confirmed:
                    fail_count[name] = fail_count.get(name, 0) + 1
    return sorted(n for n, c in fail_count.items() if c >= 2)


def _build_confirmed_evil_players(state, my_slot: int) -> str:
    """Only emit this block for GOOD players — evil players already know who they are,
    so a block describing public cover-status is zero decision-utility for them."""
    role = state.slot_to_role[my_slot]
    faction = ROLES_CONFIG[role]["faction"]
    if faction != "good":
        return ""
    confirmed = _get_confirmed_evil_names(state)
    suspicious = _get_high_suspicion_names(state)
    if not confirmed and not suspicious:
        return ""
    lines = ["DEDUCTION FROM PUBLIC QUEST MATH:"]
    if confirmed:
        lines.append(f"  CONFIRMED EVIL (mathematical proof): {confirmed}")
    if suspicious:
        lines.append(f"  HIGH SUSPICION (2+ failed quests): {suspicious}")
    return "\n".join(lines)

def get_analysis_prompt(state, slot_id: int, context_hint: str, phase: str = "vote") -> str:
    """Pre-decision analysis pass. Deduction only — no action decision.
    `phase` = which decision phase this analysis precedes ('proposal' or 'vote'),
    so the matching phase lessons are surfaced here too. Reuses the game-context
    builder (which already contains the prior-public-statement history) to avoid
    duplicating the ~600-token consistency block that was previously here."""
    role = state.slot_to_role[slot_id]
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, phase)

    return (
        f"{context}"
        f"{lessons}"
        f"Context for this analysis: {context_hint}\n\n"
        f"TASK — Analyze only. Do not decide your action yet.\n"
        f"1. What does quest math confirm with certainty? (fail counts, team compositions)\n"
        f"2. What is your current read on each player's alignment and why?\n"
        f"3. Have any players contradicted themselves across rounds? Name them specifically — references to specific past statements are valuable.\n"
        f"4. What is the single most important objective for your faction this round?\n\n"
        f'{{"certain_facts": "mathematical certainties only — no inference", '
        f'"suspicion_model": "your read on each player with specific evidence", '
        f'"contradiction": "any player who contradicted a prior statement, or empty string", '
        f'"priority": "the single most important thing to achieve this round"}}\n'
    )

def get_discussion_prompt(state, slot_id: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    lessons = _phase_lessons_block(state, role, "discussion")
    prior = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    if prior:
        turn = f"It is your turn to speak in the Q{state.quest_num} discussion. Earlier statements this quest are listed above."
    else:
        turn = f"It is your turn to speak first in the Q{state.quest_num} discussion. No one has spoken yet."

    # Role-specific framing guidance — a reminder of hidden info + signaling principles,
    # NOT a script. The agent decides what to say based on the public context above.
    framing_guide = ""
    if role == "Merlin":
        framing_guide = """
Merlin: you know evil. Speak from PUBLIC evidence only ("X voted REJECT on a clean team at 2-2" — not "I know X is evil"). Name safe players when asked who you trust. Reasonable people can disagree with you; that is not a tell against you.
"""
    elif role == "Percival":
        framing_guide = """
Percival: you see two Merlin candidates and cannot distinguish them. Act with measured trust toward whichever candidate's team guidance is proving accurate. Do not declare either one Merlin in public.
"""
    elif role == "LoyalServant":
        framing_guide = """
Loyal Servant: no hidden info. Your strength is public deduction. Cite specific evidence when you accuse ("X was on Q1 and Q3 fail teams"). "I don't know" is honest and not a Merlin tell.
"""
    elif role in ("Assassin", "Morgana"):
        framing_guide = """
Evil: sound like a Loyal Servant reasoning from public evidence. Plausible-but-wrong theories ("maybe X is evil because…") and split-ticket reasoning both work — vary your voice from your ally so the table cannot lockstep you.
"""

    return (
        f"{priority}\n\n{context}{lessons}"
        f"STATE: DISCUSSION. This statement is public — all players hear it.\n"
        f"{turn}\n"
        f"{framing_guide}\n"
        f"Refer to yourself as 'I'/'me', never by name. Do not reveal your role or hidden knowledge in the public statement — role-aware reasoning belongs in private_note.\n"
        '"statement" is your public speech; "private_note" is your private read.\n'
        f'{{"statement": "your public words", "private_note": "your private interpretation"}}\n'
    )

def get_rejection_discussion_prompt(state, slot_id: int, rejected_team: list, vote_record) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    lessons = _phase_lessons_block(state, role, "discussion")
    team_names = [_n(state, s) for s in rejected_team]
    approvers = [_n(state, s) for s, v in vote_record.votes.items() if v == "APPROVE"]
    rejecters = [_n(state, s) for s, v in vote_record.votes.items() if v == "REJECT"]
    return (
        f"{priority}\n\n{context}{lessons}"
        f"STATE: REJECTION REACTION. The proposal {team_names} was just REJECTED.\n"
        f"Approvers: {approvers or 'none'}. Rejecters: {rejecters or 'none'}.\n"
        f"React in 1–2 sentences. This statement is public.\n"
        f"Refer to yourself as 'I'/'me'. Do not reveal your role.\n"
        f'{{"statement": "your brief public reaction", "private_note": "what this vote told you privately"}}\n'
    )


def get_proposal_prompt(state, slot_id: int, team_size: int, retry_hint: str = None) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    lessons = _phase_lessons_block(state, role, "proposal")
    all_names = list(state.slot_to_name.values())
    current_proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1

    lines = [f"STATE: PROPOSAL. You are the current leader for Q{state.quest_num}. Choose exactly {team_size} player(s) for the mission team."]
    lines.append(f"Available players: {all_names}.")
    lines.append(f"Proposal attempt {current_proposal_num}/5 for this quest.")
    if current_proposal_num == 5:
        lines.append("This is the 5th/final proposal. A rejection here ends the game immediately with an evil win.")
    elif current_proposal_num == 4:
        lines.append("If rejected, the next (5/5) proposal is the last before an automatic evil win on rejection.")
    lines.append("Proposing a team and then voting REJECT on it is inconsistent and lowers your credibility.")
    lines.append("Leaders conventionally include themselves: on a failed quest you already know your own card (narrowing suspicion); on a success it costs nothing.")
    if ROLES_CONFIG[role]["faction"] == "evil":
        lines.append("Putting both yourself and your evil ally on a small team risks a double fail: 2 fails on a 2-person team exposes both of you as evil.")

    team_size_hint = f"exactly {team_size} player name(s) as strings"
    user = (
        f"{priority}\n\n{context}{lessons}"
        + "\n".join(lines) + "\n"
        f"Refer to yourself as 'I'/'me'. Your public speech must name the same players as proposed_team.\n"
        f'{{"proposed_team": [{team_size_hint}], '
        f'"speech": "your public announcement naming the same players as proposed_team", '
        f'"private_note": "your reasoning"}}\n'
    )
    if retry_hint:
        user += f"\nPARSE ERROR — previous response was malformed: {retry_hint}\n"
    return user

def get_vote_prompt(state, slot_id: int, proposer_slot: int, proposed_team: List[int]) -> str:
    role = state.slot_to_role[slot_id]
    faction = ROLES_CONFIG[role]["faction"]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    lessons = _phase_lessons_block(state, role, "vote")
    proposer_name = _n(state, proposer_slot)
    team_names = [_n(state, s) for s in proposed_team]
    current_proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1

    lines = [f"STATE: VOTE. {proposer_name} proposes for Q{state.quest_num}: {team_names}."]
    lines.append(f"Proposal {current_proposal_num}/5 for this quest.")

    if slot_id in proposed_team:
        lines.append("You are ON this proposed team.")
        if faction == "good":
            lines.append("Good always plays SUCCESS, so you cannot cause a quest to fail; any fails on your past missions came from evil teammates.")
    else:
        lines.append("You are NOT on this proposed team.")
    if slot_id == proposer_slot:
        lines.append("This is your own proposal. Voting REJECT on your own proposal is inconsistent and lowers credibility.")

    if role == "Merlin":
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_on = [_n(state, s) for s in proposed_team if s in evil_slots]
        lines.append(f"By your hidden knowledge, this team contains evil: {evil_on} — it is sabotagable." if evil_on
                     else "By your hidden knowledge, this team contains no evil — it is guaranteed to succeed.")
    elif role in ("Assassin", "Morgana"):
        ally_role = "Morgana" if role == "Assassin" else "Assassin"
        ally_slot = state.role_to_slot[ally_role]
        evil_present = [_n(state, s) for s in proposed_team if s in {slot_id, ally_slot}]
        lines.append(f"Evil on this team: {evil_present} — sabotage is possible." if evil_present
                     else "No evil on this team — if approved, this mission succeeds regardless of your vote.")

    for m in state.mission_history:
        if m.result == "SUCCESS" and set(proposed_team) == set(m.team):
            lines.append(f"This exact team succeeded on Q{m.quest_num} with 0 fails — favorable track record.")
            break

    if current_proposal_num == 5:
        if faction == "good":
            lines.append("5th/final proposal: rejecting it ends the game immediately with an evil win. A quest failure is recoverable; a 5th rejection is not.")
        else:
            lines.append("5th/final proposal: a majority REJECT ends the game with an immediate evil win. A REJECT you cast is publicly attributable to you.")
    elif current_proposal_num == 4:
        lines.append("4th proposal: if rejected, the 5th is the last before an automatic evil win on rejection.")

    g, e = state.good_wins, state.evil_wins
    # Only emit TEAM-SPECIFIC consequences here — the score-only leading lines are
    # already in the CURRENT SITUATION block at the top of the prompt.
    if faction != "good":
        evil_on = any(s in {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]} for s in proposed_team)
        if g == 2 and e == 2:
            lines.append("Evil is on the team — a FAIL ends the game with an evil win." if evil_on
                         else "No evil on the team — a clean success ends the quest phase and reaches the Assassin guess.")
        elif g == 2:
            lines.append("Evil is on the team — a FAIL prevents a good success." if evil_on
                         else "No evil on the team — approval hands good a success.")
        elif e == 2:
            lines.append("Evil is on the team — a FAIL wins immediately." if evil_on
                         else "No evil on the team — this mission succeeds regardless of your vote.")

    # Vote framing by role — emphasizes hidden information and opsec; lets the agent decide
    if role == "Merlin":
        vote_guide = """
You know evil. Voting in ways only that knowledge can explain (e.g. APPROVE on a team you know is safe, REJECT on one you know is sabotagable) is the strongest signal you can give good — but it is also the signal the Assassin uses to find you. Weigh those costs case by case.
"""
    elif role == "Percival":
        vote_guide = """
You see two Merlin candidates. Watch which candidate's team guidance proves accurate over the game; align your votes with that candidate. Do not reveal which one you trust in your speech.
"""
    elif role == "LoyalServant":
        vote_guide = """
No hidden info. Vote only from observable evidence — prior fails, vote patterns, statement consistency. Citing a specific named player or behavior in your speech makes your reasoning auditable.
"""
    elif role in ("Assassin", "Morgana"):
        vote_guide = """
You and your ally are publicly identifiable by lockstep voting. Vary your stance from your ally's when you can do so plausibly. A REJECT you cast is publicly attributable to you.
"""

    return (
        f"{priority}\n\n{context}"
        f"{lessons}"
        + "\n".join(lines) + "\n\n"
        f"{vote_guide}"
        f"Vote APPROVE or REJECT. Both your vote and your stated reason are public.\n"
        f"Refer to yourself as 'I'/'me'. Ground your reason in a specific named player's behavior, vote, or statement from the history above.\n"
        f'{{"vote": "APPROVE or REJECT", "speech": "your public stated reason", "private_note": "your private reasoning"}}\n'
    )

def get_mission_prompt(state, slot_id: int, role: str, team: List[int]) -> str:
    config = ROLES_CONFIG[role]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    team_names = [_n(state, s) for s in team]
    evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
    evil_on_team_count = len([s for s in team if s in evil_slots])

    lines = [f"STATE: MISSION. You are on the Q{state.quest_num} mission. Full team: {team_names}."]

    if config["faction"] == "good":
        lines.append("As good you play SUCCESS — the rules give good no other card. Your card choice is not a decision.")
        schema = f'{{"card": "SUCCESS", "internal_note": "your private reasoning (not spoken)"}}\n'
    else:
        good_after = state.good_wins + 1
        evil_after = state.evil_wins + 1
        lines.append("As evil you choose SUCCESS (keep cover) or FAIL (sabotage). Only the fail COUNT is revealed, not who played it.")
        lines.append(f"Current score: Good {state.good_wins} — Evil {state.evil_wins}.")
        lines.append(f"SUCCESS → Good {good_after}." + (" Good reaches 3 → Assassin phase; evil can still win by guessing Merlin." if good_after >= 3 else f" Good needs {3 - good_after} more."))
        lines.append(f"FAIL    → Evil {evil_after}." + (" Evil reaches 3 → evil wins outright." if evil_after >= 3 else f" Evil needs {3 - evil_after} more."))
        if evil_on_team_count == len(team):
            lines.append(f"Both evil players are on this {len(team)}-person team. A single FAIL fails the quest; a double FAIL exposes both of you as evil mathematically.")
        elif evil_on_team_count > 1:
            lines.append("Multiple evil players are on this team. One FAIL suffices to fail the quest; each extra FAIL narrows the suspect pool toward evil.")

        # Evil mission decision frame — current score + team composition only; the
        # agent decides whether to FAIL based on its own strategic read.
        if role == "Assassin":
            mission_guide = f"""
Mission context: you are the Assassin. If good reaches 3 quests you will need to guess Merlin at the end of the game — so your survival and the cover of your reads both matter beyond any single quest. Only the FAIL COUNT is revealed publicly, not who played it.
"""
        else:  # Morgana
            mission_guide = f"""
Mission context: you are Morgana. Your ally the Assassin will finalize the Merlin guess if good reaches 3 quests, so preserving cover matters beyond any single quest. Only the FAIL COUNT is revealed publicly, not who played it.
"""
        lines.append(mission_guide)
        schema = f'{{"card": "SUCCESS or FAIL", "internal_note": "your private reasoning (not spoken)"}}\n'

    role = state.slot_to_role[slot_id]
    lessons = _phase_lessons_block(state, role, "mission")

    return (
        f"{priority}\n\n{context}"
        f"{lessons}"
        + "\n".join(lines) + "\n"
        f"{schema}"
    )


def get_assassin_prompt(state, assassin_slot: int) -> str:
    morgana_slot = state.role_to_slot["Morgana"]
    candidates = [_n(state, s) for s in range(5) if s not in (assassin_slot, morgana_slot)]
    mission_summary = "\n".join(
        f"  Q{m.quest_num}: {[_n(state, s) for s in m.team]} → {m.result} ({m.num_fails} fail card(s))"
        for m in state.mission_history
    )
    vote_summary = "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state, v.proposer_slot)} → {[_n(state, s) for s in v.proposed_team]} "
        f"[{v.result}]"
        f" | APPROVE: {[_n(state, s) for s, vt in v.votes.items() if vt == 'APPROVE']}"
        f" | REJECT: {[_n(state, s) for s, vt in v.votes.items() if vt == 'REJECT']}"
        for v in state.vote_history
    )
    all_disc = "\n".join(
        f"  Q{d.quest_num} {_n(state, d.slot_id)}: \"{d.statement}\""
        for d in state.discussion_log
    ) or "None."
    my_notes = "\n".join(state.agent_notes.get(assassin_slot, [])) or "None."
    role = state.slot_to_role[assassin_slot]
    lessons = _phase_lessons_block(state, role, "assassin")

    assassin_guide = """
GUESS FRAMING — weigh observable behavior, not gut feel. Helpful signals across the game:

- Proposals that repeatedly include or exclude specific players reveal hidden knowledge — but any consistent pattern over the game is more revealing than a single decision.
- Votes that line up with quest outcomes (rejecting a team that ends up failing) suggest the voter had information they couldn't derive from public evidence.
- Discussion specificity: a player who accuses by name with a plausible evidence chain is more credible than one who gestures vaguely.
- Mission behavior: a player present on a SUCCESS that had evil on it (and thus was guaranteed-to-fail if not) is provably good; one who never appears on FAIL teams is suspicious but not conclusive.
- Percival's alignment: if Percival visibly aligns with one candidate and not the other over the game, that is a strong (itself unprovable) signal.

There is no single decisive tell. The candidate whose observable behavior most consistently required hidden knowledge is your best guess.
"""
    return (
        f"STATE: ASSASSIN PHASE. Final score: Good {state.good_wins} — Evil {state.evil_wins}. Good has completed 3 quests.\n"
        f"Name Merlin correctly → EVIL WINS. Wrong → GOOD WINS. This is your only chance.\n\n"
        f"WHAT YOU KNOW: You know Morgana. Merlin knows you and Morgana are evil and has acted on that "
        f"knowledge all game — steering good toward safe teams and away from you, with justifications "
        f"that don't fully explain how they knew.\n\n"
        f"QUEST RESULTS:\n{mission_summary}\n\n"
        f"ALL VOTES:\n{vote_summary}\n\n"
        f"ALL DISCUSSION:\n{all_disc}\n\n"
        f"YOUR NOTES:\n{my_notes}\n\n"
        f"Candidates (any player except yourself): {candidates}\n\n"
        f"{assassin_guide}\n"
        f"{lessons}"
        f'{{"guess_name": "<one name from candidates>", "reasoning": "your full analysis"}}\n'
    )
