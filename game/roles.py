# Per-role reflection is organized by GAME PHASE — a lesson belongs to exactly one
# phase and is only surfaced to the agent at that phase. Assassin additionally has
# the `assassin` phase (the final Merlin guess); other roles have the 4 phase buckets.

_GAME_PHASES = ["discussion", "proposal", "vote", "mission"]

ROLES_CONFIG = {
    "Merlin": {
        "faction": "good",
        "can_fail_mission": False,
        "special_info_template": "You know the evil players are: {evil_names}.",
        "phases": list(_GAME_PHASES),
    },
    "Percival": {
        "faction": "good",
        "can_fail_mission": False,
        "special_info_template": "These two players appear as Merlin to you: {merlin_candidate_names}. One is real Merlin, one is Morgana.",
        "phases": list(_GAME_PHASES),
    },
    "LoyalServant": {
        "faction": "good",
        "can_fail_mission": False,
        "special_info_template": "You have no special information. Reason from observable evidence only.",
        "phases": list(_GAME_PHASES),
    },
    "Assassin": {
        "faction": "evil",
        "can_fail_mission": True,
        "special_info_template": "Your evil ally is: {evil_ally_name}.",
        "phases": ["discussion", "proposal", "vote", "mission", "assassin"],
    },
    "Morgana": {
        "faction": "evil",
        "can_fail_mission": True,
        "special_info_template": "Your evil ally is: {evil_ally_name}.",
        "phases": list(_GAME_PHASES),
    },
}

EVIL_COORD_PHASES = list(_GAME_PHASES)
GOOD_COORD_PHASES = list(_GAME_PHASES)

PHASE_DESCRIPTIONS = {
    "discussion": (
        "How to read, signal, accuse, and deflect in PUBLIC statements without exposing "
        "your role — what you say (or refuse to say) to build reads, steer the table, or "
        "protect your identity. Covers first-to-speak framing, response to accusations, "
        "and reaction to rejected proposals."
    ),
    "proposal": (
        "Composing or evaluating a leader's TEAM PROPOSAL — who to include/exclude and how "
        "to frame the supporting speech. Covers self-inclusion, testing suspects, avoiding "
        "identifiable patterns, and the leader's credibility-credibility tradeoff."
    ),
    "vote": (
        "Weighing a proposed team and choosing APPROVE or REJECT given the score, the "
        "proposal number (5th = must-pass for good), your private reads, and the consequence "
        "of passing/failing at this score. Covers how public vote reasoning reveals alignment."
    ),
    "mission": (
        "Playing SUCCESS or FAIL on a quest team — for evil, when failing is worth the "
        "exposure risk vs preserving cover, double-fail math, and reading the fail count. "
        "For good, what a given fail count proves about who was on the team."
    ),
    "assassin": (
        "Identifying Merlin from observable behavioral tells for the final guess — which "
        "statements, votes, proposal patterns, or objections could only be explained by "
        "hidden knowledge of evil. Assassin-only phase."
    ),
}

ALL_ROLES = list(ROLES_CONFIG.keys())
