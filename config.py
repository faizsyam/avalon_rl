import os
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "meta/llama-3.1-70b-instruct")

GAMEPLAY_MAX_TOKENS = 32768
REFLECTION_MAX_TOKENS = 32768

# Early consolidation schedule: run at these specific game numbers, then every CONSOLIDATION_EVERY after
EARLY_CONSOLIDATION_GAMES = [5, 10]
CONSOLIDATION_EVERY = 20
CHECKPOINT_EVERY = 20
MAX_GAMES = 300
MAX_VOTE_FAILURES = 5
QUESTS_TO_WIN = 3
QUEST_TEAM_SIZES = [2, 3, 2, 3, 3]

STOPPING = {
    "stability_threshold": 0.90,
    "stability_window": 10,
    "win_dominance": 0.85,
    "win_window": 30,
}

DATA_DIR = "data"
LESSONS_DIR = os.path.join(DATA_DIR, "lessons")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
CHECKPOINTS_DIR = os.path.join(DATA_DIR, "checkpoints")
METRICS_FILE = os.path.join(DATA_DIR, "metrics.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
EVIL_COORD_FILE = os.path.join(LESSONS_DIR, "evil_coordination.txt")