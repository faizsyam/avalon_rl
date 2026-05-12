import json
import os
import shutil
from typing import Optional

from config import METRICS_FILE, STOPPING, CHECKPOINTS_DIR, EVIL_COORD_FILE
from game.roles import ALL_ROLES
from memory.manager import get_lesson_path, load_lessons


def load_metrics() -> dict:
    if not os.path.exists(METRICS_FILE):
        return {
            "games": [],
            "good_wins": 0,
            "evil_wins": 0,
            "assassin_attempts": 0,
            "assassin_correct": 0,
            "lesson_snapshots": {role: [] for role in ALL_ROLES},
        }
    with open(METRICS_FILE, "r") as f:
        return json.load(f)


def save_metrics(metrics: dict):
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    with open(METRICS_FILE, "w") as f:
        json.dump(metrics, f, indent=2)


def record_game(state, metrics: dict) -> dict:
    good_won = state.outcome == "GOOD_WINS"
    metrics["games"].append({
        "game_id": state.game_id,
        "outcome": state.outcome,
        "good_quests": state.good_wins,
        "evil_quests": state.evil_wins,
        "assassin_correct": state.assassin_correct,
        "slot_to_role": state.slot_to_role,
    })
    if good_won:
        metrics["good_wins"] += 1
    else:
        metrics["evil_wins"] += 1
    if state.assassin_correct is not None:
        metrics["assassin_attempts"] += 1
        if state.assassin_correct:
            metrics["assassin_correct"] += 1
    return metrics


def snapshot_lessons(metrics: dict, game_id: int):
    for role in ALL_ROLES:
        content = load_lessons(role)
        snapshots = metrics["lesson_snapshots"].setdefault(role, [])
        snapshots.append(content)
        metrics["lesson_snapshots"][role] = snapshots[-20:]


def save_checkpoint(game_id: int):
    dest = os.path.join(CHECKPOINTS_DIR, f"checkpoint_g{game_id:03d}")
    os.makedirs(dest, exist_ok=True)
    for role in ALL_ROLES:
        src = get_lesson_path(role)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(dest, f"{role.lower()}.txt"))
    if os.path.exists(EVIL_COORD_FILE):
        shutil.copy(EVIL_COORD_FILE, os.path.join(dest, "evil_coordination.txt"))
    print(f"  Checkpoint saved → {dest}")


def _rolling_win_rate(metrics: dict, window: int) -> float:
    games = metrics["games"][-window:]
    if not games:
        return 0.5
    return sum(1 for g in games if g["outcome"] == "GOOD_WINS") / len(games)


def _lesson_stability(metrics: dict, role: str, window: int) -> float:
    snaps = metrics.get("lesson_snapshots", {}).get(role, [])
    recent = snaps[-window:]
    if len(recent) < 2:
        return 0.0
    a = set(recent[-2].split("\n"))
    b = set(recent[-1].split("\n"))
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def check_stopping_criteria(metrics: dict, game_id: int) -> Optional[str]:
    total = len(metrics["games"])
    if total < 30:
        return None

    wr = _rolling_win_rate(metrics, STOPPING["win_window"])
    if wr >= STOPPING["win_dominance"]:
        return f"Good win rate {wr:.1%} over last {STOPPING['win_window']} games exceeds dominance threshold."
    if wr <= 1 - STOPPING["win_dominance"]:
        return f"Evil win rate {1-wr:.1%} over last {STOPPING['win_window']} games exceeds dominance threshold."

    if total >= 40:
        stabilities = [_lesson_stability(metrics, r, STOPPING["stability_window"]) for r in ALL_ROLES]
        avg = sum(stabilities) / len(stabilities)
        if avg >= STOPPING["stability_threshold"]:
            return f"Lesson convergence reached (avg stability {avg:.1%} across all roles)."

    return None
