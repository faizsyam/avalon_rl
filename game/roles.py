# Replace dimensions for ALL roles with these 3 universal dimensions:
# "win_loss_cause", "action_decisions", "behavioral_strategy"

ROLES_CONFIG = {
    "Merlin": {
        "faction": "good",
        "can_fail_mission": False,
        "special_info_template": "You know the evil players are: {evil_names}.",
        "dimensions": ["win_loss_cause", "action_decisions", "behavioral_strategy"],
    },
    "Percival": {
        "faction": "good",
        "can_fail_mission": False,
        "special_info_template": "These two players appear as Merlin to you: {merlin_candidate_names}. One is real Merlin, one is Morgana.",
        "dimensions": ["win_loss_cause", "action_decisions", "behavioral_strategy"],
    },
    "LoyalServant": {
        "faction": "good",
        "can_fail_mission": False,
        "special_info_template": "You have no special information. Reason from observable evidence only.",
        "dimensions": ["win_loss_cause", "action_decisions", "behavioral_strategy"],
    },
    "Assassin": {
        "faction": "evil",
        "can_fail_mission": True,
        "special_info_template": "Your evil ally is: {evil_ally_name}.",
        "dimensions": ["win_loss_cause", "action_decisions", "behavioral_strategy"],
    },
    "Morgana": {
        "faction": "evil",
        "can_fail_mission": True,
        "special_info_template": "Your evil ally is: {evil_ally_name}.",
        "dimensions": ["win_loss_cause", "action_decisions", "behavioral_strategy"],
    },
}

EVIL_COORD_DIMENSIONS = ["coordination_dynamics"]
GOOD_COORD_DIMENSIONS = ["coordination_dynamics"]

DIMENSION_DESCRIPTIONS = {
    "win_loss_cause": (
        "Root cause: the single most important reason your faction won or lost. "
        "Focus on the decision, structural failure, or information gap that was decisive."
    ),
    "action_decisions": (
        "Specific non-language actions: votes cast, teams proposed or rejected, "
        "mission cards played, and whether those decisions were correct given available information."
    ),
    "behavioral_strategy": (
        "Language, social, and behavioral strategies: how you framed arguments, "
        "built or undermined trust, deflected suspicion, or revealed/concealed your role through tone and word choice."
    ),
    "coordination_dynamics": (
        "Player interaction and coordination: how players on the same faction "
        "implicitly or explicitly aligned their decisions, and how that coordination "
        "helped or hurt the faction's outcome."
    ),
}

ALL_ROLES = list(ROLES_CONFIG.keys())