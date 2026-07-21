import os

from config import (
    CONSOLIDATION_EVERY,
    EARLY_CONSOLIDATION_GAMES,
    CHECKPOINT_EVERY,
    MAX_GAMES,
    LESSONS_DIR,
    LOGS_DIR,
    CHECKPOINTS_DIR,
    STATE_FILE,
)
from game.engine import GameEngine
from agents.llm_client import create_llm, create_reflection_llm
from memory.manager import ensure_dirs, consolidate_lessons, consolidate_evil_coord, consolidate_good_coord
from reflection.reflector import run_reflection
from evaluation.evaluator import (
    load_metrics,
    save_metrics,
    record_game,
    snapshot_lessons,
    save_checkpoint,
    check_stopping_criteria,
)
from storage.logger import save_game_log, save_run_state, load_run_state
from storage.printer import (
    print_reflection_header,
    print_reflection_role,
    print_consolidation,
    print_checkpoint,
    print_stats,
    print_stop,
    BOLD, YELLOW, RESET, DIM,
)
from game.roles import ALL_ROLES
from memory.manager import should_consolidate_now, get_lesson_path, EVIL_COORD_FILE, GOOD_COORD_FILE
import glob

def run():
    for d in [LESSONS_DIR, LOGS_DIR, CHECKPOINTS_DIR]:
        os.makedirs(d, exist_ok=True)
    ensure_dirs()

    llm = create_llm()
    reflection_llm = create_reflection_llm()
    engine = GameEngine(llm, reflection_llm)
    metrics = load_metrics()
    start_game = load_run_state()

    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}{YELLOW}  AVALON RL EXPERIMENT{RESET}")
    print(f"{DIM}  Resuming from game {start_game}{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")

    if start_game <= 1:
        for role in ALL_ROLES:
            p = get_lesson_path(role)
            if os.path.exists(p):
                os.remove(p)
        for f in [EVIL_COORD_FILE, GOOD_COORD_FILE]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

    for game_id in range(start_game, MAX_GAMES + 1):
        state = engine.run_game(game_id)

        save_game_log(state)
        save_run_state(game_id)
        metrics = record_game(state, metrics)

        print_reflection_header()
        deltas = run_reflection(state, reflection_llm)
        for role, n in (deltas or {}).items():
            if role.startswith("_"):
                continue
            total = n["tentative"] + n["confirmed"] + n["deprecated"] if isinstance(n, dict) else n
            print_reflection_role(role, total)

        snapshot_lessons(metrics, game_id)
        save_metrics(metrics)

        # On-demand consolidation for roles that hit tentative cap
        roles_needed = (deltas or {}).get("_consolidate_needed", set())
        consolidated_now = False
        if roles_needed:
            print(f"    [CONSOLIDATE ON-DEMAND] Roles at tentative cap: {roles_needed}")
            for role in ALL_ROLES:
                if role in roles_needed:
                    consolidate_lessons(role, llm, game_id)
            if "evil_coord" in roles_needed:
                consolidate_evil_coord(llm, game_id)
            if "good_coord" in roles_needed:
                consolidate_good_coord(llm, game_id)
            snapshot_lessons(metrics, game_id)
            save_metrics(metrics)
            consolidated_now = True

        if game_id % CHECKPOINT_EVERY == 0:
            save_checkpoint(game_id)
            print_checkpoint(game_id)

        should_consolidate = (
            game_id in EARLY_CONSOLIDATION_GAMES or
            (game_id > max(EARLY_CONSOLIDATION_GAMES, default=0) and game_id % CONSOLIDATION_EVERY == 0) or
            should_consolidate_now()
        )
        if should_consolidate and not consolidated_now:
            print_consolidation()
            for role in ALL_ROLES:
                consolidate_lessons(role, llm, game_id)
            consolidate_evil_coord(llm, game_id)
            consolidate_good_coord(llm, game_id)

        print_stats(metrics["good_wins"], metrics["evil_wins"])

        stop_reason = check_stopping_criteria(metrics, game_id)
        if stop_reason:
            print_stop(stop_reason)
            save_checkpoint(game_id)
            break

    print(f"\n{BOLD}Experiment complete.{RESET}\n")


if __name__ == "__main__":
    run()