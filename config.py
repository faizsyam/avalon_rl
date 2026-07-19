import os
from dotenv import load_dotenv

load_dotenv()

# Up to three NVIDIA API keys. The runtime rotator tries them in order;
# when a call hits a retriable error (rate limit / 5xx / connection / timeout),
# it advances to the next key and loops back to the first when all three fail.
NVIDIA_API_KEY1 = os.getenv("NVIDIA_API_KEY1", "")
NVIDIA_API_KEY2 = os.getenv("NVIDIA_API_KEY2", "")
NVIDIA_API_KEY3 = os.getenv("NVIDIA_API_KEY3", "")

# Backward-compat: if someone still sets the legacy single key, treat it as key1.
_LEGACY = os.getenv("NVIDIA_API_KEY", "")
if not NVIDIA_API_KEY1 and _LEGACY:
    NVIDIA_API_KEY1 = _LEGACY

NVIDIA_API_KEYS = [k for k in (NVIDIA_API_KEY1, NVIDIA_API_KEY2, NVIDIA_API_KEY3) if k]
# Primary key used for the very first attempt; mirrors key1 in the rotator.
NVIDIA_API_KEY = NVIDIA_API_KEYS[0] if NVIDIA_API_KEYS else ""

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
GOOD_COORD_FILE = os.path.join(LESSONS_DIR, "good_coordination.txt")