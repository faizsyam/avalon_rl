from typing import List
from game.roles import ROLES_CONFIG

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
- If good completes 3 quests, the game does not end — the Assassin gets exactly one guess to name Merlin.
  A correct guess means evil wins the entire game despite losing 3 quests.
  An incorrect guess means good wins.

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
   - Good players MUST play SUCCESS. They have no other option — the game rules enforce this.
   - Evil players choose freely: SUCCESS (preserve cover) or FAIL (sabotage the quest).
   - The quest fails if even ONE FAIL card is played.
   - After the mission, only the COUNT of fail cards is revealed. The identity of who played what
     is never revealed, even after the game ends. There is no way to know which specific player
     played a FAIL card.

QUEST TEAM SIZES (5-player game): Q1=2, Q2=3, Q3=2, Q4=3, Q5=3

The first faction to 3 quest wins, wins — subject to the Assassin's final guess rule described above.

PLAYERS are referred to by name.
"""

ROLE_CONTEXT = {
    "Merlin": """
=== YOUR ROLE: MERLIN (GOOD TEAM) ===
You are on the GOOD team. Good wins by completing 3 quests AND having the Assassin fail to identify you.

WHAT YOU KNOW:
You know which 2 players are Assassin and Morgana. You do not know who Percival is — Percival looks
identical to the Loyal Servant from your perspective. The two evil players know each other but do not
know you are Merlin.

YOUR SITUATION:
You hold information that no other good player has. This knowledge can guide your team toward safe
teams and away from evil players — but every action you take is observed by the Assassin, who is
actively trying to deduce your identity across all 5 quests.

The Assassin's final guess happens after good has already won 3 quests. At that point, nothing about
the quests can be changed. The Assassin will look back at everything you said and did — every
objection, every vote, every nomination — and ask: who behaved as though they knew who evil was?

Merlin's dilemma is not whether to use their knowledge. It's how visibly to use it, and when.
Acting too precisely on your knowledge makes the pattern unmistakable. Acting too passively wastes
your information advantage and costs good quests. Every decision involves this tradeoff.
""",

    "Percival": """
=== YOUR ROLE: PERCIVAL (GOOD TEAM) ===
You are on the GOOD team. Good wins by completing 3 quests AND having the Assassin fail to identify Merlin.

WHAT YOU KNOW:
You see 2 players who both appear as "Merlin." One is the real Merlin (good team, has genuine
knowledge of evil players). The other is Morgana (evil team, who appears identical to Merlin from
your initial information). You cannot tell them apart from this information alone — that distinction
must come from observing their behavior during the game.

YOUR SITUATION:
Real Merlin possesses actual knowledge and uses it — steering the group toward safe teams and away
from evil, often with accurate but vague-seeming justifications. Morgana has no such knowledge but
will imitate the behavior of an informed guide to earn your trust and misdirect you.

Two meaningful risks exist here. First, if you misidentify Merlin, you may trust and protect the
wrong person while the real Merlin is exposed. Second, if you publicly signal who you believe Merlin
is, the Assassin hears it and can use that information at game end. Your read on the two apparent
Merlins is valuable — and sensitive.
""",

    "LoyalServant": """
=== YOUR ROLE: LOYAL SERVANT (GOOD TEAM) ===
You are on the GOOD team. Good wins by completing 3 quests AND having the Assassin fail to identify Merlin.

WHAT YOU KNOW:
Nothing special. You know only your own role. You do not know who Merlin, Percival, the Assassin,
or Morgana is. Every other player is unknown to you at game start.

YOUR SITUATION:
You must reason entirely from what is observable: what people say, how they vote, and mission outcomes.
Mission outcomes are the hardest evidence available — a failed quest proves at least one evil player
was on that team. Vote patterns over multiple quests are meaningful: a player who consistently
pushes for teams that later fail, or rejects teams that succeed, is diverging from good's interests
in a traceable way. Discussion content is a softer signal — deflection, unusual certainty, and
inconsistency between stated reasoning and voting behavior can all carry information.

Somewhere in this game, Merlin exists and holds real knowledge. Their guidance may be subtle — watch
for players whose objections to specific people prove accurate over time without clear logical basis.
""",

    "Assassin": """
=== YOUR ROLE: ASSASSIN (EVIL TEAM) ===
You are on the EVIL team. Evil wins by failing 3 quests, OR by correctly naming Merlin if good completes 3 quests.

WHAT YOU KNOW:
You know Morgana. She knows you. You do not know who Merlin, Percival, or the Loyal Servant is.
The good team does not know you are evil.

YOUR SITUATION:
You have two independent paths to victory, and they operate simultaneously throughout the game.

Quest failure path: Requires getting you or Morgana onto mission teams to play FAIL. Each fail card
brings evil closer to 3 quest fails. However, fail cards create evidence — failed quests narrow
suspicion, and a fail on a small team with limited plausible suspects is highly traceable. The more
suspicion accumulates on you or Morgana, the harder it becomes to get onto future teams.

Merlin identification path: Merlin knows you and Morgana are evil and has been acting on that
knowledge across all 5 quests — steering the group away from you, raising concerns about your
presence on teams, and doing so with accuracy that no pure-information-free player could replicate.
After the game, you must name one player as Merlin. The behavioral signature to look for: accurate
objections to teams containing you or Morgana, offered with justifications that don't fully explain
the certainty; voting against proposals that include you; knowledge that the player couldn't have
derived from public information alone. This pattern, observed across multiple quests, points to Merlin.

You and Morgana must not appear coordinated. If your speech patterns, vote choices, and team
preferences visibly align, good players will identify you as a pair.
""",

    "Morgana": """
=== YOUR ROLE: MORGANA (EVIL TEAM) ===
You are on the EVIL team. Evil wins by failing 3 quests, OR by the Assassin correctly naming Merlin if good completes 3 quests.

WHAT YOU KNOW:
You know the Assassin. They know you. You do not know who Merlin, Percival, or the Loyal Servant is.
The good team does not know you are evil.
You appear as "Merlin" to Percival — Percival sees both you and the real Merlin marked identically
and cannot distinguish you from the initial information alone.

YOUR SITUATION:
Your appearance as "Merlin" to Percival creates a specific information dynamic: Percival is actively
trying to determine which of the two apparent Merlins is real. The real Merlin has genuine knowledge
and may guide Percival toward trusting them. You have no such knowledge, but you do have the ability
to shape how you appear through your behavior, tone, and the guidance you offer.

If Percival becomes convinced you are the real Merlin, the consequences ripple: they may protect
you instead of the real Merlin, their trust in your framing of other players may increase, and they
may inadvertently expose the real Merlin to the Assassin. None of this is guaranteed — it depends
on how well each of you plays across the game.

On quests: playing FAIL advances the quest-fail path but increases suspicion. Playing SUCCESS
preserves cover and continued team access.

You and the Assassin must not appear coordinated. Different framing, different tones, no obvious
lockstep in voting or team preferences — a visible pair is easily identified.
""",
}

COMMUNICATION_DIRECTIVE = """
=== HOW TO COMMUNICATE ===
All discussion and vote statements are PUBLIC — everyone hears everything said out loud.
Your private_note and internal_note fields are your personal thoughts, NOT spoken aloud.
Speak like a real person at a tense game table. Use names. React specifically to what others said.
Show genuine reasoning. Every spoken statement should serve your goal.
"""

NOTE_DIRECTIVE = """
=== YOUR PRIVATE NOTES ===
Write a compact note (2–3 lines) after each action — these persist as your memory across quests.
Name people specifically. Record what they did and what you think it means. Update your reads.
Do NOT restate facts already visible in the game history — capture your interpretation and inferences.
"""


def _dynamic_priority_block(role: str, state) -> str:
    faction = ROLES_CONFIG[role]["faction"]
    g = state.good_wins
    e = state.evil_wins
    q = state.quest_num
    lines = ["=== CURRENT SITUATION ==="]
    if faction == "evil":
        need = 3 - e
        lines.append(f"Score: Good {g} — Evil {e}. Evil needs {need} more quest fail(s) to win outright.")
        if g == 2:
            lines.append(
                "Good is one quest win away from triggering the Assassin's final guess. "
                "If good reaches 3, the only remaining path to evil winning is the Assassin correctly naming Merlin."
            )
        elif e == 2:
            lines.append("One more failed quest wins the game for evil outright — before the Assassin's guess is even needed.")
    else:
        need = 3 - g
        lines.append(f"Score: Good {g} — Evil {e}. Good needs {need} more quest success(es) to win.")
        if e == 2:
            lines.append(
                "Evil is one failed quest away from winning outright. Any evil player on a mission team "
                "can end the game by playing FAIL."
            )
    lines.append(f"Current quest: Q{q}/5.")
    return "\n".join(lines)


def build_system_prompt(role: str, special_info: str, lessons: str, evil_coord: str = "") -> str:
    config = ROLES_CONFIG[role]
    role_ctx = ROLE_CONTEXT.get(role, "")
    lessons_block = "\n=== YOUR STRATEGIC MEMORY ===\n"
    lessons_block += lessons.strip() if lessons.strip() else "No lessons yet — first game."
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
        lines.append(f"  Q{m.quest_num}: {names} → {m.result} ({m.num_fails} fail card(s)){you}")
    return "\n".join(lines)


def _build_vote_history(state) -> str:
    if not state.vote_history:
        return ""
    recent = state.vote_history[-12:]
    lines = ["PROPOSALS & VOTES (all statements are public — everyone heard these):"]
    for v in recent:
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
    return "YOUR NOTES:\n" + "\n".join(notes[-12:])


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
        f"=== Q{state.quest_num}/5 | Good: {state.good_wins} | Evil: {state.evil_wins} ===",
        f"You are {my_name}. Current leader: {leader_name}.", "",
        _build_name_roster(state, my_slot), "",
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
    prior_statements = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    if prior_statements:
        turn_instruction = (
            f"It is {my_name}'s turn to speak in the Q{state.quest_num} discussion.\n"
            f"React to what others have said. Address players by name. This is public — everyone will hear you.\n"
        )
    else:
        turn_instruction = (
            f"It is {my_name}'s turn to speak first in the Q{state.quest_num} discussion.\n"
            f"No one has spoken yet. Set the frame for this quest. This is public — everyone will hear you.\n"
        )
    return (
        f"{priority}\n\n{context}"
        f"{turn_instruction}"
        f"Write a compact private note with specific names and updated reads.\n\n"
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
        f'{{"statement": "your brief public reaction", "private_note": "what this vote told you privately"}}\n'
    )


def get_proposal_prompt(state, slot_id: int, team_size: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    all_names = list(state.slot_to_name.values())
    return (
        f"{priority}\n\n{context}"
        f"{my_name}, you are the current leader. Choose exactly {team_size} player(s) for Q{state.quest_num}.\n"
        f"Available players: {all_names}\n\n"
        f"Your speech must name the exact same players as your proposed_team — no discrepancy.\n"
        f"Write a compact private note explaining your reasoning for this team.\n\n"
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
    return (
        f"{priority}\n\n{context}"
        f"{proposer_name} proposes for Q{state.quest_num}: {team_names}\n\n"
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
        instruction = (
            "You are an evil player. You choose SUCCESS (preserve cover, no quest damage) "
            "or FAIL (sabotage the quest, advance the quest-fail path).\n"
            "Only the count of fail cards is revealed after the mission — never who played what.\n"
            "Consider what each outcome means for your position, your cover, and evil's win paths."
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
    candidates = [_n(state, s) for s in range(5) if s != assassin_slot]
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
        f"Good has completed 3 quests. {my_name}, you are the Assassin.\n"
        f"Name Merlin — if you are correct, evil wins the entire game.\n\n"
        f"WHAT YOU KNOW: You know Morgana. Merlin knows you and Morgana are evil and has been acting on "
        f"that knowledge throughout the game — steering good toward safe teams and away from you, with "
        f"justifications that don't fully explain how they knew.\n\n"
        f"BEHAVIORAL SIGNATURE TO ANALYZE:\n"
        f"- Accurate objections to teams containing you or Morgana, offered without a logical basis for certainty\n"
        f"- Voting REJECT on proposals that include you or Morgana at higher rates than chance\n"
        f"- Pushing to include or exclude specific players with apparent knowledge of their alignment\n"
        f"- Controlled, careful speech that avoids accidentally revealing too much\n"
        f"- A pattern that is consistent across multiple quests, not just one incident\n\n"
        f"QUEST RESULTS:\n{mission_summary}\n\n"
        f"ALL VOTES:\n{vote_summary}\n\n"
        f"ALL DISCUSSION:\n{all_disc}\n\n"
        f"YOUR NOTES:\n{my_notes}\n\n"
        f"Candidates (anyone except yourself): {candidates}\n\n"
        f'{{"guess_name": "<one name from candidates>", "reasoning": "your full analysis"}}\n'
    )


def get_public_lesson_prompt(state, slot_id: int, role: str) -> str:
    faction = ROLES_CONFIG[role]["faction"]
    faction_won = (state.outcome == "GOOD_WINS") == (faction == "good")
    my_name = _n(state, slot_id)
    won_str = "WON" if faction_won else "LOST"
    return (
        f"You are {my_name} ({role}, {'GOOD' if faction == 'good' else 'EVIL'} team). "
        f"Game ended: {state.outcome}. Your faction {won_str}.\n\n"
        f"Write 1–2 sentences — the single strongest lesson from this game explaining WHY your faction won or lost.\n"
        f"Be direct and specific. Reference roles explicitly (Merlin, Assassin, etc.) when relevant.\n"
        f"This will be read by ALL players to help everyone improve.\n\n"
        f"Example: 'Merlin was identified because their objections to the same two players were too consistent — "
        f"Merlin must vary their opposition timing and framing across quests.'\n\n"
        f'{{"public_lesson": "your 1–2 sentence lesson"}}\n'
    )


def get_cross_lesson_prompt(state, slot_id: int, role: str, public_lessons: dict) -> str:
    config = ROLES_CONFIG[role]
    dims = config["dimensions"]
    lessons_str = "\n".join(
        f"  {r} ({ROLES_CONFIG[r]['faction']} team): \"{l}\""
        for r, l in public_lessons.items()
    )
    return (
        f"You are {_n(state, slot_id)} ({role}). Here are the key lessons every player identified from this game:\n\n"
        f"{lessons_str}\n\n"
        f"Read each lesson carefully. If any are directly relevant to improving YOUR play as {role}, "
        f"extract them as new tentative lessons. Only include what genuinely applies to your specific role.\n"
        f"Ignore lessons that are irrelevant to your role.\n\n"
        f"Available dimensions: {dims}\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{"add_tentative": [{{"dimension": "<dim>", "lesson": "<rule-form lesson, no player names>"}}]}}\n'
    )