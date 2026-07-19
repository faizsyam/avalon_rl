from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class VoteRecord:
    quest_num: int
    proposal_num: int
    proposer_slot: int
    proposed_team: List[int]
    votes: Dict[int, str]
    speeches: Dict[int, str]
    result: str


@dataclass
class MissionRecord:
    quest_num: int
    team: List[int]
    num_fails: int
    result: str


@dataclass
class DiscussionEntry:
    quest_num: int
    slot_id: int
    role: str
    statement: str


@dataclass
class GameState:
    game_id: int
    slot_to_role: Dict[int, str] = field(default_factory=dict)
    role_to_slot: Dict[str, int] = field(default_factory=dict)
    slot_to_faction: Dict[int, str] = field(default_factory=dict)

    quest_num: int = 1
    proposal_num: int = 1
    leader_slot: int = 0

    good_wins: int = 0
    evil_wins: int = 0

    vote_history: List[VoteRecord] = field(default_factory=list)
    mission_history: List[MissionRecord] = field(default_factory=list)
    discussion_log: List[DiscussionEntry] = field(default_factory=list)

    # Per-slot accumulated private notes from within-game reasoning
    # Key: slot_id (int), Value: list of note strings (one per turn)
    agent_notes: Dict[int, List[str]] = field(default_factory=dict)

    # Per-agent, per-phase TIGHT memory layer used for in-game prompting.
    # Key: slot_id (int), Value: {phase_name: [bulletin, ...]} where each
    # bulletin is a single line (<= 140 chars) carrying the agent's own
    # interpretation. Distinct from `agent_notes` — `agent_notes` keeps the
    # full verbose log for post-game reflection; `agent_phase_memory` is the
    # compressed cross-phase memory injected into phase prompts.
    agent_phase_memory: Dict[int, Dict[str, List[str]]] = field(default_factory=dict)

    # Per-agent deterministic game-state-derived digest. Recomputed by the
    # engine after every mission and vote outcome (no LLM), so reads always
    # reflect the latest public evidence. Role-templated on construction:
    # good agents see evil-suspicion lines, evil agents see Merlin-candidate
    # lines. Distinct from the LLM-written `agent_phase_memory`.
    agent_running_digest: Dict[int, List[str]] = field(default_factory=dict)

    outcome: Optional[str] = None
    assassin_guess_slot: Optional[int] = None
    assassin_correct: Optional[bool] = None

    slot_to_name: Dict[int, str] = field(default_factory=dict)
    name_to_slot: Dict[str, int] = field(default_factory=dict)

    log_lines: List[str] = field(default_factory=list)


HUMAN_NAMES = [
    "Alice", "Ben", "Clara", "David", "Elena",
    "Felix", "Grace", "Henry", "Iris", "James",
    "Kara", "Leo", "Maya", "Noah", "Olivia",
    "Peter", "Quinn", "Rosa", "Sam", "Tara",
]