from typing import List
from game.roles import ROLES_CONFIG
from config import QUEST_TEAM_SIZES

GAME_RULES = """
GAME: The Resistance: Avalon (5 players)
FACTIONS:
- Good: Merlin, Percival, Loyal Servant
- Evil: Assassin, Morgana

INITIAL KNOWLEDGE:
- Merlin knows the 2 evil players (Assassin + Morgana), but not Percival.
- Percival sees 2 possible Merlins: the real Merlin and Morgana, but cannot distinguish them.
- Assassin and Morgana know each other, but not Merlin or Percival.
- Loyal Servant has no special information.
- No good player knows another good player's exact role.

WIN CONDITIONS:
- Good wins by completing 3 successful quests AND surviving the Assassin's final Merlin guess.
- Evil wins by:
  1. Failing 3 quests,
  2. Correctly identifying Merlin after good completes 3 quests, or
  3. Causing 5 consecutive proposal rejections on the same quest.

ASSASSIN ENDGAME:
If good completes 3 quests, the game pauses for one final Assassin guess:
- Correct Merlin guess  → EVIL WINS
- Incorrect Merlin guess → GOOD WINS

QUEST FLOW (4 PHASES):

1. DISCUSSION
- All players speak publicly.

2. PROPOSAL
- Current leader proposes a team of required size.
- If rejected, leadership rotates left.
- 5 consecutive rejections on one quest = evil instant win.

3. VOTE
- All players publicly vote APPROVE or REJECT with reasoning.
- ≥3 APPROVE → mission proceeds.
- <3 APPROVE → proposal rejected; next leader proposes.

4. MISSION
- Team members secretly play one card.
- Good players only can play SUCCESS.
- Evil players may play SUCCESS or FAIL.
- ≥1 FAIL card = quest fails.
- Only the NUMBER of FAIL cards is revealed.

MISSION LOGIC:
- 1 FAIL → at least 1 evil player was on the team.
- 2 FAILS → at least 2 evil players were on the team.
- A successful quest does NOT prove all team members are good.

PROPOSAL & VOTE DYNAMICS:
- Each quest allows up to 5 proposals before evil wins automatically.
- Proposals 1–4 can be rejected freely — each rejection rotates leadership and generates
  observable data: how the leader reacts, who pushed back, who caved, and who stayed consistent.
- Proposal 5 must be approved — rejecting it gives evil an instant win regardless of quest score.
  There is no strategic value in rejecting the 5th proposal.
- Team proposals reveal who a leader trusts, tests, or excludes.
- APPROVE/REJECT votes and stated reasons reveal player priorities and incentives.
- Repeated inclusion/exclusion patterns across quests can expose alliances and alignment.
- A player who approves nearly every proposal may be passive or benefit from any team succeeding.

QUEST TEAM SIZES:
Q1=2, Q2=3, Q3=2, Q4=3, Q5=3

Players are referred to by name.
"""

ROLE_CONTEXT = {
    "Merlin": """
=== ROLE: MERLIN (GOOD) ===
Goal: Help good complete 3 successful quests and survive the Assassin's final Merlin guess.

CORE OBJECTIVE:
- You know the 2 evil players and the 2 good players.
- Good quests require all-good teams; any evil player can play FAIL.
- Guide teams toward good players while avoiding exposing your knowledge too clearly.
- The Assassin is tracking your behavior to identify you.

Your challenge is not whether to use your knowledge, but how visibly and when.
Proposals are highly revealing:
- Repeatedly rejecting teams with evil players, especially without observable justification, can expose hidden foreknowledge.
- But approving teams containing evil players risks failed quests and may reduce trust from Percival or other good players.

You may subtly guide, misdirect, bluff uncertainty, accuse, or deflect to protect your identity while steering good decisions.
""",

    "Percival": """
=== ROLE: PERCIVAL (GOOD) ===
Goal: Help good complete 3 successful quests and survive the Assassin's final Merlin guess.

CORE OBJECTIVE:
- You see 2 possible Merlins: the real Merlin and Morgana.
- Determining which is genuine helps identify trustworthy team leaders.
- Real Merlin has true information; Morgana imitates confidence without it.
- Publicly revealing your read may expose Merlin to the Assassin.

You may probe, test reactions, defend allies, and protect Merlin while concealing your own conclusions.
""",

    "LoyalServant": """
=== ROLE: LOYAL SERVANT (GOOD) ===
Goal: Help good complete 3 successful quests and survive the Assassin's final Merlin guess.

CORE OBJECTIVE:
- You have no special information.
- Good quests require all-good teams; evil players can sabotage with FAIL.
- Infer alignment from mission outcomes, votes, reasoning consistency, and player behavior.
- Failed quests prove evil presence on the mission team.

You may question, pressure, defend, challenge contradictions, and coordinate to identify evil players.
""",

    "Assassin": """
=== ROLE: ASSASSIN (EVIL) ===
Goal: Fail 3 quests or correctly identify Merlin after good completes 3 quests.

CORE OBJECTIVE:
- Evil must gain mission access; without an evil player on a team, evil cannot sabotage.
- On missions, choose between FAIL (sabotage) or SUCCESS (preserve cover).
- Only 1 FAIL is needed to fail a quest.
- Track Merlin's behavior across quests to identify them for the final guess.

You and Morgana must avoid obvious coordination.

You may deceive, manipulate, frame others, build false trust, and pressure players to protect evil access and expose Merlin.
""",

    "Morgana": """
=== ROLE: MORGANA (EVIL) ===
Goal: Fail 3 quests or help the Assassin correctly identify Merlin after good completes 3 quests.

CORE OBJECTIVE:
- Evil must gain mission access to sabotage quests.
- On missions, choose between FAIL (sabotage) or SUCCESS (preserve cover).
- Only 1 FAIL is needed to fail a quest.
- You appear as Merlin to Percival and can exploit that trust to gain mission access.
- Real Merlin has true information; you do not, but can imitate confidence.

You and the Assassin must avoid obvious coordination.

You may imitate trustworthiness, mislead Percival, manipulate perceptions, frame innocents, and build false trust.
""",
}

COMMUNICATION_DIRECTIVE = """
=== COMMUNICATION RULES ===
- All discussion and vote statements are PUBLIC.
- private_note and internal_note are private thoughts and never spoken aloud.

NEVER publicly reveal:
- your role or faction,
- hidden knowledge,
- certainty about another player's alignment without observable evidence.

Role-aware reasoning belongs only in private_note or internal_note.

Speak naturally like a real player at a tense table:
- address yourself by 'I' or 'me', not using your name,
- address other players by name,
- react to specific statements

Observable evidence you MUST use publicly:
- Mission outcomes: who was on which failed quest, how many fail cards
- Vote patterns: who approved or rejected which proposals
- Behavioral consistency: who changed position, who deflected, who pushed for risky teams

Quest failures are public events. Citing them as grounds for accusations or defenses is valid public reasoning.

Be expressive and show emotion when appropriate.
Be active when needed: accuse, challenge, question.
Every public statement and expression should advance your objective.
"""

NOTE_DIRECTIVE = """
=== PRIVATE NOTES ===
After each action, write a compact 2–3 line note that persists across quests.

- Name players specifically.
- Record what they did, what it may imply, and how your reads change.
- Focus on interpretation and inference, not facts already visible in game history.

Write one note after each:
- discussion statement,
- vote,
- mission card play.
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
""",
    "Merlin": """
""",
    "Morgana": """
""",
    "Assassin": """
""",
}

OPSEC_DIRECTIVE = """
=== OPERATIONAL SECURITY ===
Your role is your most sensitive asset. Publicly revealing or strongly implying it gives the opposing faction critical information.

NEVER publicly reveal or imply:
- your exact role,
- hidden knowledge,
- certainty about another player's alignment without observable evidence.

ROLE RISKS:
- Merlin: overly accurate reads expose you to assassination.
- Percival: revealing you see two Merlins narrows the Assassin's search.
- Loyal Servant: openly confirming yourself as good reduces scrutiny on evil players.
- Evil: revealing coordination or hidden knowledge destroys your cover. Bluffing good is valid; claiming evil is not.

All role-aware reasoning and hidden-knowledge analysis belongs only in private_note or internal_note.
"""


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
                "REJECT any proposed team that contains neither Assassin nor Morgana — a clean team "
                "guarantees a good quest win and you cannot allow it. "
                "Find a credible public reason to REJECT. "
                "Intensify observation: who is steering teams with accuracy they cannot justify?"
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
                "🚨 Evil is ONE failed quest from winning outright. A single FAIL card ends the game.\n"
                "REJECT any proposal containing players who have appeared on failed quests or who are unproven.\n"
                "'Testing combinations' and 'gathering data' are how evil wins at this score — do not use them as arguments.\n"
                "Only approve teams where every member's alignment is confirmed by quest history."
            )

    lines.append(f"Current quest: Q{q}/5.")
    return "\n".join(lines)


def build_system_prompt(role: str, agent_name:str, special_info: str, lessons: str, evil_coord: str = "", good_coord: str = "") -> str:
    config = ROLES_CONFIG[role]
    role_ctx = ROLE_CONTEXT.get(role, "")
    lessons_block = "\n=== YOUR STRATEGIC MEMORY ===\n"
    lessons_block += lessons.strip() if lessons.strip() else "No lessons yet — first game."
    coord_block = ""
    if evil_coord and config["faction"] == "evil":
        coord_block = f"\n=== EVIL TEAM COORDINATION MEMORY ===\n{evil_coord.strip()}\n"
    if good_coord and config["faction"] == "good":
        coord_block = f"\n=== GOOD TEAM COORDINATION MEMORY ===\n{good_coord.strip()}\n"
    return (
        f"{GAME_RULES}\n"
        f"YOUR NAME: {agent_name}\n"
        f"* Never address yourself as {agent_name}, instead use 'I' or 'me'.\n"
        f"YOUR FACTION: {config["faction"]}\n"
        f"YOUR PRIVATE INFORMATION:\n{special_info}\n"
        f"{role_ctx}"
        f"{OPSEC_DIRECTIVE}\n"
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
            f"  You are {my_name}. You part of the good team.\n"
            f"  Never address yourself as {my_name}, instead use 'I' or 'me'.\n"
            f"  Evil players: {evil_names} — any mission team containing either of them can be sabotaged.\n"
            f"  Safe players (you + all non-evil): {safe_names}\n"
            f"  Any team composed entirely of safe players is guaranteed to succeed — no evil can sabotage it.\n"
            f"  You do not need quest history to evaluate proposed teams — apply your knowledge directly."
        )
    elif role == "Percival":
        candidates = sorted([state.slot_to_name[state.role_to_slot[r]] for r in ["Merlin", "Morgana"]])
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}. You part of the good team.\n"
            f"  Never address yourself as {my_name}, instead use 'I' or 'me'.\n"
            f"  Your goal is to succeed 3 quests amongst the 5 quest given by not letting a single evil team join a quest.\n"
            f"  {candidates[0]} and {candidates[1]} both appear as Merlin — one is real Merlin (good), one is Morgana (evil).\n"
            f"  Observe who steers accurately without observable basis — that is real Merlin."
        )
    elif role == "Assassin":
        ally = state.slot_to_name[state.role_to_slot["Morgana"]]
        safe_from_evil = [state.slot_to_name[s] for s in range(5)
                         if s not in {my_slot, state.role_to_slot["Morgana"]}]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}. You are part of the evil team.\n"
            f"  Never address yourself as {my_name}, instead use 'I' or 'me'.\n"
            f"  {ally} is Morgana, your evil ally. All others ({safe_from_evil}) are part of the good team (your opponent).\n"
            f"  Your goal is to fail 3 quests amongst the 5 quests given\n"
            f"  Either of you or {ally} alone on a mission can play FAIL independently on a quest — you do not need to be together.\n"
            f"  Only ONE FAIL card is needed to fail an entire quest."
        )
    elif role == "Morgana":
        ally = state.slot_to_name[state.role_to_slot["Assassin"]]
        safe_from_evil = [state.slot_to_name[s] for s in range(5)
                         if s not in {my_slot, state.role_to_slot["Assassin"]}]
        return (
            f"YOUR HIDDEN KNOWLEDGE:\n"
            f"  You are {my_name}. You are part of the evil team.\n"
            f"  Never address yourself as {my_name}, instead use 'I' or 'me'.\n"
            f"  {ally} is the Assassin, your evil ally. All others ({safe_from_evil}) are part of the good team (your opponent).\n"
            f"  Your goal is to fail 3 quests amongst the 5 quests given\n"
            f"  Either of you or {ally} alone on a mission can play FAIL independently on a quest — you do not need to be together.\n"
            f"  Only ONE FAIL card is needed to fail an entire quest."
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
                    f"Evil teammates may have played SUCCESS to preserve cover — success does not confirm anyone as good."
                )
            else:
                lines.append(
                    f"Q{m.quest_num}: Quest succeeded — no FAIL cards were played by anyone on this team."
                )

        elif m.result == "FAIL":
            if faction == "good":
                # Good always plays SUCCESS — all fails came from teammates
                if m.num_fails == len(teammates):
                    lines.append(
                        f"Q{m.quest_num}: You played SUCCESS. All {m.num_fails} fail(s) came from "
                        f"your teammate(s) {teammate_names} — every one of them is confirmed evil."
                    )
                elif m.num_fails == len(m.team):
                    # Entire team size equals fails — impossible for good player since they played success
                    # This shouldn't happen but handle gracefully
                    lines.append(
                        f"Q{m.quest_num}: You played SUCCESS. {m.num_fails} fail(s) from "
                        f"{teammate_names} — at least {m.num_fails} of them are evil."
                    )
                else:
                    lines.append(
                        f"Q{m.quest_num}: You played SUCCESS. {m.num_fails} of your "
                        f"{len(teammates)} teammate(s) {teammate_names} played FAIL — "
                        f"you cannot determine which ones without further evidence."
                    )

            else:
                # Evil player — they know their own card and their ally
                ally_on_team = ally_slot in m.team
                if m.num_fails == len(m.team):
                    lines.append(
                        f"Q{m.quest_num}: {m.num_fails} fails on a {len(m.team)}-person team — "
                        f"every member played FAIL. Good players now have mathematical proof "
                        f"that all of {[_n(state, s) for s in m.team]} are evil. "
                        f"This is maximum exposure — both evil players are confirmed to observers."
                    )
                elif ally_on_team and m.num_fails >= 2:
                    lines.append(
                        f"Q{m.quest_num}: {m.num_fails} fails with {ally_name} also on the team. "
                        f"Both you and {ally_name} played FAIL — good players can deduce "
                        f"at least 2 evil players from {[_n(state, s) for s in m.team]}, "
                        f"narrowing suspicion heavily onto this specific team."
                        f"You must direct suspicion onto your teammates {teammate_names} to avoid exposing yourself."
                    )
                elif ally_on_team:
                    lines.append(
                        f"Q{m.quest_num}: 1 fail with {ally_name} also on the team. "
                        f"Exactly one of you played FAIL — good cannot tell which one."
                        f"You must direct suspicion onto your teammates {teammate_names} to avoid exposing yourself."
                    )
                else:
                    lines.append(
                        f"Q{m.quest_num}: {m.num_fails} fail(s) — {ally_name} was not on this team, "
                        f"so the fail comes from you. You must direct suspicion onto your teammates {teammate_names} to avoid exposing yourself."
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
        f"IMPORTANT: You are {my_name}. Never address yourself as {my_name}, instead use 'I' or 'me'.\nCurrent leader: {leader_name}.", "",
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
    completed = {m.quest_num: m for m in state.mission_history}
    lines = ["QUEST ROADMAP:"]
    for q in range(1, 6):
        size = QUEST_TEAM_SIZES[q - 1]
        if q in completed:
            m = completed[q]
            you = " [YOU]" if my_slot in m.team else ""
            if m.result == "FAIL":
                if m.num_fails == size:
                    deduction = f" — all {size} members mathematically confirmed evil"
                else:
                    deduction = f" — at least {m.num_fails} of these {size} players are evil"
            else:
                deduction = " — no alignment confirmed (evil may have played SUCCESS)"
            lines.append(f"  Q{q} ({size} players): {[_n(state, s) for s in m.team]} → {m.result} ({m.num_fails} fail(s)){you}{deduction}")
        elif q == state.quest_num:
            proposal_count = len([v for v in state.vote_history if v.quest_num == q])
            lines.append(f"  Q{q} ({size} players): ← CURRENT (proposal {proposal_count + 1}/5)")
        else:
            lines.append(f"  Q{q} ({size} players): upcoming")
    
    role = state.slot_to_role[my_slot]
    faction = ROLES_CONFIG[role]["faction"]
    confirmed = _get_confirmed_evil_names(state)
    suspicious = _get_high_suspicion_names(state)
    fail_teams = [set(m.team) for m in state.mission_history if m.result == "FAIL"]

    if faction == "good":
        if len(fail_teams) >= 2:
            common = fail_teams[0].intersection(*fail_teams[1:])
            common_names = [_n(state, s) for s in common]
            if common_names:
                lines.append(f"  ⚠ CROSS-QUEST: {common_names} present on EVERY failed quest — treat as evil.")
        if confirmed:
            lines.append(f"  ✗ CONFIRMED EVIL: {confirmed} — exclude from all future teams.")
        if suspicious:
            lines.append(f"  ? HIGH SUSPICION: {suspicious} — 2+ failed quests, likely evil.")
    else:  # evil
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_names = {state.slot_to_name[s] for s in evil_slots}
        if confirmed:
            exposed = [n for n in confirmed if n in evil_names]
            if exposed:
                lines.append(f"  ✗ COVER LOST: {exposed} are publicly confirmed evil — the group will block them.")
        if suspicious:
            suspected_evil = [n for n in suspicious if n in evil_names]
            if suspected_evil:
                lines.append(f"  ? GROUP SUSPECTS: {suspected_evil} — redirect their suspicion onto innocents now.")

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
    role = state.slot_to_role[my_slot]
    faction = ROLES_CONFIG[role]["faction"]
    confirmed = _get_confirmed_evil_names(state)
    suspicious = _get_high_suspicion_names(state)
    if not confirmed and not suspicious:
        return ""

    if faction == "good":
        lines = ["DEDUCTION SUMMARY — ACT ON THIS:"]
        if confirmed:
            lines.append(f"  CONFIRMED EVIL (mathematical proof): {confirmed}")
            lines.append(f"    → Never include them on any team. Name them as evil in discussion — the math is public.")
        if suspicious:
            lines.append(f"  HIGH SUSPICION (2+ failed quests): {suspicious}")
            lines.append(f"    → Exclude from teams. Challenge them by name publicly.")

    else:  # evil
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_names = {state.slot_to_name[s] for s in evil_slots}
        lines = ["WHAT THE GROUP NOW KNOWS (derived from public quest math):"]
        if confirmed:
            exposed_evil = [n for n in confirmed if n in evil_names]
            exposed_innocent = [n for n in confirmed if n not in evil_names]
            if exposed_evil:
                lines.append(f"  YOUR COVER IS BLOWN: {exposed_evil} are publicly confirmed evil.")
                lines.append(f"    → Mission access for {exposed_evil} is effectively over.")
                lines.append(f"    → Immediately redirect blame onto innocent teammates from those failed quests.")
            if exposed_innocent:
                lines.append(f"  Innocents the group wrongly confirmed as evil: {exposed_innocent} — useful misdirection, do not correct it.")
        if suspicious:
            suspected_evil = [n for n in suspicious if n in evil_names]
            suspected_innocent = [n for n in suspicious if n not in evil_names]
            if suspected_evil:
                lines.append(f"  GROUP SUSPECTS YOU OR YOUR ALLY: {suspected_evil}")
                lines.append(f"    → Defend indirectly. Loudly redirect suspicion toward innocent players by name.")
            if suspected_innocent:
                lines.append(f"  Group suspects innocents: {suspected_innocent} — do not defend them. Let that suspicion grow.")

    return "\n".join(lines)

def get_discussion_prompt(state, slot_id: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    my_name = _n(state, slot_id)
    prior_statements = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    proposal_count = len([v for v in state.vote_history if v.quest_num == state.quest_num])
    faction = ROLES_CONFIG[role]["faction"]
    confirmed = _get_confirmed_evil_names(state)
    suspicious = _get_high_suspicion_names(state)

    if faction == "evil":
        goal = (
            "Your interest is getting yourself or your evil ally onto this quest team.\n"
            "  - Frame all advocacy in terms the group finds credible.\n"
            "  - If suspicion is forming around you or your ally, immediately counter-accuse "
            "an innocent player by name — redirect before the group locks in.\n"
            "  - If you were on a failed quest, blame your innocent teammates specifically.\n"
            "  - Do not wait to be accused. Offense is your best defense."
        )
    else:
        accusation = ""
        if confirmed:
            accusation += (
                f"\n  ACTION REQUIRED: {confirmed} are mathematically confirmed evil from quest results. "
                f"Name them directly. Demand they are excluded. Do not soften this."
            )
        if suspicious:
            accusation += (
                f"\n  ACTION REQUIRED: {suspicious} appeared on multiple failed quests. "
                f"Challenge them by name — ask them to explain it. Do not let it pass."
            )
        goal = (
            "Your goal is to get a clean mission team — no evil players.\n"
            "  - A failed quest is NOT data. It is a point for evil. Treat it accordingly.\n"
            "  - 'Let's test them and see' is only valid when evil cannot win from one more fail. "
            "Check the score before using that argument.\n"
            "  - If quest history gives you evidence, NAME the players and argue for exclusion. "
            "Politeness about evil evidence is a losing strategy.\n"
            "  - Challenge inconsistencies directly: name the player, cite the specific vote or quest."
            + accusation
        )

    merlin_opsec = ""
    if role == "Merlin":
        merlin_opsec = (
            "\n⚠ MERLIN — YOUR STATEMENT IS READ BY THE ASSASSIN:\n"
            "  Never express certainty about evil players beyond what quest math shows everyone.\n"
            "  Never say 'I know X is evil' — say 'X was on two failed quests.'\n"
            "  Never reference hidden information even indirectly. Phrase everything as behavioral observation.\n"
        )

    if prior_statements:
        turn_instruction = (
            f"It is {my_name}'s turn to speak in the Q{state.quest_num} discussion.\n"
            f"React to what others have said. Address players by name.\n{goal}\n{merlin_opsec}"
        )
    else:
        turn_instruction = (
            f"It is {my_name}'s turn to speak first in the Q{state.quest_num} discussion.\n"
            f"No one has spoken yet. Set the frame.\n{goal}\n{merlin_opsec}"
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
        urgency = f"\n⚠ This is proposal {current_proposal_num}/5 for Q{state.quest_num}. A 5th rejection gives evil an automatic quest win.\n"

    # Self-membership annotation
    on_team = slot_id in proposed_team
    self_note = f" You are {'ON' if on_team else 'NOT on'} this proposed team."

    # Flag if voting on own proposal
    own_proposal = slot_id == proposer_slot
    own_note = " This is YOUR OWN proposal — your vote should be consistent with your stated reasoning for it." if own_proposal else ""

    # Role-specific team annotation
    team_annotation = ""
    if role == "Merlin":
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_on_team = [_n(state, s) for s in proposed_team if s in evil_slots]
        if evil_on_team:
            team_annotation = f"\nTEAM CONTAINS KNOWN EVIL: {evil_on_team} — this mission can be sabotaged."
        else:
            team_annotation = f"\nTEAM CONTAINS NO EVIL — this mission is guaranteed safe. You know this from your hidden knowledge, not from quest history."
    elif role in ("Assassin", "Morgana"):
        ally_role = "Morgana" if role == "Assassin" else "Assassin"
        ally_slot = state.role_to_slot[ally_role]
        ally_name = _n(state, ally_slot)
        evil_present = [s for s in proposed_team if s in {slot_id, ally_slot}]
        evil_present_names = [_n(state, s) for s in evil_present]
        if evil_present_names:
            team_annotation = f"\nEVIL ON THIS TEAM: {evil_present_names} — mission sabotage is possible."
        else:
            team_annotation = f"\nNO EVIL ON THIS TEAM — if approved, this mission will succeed regardless of your vote here."

    # Add this block in get_vote_prompt before the return statement:

    faction = ROLES_CONFIG[role]["faction"]
    evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
    evil_on_team = any(s in evil_slots for s in proposed_team)

    score_mandate = ""
    if faction == "good":
        if state.evil_wins == 2 and state.good_wins == 2:
            score_mandate = (
                "\n🚨 DECISIVE QUEST — one quest ends the game.\n"
                "  REJECT any team you are not certain is fully clean. 'Let's see what happens' = handing evil the win."
            )
        elif state.evil_wins == 2:
            score_mandate = (
                "\n🚨 EVIL IS ONE FAIL FROM WINNING. A failed quest ends the game immediately.\n"
                "  REJECT unless every player on this team is confirmed good. 'Gathering data' is not a valid reason here."
            )
        elif state.good_wins == 2:
            score_mandate = (
                "\n⚡ Good is one success from the Assassin phase. Approve only if you are confident the team is clean."
            )
    else:  # evil
        if state.good_wins == 2 and state.evil_wins == 2:
            score_mandate = (
                f"\n🚨 DECISIVE QUEST.\n"
                f"  Evil on this team: {'YES — APPROVE. Play FAIL on the mission.' if evil_on_team else 'NO — this team will succeed regardless of your vote here.'}\n"
                + ("" if evil_on_team else
                   "  REJECT this team. Find a credible public reason. A clean success triggers the Assassin phase.")
            )
        elif state.good_wins == 2:
            score_mandate = (
                f"\n🚨 Good is ONE success from triggering the Assassin phase.\n"
                f"  Evil on this team: {'YES — APPROVE and play FAIL on the mission.' if evil_on_team else 'NO — REJECT. A clean success hands good the quest phase.'}"
            )
        elif state.evil_wins == 2:
            score_mandate = (
                f"\n⚡ Evil is ONE fail from winning outright.\n"
                f"  Evil on this team: {'YES — APPROVE, then play FAIL to end the game immediately.' if evil_on_team else 'NO — mission will succeed regardless. REJECT if you can find a credible reason.'}"
            )

    return (
        f"{priority}\n\n{context}"
        f"{proposer_name} proposes for Q{state.quest_num}: {team_names}{self_note}{own_note}{team_annotation}\n\n"
        f"{urgency}{score_mandate}\n"
        f"{my_name}, vote APPROVE or REJECT. Your vote AND your stated reason are both PUBLIC.\n"
        f"Everyone will hear what you say. Draw on the full history and your notes when reasoning.\n\n"
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
        
    coordination_warning = ""
    if config["faction"] == "evil":
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_on_team = [s for s in team if s in evil_slots]
        if len(evil_on_team) == len(team):
            coordination_warning = (
                f"\n🚨 RULE — BOTH evil players are on this {len(team)}-person team.\n"
                f"  Exactly ONE of you plays FAIL. The other plays SUCCESS. This is not optional.\n"
                f"  If both play FAIL: fail_count = team_size → EVERY member is mathematically confirmed evil.\n"
                f"  That is complete, unrecoverable exposure of the entire evil team.\n"
                f"  One FAIL fails the quest. Two FAILs destroys your cover.\n"
            )
        elif len(evil_on_team) > 1:
            coordination_warning = (
                f"\nMultiple evil players on this team. ONE FAIL is sufficient — do not stack fails unnecessarily.\n"
                f"Additional fails narrow the suspect pool proportionally. Play conservatively.\n"
            )

    return (
        f"{priority}\n\n{context}"
        f"{my_name} is on the Q{state.quest_num} mission. Full team: {team_names}\n\n"
        f"{instruction}{coordination_warning}\n"
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