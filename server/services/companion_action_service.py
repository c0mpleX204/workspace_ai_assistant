from typing import Dict, Tuple

from server.api.routers.schemas import CompanionActionIntent
from server.services.game_control_service import execute_game_control


ACTION_TYPES = {
    "live2d_expression",
    "live2d_motion",
    "live2d_look_at",
    "game_control",
}
EXPRESSIONS = {"neutral", "smile", "sad", "angry", "surprised"}
MOTION_GROUPS = {"idle", "tap_body", "wave", "greet"}
GAME_CMDS = {"jump", "attack", "move_left", "move_right", "interact"}


def validate_expression(payload: Dict[str, object]) -> Tuple[bool, str]:
    name = payload.get("name")
    weight = payload.get("weight", 1.0)
    if name not in EXPRESSIONS:
        return False, "invalid expression weight"
    if not isinstance(weight, (int, float)) or not (0.0 <= weight <= 1.0):
        return False, "invalid expression weight"
    return True, ""


def validate_motion(payload: Dict[str, object]) -> Tuple[bool, str]:
    group = payload.get("group")
    priority = payload.get("priority", 2)
    if group not in MOTION_GROUPS:
        return False, "invalid motion group"
    if not isinstance(priority, int) or not (1 <= priority <= 3):
        return False, "invalid motion priority"
    return True, ""


def validate_look_at(payload: Dict[str, object]) -> Tuple[bool, str]:
    x = payload.get("x")
    y = payload.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False, "invalid look_at args"
    if not (-1.0 <= float(x) <= 1.0) or not (-1.0 <= float(y) <= 1.0):
        return False, "look_at out of range"
    return True, ""


def validate_game(payload: Dict[str, object]) -> Tuple[bool, str]:
    cmd = payload.get("command")
    duration = payload.get("duration_ms", 120)
    if cmd not in GAME_CMDS:
        return False, "invalid game command"
    if not isinstance(duration, int) or not (100 <= duration <= 3000):
        return False, "invalid game duration"
    return True, ""


def validate_intent(intent: CompanionActionIntent) -> Tuple[bool, str]:
    if intent.type not in ACTION_TYPES:
        return False, f"unsupported type:{intent.type}"
    if intent.type == "live2d_expression":
        return validate_expression(intent.payload)
    if intent.type == "live2d_motion":
        return validate_motion(intent.payload)
    if intent.type == "live2d_look_at":
        return validate_look_at(intent.payload)
    if intent.type == "game_control":
        return validate_game(intent.payload)
    return False, "unknown type"


def dispatch_intent(intent: CompanionActionIntent) -> Tuple[bool, str]:
    if intent.type in {"live2d_expression", "live2d_motion", "live2d_look_at"}:
        return True, "ok"
    if intent.type == "game_control":
        result = execute_game_control(intent.payload)
        return bool(result.ok), str(result.reason or "")
    return False, "unsupported_dispatch_type"
