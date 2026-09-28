# Contributing

Thank you for your interest in Avalon Self-Learning Agents. This is a personal research project — contributions that improve accuracy, extensibility, or reproducibility are welcome.

---

## Getting Started

1. Fork and clone the repo
2. Follow the [Installation](README.md#installation) steps
3. Run `python -c "import main"` to verify your setup is importable

---

## How to Extend

### Add a new LLM model or backend

Change `MODEL_NAME` in `.env` (or `config.py`). The project uses the OpenAI-compatible API format, so any endpoint that speaks that protocol works. Adjust `NVIDIA_BASE_URL` in `config.py` if using a different provider.

### Change agent temperatures

Edit `create_llm()` and `create_reflection_llm()` in [`agents/llm_client.py`](agents/llm_client.py).

### Add a new game phase

1. Add the phase name to `ROLES_CONFIG[role]["phases"]` in [`game/roles.py`](game/roles.py)
2. Add a `PHASE_DESCRIPTIONS` entry describing what lessons in that phase should capture
3. Add a prompt builder in [`agents/prompts.py`](agents/prompts.py)
4. Call it from [`game/engine.py`](game/engine.py) at the right point in `_run_quest()`
5. Add phase-appropriate action verb stems to `PHASE_ACTION_STEMS` in [`memory/manager.py`](memory/manager.py)

### Change stopping criteria

Edit the `STOPPING` dict in [`config.py`](config.py). The `win_dominance` threshold, `win_window`, `stability_threshold`, and `stability_window` are all hot-configurable without touching any other file.

### Change lesson consolidation schedule

Edit `EARLY_CONSOLIDATION_GAMES` (list of specific game numbers) and `CONSOLIDATION_EVERY` (periodic interval) in [`config.py`](config.py).

---

## Debugging

| Problem | Where to look |
|---|---|
| Agent made a strange decision | `data/logs/game_NNN.txt` — full turn-by-turn transcript |
| LLM returned malformed JSON | `data/logs/warns.txt` — logged with raw response |
| Lessons not accumulating | `data/logs/reflection_debug.log` — grep for `WARN` to find dropped/repaired lessons |
| Lesson file looks wrong | `data/lessons/{role}.txt` — inspect directly; format is plain text |
| Checkpoint missing files | `data/checkpoints/checkpoint_gNNN/` — should contain all 5 role files + both coordination files |

---

## Code Style

- Standard Python; no linter config enforced, but `black`-style formatting is preferred
- Docstrings: Google-style or reStructuredText are both fine; the existing module docstrings use prose paragraphs
- No tests exist yet — if you add one, place it in a `tests/` directory and use `pytest`

---

## Key File Index (quick navigation)

| Task | File |
|---|---|
| Change game rules or win conditions | [`agents/prompts.py`](agents/prompts.py) (GAME_RULES, ROLE_CONTEXT) |
| Change role abilities or phase assignments | [`game/roles.py`](game/roles.py) |
| Change LLM model or temperature | [`config.py`](config.py), [`agents/llm_client.py`](agents/llm_client.py) |
| Change stopping criteria | [`config.py`](config.py) (STOPPING dict) |
| Change lesson storage format | [`memory/manager.py`](memory/manager.py) (parser/serializer) |
| Change reflection prompts or constraints | [`reflection/reflector.py`](reflection/reflector.py) |
| Add a new game phase | [`game/engine.py`](game/engine.py), [`game/roles.py`](game/roles.py), [`agents/prompts.py`](agents/prompts.py), [`memory/manager.py`](memory/manager.py) |
