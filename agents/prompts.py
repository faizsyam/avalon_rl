from typing import List
from game.roles import ROLES_CONFIG
from config import QUEST_TEAM_SIZES

GAME_RULES = """
GAME: The Resistance: Avalon — 5 players
FACTIONS: Good (Merlin, Percival, Loyal Servant) vs. Evil (Assassin, Morgana).

KNOWLEDGE STRUCTURE (established at game start, before any discussion):
- Merlin knows which 2 players are Assassin and Morgana. Merlin does not know who Percival is.
- Percival sees 2 players marked as "Merlin": one is the real Merlin (good), one is Morgana (evil pretending).
  Percival cannot tell them apart from this initial information alone.
- Assassin and Morgana know each other. Neither knows who Merlin or Percival is.
- Loyal Servant has no special knowledge — they know only their own role.
- No good player knows the specific role of any other good player.

WINNING:
- Good wins by completing 3 quests successfully AND surviving the Assassin's final guess.
- Evil wins by failing 3 quests, OR by the Assassin correctly naming Merlin if good completes 3 quests.
- Both win conditions matter simultaneously: good must protect quests AND protect Merlin's identity.
- If good completes 3 quests, the game is NOT over. The Assassin gets exactly one guess:
    → Assassin names Merlin CORRECTLY  = EVIL WINS (overrides all quest results)
    → Assassin names Merlin INCORRECTLY = GOOD WINS (quest results stand)
  The Assassin's guess is not a guaranteed evil win. It succeeds only if Merlin's identity was
  exposed during the game. An incorrect guess is a complete loss for evil.

EACH QUEST PROCEEDS IN 4 PHASES:

1. DISCUSSION
   Every player speaks publicly. All statements are heard by all players.
   This is the primary window for persuasion, accusation, and trust-building.

2. PROPOSAL
   The current leader nominates a team of exactly the required size for that quest.
   The leader role rotates to the next player (left) each time a proposal is rejected.
   If 5 consecutive proposals are rejected for the same quest, evil wins the entire game immediately.
   Leadership is therefore a limited, expiring resource on each quest.

3. VOTE
   All players simultaneously vote APPROVE or REJECT and publicly state their reason.
   All votes and stated reasons are heard by everyone — nothing is hidden here.
   3 or more APPROVE votes sends the team on the mission.
   Fewer than 3 APPROVE votes rejects the proposal; leadership passes left.

4. MISSION
   Each team member secretly and independently plays one card.
   - Good players MUST play SUCCESS. Good players can never play FAIL.
   - Evil players choose freely: SUCCESS (preserve cover) or FAIL (sabotage the quest).
   - The quest fails if ONE OR MORE FAIL cards are played.
   - After the mission, only the COUNT of fail cards is revealed. Who played what remains secret.
   - LOGICAL CONSEQUENCES:
     * 1 revealed FAIL card proves at least 1 evil player was on that mission team.
     * 2 revealed FAIL cards prove at least 2 evil players were on that mission team.
     * A successful quest does NOT prove the team is entirely good (evil players often play SUCCESS to build trust or avoid exposure).

QUEST TEAM SIZES (5-player game): Q1=2, Q2=3, Q3=2, Q4=3, Q5=3

The first faction to 3 quest wins, wins — subject to the Assassin's final guess rule described above.

PLAYERS are referred to by name.
"""

ROLE_CONTEXT = {
    "Merlin": """
=== YOUR ROLE: MERLIN (GOOD) ===
Goal: Complete 3 quests successfully AND survive the Assassin's final guess. You know the identities of the two
evil players (Assassin and Morgana), but you must never reveal this knowledge directly or indirectly in public
discussion or voting patterns.

You hold knowledge no other good player has. Every action you take is observed by the Assassin,
who will retrospectively analyze your behavior to find the pattern that reveals you.

Merlin's dilemma: acting too precisely on your knowledge makes the pattern unmistakable; acting
too passively wastes your information advantage and costs good quests.

Act on your knowledge — vote and steer as your knowledge demands. What you disguise is not your decisions,
but how you justify them publicly. Your public reasoning must never exceed what observable evidence can explain;
your decisions can.

Feel free to subtly guide, misdirect, manipulate suspicion, bluff uncertainty, and strategically accuse or deflect.
""",

    "Percival": """
=== YOUR ROLE: PERCIVAL (GOOD) ===
Goal: Complete 3 quests successfully AND protect Merlin's identity.

You see two players marked as Merlin — one is real, one is Morgana. You cannot tell them apart
from the initial information alone; you must infer it from behavior across the game.

Real Merlin has genuine knowledge and steers accurately. Morgana has none and will imitate that.
Your read on the two candidates is valuable and sensitive — if you signal it publicly, the
Assassin hears it.

Feel free to probe, defend potential allies, test reactions, and help protect Merlin — but guard
your own read carefully.
""",

    "LoyalServant": """
=== YOUR ROLE: LOYAL SERVANT (GOOD) ===
Goal: Complete 3 quests successfully AND help protect Merlin's identity.

You have no special knowledge. Reason entirely from what is observable: mission outcomes, vote
patterns, and behavioral consistency. A failed quest proves at least one evil player was on that
team. Watch for players whose objections prove accurate without a logical basis — that pattern
points toward Merlin, whom you should protect without naming.

Feel free to question, pressure, defend, challenge contradictions, and coordinate to identify evil.
""",

    "Assassin": """
=== YOUR ROLE: ASSASSIN (EVIL) ===
Goal: Fail 3 quests. OR: if good completes 3 quests, correctly identify and assassinate Merlin.

Two independent paths to victory operate simultaneously. Quest failure path: get yourself or
Morgana on mission teams to play FAIL. Crucially, you do not both need to be on the same team —
if Morgana is on a mission alone, she can play FAIL without you present. Coordinating who gets
on which team matters as much as the card played. Each fail card narrows suspicion.
Merlin identification path: Merlin has been acting on hidden knowledge all game. The behavioral signature
is accurate objections to teams containing you or Morgana, offered with certainty that observable
evidence cannot explain. Catalogue this across all quests.

You and Morgana must not appear coordinated — different framing, different tones, no lockstep voting.

Feel free to deceive, manipulate, frame others, build false trust, and pressure players to protect
the bad team and identify Merlin.
""",

    "Morgana": """
=== YOUR ROLE: MORGANA (EVIL) ===
Goal: Fail 3 quests.

You appear as Merlin to Percival. If Percival becomes convinced you are real Merlin, the
consequences ripple: they may protect you instead, trust your framing, and inadvertently expose
the real Merlin to the Assassin.

On quests, FAIL advances the sabotage path but raises suspicion; SUCCESS preserves your access to
future teams. You and the Assassin do not both need to be on the same mission — if you are on a
team alone, you can play FAIL without the Assassin present. You and the Assassin must not appear coordinated.

Feel free to imitate trustworthiness, manipulate perceptions, mislead Percival, frame innocents,
and build false trust to protect the bad team.
""",
}

COMMUNICATION_DIRECTIVE = """
=== HOW TO COMMUNICATE ===
All discussion and vote statements are PUBLIC — everyone hears everything said out loud.
Your private_note and internal_note fields are your personal thoughts, NOT spoken aloud.

NEVER reveal in any public field: your role, your faction, your hidden knowledge, or certainty
about another player's alignment that has no observable basis.
All role-aware reasoning belongs exclusively in private_note or internal_note.

Speak like a real person at a tense game table. Call others by their names. React specifically
to what others said. Base public statements only on observable evidence: mission outcomes, vote
patterns, and stated behavior. Be expressive and show emotion when needed.
Every spoken statement should serve your goal.
"""

NOTE_DIRECTIVE = """
=== YOUR PRIVATE NOTES ===
Write a compact note (2–3 lines) after each action — these persist as your memory across quests.
Name people specifically. Record what they did and what you think it means. Update your reads.
Do NOT restate facts already visible in the game history — capture your interpretation and inferences.
Write after each discussion statement, vote, and mission card — one note per action phase.
"""

ROLE_DEDUCTION = {
    "LoyalServant": """
=== DEDUCTION ===
- Fail count on a quest = minimum evil players present on that team.
- 1 fail / 2-person team: at least 1 of those 2 is evil.
- 1 fail / 3-person team: at least 1 of those 3 is evil.
- 2 fails / 3-person team: at least 2 of those 3 are evil.
- A successful quest proves nothing about alignment — evil players can play SUCCESS.
""",
    "Percival": """
=== DEDUCTION ===
- Fail count on a quest = minimum evil players present on that team.
- 1 fail / 2-person team: at least 1 of those 2 is evil.
- 1 fail / 3-person team: at least 1 of those 3 is evil.
- 2 fails / 3-person team: at least 2 of those 3 are evil.
- A successful quest proves nothing about alignment — evil players can play SUCCESS.
- Of your two Merlin candidates: the one whose team steering consistently aligns with actual quest outcomes
 is more likely real Merlin; the one whose guidance correlates with failed quests or serves evil teams is more likely Morgana.
""",
    "Merlin": """
""",
    "Morgana": """
""",
    "Assassin": """
""",
}


def _dynamic_priority_block(role: str, state) -> str:
    faction = ROLES_CONFIG[role]["faction"]
    g = state.good_wins
    e = state.evil_wins
    q = state.quest_num
    lines = ["=== CURRENT SITUATION ==="]

    if g == 2 and e == 2:
        lines.append(
            f"Score: Good {g} — Evil {e}. DECISIVE QUEST — both sides are one step from victory. "
            "A single fail card ends the game for evil; a clean success forces the Assassin's guess."
        )
    elif faction == "evil":
        need = 3 - e
        lines.append(f"Score: Good {g} — Evil {e}. Evil needs {need} more quest fail(s) to win outright.")
        if g == 2:
            lines.append(
                "Good is ONE quest win away. Any quest success ends the quest phase and forces the "
                "Assassin's guess — which is NOT a guaranteed evil win. "
                "Suggest to vote reject any proposed team that contains neither Assassin nor Morgana — a clean team "
                "guarantees a good quest win. Find a credible public reason to REJECT. "
                "Intensify behavioral observation: who is steering teams with accuracy they cannot justify?"
            )
        elif e == 2:
            lines.append(
                "Evil is ONE failed quest from winning outright. Cover is expendable if you are on "
                "a mission team — a single FAIL ends the game immediately."
            )
    else:
        need = 3 - g
        lines.append(f"Score: Good {g} — Evil {e}. Good needs {need} more quest success(es) to win.")
        if g == 2:
            lines.append(
                "Good is ONE quest success from winning the quest phase. "
                "A clean team on this quest ends the quest phase and forces the Assassin's final guess. "
                "Approve any proposed team you are confident contains no evil players."
            )
        if e == 2:
            lines.append(
                "Evil is ONE failed quest from winning outright. A single FAIL card ends the game "
                "immediately — there is no recovery. The team must be guaranteed clean: only players "
                "whose alignment has been confirmed good by your judgement. "
                "Suggest to vote REJECT any proposal containing unproven players regardless of stated reasoning. "
                "Experimentation and 'gathering data' are losing strategies at this score."
            )

    lines.append(f"Current quest: Q{q}/5.")
    return "\n".join(lines)


def build_system_prompt(role: str, special_info: str, lessons: str, evil_coord: str = "", good_coord: str = "") -> str:
    config = ROLES_CONFIG[role]
    role_ctx = ROLE_CONTEXT.get(role, "")
    lessons_block = "\n=== YOUR STRATEGIC MEMORY ===\n"
    lessons_block += lessons.strip() if lessons.strip() else "No lessons yet — first game."
    coord_block = ""
    if evil_coord and config["faction"] == "evil":
        coord_block = f"\n=== EVIL TEAM COORDINATION MEMORY ===\n{evil_coord.strip()}\n"
    elif good_coord and config["faction"] == "good":
        coord_block = f"\n=== GOOD TEAM COORDINATION MEMORY ===\n{good_coord.strip()}\n"
    return (
        f"{GAME_RULES}\n"
        f"YOUR PRIVATE INFORMATION:\n{special_info}\n"
        f"{role_ctx}"
        f"{ROLE_DEDUCTION.get(role, '')}\n"
        f"{lessons_block}\n"
        f"{coord_block}"
        f"{COMMUNICATION_DIRECTIVE}\n"
        f"{NOTE_DIRECTIVE}\n"
    )


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
            f"  Evil players: {evil_names}\n"
            f"  Confirmed safe players: {safe_names}\n"
            f"  A team containing any evil player can be sabotaged at their discretion."
        )
    elif role == "Percival":
        candidates = sorted([state.slot_to_name[state.role_to_slot[r]] for r in ["Merlin", "Morgana"]])
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  {candidates[0]} and {candidates[1]} both appear as Merlin — one is real Merlin (good), one is Morgana (evil).\n"
        )
    elif role == "Assassin":
        ally = state.slot_to_name[state.role_to_slot["Morgana"]]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  {ally} is Morgana, your evil ally. All other non-you players are good.\n"
            f"  Either of you alone on a mission can play FAIL independently."
        )
    elif role == "Morgana":
        ally = state.slot_to_name[state.role_to_slot["Assassin"]]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  {ally} is the Assassin, your evil ally. All other non-you players are good.\n"
            f"  Either of you alone on a mission can play FAIL independently."
        )
    return ""

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
                lines.append(f"    {name} [{vote}]: \"{speech}\"")
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
        f"You are {my_name}. Current leader: {leader_name}.", "",
        _build_name_roster(state, my_slot), "",
    ]
    reminder = _build_role_knowledge_reminder(state, my_slot)
    if reminder:
        parts += [reminder, ""]
    mh = _build_quest_roadmap(state, my_slot)
    if mh:
        parts += [mh, ""]
    lr = _build_leader_rotation(state)
    if lr:
        parts += [lr, ""]
    pqs = _build_player_quest_summary(state)
    if pqs:
        parts += [pqs, ""]
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

def _build_quest_roadmap(state, my_slot: int) -> str:
    from config import QUEST_TEAM_SIZES
    completed = {m.quest_num: m for m in state.mission_history}
    lines = ["QUEST ROADMAP:"]
    for q in range(1, 6):
        size = QUEST_TEAM_SIZES[q - 1]
        if q in completed:
            m = completed[q]
            you = " [YOU]" if my_slot in m.team else ""
            lines.append(f"  Q{q} ({size} players): {[_n(state, s) for s in m.team]} → {m.result} ({m.num_fails} fail(s)){you}")
        elif q == state.quest_num:
            proposal_count = len([v for v in state.vote_history if v.quest_num == q])
            lines.append(f"  Q{q} ({size} players): ← CURRENT (proposal {proposal_count + 1}/5)")
        else:
            lines.append(f"  Q{q} ({size} players): upcoming")
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

def get_discussion_prompt(state, slot_id: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    prior_statements = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    proposal_count = len([v for v in state.vote_history if v.quest_num == state.quest_num])
    goal = (
        "Goal: build a case for which players should or should not be on this quest's team. "
        "Base public arguments only on observable evidence."
    )
    if prior_statements:
        turn_instruction = (
            f"It is {my_name}'s turn to speak in the Q{state.quest_num} discussion.\n"
            f"React to what others have said. Address players by name. {goal}\n"
            f"Proposal attempt {proposal_count + 1}/5 for Q{state.quest_num}.\n"
        )
    else:
        turn_instruction = (
            f"It is {my_name}'s turn to speak first in the Q{state.quest_num} discussion.\n"
            f"No one has spoken yet. Set the frame for this quest. {goal}\n"
            f"Proposal attempt {proposal_count + 1}/5 for Q{state.quest_num}.\n"
        )
    return (
        f"{priority}\n\n{context}"
        f"{turn_instruction}"
        f'`statement` is spoken aloud, other players can read, do not expose your role. If it reads like a private note, it belongs in private_note.\n'
        f'{{"statement": "your public spoken words", "private_note": "your private interpretation"}}\n'
    )


def get_rejection_discussion_prompt(state, slot_id: int, rejected_team: list, vote_record) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    team_names = [_n(state, s) for s in rejected_team]
    approvers = [_n(state, s) for s, v in vote_record.votes.items() if v == "APPROVE"]
    rejecters = [_n(state, s) for s, v in vote_record.votes.items() if v == "REJECT"]
    return (
        f"{priority}\n\n{context}"
        f"The proposal {team_names} was just REJECTED.\n"
        f"Approvers: {approvers}. Rejecters: {rejecters}.\n\n"
        f"{my_name}, react to this outcome in 1–2 sentences. Address players by name if relevant.\n"
        f"What does this vote pattern tell you? What do you want the group to hear?\n"
        f"This statement is PUBLIC — everyone will hear it.\n\n"
        f'`statement` is spoken aloud, other players can read, do not expose your role. If it reads like a private note, it belongs in private_note.\n'
        f'{{"statement": "your brief public reaction", "private_note": "what this vote told you privately"}}\n'
    )


def get_proposal_prompt(state, slot_id: int, team_size: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    all_names = list(state.slot_to_name.values())
    current_proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1
    proposal_urgency = (
        f"\n⚠ Proposal attempt {current_proposal_num}/5. A 5th rejection is an immediate evil win.\n"
        if current_proposal_num >= 4 else f"Proposal attempt {current_proposal_num}/5.\n"
    )
    config = ROLES_CONFIG[role]
    self_inclusion_hint = (
        f"Convention: leaders almost always include themselves — on a failed quest you already know your own card, "
        f"which immediately narrows the culprit pool; on a successful one, self-inclusion costs nothing. "
        f"Not doing so is itself a readable signal to the table.\n\n"
        if config["faction"] == "good" else
        f"Convention: leaders almost always include themselves — deviating without a visible reason draws suspicion. "
        f"Self-inclusion also keeps you on the mission where you directly control the outcome. "
        f"Not doing so is a readable signal others will notice.\n"
        f"Be careful proposing your evil partner on the same team as yourself — two fail cards on a 2-person quest "
        f"exposes you both instantly; on a 3-person quest it pins 2 of 3 as evil, nearly as damning.\n\n"
    )
    return (
        f"{priority}\n\n{context}"
        f"{my_name}, you are the current leader. Choose exactly {team_size} player(s) for Q{state.quest_num}.\n"
        f"Available players: {all_names}\n\n"
        f"{proposal_urgency}\n"
        f"{self_inclusion_hint}"
        f"Your speech must name the exact same players as your proposed_team — no discrepancy.\n"
        f'`speech` is spoken aloud, other players can read, so must having zero role names.\n'
        f'{{"proposed_team": [exactly {team_size} player name(s) as strings], '
        f'"speech": "your public announcement — must name the same players as proposed_team", '
        f'"private_note": "your reasoning"}}\n'
    )


def get_vote_prompt(state, slot_id: int, proposer_slot: int, proposed_team: List[int]) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    proposer_name = _n(state, proposer_slot)
    team_names = [_n(state, s) for s in proposed_team]
    current_proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1
    urgency = ""
    if current_proposal_num >= 4:
        urgency = f"\n⚠ This is proposal {current_proposal_num}/5 — one more rejection ends the game for evil.\n"
    elif current_proposal_num >= 2:
        urgency = f"\nThis is proposal {current_proposal_num}/5 for Q{state.quest_num}.\n"
    else:
        urgency = ""
    return (
        f"{priority}\n\n{context}"
        f"{proposer_name} proposes for Q{state.quest_num}: {team_names}\n\n"
        f"{urgency}"
        f"{my_name}, vote APPROVE or REJECT. Your vote AND your stated reason are both PUBLIC.\n"
        f"Everyone will hear what you say. Draw on the full history and your notes when reasoning.\n"
        f"Write a private note with your actual reasoning (not spoken aloud).\n\n"
        f'{{"vote": "APPROVE or REJECT", '
        f'"speech": "your public stated reason for this vote", '
        f'"private_note": "your private reasoning"}}\n'
    )


def get_mission_prompt(state, slot_id: int, role: str, team: List[int]) -> str:
    config = ROLES_CONFIG[role]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    team_names = [_n(state, s) for s in team]
    
    if config["faction"] == "good":
        instruction = (
            "You are a good player. You MUST play SUCCESS — the rules give good players no other option.\n"
            "Your card choice is not a decision."
        )
        card_hint = "SUCCESS"
    else:
        good_after = state.good_wins + 1
        evil_after = state.evil_wins + 1
        instruction = (
            f"You are an evil player. You choose SUCCESS (preserve cover) or FAIL (sabotage quest).\n"
            f"Only the total count of fail cards is revealed. Your identity is protected.\n"
            f"CURRENT SCORE: Good {state.good_wins} — Evil {state.evil_wins}.\n"
            f"  Playing SUCCESS → Good reaches {good_after}. "
            + ("GOOD WINS 3 QUESTS — game enters Assassin phase:\n"
               "      Assassin names Merlin CORRECTLY  → EVIL WINS\n"
               "      Assassin names Merlin INCORRECTLY → GOOD WINS (complete loss for evil)\n"
               "    This is NOT a safe outcome — only choose SUCCESS if the Assassin is confident.\n"
               if good_after >= 3 else f"Good needs {3 - good_after} more win(s).\n")
            + f"  Playing FAIL   → Evil reaches {evil_after}. "
            + ("EVIL WINS OUTRIGHT — game ends immediately.\n"
               if evil_after >= 3 else f"Evil needs {3 - evil_after} more fail(s).\n")
            + "Make the optimal strategic choice for your faction given these exact consequences."
        )
        card_hint = 'SUCCESS" or "FAIL'
        
    return (
        f"{priority}\n\n{context}"
        f"{my_name} is on the Q{state.quest_num} mission. Full team: {team_names}\n\n"
        f"{instruction}\n\n"
        f'{{"card": "{card_hint}", "internal_note": "your private strategic reasoning (not spoken aloud)"}}\n'
    )


def get_assassin_prompt(state, assassin_slot: int) -> str:
    my_name = _n(state, assassin_slot)
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
    return (
        f"FINAL SCORE: Good {state.good_wins} — Evil {state.evil_wins}. Good has completed 3 quests.\n"
        f"If you name Merlin correctly → EVIL WINS. If wrong → GOOD WINS. This is your only chance.\n\n"
        f"WHAT YOU KNOW: You know Morgana. Merlin knows you and Morgana are evil and has been acting on "
        f"that knowledge throughout the game — steering good toward safe teams and away from you, with "
        f"justifications that don't fully explain how they knew.\n\n"
        f"QUEST RESULTS:\n{mission_summary}\n\n"
        f"ALL VOTES:\n{vote_summary}\n\n"
        f"ALL DISCUSSION:\n{all_disc}\n\n"
        f"YOUR NOTES:\n{my_notes}\n\n"
        f"Candidates (anyone except yourself): {candidates}\n\n"
        f'{{"guess_name": "<one name from candidates>", "reasoning": "your full analysis"}}\n'
    )