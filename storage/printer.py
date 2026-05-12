RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"
MAGENTA = "\033[95m"
BLUE    = "\033[94m"

ROLE_COLORS = {
    "Merlin":        BLUE,
    "Percival":      CYAN,
    "LoyalServant":  GREEN,
    "Assassin":      RED,
    "Morgana":       MAGENTA,
}

def _tag(name: str, role: str) -> str:
    color = ROLE_COLORS.get(role, WHITE)
    return f"{color}{BOLD}[{name}]{RESET}"

def print_game_header(game_id: int, slot_to_role: dict, slot_to_name: dict):
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}{YELLOW}  ♛  GAME {game_id}  ♛{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")
    print(f"\n{DIM}Players:{RESET}")
    for slot, role in slot_to_role.items():
        name = slot_to_name.get(slot, f"Slot{slot}")
        color = ROLE_COLORS.get(role, WHITE)
        faction = f"{GREEN}▲ good{RESET}" if role in ("Merlin", "Percival", "LoyalServant") else f"{RED}▼ evil{RESET}"
        print(f"  {color}{BOLD}{name:<10} {role:<16}{RESET}  {faction}")
    print()

def print_quest_header(quest_num: int, team_size: int, leader_slot: int, leader_role: str, slot_to_name: dict = None):
    color = ROLE_COLORS.get(leader_role, WHITE)
    leader_name = slot_to_name.get(leader_slot, f"Slot{leader_slot}") if slot_to_name else f"Slot{leader_slot}"
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  QUEST {quest_num}  {RESET}{DIM}(team size: {team_size}){RESET}")
    print(f"  Leader → {color}{BOLD}{leader_name} · {leader_role}{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")

def print_discussion_header():
    print(f"\n  {YELLOW}{BOLD}📣 DISCUSSION{RESET}")

def print_statement(slot: int, role: str, statement: str, slot_to_name: dict = None):
    name = slot_to_name.get(slot, f"Slot{slot}") if slot_to_name else f"Slot{slot}"
    tag = _tag(name, role)
    print(f"  {tag}")
    print(f"    {WHITE}\"{statement}\"{RESET}\n")

def print_proposal_header(attempt: int, leader_slot: int, leader_role: str, slot_to_name: dict = None):
    color = ROLE_COLORS.get(leader_role, WHITE)
    name = slot_to_name.get(leader_slot, f"Slot{leader_slot}") if slot_to_name else f"Slot{leader_slot}"
    print(f"\n  {YELLOW}{BOLD}📋 PROPOSAL {attempt}{RESET}  {DIM}Leader: {color}{name} · {leader_role}{RESET}")

def print_proposal(leader_slot: int, leader_role: str, team: list, speech: str, slot_to_name: dict = None):
    color = ROLE_COLORS.get(leader_role, WHITE)
    if slot_to_name:
        team_str = ", ".join(slot_to_name.get(s, f"Slot{s}") for s in team)
    else:
        team_str = ", ".join(str(s) for s in team)
    print(f"  {color}{BOLD}→ Proposed team: [{team_str}]{RESET}")
    print(f"    {WHITE}\"{speech}\"{RESET}\n")

def print_vote_header():
    print(f"  {YELLOW}{BOLD}🗳  VOTES{RESET}")

def print_vote(slot: int, role: str, vote: str, speech: str, slot_to_name: dict = None):
    name = slot_to_name.get(slot, f"Slot{slot}") if slot_to_name else f"Slot{slot}"
    tag = _tag(name, role)
    vote_display = f"{GREEN}{BOLD}✔ APPROVE{RESET}" if vote == "APPROVE" else f"{RED}{BOLD}✘ REJECT{RESET}"
    print(f"  {tag}  {vote_display}")
    print(f"    {DIM}\"{speech}\"{RESET}\n")

def print_vote_result(result: str, approve_count: int):
    if result == "APPROVED":
        print(f"  {GREEN}{BOLD}✔ APPROVED  ({approve_count}/5){RESET}")
    else:
        print(f"  {RED}{BOLD}✘ REJECTED  ({approve_count}/5){RESET}")

def print_mission_header(team: list, slot_to_name: dict = None):
    if slot_to_name:
        team_str = ", ".join(slot_to_name.get(s, f"Slot{s}") for s in team)
    else:
        team_str = ", ".join(str(s) for s in team)
    print(f"\n  {YELLOW}{BOLD}⚔  MISSION  [{team_str}]{RESET}")

def print_mission_private(slot: int, role: str, card: str, note: str, slot_to_name: dict = None):
    color = ROLE_COLORS.get(role, WHITE)
    name = slot_to_name.get(slot, f"Slot{slot}") if slot_to_name else f"Slot{slot}"
    card_str = f"{RED}{BOLD}FAIL{RESET}" if card == "FAIL" else f"{GREEN}{BOLD}SUCCESS{RESET}"
    print(f"  {color}{DIM}[PRIVATE] {name} ({role}) played {RESET}{card_str}")
    print(f"    {DIM}\"{note}\"{RESET}")

def print_mission_result(result: str, num_fails: int):
    if result == "SUCCESS":
        print(f"\n  {GREEN}{BOLD}★ QUEST SUCCESS  ({num_fails} fail cards){RESET}")
    else:
        print(f"\n  {RED}{BOLD}✖ QUEST FAILED  ({num_fails} fail card(s)){RESET}")

def print_score(good_wins: int, evil_wins: int):
    g = f"{GREEN}{BOLD}{good_wins}{RESET}"
    e = f"{RED}{BOLD}{evil_wins}{RESET}"
    print(f"\n  Score → Good {g}  ·  Evil {e}  (first to 3 wins)\n")

def print_assassin_phase(assassin_slot: int, assassin_role: str, slot_to_name: dict = None):
    name = slot_to_name.get(assassin_slot, f"Slot{assassin_slot}") if slot_to_name else f"Slot{assassin_slot}"
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{RED}{BOLD}  🗡  ASSASSIN'S MOMENT{RESET}")
    print(f"  Good has won 3 quests — but the Assassin gets one final strike.")
    print(f"  {_tag(name, assassin_role)} must identify Merlin now.")
    print(f"{BOLD}{'─'*60}{RESET}\n")

def print_assassin_guess(guess_slot: int, reasoning: str, merlin_slot: int, correct: bool, slot_to_name: dict = None):
    guess_name = slot_to_name.get(guess_slot, f"Slot{guess_slot}") if slot_to_name else f"Slot{guess_slot}"
    merlin_name = slot_to_name.get(merlin_slot, f"Slot{merlin_slot}") if slot_to_name else f"Slot{merlin_slot}"
    print(f"  Assassin points at {WHITE}{BOLD}{guess_name}{RESET}")
    print(f"  {DIM}\"{reasoning}\"{RESET}\n")
    if correct:
        print(f"  {RED}{BOLD}💀 Correct. {guess_name} was Merlin. EVIL WINS.{RESET}")
    else:
        print(f"  {GREEN}{BOLD}✓ Wrong. Merlin was {merlin_name}. GOOD WINS.{RESET}")

def print_outcome(outcome: str):
    print(f"\n{BOLD}{'═'*60}{RESET}")
    if outcome == "GOOD_WINS":
        print(f"{GREEN}{BOLD}  ★  GOOD WINS  ★{RESET}")
    else:
        print(f"{RED}{BOLD}  ✖  EVIL WINS  ✖{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}\n")

def print_reflection_header():
    print(f"\n{DIM}{'·'*60}{RESET}")
    print(f"{DIM}  Post-game reflection...{RESET}")

def print_reflection_role(role: str, n_added: int):
    color = ROLE_COLORS.get(role, WHITE)
    print(f"  {color}{role}{RESET} {DIM}→ {n_added} lesson delta(s){RESET}")

def print_consolidation():
    print(f"  {DIM}Consolidating lessons...{RESET}")

def print_checkpoint(game_id: int):
    print(f"  {DIM}Checkpoint saved at game {game_id}{RESET}")

def print_stats(good: int, evil: int):
    total = good + evil
    if total == 0:
        return
    print(f"\n  {DIM}Running totals → Good {good}/{total} ({good/total:.0%})  ·  Evil {evil}/{total} ({evil/total:.0%}){RESET}")

def print_stop(reason: str):
    print(f"\n{YELLOW}{BOLD}  ⏹  STOPPING: {reason}{RESET}\n")

def print_five_proposals_auto():
    print(f"\n  {RED}{BOLD}⚠ 5 proposals rejected — evil wins this quest automatically.{RESET}")