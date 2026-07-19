from typing import List
from game.roles import ROLES_CONFIG
from config import QUEST_TEAM_SIZES
from memory.manager import load_lessons, load_evil_coord, load_good_coord

# Hard cap on per-phase memory bullet length. The engine trims to first
# non-empty line and applies this before storing into `agent_phase_memory`.
PHASE_MEMORY_LINE_CAP = 140
# Per-agent, per-phase bullet cap. Older entries are evicted when new ones push
# beyond this — keeps the in-prompt memory layer bounded.
PHASE_MEMORY_PER_PHASE_CAP = 4
# Hard ceiling on the size of the deterministic running digest the engine
# rebuilds after each mission / vote outcome.
RUNNING_DIGEST_LINE_CAP = 12

# Compact, decision-oriented game rules. Section headers preserved for status
# signals but every line carries information the agent needs to act.
GAME_RULES = """
GAME: The Resistance: Avalon (5 players). Factions: Good (Merlin, Percival, Loyal Servant — 3), Evil (Assassin, Morgana — 2). Players addressed by name.

WIN:
- Good: complete 3 successful quests AND survive Assassin's final Merlin guess.
- Evil: fail 3 quests, OR guess Merlin correctly after good reaches 3, OR trigger 5 consecutive rejections on one quest.

INITIAL KNOWLEDGE:
- Merlin knows the 2 evil players by name.
- Percival sees 2 players as "Merlin" (real Merlin + Morgana) — cannot tell which.
- Assassin and Morgana know each other only.
- Loyal Servant has no special info. No good player knows who the other two good are.

QUEST FLOW (≤5 quests; first to 3 quest wins ends the quest phase):
1. DISCUSSION — all 5 speak publicly in random order.
2. PROPOSAL — leader proposes a team of required size.
3. VOTE — all 5 vote APPROVE / REJECT with public reason. ≥3 APPROVE passes; else proposal rejected, leader rotates. 5 rejections on one quest = evil wins outright.
4. MISSION — team members secretly play. Good must play SUCCESS; evil chooses. ≥1 FAIL = quest fails. Only the NUMBER of fails is public, never who played them.
5. ASSASSIN PHASE — if good reached 3, Assassin names Merlin. Correct = evil wins, wrong = good wins.

PUBLIC MATH:
- N fails on N-person team → all N are confirmed evil.
- 1 fail on 2-person team → at least 1 of 2 is evil.
- 2 fails on 3-person team → at least 2 of 3 are evil.
- A successful quest does NOT clear its members — evil may play SUCCESS for cover.

TEAM SIZES: Q1=2, Q2=3, Q3=2, Q4=3, Q5=3.
"""

ROLE_CONTEXT = {
    "Merlin": """
=== MERLIN (GOOD) ===
Help good reach 3 successes and survive the Assassin's final Merlin guess.
You know evil by name from the start. Good always plays SUCCESS on missions.
Key risk: the Assassin is hunting YOU. Rejecting only teams with evil, or always proposing safe players, leaks your hidden knowledge.
Frame EVERY public statement as a deduction from PUBLIC evidence (votes/proposals/outcomes). Say "X's vote on Q2 aligns with evil incentives", never "I know X is evil." Role-aware reasoning belongs in private_note only.
""",

    "Percival": """
=== PERCIVAL (GOOD) ===
Help good reach 3 successes and survive the Assassin's final Merlin guess.
You see TWO players as Merlin — one is real Merlin, the other is Morgana (evil). You cannot tell which directly.
Watch whose team guidance actually proves correct over the game; align your votes with that candidate. Externally, act with measured trust toward whichever one; never declare either as Merlin publicly. Good always plays SUCCESS.
""",

    "LoyalServant": """
=== LOYAL SERVANT (GOOD) ===
Help good reach 3 successes and survive the Assassin's final Merlin guess.
No hidden info. Your strength is public deduction: cite specific named behavior (e.g. "X was on Q1 and Q3 fails"). A failed quest proves ≥ fail-count evil on the team; a success proves nothing. "I don't know" is honest and not a Merlin tell. Good always plays SUCCESS.
""",

    "Assassin": """
=== ASSASSIN (EVIL) ===
Fail 3 quests before good reaches 3, OR guess Merlin correctly if good reaches 3.
You know Morgana only. On missions choose SUCCESS (cover) or FAIL (sabotage) — one FAIL fails the quest. You or Morgana alone can FAIL.
Avoid lockstep voting with Morgana, identical arguments, or failing together on small teams (2 fails on 2-person team exposes you both). After every decision, write a private note tracking the most-Merlin-like behavior for the eventual guess.
""",

    "Morgana": """
=== MORGANA (EVIL) ===
Fail 3 quests before good reaches 3, OR help the Assassin identify Merlin if good reaches 3.
You know the Assassin only. On missions choose SUCCESS or FAIL. You appear as "Merlin" to Percival — imitate evidence-based confidence to look like one of the candidates.
Vary your votes/arguments from the Assassin to avoid lockstep tell. Double-failing a small team reveals you both. Help the Assassin track Merlin through shared private reads.
""",
}

# Single compact directives block — merged from the prior OPSEC /
# COMMUNICATION / NOTE trio. Every line still earns its keep.
DIRECTIVES = """
=== RULES YOU MUST FOLLOW ===

PUBLIC vs PRIVATE:
- Discussion statements, vote speeches, and the public team you propose are PUBLIC. Everyone hears them.
- private_note, internal_note, reasoning are PRIVATE — never spoken aloud.

OPSEC (your role and hidden knowledge are private):
- Never state your exact role, faction, or hidden knowledge publicly.
- Never claim certainty about another player's role without observable evidence.
- Role-aware reasoning goes in private_note / internal_note ONLY.

SPEAKING STYLE (public statements):
- Refer to yourself as "I"/"me", never by name.
- Address other players by name.
- React to specific statements and game events — not generic platitudes.
- Cite a specific named player's vote, proposal, or statement when justifying.

PRIVATE NOTES (after each action):
- ONE LINE only (~25 words). The engine keeps your private_note across the whole game and surfaces it later; verbose notes bloat later prompts.
- Name specific players. State what their behavior moved on YOUR read — not raw facts already visible in the game history.
- Prefer triggers over facts: "Bob voted REJECT on my Q2 team at 2-2 — now in suspect pool" beats "Bob voted REJECT".
- Drop weak/vague updates ("nothing new", "still unsure"). If nothing moved this turn, write "".
- Write a note after your discussion statement, your vote, and your mission card play.

TWO-LAYER MEMORY — what you see vs what the engine keeps:
- The prompt you receive has TWO memory layers. The "READS SO FAR" block is a deterministic snapshot the engine rebuilt from public events — trust it as ground truth. The "MY PAST NOTES" block is your own prior private_notes from earlier phases this game; both layers persist across phases.
- The engine CAPS your stored notes. Anything not in those capped layers is gone — what you write in private_note IS your future memory, so make it count.
"""


def _dynamic_priority_block(role: str, state) -> str:
    faction = ROLES_CONFIG[role]["faction"]
    g, e, q = state.good_wins, state.evil_wins, state.quest_num
    decisive = (g == 2 and e == 2)
    lines = [
        "=== SITUATION ===",
        f"Score: Good {g} — Evil {e}. Quest: Q{q}/5. Good needs {3 - g} more, evil {3 - e} more.",
    ]
    if decisive:
        lines.append("DECISIVE — both one quest result from ending the phase.")
    elif g == 2:
        lines.append("Good one success from ending the phase (Assassin guess next).")
    elif e == 2:
        lines.append("Evil one FAIL from winning outright.")

    if faction == "good":
        if e == 2:
            lines.append("One FAIL card this quest = evil wins immediately. Not recoverable.")
        elif g == 2:
            lines.append("Clean success → quest phase ends, Assassin must guess Merlin.")
    else:
        if e == 2:
            lines.append("Any FAIL you or your ally can play this quest = immediate evil win.")
        elif g == 2:
            lines.append("Clean success → quest phase ends, Assassin must guess (not a guaranteed evil win).")
    return "\n".join(lines)


def build_system_prompt(role: str, agent_name: str, special_info: str) -> str:
    """Static system prompt: rules, role context, and behavioral directives.
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
        f"{DIRECTIVES}"
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
    """Legacy verbose note stream. Kept in state.agent_notes for the
    reflection pass at game end. The IN-PROMPT memory layer is now served
    by the layered blocks above (`_build_phase_memory` + `build_running_digest`);
    this function is a small safety-net showing the most-recent raw notes so
    we don't double-feed what the layered blocks already cover."""
    notes = state.agent_notes.get(my_slot, [])
    if not notes:
        return ""
    recent = notes[-3:]
    return "PAST RAW NOTES (recent):\n" + "\n".join(recent)


def _build_phase_memory(state, my_slot: int, current_phase: str) -> str:
    """Compact block of the agent's own past private_notes, grouped by phase
    and tagged with quest number. Already capped by the engine at the most
    recent PHASE_MEMORY_PER_PHASE_CAP entries per phase.

    `current_phase`: which phase we're about to enter. Past entries from
    earlier phases this game stream in; entries from the SAME phase this
    quest are surfaced only if they exist (e.g., earlier-turn notes
    written within the same discussion round).
    """
    per_phase = state.agent_phase_memory.get(my_slot)
    if not per_phase:
        return ""

    by_quest_order: list[tuple[int, str, list[str]]] = []
    # Zone A: ALL completed quests' notes from prior phases (cross-phase memory).
    prior_phases = ("discussion", "proposal", "vote", "mission", "rejection", "analysis")
    for ph in prior_phases:
        lst = per_phase.get(ph) or []
        if not lst:
            continue
        # Parse the "[Q{n} {phase}] ..." prefix back out of each line.
        rendered = []
        for line in lst:
            prefix, _, body = line.partition("] ")
            rendered.append(f"  • {body}")
        by_quest_order.append((0, ph, rendered))

    if not by_quest_order:
        return ""

    header = "MY PAST NOTES (this game, by phase — capped at last 4 per phase):"
    lines = [header]
    for _priority, ph, rendered in by_quest_order:
        lines.append(f"[{ph}]")
        lines.extend(rendered)
    return "\n".join(lines)


def _per_player_signal(state) -> dict[str, dict]:
    """Derive per-player behavioral signals from public history in O(#rounds).

    Returns a dict keyed by player name with:
      - confirmed_evil: bool
      - on_fail_teams: list of quest_nums
      - approve_count, reject_count, last_vote
      - appeared_on_quests: list of quest_nums
    """
    confirmed_set = set(_get_confirmed_evil_names(state))
    out: dict[str, dict] = {}
    for name in state.slot_to_name.values():
        out[name] = {
            "confirmed_evil": name in confirmed_set,
            "on_fail_teams": [],
            "approve_count": 0,
            "reject_count": 0,
            "last_vote": None,
            "appeared_on_quests": [],
        }

    for m in state.mission_history:
        for slot in m.team:
            entry = out[state.slot_to_name[slot]]
            entry["appeared_on_quests"].append(m.quest_num)
            if m.result == "FAIL" and not entry["confirmed_evil"]:
                entry["on_fail_teams"].append(m.quest_num)

    for v in state.vote_history:
        for slot, vote in v.votes.items():
            entry = out[state.slot_to_name[slot]]
            if vote == "APPROVE":
                entry["approve_count"] += 1
            elif vote == "REJECT":
                entry["reject_count"] += 1
            entry["last_vote"] = (v.quest_num, v.proposal_num, vote)
    return out


def _build_good_digest(state, my_slot: int, role: str) -> list[str]:
    signal = _per_player_signal(state)
    my_name = _n(state, my_slot)
    lines: list[str] = []

    if not state.mission_history and not state.vote_history:
        return ["(No quest data yet — only the opening situation block applies.)"]

    # 1) Confirmed-evil list (always public, this is the highest-signal fact).
    confirmed = sorted([n for n, e in signal.items() if e["confirmed_evil"]])
    if confirmed:
        lines.append(f"Confirmed evil (math): {', '.join(confirmed)}")

    # 2) Suspects (2+ fail quests) — distinguish from confirmed.
    suspects = sorted([
        n for n, e in signal.items()
        if not e["confirmed_evil"] and len(e["on_fail_teams"]) >= 2
    ])
    if suspects:
        lines.append(f"Multi-quest fails: {', '.join(suspects)}")

    # 3) Per-player compressed behavior — only the ones with interesting signals.
    interesting = []
    for name, e in signal.items():
        if name == my_name or e["confirmed_evil"]:
            continue
        flags = []
        if e["on_fail_teams"]:
            flags.append(f"on F:{e['on_fail_teams']}")
        if e["reject_count"] >= 2 and e["approve_count"] == 0:
            flags.append("pure-reject")
        elif e["approve_count"] >= 2 and e["reject_count"] == 0:
            flags.append("pure-approve")
        elif (e["reject_count"] + e["approve_count"]) >= 2:
            flags.append(f"{e['approve_count']}A/{e['reject_count']}R")
        if e["last_vote"]:
            q, p, vote = e["last_vote"]
            flags.append(f"last:Q{q}P{p} {vote[:1]}")
        if flags:
            interesting.append((name, flags))
    if interesting:
        lines.append("Behavior:")
        for name, flags in interesting:
            lines.append(f"  {name}: {', '.join(flags)}")

    # 4) Cross-quest common suspect (most damning pattern: same suspect
    #    present on multiple failed quests).
    cross_quest = set.intersection(*[
        set(state.slot_to_name[s] for s in m.team)
        for m in state.mission_history if m.result == "FAIL"
    ]) if sum(1 for m in state.mission_history if m.result == "FAIL") >= 2 else set()
    cross_quest -= {my_name}
    if cross_quest:
        lines.append(f"Cross-quest overlap on every fail: {sorted(cross_quest)}")

    return lines or ["(No quest data yet.)"]


def _build_percival_digest(state, my_slot: int) -> list[str]:
    my_name = _n(state, my_slot)
    merlin_slot = state.role_to_slot["Merlin"]
    morgana_slot = state.role_to_slot["Morgana"]
    cand_a = _n(state, merlin_slot)
    cand_b = _n(state, morgana_slot)
    signal = _per_player_signal(state)
    a = signal.get(cand_a, {})
    b = signal.get(cand_b, {})

    lines = [f"Perceived Merlin candidates: {cand_a} vs {cand_b}"]

    def _tally(s):
        if not s:
            return "no data"
        total = s.get("approve_count", 0) + s.get("reject_count", 0)
        return f"{s.get('approve_count', 0)}A/{s.get('reject_count', 0)}R over {total} votes; on Q{s.get('appeared_on_quests', []) or '—'}; on fails {s.get('on_fail_teams', []) or 'none'}"

    lines.append(f"{cand_a}: {_tally(a)}")
    lines.append(f"{cand_b}: {_tally(b)}")
    if a.get("confirmed_evil"):
        lines.append(f"{cand_a} confirmed evil by math — not the real Merlin, but lockstep-tracked.")
    if b.get("confirmed_evil"):
        lines.append(f"{cand_b} confirmed evil by math — not the real Merlin.")

    if not state.vote_history and not state.mission_history:
        return ["(No quest data yet. Consider whose opening speech sounds more Merlin-like.)"]
    return lines


def _build_evil_digest(state, my_slot: int, role: str) -> list[str]:
    ally_role = "Morgana" if role == "Assassin" else "Assassin"
    ally_slot = state.role_to_slot[ally_role]
    ally_name = _n(state, ally_slot)
    my_name = _n(state, my_slot)
    signal = _per_player_signal(state)
    candidates = [
        n for n, s in signal.items()
        if n not in (my_name, ally_name)
    ]
    lines = ["Merlin candidates (the 3 good players)"]

    if not state.vote_history:
        return ["(No quest data yet — track speech style; one will sound most evidence-steered.)"]

    # Vote alignment with ally -> lockstep warning.
    my_record, ally_record = [], []
    for v in state.vote_history:
        if v.votes.get(my_slot) in ("APPROVE", "REJECT"):
            my_record.append(v.votes[my_slot])
        if v.votes.get(ally_slot) in ("APPROVE", "REJECT"):
            ally_record.append(v.votes[ally_slot])
    matches = sum(1 for a, b in zip(my_record, ally_record) if a == b)
    if my_record and ally_record and matches >= max(2, len(my_record) - 1):
        lines.append(
            f"LOCKSTEP WARN: you and {ally_name} voted identically on "
            f"{matches}/{min(len(my_record), len(ally_record))} rounds. Vary soon."
        )

    for name in candidates:
        e = signal[name]
        tags = []
        total = e["approve_count"] + e["reject_count"]
        if total:
            tags.append(f"{e['approve_count']}A/{e['reject_count']}R")
        if e["on_fail_teams"]:
            tags.append(f"on F:{e['on_fail_teams']}")
        if e["appeared_on_quests"]:
            tags.append(f"on Q{e['appeared_on_quests']}")
        if e["last_vote"]:
            q, p, vote = e["last_vote"]
            tags.append(f"last:Q{q}P{p} {vote[:1]}")
        lines.append(f"  {name}: " + ", ".join(tags) if tags else f"  {name}: no data")

    return lines


def build_running_digest(state, my_slot: int) -> list[str]:
    """Deterministic, role-templated snapshot of cross-phase reads.

    Engine rebuilds after every mission outcome and vote outcome, so the
    digest always reflects the latest public evidence. Cheap (no LLM).
    """
    role = state.slot_to_role[my_slot]
    faction = ROLES_CONFIG[role]["faction"]

    # Check role FIRST (Percival branches off the good faction) before the
    # faction-based default. Otherwise Percival would hit the generic good
    # digest and lose the two-Merlin-candidate framing it specifically needs.
    if role == "Percival":
        raw = _build_percival_digest(state, my_slot)
    elif faction == "good":
        raw = _build_good_digest(state, my_slot, role)
    else:  # evil: Assassin / Morgana
        raw = _build_evil_digest(state, my_slot, role)

    # Header line: score + quest.
    header = f"READS SO FAR — G{state.good_wins}/E{state.evil_wins}, Q{state.quest_num}/5"
    out = [header] + raw
    return out[:RUNNING_DIGEST_LINE_CAP + 1]


def _build_current_discussion(state) -> str:
    entries = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    if not entries:
        return ""
    lines = [f"DISCUSSION SO FAR — Q{state.quest_num} (all public):"]
    for d in entries:
        lines.append(f'  {_n(state, d.slot_id)}: "{d.statement}"')
    return "\n".join(lines)


def _format_memory_layer(state, my_slot: int, current_phase: str) -> str:
    """Compose the two-layer memory block: deterministic digest + agent's
    own past phase notes. Inserted FIRST in the prompt so the agent reads
    its compressed memory before wading through raw context.

    `current_phase`: which phase the prompt is for. Lets us shape ordering
    and keep digest-first even when no per-phase memory exists yet.
    """
    digest_lines = build_running_digest(state, my_slot)
    memory_block = _build_phase_memory(state, my_slot, current_phase)

    parts = ["=== MEMORY (what you carry into this phase) ==="]
    parts.append("\n".join(digest_lines))
    if memory_block:
        parts.append("")
        parts.append(memory_block)
    return "\n".join(parts) + "\n"


def _build_game_context(state, my_slot: int) -> str:
    my_name = _n(state, my_slot)
    leader_name = _n(state, state.leader_slot)
    # Order matters: the memory layer goes FIRST so the agent reads its
    # compressed cross-phase state before raw context. The "current phase"
    # (discussion/vote/mission/etc.) is supplied by the calling prompt.
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

_FRAMING_GUIDE = {
    "Merlin": "Speak from PUBLIC evidence only (\"X voted REJECT on a clean team at 2-2\"), never \"I know\". Reasonable disagreement is not a tell.",
    "Percival": "Act uncertain between your two Merlin candidates; align with whichever's guidance proves accurate. Never declare either as Merlin publicly.",
    "LoyalServant": "No hidden info — your strength is public deduction. Cite specific evidence (\"X was on Q1 and Q3 fails\"). \"I don't know\" is honest and not a Merlin tell.",
    "Assassin": "Sound like a Loyal Servant reasoning publicly. Plausible-but-wrong theories and split-ticket votes work — vary your voice from your ally.",
    "Morgana": "Imitate evidence-based confidence so Percival can't pick you from the real Merlin. Vary votes/arguments from the Assassin.",
}

_VOTE_GUIDE = {
    "Merlin": "You know evil. VOTE in patterns only that knowledge explains — but that is also the Assassin's signal. Trade off case by case.",
    "Percival": "Watch each Merlin candidate's team guidance; align your votes with whichever proves accurate — without revealing which.",
    "LoyalServant": "No hidden info. Vote only from observable evidence — prior fails, vote patterns, statement consistency.",
    "Assassin": "Lockstep with Morgana is detectable. Vary your stance from your ally when you can do so plausibly.",
    "Morgana": "Lockstep with the Assassin is detectable. Vary your stance from your ally when you can do so plausibly.",
}


def get_analysis_prompt(state, slot_id: int, context_hint: str, phase: str = "vote") -> str:
    """Pre-decision analysis pass. Deduction only — no action decision.
    `phase` = which decision phase this analysis precedes ('proposal' or 'vote'),
    so the matching phase lessons are surfaced here too."""
    role = state.slot_to_role[slot_id]
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, phase)
    return (
        f"{context}{lessons}"
        f"Context for this analysis: {context_hint}\n\n"
        f"TASK — Analyze only. Do not decide your action yet.\n"
        f"1. What does quest math confirm with certainty? (fail counts, team compositions)\n"
        f"2. What is your current read on each player's alignment and why?\n"
        f"3. Have any players contradicted themselves across rounds? Name them specifically.\n"
        f"4. What is the single most important objective for your faction this round?\n\n"
        f'{{"certain_facts": "...", "suspicion_model": "...", "contradiction": "...", "priority": "..."}}\n'
    )


def get_discussion_prompt(state, slot_id: int) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, "discussion")
    memory = _format_memory_layer(state, slot_id, "discussion")
    prior = [d for d in state.discussion_log if d.quest_num == state.quest_num]
    turn = (
        f"Your turn to speak in the Q{state.quest_num} discussion. Earlier statements this quest are listed above."
        if prior else
        f"Your turn to speak first in the Q{state.quest_num} discussion. No one has spoken yet."
    )
    framing = _FRAMING_GUIDE.get(role, "")
    return (
        f"{priority}\n\n{memory}{context}{lessons}"
        f"PHASE: DISCUSSION. Your statement is PUBLIC.\n"
        f"{turn}\n"
        f"Framing: {framing}\n\n"
        f'REQUIRED JSON — exactly these fields, in this order:\n'
        f'{{"statement": "<your public speech as I/me>", "private_note": "<ONE LINE ~25 words: what this Statement just moved on YOUR read>"}}\n'
    )


def get_rejection_discussion_prompt(state, slot_id: int, rejected_team: list, vote_record) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, "discussion")
    memory = _format_memory_layer(state, slot_id, "discussion")
    team_names = [_n(state, s) for s in rejected_team]
    approvers = [_n(state, s) for s, v in vote_record.votes.items() if v == "APPROVE"]
    rejecters = [_n(state, s) for s, v in vote_record.votes.items() if v == "REJECT"]
    return (
        f"{priority}\n\n{memory}{context}{lessons}"
        f"PHASE: REJECTION REACTION. Proposal {team_names} was REJECTED.\n"
        f"Approvers: {approvers or 'none'}. Rejecters: {rejecters or 'none'}.\n"
        f"React in 1–2 sentences (public).\n\n"
        f'REQUIRED JSON — exactly these fields:\n'
        f'{{"statement": "<your brief public reaction as I/me>", "private_note": "<ONE LINE ~25 words: what this vote just moved on YOUR read>"}}\n'
    )


def get_proposal_prompt(state, slot_id: int, team_size: int, retry_hint: str = None) -> str:
    role = state.slot_to_role[slot_id]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, "proposal")
    memory = _format_memory_layer(state, slot_id, "proposal")
    all_names = list(state.slot_to_name.values())
    current_proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1

    lines = [
        f"PHASE: PROPOSAL. You are the current leader for Q{state.quest_num}. Pick exactly {team_size} player(s) for the mission team.",
        f"Available: {all_names}.",
        f"Proposal {current_proposal_num}/5 this quest.",
    ]
    if current_proposal_num == 5:
        lines.append("FINAL PROPOSAL — rejection = evil wins immediately.")
    elif current_proposal_num == 4:
        lines.append("If rejected, the next (5/5) proposal is the last before auto-evil-win.")
    lines.append("Don't REJECT your own proposal — it kills your credibility.")
    lines.append("Include yourself by default — costs nothing on success, lets you read your own card on failure.")
    if ROLES_CONFIG[role]["faction"] == "evil":
        lines.append("Don't double-fail a small team — 2 fails on 2-person exposes you both.")

    user = (
        f"{priority}\n\n{memory}{context}{lessons}"
        + "\n".join(lines) + "\n"
        f'REQUIRED JSON — exactly these fields:\n'
        f'{{"proposed_team": [<exactly {team_size} player name strings>], '
        f'"speech": "<your public announcement naming the SAME players as proposed_team>", '
        f'"private_note": "<ONE LINE ~25 words: what your team choice just signaled>"}}\n'
    )
    if retry_hint:
        user += f"\nPARSE HINT: {retry_hint}\n"
    return user


def get_vote_prompt(state, slot_id: int, proposer_slot: int, proposed_team: List[int]) -> str:
    role = state.slot_to_role[slot_id]
    faction = ROLES_CONFIG[role]["faction"]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, "vote")
    memory = _format_memory_layer(state, slot_id, "vote")
    proposer_name = _n(state, proposer_slot)
    team_names = [_n(state, s) for s in proposed_team]
    current_proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1

    lines = [
        f"PHASE: VOTE. {proposer_name} proposes for Q{state.quest_num}: {team_names}.",
        f"Proposal {current_proposal_num}/5 this quest.",
    ]
    if slot_id in proposed_team:
        lines.append("You ARE on this team.")
        if faction == "good":
            lines.append("Good always plays SUCCESS — any past fails came from evil teammates.")
    else:
        lines.append("You are NOT on this team.")
    if slot_id == proposer_slot:
        lines.append("This is your own proposal; REJECT here kills your credibility.")

    if role == "Merlin":
        evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
        evil_on = [_n(state, s) for s in proposed_team if s in evil_slots]
        lines.append(f"Hidden knowledge — evil on this team: {evil_on} (sabotagable)." if evil_on
                     else "Hidden knowledge — no evil on this team (guaranteed success).")
    elif role in ("Assassin", "Morgana"):
        ally_role = "Morgana" if role == "Assassin" else "Assassin"
        ally_slot = state.role_to_slot[ally_role]
        evil_present = [_n(state, s) for s in proposed_team if s in {slot_id, ally_slot}]
        lines.append(f"Evil on this team: {evil_present} (sabotage possible)." if evil_present
                     else "No evil here — mission succeeds regardless of your vote.")

    for m in state.mission_history:
        if m.result == "SUCCESS" and set(proposed_team) == set(m.team):
            lines.append(f"Same team already succeeded on Q{m.quest_num} — favorable track record.")
            break

    if current_proposal_num == 5:
        if faction == "good":
            lines.append("5th proposal — REJECT ends the game immediately with an evil win. Quest failure is recoverable; 5th rejection is not.")
        else:
            lines.append("5th proposal — a REJECT you cast is publicly attributable to you.")
    elif current_proposal_num == 4:
        lines.append("4th proposal — rejected → 5th is last before auto-evil-win.")

    g, e = state.good_wins, state.evil_wins
    if faction != "good":
        evil_on = any(s in {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]} for s in proposed_team)
        if g == 2 and e == 2:
            lines.append("Decisive quest — evil on team? a FAIL ends game." if evil_on
                         else "No evil — clean success lets good reach Assassin phase.")
        elif g == 2:
            lines.append("Evil on team? a FAIL prevents good success." if evil_on
                         else "No evil — approval hands good a success.")
        elif e == 2:
            lines.append("Evil on team? a FAIL wins immediately." if evil_on
                         else "No evil — mission succeeds regardless of your vote.")

    vote_guide = _VOTE_GUIDE.get(role, "")
    return (
        f"{priority}\n\n{memory}{context}{lessons}"
        + "\n".join(lines) + "\n\n"
        f"Voting hint: {vote_guide}\n"
        f"Both your vote and your reason are public — cite a specific named player/behavior.\n\n"
        f'REQUIRED JSON — exactly these fields:\n'
        f'{{"vote": "<APPROVE or REJECT>", "speech": "<your public reason>", "private_note": "<ONE LINE ~25 words: what this vote just moved on YOUR read>"}}\n'
    )


def get_mission_prompt(state, slot_id: int, role: str, team: List[int]) -> str:
    config = ROLES_CONFIG[role]
    priority = _dynamic_priority_block(role, state)
    context = _build_game_context(state, slot_id)
    lessons = _phase_lessons_block(state, role, "mission")
    memory = _format_memory_layer(state, slot_id, "mission")
    team_names = [_n(state, s) for s in team]
    evil_slots = {state.role_to_slot["Assassin"], state.role_to_slot["Morgana"]}
    evil_on_team_count = len([s for s in team if s in evil_slots])

    lines = [f"PHASE: MISSION. You are on Q{state.quest_num}: {team_names}."]

    if config["faction"] == "good":
        lines.append("Good always plays SUCCESS — no real choice.")
        schema = '{"card": "SUCCESS", "internal_note": "<ONE LINE ~25 words: cover moves for next quest>"}\n'
    else:
        good_after = state.good_wins + 1
        evil_after = state.evil_wins + 1
        lines.append("Evil chooses SUCCESS (cover) or FAIL (sabotage). Only the FAIL COUNT is public, never who played it.")
        lines.append(f"Score: Good {state.good_wins} — Evil {state.evil_wins}.")
        lines.append(f"SUCCESS → Good {good_after}." + (" (reaches 3 → Assassin phase; evil can still win by guessing Merlin)" if good_after >= 3 else f" (good needs {3 - good_after} more)"))
        lines.append(f"FAIL    → Evil {evil_after}." + (" (reaches 3 → evil wins outright)" if evil_after >= 3 else f" (evil needs {3 - evil_after} more)"))
        if evil_on_team_count == len(team):
            lines.append(f"All evil on this {len(team)}-person team — 1 FAIL fails it; 2 FAILs exposes you both mathematically.")
        elif evil_on_team_count > 1:
            lines.append("Multiple evil here — one FAIL suffices; extra FAILs narrow the suspect pool.")
        lines.append(f"Mission hint: keep cover beyond this single quest; your survival matters for the Assassin's eventual guess.")
        schema = '{"card": "<SUCCESS or FAIL>", "internal_note": "<ONE LINE ~25 words: why this card: cover/sabotage/cover-protect-ally>"}\n'

    role = state.slot_to_role[slot_id]
    return (
        f"{priority}\n\n{memory}{context}{lessons}"
        + "\n".join(lines) + "\n\n"
        f"REQUIRED JSON — exactly these fields:\n"
        f"{schema}"
    )


def get_assassin_prompt(state, assassin_slot: int) -> str:
    morgana_slot = state.role_to_slot["Morgana"]
    candidates = [_n(state, s) for s in range(5) if s not in (assassin_slot, morgana_slot)]
    mission_summary = "\n".join(
        f"  Q{m.quest_num}: {[_n(state, s) for s in m.team]} → {m.result} ({m.num_fails} fail)"
        for m in state.mission_history
    ) or "  None."
    vote_summary = "\n".join(
        f"  Q{v.quest_num}P{v.proposal_num}: {_n(state, v.proposer_slot)} → {[_n(state, s) for s in v.proposed_team]} [{v.result}]"
        f" | APPROVE: {[_n(state, s) for s, vt in v.votes.items() if vt == 'APPROVE']}"
        f" | REJECT: {[_n(state, s) for s, vt in v.votes.items() if vt == 'REJECT']}"
        for v in state.vote_history
    ) or "  None."
    # Full discussion preserved verbatim — the Assassin's Merlin read depends on
    # exact phrasing more than any other phase, so we keep this rich block.
    all_disc = "\n".join(
        f"  Q{d.quest_num} {_n(state, d.slot_id)}: \"{d.statement}\""
        for d in state.discussion_log
    ) or "  None."
    my_notes = "\n".join(state.agent_notes.get(assassin_slot, [])) or "  None."
    role = state.slot_to_role[assassin_slot]
    lessons = _phase_lessons_block(state, role, "assassin")
    digest_text = "\n".join(build_running_digest(state, assassin_slot))
    phase_memory_block = _build_phase_memory(state, assassin_slot, "assassin")

    return (
        f"PHASE: ASSASSIN. Final score: Good {state.good_wins} — Evil {state.evil_wins}. Good reached 3.\n"
        f"Correct Merlin guess → evil wins. Wrong → good wins. ONE chance.\n\n"
        f"You know Morgana. Merlin has acted on hidden knowledge of you all game — steering good away from you.\n\n"
        f"=== YOUR CARRIED MEMORY (compact digest of cross-phase reads) ===\n"
        f"{digest_text}\n"
        f"{phase_memory_block}\n\n"
        f"QUEST RESULTS:\n{mission_summary}\n\n"
        f"ALL VOTES:\n{vote_summary}\n\n"
        f"ALL DISCUSSION (verbatim):\n{all_disc}\n\n"
        f"YOUR NOTES:\n{my_notes}\n\n"
        f"Candidates (anyone except you): {candidates}\n\n"
        f"Guess heuristics — weigh observable behavior:\n"
        f"  - Proposals/votes that consistently differ from public evidence imply hidden knowledge.\n"
        f"  - A player who accuses by name with a plausible chain is more credible than vague gesturing.\n"
        f"  - A player present on a SUCCESS where evil was provably present is provably good.\n"
        f"  - A player never appearing on FAIL quests is suspicious but not conclusive.\n"
        f"  - If Percival visibly aligns with one candidate over the other, that is a strong (itself unprovable) signal.\n"
        f"{lessons}"
        f'REQUIRED JSON — exactly these fields:\n'
        f'{{"guess_name": "<one name from candidates>", "reasoning": "<your full analysis>"}}\n'
    )
