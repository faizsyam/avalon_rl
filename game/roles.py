ROLES_CONFIG = {
    "Merlin": {
        "faction": "good",
        "win_condition": "Complete 3 quests successfully. Then prevent the Assassin from identifying you.",
        "backstory": (
            "You are Merlin — the secret guardian of the good side. You know which two players "
            "are evil (Assassin and Morgana), but you cannot reveal this directly or the Assassin "
            "will identify and kill you at game end. Guide the good side subtly. Protect carefully. "
            "Every word you say is a clue someone might use to unmask you."
        ),
        "special_info_template": "The evil players (Assassin and Morgana) are: {evil_names}. You cannot tell which role each holds.",
        "can_fail_mission": False,
        "dimensions": [
            "identity_concealment",
            "team_selection_guidance",
            "suspicion_communication",
            "handling_accusations",
            "late_game_behavior",
            "communication_style_and_tone",
            "mistakes_to_avoid",
        ],
    },
    "Percival": {
        "faction": "good",
        "win_condition": "Complete 3 quests successfully.",
        "backstory": (
            "You are Percival — a loyal knight who can see two players who appear as Merlin. "
            "One is the real Merlin; the other is Morgana deceiving you. You must protect the real Merlin "
            "without exposing them, and figure out which one is genuine through the flow of the game."
        ),
        "special_info_template": "These two players both appear as Merlin to you: {merlin_candidate_names}. One is real Merlin; one is Morgana in disguise.",
        "can_fail_mission": False,
        "dimensions": [
            "merlin_identification_strategy",
            "protecting_merlin",
            "team_selection_guidance",
            "suspicion_management",
            "communication_style_and_tone",
            "mistakes_to_avoid",
        ],
    },
    "LoyalServant": {
        "faction": "good",
        "win_condition": "Complete 3 quests successfully.",
        "backstory": (
            "You are a Loyal Servant of Arthur. You have no special knowledge — no hidden sight, no secret allies. "
            "You must read the room, trust your gut, build alliances, and deduce who is lying through "
            "observation and reasoning alone. You are the everyman — and the hardest role to play well."
        ),
        "special_info_template": "You have no special knowledge. Everything you learn must come from watching people carefully.",
        "can_fail_mission": False,
        "dimensions": [
            "reading_player_behavior",
            "team_selection_guidance",
            "vote_strategy",
            "building_trust",
            "communication_style_and_tone",
            "mistakes_to_avoid",
        ],
    },
    "Assassin": {
        "faction": "evil",
        "win_condition": "Fail 3 quests. OR: if good completes 3 quests, correctly identify and assassinate Merlin.",
        "backstory": (
            "You are the Assassin — calculating, patient, and lethal. You know your evil ally Morgana. "
            "Sabotage missions covertly, appear trustworthy, and closely study every player to identify Merlin "
            "for the final assassination. If good wins 3 quests, one correct guess and evil wins everything."
        ),
        "special_info_template": "Your evil ally (Morgana) is: {evil_ally_name}. Coordinate subtly — you must not expose each other.",
        "can_fail_mission": True,
        "dimensions": [
            "merlin_identification",
            "mission_sabotage_timing",
            "cover_and_deception",
            "vote_manipulation",
            "communication_style_and_tone",
            "evil_coordination",
            "mistakes_to_avoid",
        ],
    },
    "Morgana": {
        "faction": "evil",
        "win_condition": "Fail 3 quests.",
        "backstory": (
            "You are Morgana — a master of deception who appears as Merlin to Percival. "
            "You know your evil ally Assassin. Impersonate Merlin convincingly, sow confusion, "
            "misdirect Percival, sabotage at the right moments, and never let your mask slip."
        ),
        "special_info_template": "Your evil ally (Assassin) is: {evil_ally_name}. You appear as Merlin to Percival — exploit this.",
        "can_fail_mission": True,
        "dimensions": [
            "merlin_impersonation",
            "confusion_tactics",
            "mission_sabotage_timing",
            "cover_and_deception",
            "communication_style_and_tone",
            "evil_coordination",
            "mistakes_to_avoid",
        ],
    },
}

EVIL_COORD_DIMENSIONS = [
    "covering_for_each_other",
    "vote_synchronization",
    "mission_sabotage_timing",
    "blame_deflection",
]

GOOD_COORD_DIMENSIONS = [
    "merlin_signal_protection",
    "evil_identification_coordination",
    "team_composition_alignment",
    "vote_coordination",
    "merlin_concealment_support",
]

ALL_ROLES = list(ROLES_CONFIG.keys())