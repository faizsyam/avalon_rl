import os
import json
from config import LOGS_DIR, STATE_FILE
from game.state import GameState


def save_game_log(state: GameState):
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, f"game_{state.game_id:03d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(state.log_lines))


def save_run_state(game_id: int):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"next_game_id": game_id + 1}, f)


def load_run_state() -> int:
    if not os.path.exists(STATE_FILE):
        return 1
    with open(STATE_FILE, "r") as f:
        return json.load(f).get("next_game_id", 1)
