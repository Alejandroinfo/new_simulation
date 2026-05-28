"""
saveload.py — Save and load game state as JSON.

Design:
  Serializes the full scenario state to JSON using a custom encoder
  that handles dataclasses, Enums, and sets.
  On load, reconstructs the scenario from scratch with the same seed
  and difficulty, then patches the state back in.

Usage:
  from saveload import save_game, load_game
  path = save_game(scenario, "save_01.json")
  scenario = load_game("save_01.json")
"""
from __future__ import annotations
import json
import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any

class _Encoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {"__dc__": type(obj).__name__, **dataclasses.asdict(obj)}
        if isinstance(obj, Enum):
            return {"__enum__": type(obj).__name__, "value": obj.value}
        if isinstance(obj, set):
            return {"__set__": list(obj)}
        return super().default(obj)


def _serialize(obj: Any) -> Any:
    """Recursively serialize for JSON."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = {"__dc__": type(obj).__name__}
        for f in dataclasses.fields(obj):
            d[f.name] = _serialize(getattr(obj, f.name))
        return d
    if isinstance(obj, Enum):
        return {"__enum__": type(obj).__name__, "value": obj.value}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(i) for i in obj]
    if isinstance(obj, set):
        return {"__set__": [_serialize(i) for i in obj]}
    return obj


def _deserialize(obj: Any, registry: dict) -> Any:
    """Reconstruct from serialized form."""
    if isinstance(obj, dict):
        if "__enum__" in obj:
            cls = registry.get(obj["__enum__"])
            return cls(obj["value"]) if cls else obj["value"]
        if "__set__" in obj:
            return set(_deserialize(i, registry) for i in obj["__set__"])
        if "__dc__" in obj:
            cls = registry.get(obj["__dc__"])
            if cls:
                kwargs = {k: _deserialize(v, registry)
                          for k, v in obj.items() if k != "__dc__"}
                try:
                    return cls(**kwargs)
                except Exception:
                    return kwargs
            return {k: _deserialize(v, registry) for k, v in obj.items() if k != "__dc__"}
        return {k: _deserialize(v, registry) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deserialize(i, registry) for i in obj]
    return obj


def _build_registry() -> dict:
    """Build a map of class name → class for deserialization."""
    from scenarios.base import (
        Character, Clue, Secret, Relationship,
        DialogueOption, ScenarioResult,
        CaseType, RelKind, ConfrontationState, ConfrontationClue,
    )
    from scenarios.murderer import MurdererState
    registry = {
        "Character": Character, "Clue": Clue, "Secret": Secret,
        "Relationship": Relationship, "DialogueOption": DialogueOption,
        "ScenarioResult": ScenarioResult, "ConfrontationState": ConfrontationState,
        "ConfrontationClue": ConfrontationClue,
        "MurdererState": MurdererState,
        "CaseType": CaseType, "RelKind": RelKind,
    }
    return registry

def save_game(scenario, path: str | None = None,
              conversation_log: list | None = None) -> str:
    """Save the full scenario state. Returns the file path."""
    from scenarios.murderer import MurdererScenario
    if not isinstance(scenario, MurdererScenario):
        raise ValueError("save_game only supports MurdererScenario for now.")

    data = {
        "scenario_type": "murderer",
        "seed": scenario.state.seed_used,
        "difficulty": scenario.state.difficulty,
        "state": _serialize(scenario.state),
        "characters": {cid: _serialize(c) for cid, c in scenario.characters.items()},
        "clues": {cid: _serialize(c) for cid, c in scenario.clues.items()},
        "clue_holders": scenario.clue_holders,
        "secrets": {sid: _serialize(s) for sid, s in scenario.secrets.items()},
        "relationships": {rid: _serialize(r) for rid, r in scenario.relationships.items()},
        "events": scenario.events[-50:],
        "town_name": scenario.town_name,
        "first_victim_name": scenario.first_victim_name,
        "conversation_log": (conversation_log or [])[-30:],
    }

    if path is None:
        import datetime
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"save_{scenario.town_name.lower()}_{ts}.json"

    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_game(path: str) -> tuple:
    """Load a saved game. Returns (scenario, conversation_log)."""
    from scenarios.murderer import MurdererScenario, MurdererState
    reg = _build_registry()

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    assert raw.get("scenario_type") == "murderer", "Only murderer saves supported."

    # Rebuild scenario from seed (sets up fresh state)
    scenario = MurdererScenario(seed=raw["seed"], difficulty=raw["difficulty"])

    # Patch back the saved state
    scenario.state   = _deserialize(raw["state"], reg)
    scenario.characters = {
        cid: _deserialize(c, reg) for cid, c in raw["characters"].items()
    }
    scenario.clues = {
        cid: _deserialize(c, reg) for cid, c in raw["clues"].items()
    }
    scenario.clue_holders = {
        k: v for k, v in raw["clue_holders"].items()
    }
    scenario.secrets = {
        sid: _deserialize(s, reg) for sid, s in raw["secrets"].items()
    }
    scenario.relationships = {
        rid: _deserialize(r, reg) for rid, r in raw["relationships"].items()
    }
    scenario.events        = raw.get("events", [])
    scenario.town_name     = raw.get("town_name", scenario.town_name)
    scenario.first_victim_name = raw.get("first_victim_name", "")

    conv_log = raw.get("conversation_log", [])
    return scenario, conv_log
