import random
from collections import Counter
from typing import Dict, List, Tuple

from config import QUEST_TEAM_SIZES, MAX_VOTE_FAILURES, QUESTS_TO_WIN
from game.roles import ROLES_CONFIG, ALL_ROLES
from game.state import GameState, VoteRecord, MissionRecord, DiscussionEntry, HUMAN_NAMES
from agents.prompts import (
    build_system_prompt,
    get_discussion_prompt,
    get_rejection_discussion_prompt,
    get_proposal_prompt,
    get_vote_prompt,
    get_mission_prompt,
    get_assassin_prompt,
    get_analysis_prompt,
)
from agents.llm_client import call_llm_json, log_llm_call
from agents.schemas import (
    DiscussionOutput,
    RejectionReactionOutput,
    ProposalOutput,
    VoteOutput,
    MissionOutput,
    AssassinOutput,
    AnalysisOutput,
)
from storage.printer import (
    print_game_header, print_quest_header, print_discussion_header,
    print_statement, print_proposal_header, print_proposal,
    print_vote_header, print_vote, print_vote_result,
    print_mission_header, print_mission_private, print_mission_result,
    print_score, print_assassin_phase, print_assassin_guess,
    print_outcome, print_five_proposals_auto,
    DIM, RESET,
)


class GameEngine:
    def __init__(self, llm, analysis_llm=None):
        self.llm = llm
        self.analysis_llm = analysis_llm or llm
        self._system_cache: Dict[str, str] = {}
        # Cache of (state_id, slot, phase) -> context string. State is mutated only
        # between quest turns / between proposals, so caching by (state version, slot) is
        # safe and avoids rebuilding the ~1500-token context repeatedly within one phase.
        self._phase_version = -1
        self._ctx_cache: Dict[Tuple, str] = {}

    def _bump_phase(self, state: GameState):
        """Mark a new phase boundary so cached contexts become stale."""
        version = id(state) ^ (state.quest_num * 1000 + state.proposal_num)
        if version != self._phase_version:
            self._phase_version = version
            self._ctx_cache.clear()

    def _system(self, role: str, state: GameState) -> str:
        if role not in self._system_cache:
            agent_name = state.slot_to_name[state.role_to_slot[role]]
            special_info = self._build_special_info(role, state)
            self._system_cache[role] = build_system_prompt(role, agent_name, special_info)
        return self._system_cache[role]

    def _build_special_info(self, role: str, state: GameState) -> str:
        template = ROLES_CONFIG[role]["special_info_template"]
        if role == "Merlin":
            evil_names = [state.slot_to_name[state.role_to_slot[r]] for r in ["Assassin", "Morgana"]]
            return template.format(evil_names=evil_names)
        elif role == "Percival":
            candidate_names = sorted([state.slot_to_name[state.role_to_slot[r]] for r in ["Merlin", "Morgana"]])
            return template.format(merlin_candidate_names=candidate_names)
        elif role in ["Assassin", "Morgana"]:
            ally = "Morgana" if role == "Assassin" else "Assassin"
            return template.format(evil_ally_name=state.slot_to_name[state.role_to_slot[ally]])
        return template

    def _append_note(self, state: GameState, slot_id: int, note: str):
        """Append a note to a specific agent's private notes."""
        if not note or not note.strip():
            return
        if slot_id not in state.agent_notes:
            state.agent_notes[slot_id] = []
        state.agent_notes[slot_id].append(note.strip())

    def _record_phase_memory(self, state: GameState, slot_id: int, phase: str, text: str, quest_num: int = None):
        """Slim `text` to one tight line and append to per-agent phase memory.

        The slim rule: first non-empty line, hard-capped at 140 chars (truncated
        with ellipsis on overflow). `quest_num` is prepended as a `[Q{n} {phase}]`
        tag so the agent sees the cross-quest timeline at a glance.
        """
        from agents.prompts import PHASE_MEMORY_LINE_CAP
        if not text or not text.strip():
            return
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if not first_line:
            return
        if len(first_line) > PHASE_MEMORY_LINE_CAP:
            first_line = first_line[: PHASE_MEMORY_LINE_CAP - 1].rstrip() + "…"
        qn = quest_num if quest_num is not None else state.quest_num
        bullet = f"[Q{qn} {phase}] {first_line}"
        per_phase = state.agent_phase_memory.setdefault(slot_id, {}).setdefault(phase, [])
        per_phase.append(bullet)

    def _prune_phase_memory(self, state: GameState, slot_id: int):
        """Cap each phase's bullet list to the most recent entries."""
        from agents.prompts import PHASE_MEMORY_PER_PHASE_CAP
        per_phase = state.agent_phase_memory.get(slot_id)
        if not per_phase:
            return
        for phase, lst in list(per_phase.items()):
            if len(lst) > PHASE_MEMORY_PER_PHASE_CAP:
                per_phase[phase] = lst[-PHASE_MEMORY_PER_PHASE_CAP:]

    def _refresh_running_digest(self, state: GameState, slots=None):
        """Recompute the deterministic game-state digest for one or all agents.

        Cheap (no LLM): walks state.mission_history / state.vote_history /
        state.discussion_log to produce a role-templated snapshot. Called
        after every mission conclusion and vote outcome so reads always
        reflect the latest evidence. Same call works mid-game (e.g., between
        proposals) so the in-prompt digest never goes stale."""
        from agents.prompts import build_running_digest
        targets = slots if slots is not None else list(range(5))
        for s in targets:
            digest = build_running_digest(state, s)
            state.agent_running_digest[s] = digest

    def _broadcast_event_note(self, state: GameState, note: str, slots: List[int] = None):
        """Write a factual game event note to all agents (or a subset)."""
        targets = slots if slots is not None else list(range(5))
        for slot in targets:
            self._append_note(state, slot, note)

    def setup_game(self, game_id: int) -> GameState:
        state = GameState(game_id=game_id)
        roles = ALL_ROLES.copy()
        random.shuffle(roles)
        self._system_cache = {}
        self._phase_version = -1
        self._ctx_cache.clear()
        for slot, role in enumerate(roles):
            state.slot_to_role[slot] = role
            state.role_to_slot[role] = slot
            state.slot_to_faction[slot] = ROLES_CONFIG[role]["faction"]
        state.leader_slot = random.randint(0, 4)

        names = random.sample(HUMAN_NAMES, 5)
        for slot, name in enumerate(names):
            state.slot_to_name[slot] = name
            state.name_to_slot[name] = slot

        state.log_lines.append(f"=== GAME {game_id} ===")
        state.log_lines.append(f"Names: {state.slot_to_name}")
        state.log_lines.append(f"Roles: {state.slot_to_role}")
        state.log_lines.append(f"Leader: {state.slot_to_name[state.leader_slot]}")
        state.log_lines.append("")
        print_game_header(game_id, state.slot_to_role, state.slot_to_name)
        return state

    def run_game(self, game_id: int) -> GameState:
        state = self.setup_game(game_id)
        while state.good_wins < QUESTS_TO_WIN and state.evil_wins < QUESTS_TO_WIN:
            self._run_quest(state)
        if state.good_wins == QUESTS_TO_WIN:
            self._run_assassin_phase(state)
            state.outcome = "EVIL_WINS" if state.assassin_correct else "GOOD_WINS"
        else:
            state.outcome = "EVIL_WINS"
        state.log_lines.append(f"\n=== OUTCOME: {state.outcome} ===")
        print_outcome(state.outcome)
        return state

    def _run_quest(self, state: GameState):
        q = state.quest_num
        team_size = QUEST_TEAM_SIZES[q - 1]
        leader_role = state.slot_to_role[state.leader_slot]

        state.log_lines.append(f"\n--- QUEST {q} (team size: {team_size}, leader: Slot {state.leader_slot}) ---")
        print_quest_header(q, team_size, state.leader_slot, leader_role, state.slot_to_name)

        self._inject_situational_notes(state)

        self._run_discussion(state)

        approved_team = None
        for attempt in range(MAX_VOTE_FAILURES):
            state.log_lines.append(f"\n[PROPOSAL {attempt + 1}] Leader: Slot {state.leader_slot}")
            print_proposal_header(attempt + 1, state.leader_slot, state.slot_to_role[state.leader_slot], state.slot_to_name)

            self._inject_situational_notes(state)
            team = self._get_proposal(state, team_size)
            votes, speeches = self._get_votes(state, team)

            approve_count = sum(1 for v in votes.values() if v == "APPROVE")
            result = "APPROVED" if approve_count > 2 else "REJECTED"

            record = VoteRecord(
                quest_num=q, proposal_num=attempt + 1,
                proposer_slot=state.leader_slot, proposed_team=team,
                votes=votes, speeches=speeches, result=result,
            )
            state.vote_history.append(record)

            state.log_lines.append("[VOTES]")
            for slot in range(5):
                state.log_lines.append(
                    f'  Slot {slot} ({state.slot_to_role[slot]}): {votes[slot]} — "{speeches[slot]}"'
                )
            state.log_lines.append(f"Vote result: {result} ({approve_count}/5 approve)")
            print_vote_result(result, approve_count)
            # Cheap deterministic rebuild — voting history shifted, so per-player
            # voting patterns (used in the running digest) change.
            self._refresh_running_digest(state)

            # Broadcast factual vote outcome as an event note to all agents
            approvers = [s for s, v in votes.items() if v == "APPROVE"]
            rejecters = [s for s, v in votes.items() if v == "REJECT"]
            leader_name = state.slot_to_name[state.leader_slot]
            team_names = [state.slot_to_name[s] for s in team]
            approver_names = [state.slot_to_name[s] for s in approvers]
            rejecter_names = [state.slot_to_name[s] for s in rejecters]
            self._broadcast_event_note(
                state,
                f"[EVENT] Q{q}P{attempt+1}: {leader_name}→{team_names} {result} | A:{approver_names} R:{rejecter_names}"
            )

            if result == "APPROVED":
                approved_team = team
                break

            print(f"\n  {DIM}[Reactions to rejected proposal...]{RESET}")
            self._run_rejection_discussion(state, team, record)

            state.leader_slot = (state.leader_slot + 1) % 5
            state.proposal_num += 1

        if approved_team is None:
            state.log_lines.append("5 proposals rejected — evil wins the entire game immediately.")
            state.mission_history.append(MissionRecord(quest_num=q, team=[], num_fails=0, result="FAIL_AUTO"))
            state.evil_wins = QUESTS_TO_WIN
            print_five_proposals_auto()
            self._broadcast_event_note(state, f"[EVENT] Q{q}: 5 proposals rejected — evil auto-wins the game. Score G{state.good_wins}/E{state.evil_wins}")
        else:
            self._run_mission(state, approved_team)

        print_score(state.good_wins, state.evil_wins)
        state.quest_num += 1
        state.leader_slot = (state.leader_slot + 1) % 5
        state.proposal_num = 1

    def _run_discussion(self, state: GameState):
        state.log_lines.append("\n[DISCUSSION]")
        print_discussion_header()
        order = list(range(5))
        random.shuffle(order)

        for slot in order:
            role = state.slot_to_role[slot]
            result = call_llm_json(
                self.llm,
                self._system(role, state),
                get_discussion_prompt(state, slot),
                call_label=f"discussion Q{state.quest_num} Slot{slot}",
                schema=DiscussionOutput,
            )
            log_llm_call(
                f"discussion Q{state.quest_num} Slot{slot}",
                self._system(role, state),
                get_discussion_prompt(state, slot),
                "",  # response not captured here
                result,
                game_id=state.game_id,
                phase="discussion",
                role=role,
                slot_id=slot,
            )
            statement = result.get("statement", "").strip() or "..."
            note = result.get("private_note", "")

            entry = DiscussionEntry(quest_num=state.quest_num, slot_id=slot, role=role, statement=statement)
            state.discussion_log.append(entry)
            name = state.slot_to_name[slot]
            state.log_lines.append(f'  {name} ({role}): "{statement}"')

            if note:
                self._append_note(state, slot, f"[Q{state.quest_num} Discussion] {note}")
                self._record_phase_memory(state, slot, "discussion", note, quest_num=state.quest_num)
            print_statement(slot, role, statement, state.slot_to_name)

    def _get_proposal(self, state: GameState, team_size: int) -> List[int]:
        leader = state.leader_slot
        role = state.slot_to_role[leader]

        analysis = self._run_analysis_pass(state, leader, f"choosing a {team_size}-person team to propose for Q{state.quest_num}", phase="proposal")
        if analysis:
            self._append_note(state, leader, f"[PRE-PROPOSAL ANALYSIS Q{state.quest_num}] {analysis}")

        last_hint = None
        for attempt in range(3):
            result = call_llm_json(
                self.llm,
                self._system(role, state),
                get_proposal_prompt(state, leader, team_size, retry_hint=last_hint),
                call_label=f"proposal Q{state.quest_num} Slot{leader}" + (f" (retry {attempt+1})" if attempt else ""),
                schema=ProposalOutput,
            )
            log_llm_call(
                f"proposal Q{state.quest_num} Slot{leader}",
                self._system(role, state),
                get_proposal_prompt(state, leader, team_size),
                "",
                result,
                game_id=state.game_id,
                phase="proposal",
                role=role,
                slot_id=leader,
            )
            if not result:
                continue

            raw_team = result.get("proposed_team", [])
            valid, unknown = [], []
            seen = set()
            for item in raw_team:
                if isinstance(item, str) and item in state.name_to_slot:
                    s = state.name_to_slot[item]
                elif isinstance(item, int) and 0 <= item < 5:
                    s = item
                else:
                    unknown.append(item)
                    continue
                if s in seen:
                    continue
                seen.add(s)
                valid.append(s)

            if len(valid) == team_size and not unknown:
                speech = result.get("speech", "").strip() or "This is my pick."
                note = result.get("private_note", "")
                team_names = [state.slot_to_name[s] for s in valid]
                leader_name = state.slot_to_name[leader]
                state.log_lines.append(f'  {leader_name} ({role}) proposes {team_names}: "{speech}"')
                if note:
                    self._append_note(state, leader, f"[Q{state.quest_num} Proposal] {note}")
                    self._record_phase_memory(state, leader, "proposal", note, quest_num=state.quest_num)
                print_proposal(leader, role, valid, speech, state.slot_to_name)
                return valid

            last_hint = (
                f"Your previous proposal had {len(valid)}/{team_size} recognized players"
                + (f" and these unrecognized entries: {unknown[:5]}" if unknown else "")
                + (f" with {len(raw_team) - len(valid) - len(unknown)} duplicate(s). "
                   f"Return EXACTLY {team_size} distinct valid player names from: {list(state.slot_to_name.values())}.")
            )

        # All retries failed. Deterministic safe fallback instead of random fill —
        # random could place an EVIL player on a Merlin-led team, sabotaging intent.
        valid = [leader]
        for s in range(5):
            if s != leader and len(valid) < team_size:
                valid.append(s)
        valid = valid[:team_size]
        print(f"    [PROPOSAL FALLBACK] Using leader + first-N team {valid} after 3 failed parses.")
        leader_name = state.slot_to_name[leader]
        team_names = [state.slot_to_name[s] for s in valid]
        state.log_lines.append(f'  {leader_name} ({role}) proposes {team_names} (fallback after parse failures)')
        return valid

    def _get_votes(self, state: GameState, team: List[int]) -> Tuple[Dict, Dict]:
        votes, speeches = {}, {}
        print_vote_header()
        team_names = [state.slot_to_name[s] for s in team]
        for slot in range(5):
            role = state.slot_to_role[slot]

            # Analysis pre-pass: deduction isolated from decision
            analysis = self._run_analysis_pass(state, slot, f"voting on proposed team {team_names}", phase="vote")
            if analysis:
                self._append_note(state, slot, f"[PRE-VOTE ANALYSIS Q{state.quest_num}] {analysis}")

            result = call_llm_json(
                self.llm,
                self._system(role, state),
                get_vote_prompt(state, slot, state.leader_slot, team),
                call_label=f"vote Q{state.quest_num} Slot{slot}",
                schema=VoteOutput,
            )
            log_llm_call(
                f"vote Q{state.quest_num} Slot{slot}",
                self._system(role, state),
                get_vote_prompt(state, slot, state.leader_slot, team),
                "",
                result,
                game_id=state.game_id,
                phase="vote",
                role=role,
                slot_id=slot,
            )

            vote_raw = result.get("vote") if isinstance(result, dict) else None
            if vote_raw not in ("APPROVE", "REJECT"):
                # Safe deterministic fallback rather than KeyError crash.
                # Reject is the lower-blast-radius choice for an unparseable vote:
                # rejecting at >=3 still needs majority, so this rarely auto-wins anything.
                vote = "REJECT" if state.leader_slot == slot else "APPROVE"
                print(f"    [VOTE FALLBACK] Slot{slot}: parse failed, defaulting to {vote}.")
            else:
                vote = vote_raw
            votes[slot] = vote
            speeches[slot] = (result.get("speech", "") if isinstance(result, dict) else "").strip() or "..."
            note = result.get("private_note", "") if isinstance(result, dict) else ""
            if note:
                self._append_note(state, slot, f"[Q{state.quest_num} Vote] {note}")
                self._record_phase_memory(state, slot, "vote", note, quest_num=state.quest_num)
            print_vote(slot, role, vote, speeches[slot], state.slot_to_name)
        return votes, speeches

    def _run_rejection_discussion(self, state: GameState, rejected_team: list, vote_record):
        state.log_lines.append("\n[REJECTION REACTION]")
        order = list(range(5))
        random.shuffle(order)
        for slot in order:
            role = state.slot_to_role[slot]
            result = call_llm_json(
                self.llm,
                self._system(role, state),
                get_rejection_discussion_prompt(state, slot, rejected_team, vote_record),
                call_label=f"rejection-react Q{state.quest_num} Slot{slot}",
                schema=RejectionReactionOutput,
            )
            log_llm_call(
                f"rejection-react Q{state.quest_num} Slot{slot}",
                self._system(role, state),
                get_rejection_discussion_prompt(state, slot, rejected_team, vote_record),
                "",
                result,
                game_id=state.game_id,
                phase="rejection",
                role=role,
                slot_id=slot,
            )
            statement = result.get("statement", "").strip() or "..."
            note = result.get("private_note", "")
            entry = DiscussionEntry(quest_num=state.quest_num, slot_id=slot, role=role, statement=statement)
            state.discussion_log.append(entry)
            name = state.slot_to_name[slot]
            state.log_lines.append(f'  {name}: "{statement}"')
            if note:
                self._append_note(state, slot, f"[Q{state.quest_num} Rejection] {note}")
                self._record_phase_memory(state, slot, "discussion", note, quest_num=state.quest_num)
            print_statement(slot, role, statement, state.slot_to_name)

    def _run_mission(self, state: GameState, team: List[int]):
        state.log_lines.append(f"\n[MISSION] Team: {team}")
        print_mission_header(team, state.slot_to_name)
        cards = []
        for slot in team:
            role = state.slot_to_role[slot]
            if not ROLES_CONFIG[role]["can_fail_mission"]:
                card = "SUCCESS"
                # Good always plays SUCCESS — no LLM call; just generate a concise internal note
                team_names = [state.slot_to_name[s] for s in team]
                internal = f"Good always plays SUCCESS. Team: {team_names}"
                self._append_note(state, slot, f"[Q{state.quest_num} Mission] {internal}")
                self._record_phase_memory(state, slot, "mission", f"Good — no choice: SUCCESS on team {team_names}", quest_num=state.quest_num)
                cards.append(card)
                state.log_lines.append(f'  [PRIVATE] Slot {slot} ({role}) played {card}: "{internal}"')
                print_mission_private(slot, role, card, internal, state.slot_to_name)
            else:
                result = call_llm_json(
                    self.llm,
                    self._system(role, state),
                    get_mission_prompt(state, slot, role, team),
                    call_label=f"mission Q{state.quest_num} Slot{slot}",
                    schema=MissionOutput,
                )
                log_llm_call(
                    f"mission Q{state.quest_num} Slot{slot}",
                    self._system(role, state),
                    get_mission_prompt(state, slot, role, team),
                    "",
                    result,
                    game_id=state.game_id,
                    phase="mission",
                    role=role,
                    slot_id=slot,
                )
                raw_card = result.get("card", "SUCCESS").strip().upper()
                if raw_card == "FAIL":
                    card = "FAIL"
                else:
                    card = "SUCCESS"
                internal = result.get("internal_note", "").strip() or "..."
                cards.append(card)
                state.log_lines.append(f'  [PRIVATE] Slot {slot} ({role}) played {card}: "{internal}"')
                print_mission_private(slot, role, card, internal, state.slot_to_name)
                # Evil only — their interpretation is the cross-quest memory that matters.
                self._record_phase_memory(state, slot, "mission", internal, quest_num=state.quest_num)

        num_fails = cards.count("FAIL")
        mission_result = "FAIL" if num_fails > 0 else "SUCCESS"
        state.log_lines.append(f"Cards: {num_fails} FAIL(s) — Quest result: {mission_result}")
        print_mission_result(mission_result, num_fails)

        state.mission_history.append(
            MissionRecord(quest_num=state.quest_num, team=team, num_fails=num_fails, result=mission_result)
        )
        if mission_result == "SUCCESS":
            state.good_wins += 1
        else:
            state.evil_wins += 1

        # Broadcast factual mission result to all agents
        team_names = [state.slot_to_name[s] for s in team]
        self._broadcast_event_note(
            state,
            f"[EVENT] Q{state.quest_num} MISSION: team={team_names} → {mission_result} ({num_fails} fail(s)). Score G{state.good_wins}/E{state.evil_wins}"
        )

        # Mission outcome is the single highest-information transition in the
        # game: it can mathematically confirm new evil players and changes who
        # is suspicious. Refresh every agent's digest deterministically here
        # so the next phase prompt reads the new public evidence.
        for s in range(5):
            self._prune_phase_memory(state, s)
        self._refresh_running_digest(state)

    def _run_assassin_phase(self, state: GameState):
        assassin_slot = state.role_to_slot["Assassin"]
        merlin_slot = state.role_to_slot["Merlin"]
        morgana_slot = state.role_to_slot["Morgana"]
        candidate_names = [state.slot_to_name[s] for s in range(5) if s not in (assassin_slot, morgana_slot)]
        state.log_lines.append("\n--- ASSASSIN'S CHOICE ---")
        print_assassin_phase(assassin_slot, "Assassin", state.slot_to_name)

        guess = -1
        result = None
        reasoning = "..."
        for attempt in range(2):
            result = call_llm_json(
                self.llm,
                self._system("Assassin", state),
                get_assassin_prompt(state, assassin_slot),
                call_label="assassin guess" + (" (retry)" if attempt else ""),
                schema=AssassinOutput,
            )
            log_llm_call(
                "assassin guess",
                self._system("Assassin", state),
                get_assassin_prompt(state, assassin_slot),
                "",
                result,
                game_id=state.game_id,
                phase="assassin",
                role="Assassin",
                slot_id=assassin_slot,
            )
            guess_name = (result.get("guess_name", "") or "").strip() if isinstance(result, dict) else ""
            reasoning = (result.get("reasoning", "") or "").strip() or "..."
            # Strict name lookup; no substring matching.
            guess = state.name_to_slot.get(guess_name, -1)
            if guess in (assassin_slot, morgana_slot):
                guess = -1  # never points at the assassin themselves or their ally
            if guess >= 0:
                break
            if attempt == 0:
                print(f"    [ASSASSIN RETRY] guess_name {guess_name!r} not in candidates {candidate_names}; retrying.")

        state.assassin_guess_slot = guess
        state.assassin_correct = guess == merlin_slot

        assassin_name = state.slot_to_name[assassin_slot]
        merlin_name = state.slot_to_name[merlin_slot]
        guess_display = state.slot_to_name.get(guess, "unknown")
        state.log_lines.append(f"{assassin_name} (Assassin) guesses {guess_display} is Merlin.")
        state.log_lines.append(f'Reasoning: "{reasoning}"')
        state.log_lines.append(f"Merlin was {merlin_name}. Correct: {state.assassin_correct}")
        print_assassin_guess(guess, reasoning, merlin_slot, state.assassin_correct, state.slot_to_name)

    def _run_analysis_pass(self, state: GameState, slot: int, context_hint: str, phase: str = "vote") -> str:
        """Isolated deduction call at low temperature before an action decision.
        Result is injected into agent notes so it appears in the next prompt's context.
        `phase` = which decision phase this analysis precedes ('proposal' or 'vote')."""
        role = state.slot_to_role[slot]
        result = call_llm_json(
            self.analysis_llm,
            self._system(role, state),
            get_analysis_prompt(state, slot, context_hint, phase),
            call_label=f"analysis Q{state.quest_num} Slot{slot}",
        )
        if not result:
            return ""
        parts = []
        if result.get("certain_facts"):
            parts.append(f"CERTAIN: {result['certain_facts']}")
        if result.get("suspicion_model"):
            parts.append(f"READS: {result['suspicion_model']}")
        if result.get("contradiction"):
            parts.append(f"CONTRADICTION DETECTED: {result['contradiction']}")
        if result.get("priority"):
            parts.append(f"THIS ROUND PRIORITY: {result['priority']}")
        return "\n".join(parts)

    def _inject_situational_notes(self, state: GameState):
        """Inject factual consequence reminders into agent notes before decisions.
        No decisions are made here — only information is surfaced."""

        proposal_num = len([v for v in state.vote_history if v.quest_num == state.quest_num]) + 1

        for slot in range(5):
            role = state.slot_to_role[slot]
            faction = ROLES_CONFIG[role]["faction"]

            if proposal_num == 5 and faction == "good":
                self._append_note(state, slot,
                    f"[SITUATION Q{state.quest_num}P5] This is proposal 5/5. "
                    "If the majority rejects it, evil wins the entire game immediately — regardless of team composition."
                )

            # Merlin fingerprint detection — inform, do not direct.
            if role == "Merlin":
                prior_merlin_teams = [
                    frozenset(v.proposed_team)
                    for v in state.vote_history
                    if v.proposer_slot == slot
                ]
                if len(prior_merlin_teams) >= 2:
                    counts = Counter(prior_merlin_teams)
                    prior_summaries = [
                        [state.slot_to_name[s] for s in team] for team, _ in counts.items()
                    ]
                    if prior_summaries:
                        self._append_note(state, slot,
                            f"[MERLIN FINGERPRINT WARNING] You have previously proposed these "
                            f"team(s): {prior_summaries}. Repeating a composition is one signal "
                            "the Assassin tracks — but so is wildly varying teams. Use your judgment."
                        )