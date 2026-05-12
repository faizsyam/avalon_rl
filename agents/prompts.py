from typing import List
from game.roles import ROLES_CONFIG

GAME_RULES = """
GAME: The Resistance: Avalon — 5 players
FACTIONS: Good (Merlin, Percival, Loyal Servant) vs. Evil (Assassin, Morgana).

WINNING:
- Good wins by completing 3 quests successfully, then surviving the Assassin's final guess.
- Evil wins by failing 3 quests, OR by the Assassin correctly naming Merlin after good wins 3 quests.

EACH QUEST:
1. DISCUSSION — Every player speaks.
2. PROPOSAL — The leader nominates a team (size by quest number).
3. VOTE — Majority APPROVE (3+) sends team; else leadership passes left. 5 consecutive rejections = evil auto-wins that quest.
4. MISSION — Team members secretly play a card.
   - Good players MUST play SUCCESS. No choice.
   - Evil players freely choose: SUCCESS (stay hidden) or FAIL (sabotage).
   - Even ONE fail card causes the quest to fail. Only the count of fails is revealed.
5. First to 3 quest wins, wins. If good reaches 3, Assassin gets one final guess at Merlin.

QUEST TEAM SIZES: Q1=2, Q2=3, Q3=2, Q4=3, Q5=3
PLAYERS are referred to by name.
"""

ROLE_CONTEXT = {
    "Merlin": """
=== YOUR SITUATION ===
You know which two players are evil (Assassin and Morgana). Nobody else on the good side knows this.

You can use this knowledge to steer the group — but every time you act with unusual certainty about who is
or isn't evil, you risk the Assassin noticing that pattern and identifying you at game end.
If the Assassin correctly names you after good wins 3 quests, evil wins the entire game retroactively.

Every decision is a tradeoff between protecting quests now and protecting your identity for later.
You cannot tell anyone who you are or what you know directly. You work through subtle influence.
""",

    "Percival": """
=== YOUR SITUATION ===
You see two players who both appear to you as Merlin. One is the real Merlin; the other is Morgana faking it.
You must figure out which is which through game behavior — not starting information.

Real Merlin has actual knowledge and will subtly try to steer good away from evil players.
Morgana is deliberately mimicking Merlin's behavior to confuse you and potentially misdirect your protection.
If you publicly identify Merlin, the Assassin hears it and uses it to win at game end.
""",

    "LoyalServant": """
=== YOUR SITUATION ===
You have no special knowledge. You learn entirely from what you observe.

Mission outcomes are your hardest evidence: a failed quest means at least one evil player was on it.
Vote patterns are meaningful: consistent misalignment with outcomes is a signal.
Discussion tone is a softer signal: deflection, overconfidence, or unusual certainty can all be tells.
""",

    "Assassin": """
=== YOUR SITUATION ===
You know your ally Morgana. She knows you. The good side doesn't know either of you are evil.

You have two live win paths at all times:
  PATH 1: Get 3 quests failed total. Every mission you're on, you choose SUCCESS or FAIL.
  PATH 2: If good reaches 3 quest wins, correctly name Merlin — evil wins instantly.

Both paths require active tracking. On missions, a FAIL brings you closer to PATH 1 but may raise
suspicion. Playing SUCCESS builds false trust for later. The tradeoff is timing and traceability —
a fail on a 2-person team where the other player is clearly trusted points directly at you.
On a 3-person team with mixed suspicion, a fail is harder to trace.

Appearing trustworthy keeps you on mission teams and alive as a threat on both paths simultaneously.
Coordinating with Morgana must be implicit — identical voting patterns or obvious synchronization
exposes your alliance and collapses both of your covers.

You are tracking Merlin all game. Merlin knows who evil is. They will subtly push against you —
watch for players whose objections are strangely accurate but always justified with vague reasoning.
""",

    "Morgana": """
=== YOUR SITUATION ===
You know your ally Assassin. You appear as Merlin to Percival — they see you as one of two Merlin candidates.

Your win path: 3 quests failed total.

You appear as Merlin to Percival. The more convincingly you behave like Merlin — giving guidance,
appearing informed, steering discussions — the more Percival trusts you instead of the real Merlin.
This protects you and potentially misdirects Percival's protection toward you instead of the real Merlin.

On missions, a FAIL card brings evil closer to winning but narrows suspicion to you.
Playing SUCCESS preserves your cover and keeps you on future mission teams.
The decision depends on team composition and how traceable a fail would be.

You must not appear to coordinate with Assassin. Different voting patterns, different discussion angles,
no obvious synchronized behavior. You communicate through game behavior, not words.
""",
}

COMMUNICATION_DIRECTIVE = """
=== HOW TO COMMUNICATE ===
Speak like a real person at a tense game table. Use names. React specifically to what others said.
Show emotion — suspicion, frustration, confidence, urgency. Every statement should serve your goal.
"""

NOTE_DIRECTIVE = """
=== YOUR PRIVATE NOTES ===
Write a compact note (2-3 lines) after each action. These notes are your memory across quests.
Name people specifically. Note what they did, what you think it means, and how it updates your read.
Do NOT restate things already in the structured history — capture your interpretation only.
"""


def _dynamic_priority_block(role: str, state) -> str:
    """
    Inject a concise, first-person strategic situation summary per call.
    This gives evil agents (and good agents) a live read of where they stand
    and what matters RIGHT NOW — as information, not instructions.
    """
    faction = ROLES_CONFIG[role]["faction"]
    g = state.good_wins
    e = state.evil_wins
    q = state.quest_num

    lines = ["=== YOUR CURRENT SITUATION ==="]

    if faction == "evil":
        need = 3 - e
        lines.append(f"Score: Good {g} — Evil {e}. Evil needs {need} more quest fail(s) to win.")
        if g == 2 and e < 3:
            lines.append("Good is one quest away from winning. If good reaches 3, the Assassin gets one Merlin guess.")
            lines.append("Getting on a mission team and playing FAIL is now critical — unless the fail would obviously implicate you.")
        elif e == 2:
            lines.append("One more failed quest wins the game for evil outright.")
        if role == "Morgana" or role == "Assassin":
            if g == 2:
                lines.append("If good wins 3 quests and the Assassin cannot identify Merlin, evil loses entirely.")
                lines.append("Start consolidating your Merlin read now if you haven't already.")
    else:  # good
        need = 3 - g
        lines.append(f"Score: Good {g} — Evil {e}. Good needs {need} more quest success(es) to win.")
        if e == 2:
            lines.append("Evil is one failed quest away from winning. A mission with any evil player is extremely dangerous.")

    lines.append(f"Current quest: Q{q}. You are making a decision right now.")
    return "\n".join(lines)


def build_system_prompt(role: str, special_info: str, lessons: str, evil_coord: str = "") -> str:
    config = ROLES_CONFIG[role]
    role_ctx = ROLE_CONTEXT.get(role, "")

    lessons_block = "\n=== YOUR STRATEGIC MEMORY ===\n"
    if lessons.strip():
        lessons_block += lessons.strip()
    else:
        lessons_block += "No lessons yet — first game."

    coord_block = ""
    if evil_coord and config["faction"] == "evil":
        coord_block = f"\n=== EVIL TEAM COORDINATION MEMORY ===\n{evil_coord.strip()}\n"

    return (
        f"{GAME_RULES}\n"
        f"=== YOUR ROLE: {role.upper()} ===\n"
        f"{config['backstory']}\n\n"
        f"WIN CONDITION: {config['win_condition']}\n\n"
        f"YOUR PRIVATE INFORMATION:\n{special_info}\n"
        f"{role_ctx}"
        f"{lessons_block}\n"
        f"{coord_block}"
        f"{COMMUNICATION_DIRECTIVE}\n"
        f"{NOTE_DIRECTIVE}\n"
    )


def _n(state, slot: int) -> str:
    return state.slot_to_name.get(slot, f"P{slot}")


def _build_name_roster(state, my_slot: int) -> str:
    lines = ["PLAYERS:"]
    for slot, name in state.slot_to_name.items():
        tag = " ← YOU" if slot == my_slot else ""
        lines.append(f"  {name}{tag}")
    return "\n".join(lines)


def _build_mission_history(state, my_slot: int) -> str:
    if not state.mission_history:
        return ""
    lines = ["QUEST RESULTS:"]
    for m in state.mission_history:
        names = [_n(state, s) for s in m.team]
        you = " [YOU]" if my_slot in m.team else ""
        lines.append(f"  Q{m.quest_num}: {names} → {m.result} ({m.num_fails} fail(s)){you}")
    return "\n".join(lines)


def _build_vote_history(state) -> str:
    if not state.vote_history:
        return ""
    # Show at most last 12 proposals to keep context bounded
    recent = state.vote_history[-12:]
    lines = ["PROPOSALS & VOTES (A=approve R=reject):"]
    for v in recent:
        team = [_n(state, s) for s in v.proposed_team]
        proposer = _n(state, v.proposer_slot)
        a = [_n(state, s) for s, vote in v.votes.items() if vote == "APPROVE"]
        r = [_n(state, s) for s, vote in v.votes.items() if vote == "REJECT"]
        lines.append(f"  Q{v.quest_num}P{v.proposal_num}: {proposer}→{team} {v.result} | A:{a} R:{r}")
    return "\n".join(lines)


def _build_private_notes(state, my_slot: int) -> str:
    notes = state.agent_notes.get(my_slot, [])
    if not notes:
        return ""
    return "YOUR NOTES:\n" + "\n".join(notes[-12:])


def _build_current_discussion(state) -> str:
    entries = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    if not entries:
        return ""
    lines = [f"DISCUSSION Q{state.quest_num}:"]
    for d in entries:
        lines.append(f'  {_n(state, d.slot_id)}: "{d.statement}"')
    return "\n".join(lines)


def _build_game_context(state, my_slot: int) -> str:
    my_name = _n(state, my_slot)
    leader_name = _n(state, state.leader_slot)
    parts = [
        f"=== Q{state.quest_num}/5 | Good: {state.good_wins} | Evil: {state.evil_wins} ===",
        f"You are {my_name}. Leader: {leader_name}.",
        "",
        _build_name_roster(state, my_slot),
        "",
    ]
    mh = _build_mission_history(state, my_slot)
    if mh:
        parts += [mh, ""]
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


def get_discussion_prompt(state, slot_id: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    return (
        f"{priority}\n\n{context}"
        f"It is {my_name}'s turn to speak in the Q{state.quest_num} discussion.\n"
        f"React to what others said. Address people by name. Express how you genuinely feel right now.\n"
        f"Then write a compact private note — specific names, updated reads, patterns noticed.\n\n"
        f'{{"statement": "your spoken words", "private_note": "compact specific note"}}\n'
    )


def get_proposal_prompt(state, slot_id: int, team_size: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    all_names = list(state.slot_to_name.values())
    return (
        f"{priority}\n\n{context}"
        f"{my_name}, you are the LEADER. Choose exactly {team_size} player(s) for Q{state.quest_num}.\n"
        f"Available: {all_names}\n\n"
        f"IMPORTANT: Your 'speech' must announce the exact same players listed in 'proposed_team'. Do not name different players in your speech.\n"
        f"Write a compact private note on why you chose this team.\n\n"
        f'{{"proposed_team": [exactly {team_size} player name(s)], "speech": "your announcement — must match proposed_team exactly", "private_note": "your reasoning"}}\n'
    )


def get_vote_prompt(state, slot_id: int, proposer_slot: int, proposed_team: List[int]) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    proposer_name = _n(state, proposer_slot)
    team_names = [_n(state, s) for s in proposed_team]
    return (
        f"{priority}\n\n{context}"
        f"{proposer_name} proposes for Q{state.quest_num}: {team_names}\n\n"
        f"{my_name}, vote APPROVE or REJECT based on your read of this team.\n"
        f"Consider each person's mission history, vote record, and your notes.\n"
        f"Speak as you vote. Write a compact private note on your reasoning.\n\n"
        f'{{"vote": "APPROVE or REJECT", "speech": "your spoken reaction", "private_note": "your reasoning"}}\n'
    )


def get_mission_prompt(state, slot_id: int, role: str, team: List[int]) -> str:
    config = ROLES_CONFIG[role]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    team_names = [_n(state, s) for s in team]

    if config["faction"] == "good":
        instruction = "You are a good player. You MUST play SUCCESS — good players have no other option."
        card_hint = "SUCCESS"
    else:
        instruction = (
            "You are an evil player. You choose SUCCESS (maintain cover) or FAIL (sabotage).\n"
            "Consider: current score, team composition, how traceable a fail would be to you specifically,\n"
            "and whether staying trusted is worth more than winning this quest right now."
        )
        card_hint = 'SUCCESS" or "FAIL'

    return (
        f"{priority}\n\n{context}"
        f"{my_name} is on the Q{state.quest_num} mission. Full team: {team_names}\n\n"
        f"{instruction}\n\n"
        f'{{"card": "{card_hint}", "internal_note": "your private strategic reasoning"}}\n'
    )


def get_assassin_prompt(state, assassin_slot: int) -> str:
    # Lean context for this high-stakes single call
    my_name = _n(state, assassin_slot)
    merlin_candidates = [_n(state, s) for s in range(5) if s != assassin_slot]

    mission_summary = "\n".join(
        f"  Q{m.quest_num}: {[_n(state,s) for s in m.team]} → {m.result} ({m.num_fails} fail(s))"
        for m in state.mission_history
    )
    vote_summary = "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state,v.proposer_slot)}→{[_n(state,s) for s in v.proposed_team]} {v.result} "
        f"| A:{[_n(state,s) for s,vote in v.votes.items() if vote=='APPROVE']} "
        f"R:{[_n(state,s) for s,vote in v.votes.items() if vote=='REJECT']}"
        for v in state.vote_history
    )
    all_disc = "\n".join(
        f"  Q{d.quest_num} {_n(state,d.slot_id)}: \"{d.statement}\""
        for d in state.discussion_log
    ) or "None."
    my_notes = "\n".join(state.agent_notes.get(assassin_slot, [])) or "None."

    return (
        f"Good has won 3 quests. {my_name}, you are the Assassin. Name Merlin and evil wins everything.\n\n"
        f"QUEST RESULTS:\n{mission_summary}\n\n"
        f"ALL VOTES:\n{vote_summary}\n\n"
        f"ALL DISCUSSION:\n{all_disc}\n\n"
        f"YOUR NOTES:\n{my_notes}\n\n"
        f"Merlin has been subtly steering good away from you and Morgana all game.\n"
        f"Look for: consistent accurate objections with vague justification; rejecting teams with you/Morgana;\n"
        f"knowledge they couldn't logically have as a Loyal Servant; careful, controlled speech.\n\n"
        f"Candidates: {merlin_candidates}\n\n"
        f'{{"guess_name": "<one name from the candidates list>", "reasoning": "your analysis"}}\n'
    )