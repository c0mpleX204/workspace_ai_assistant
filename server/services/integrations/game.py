import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(slots=True)
class GameControlConfig:
    enabled: bool
    dry_run: bool


@dataclass(slots=True)
class GameControlResult:
    ok: bool
    reason: str = ""


def get_game_control_config() -> GameControlConfig:
    enabled = os.getenv("GAME_CONTROL_ENABLED", "false").strip().lower() == "true"
    dry_run = os.getenv("GAME_CONTROL_DRY_RUN", "true").strip().lower() == "true"
    return GameControlConfig(enabled=enabled, dry_run=dry_run)


def execute_game_control(payload: Dict[str, object]) -> GameControlResult:
    """Execute one game control command.

    Phase-1 implementation is intentionally safe:
    - Disabled by default.
    - Dry-run by default even when enabled.
    - Real input injection will be added in next phase.
    """

    cfg = get_game_control_config()
    command = str(payload.get("command", "")).strip()
    duration_ms = int(payload.get("duration_ms", 120) or 120)

    if not cfg.enabled:
        logging.info("game_control skipped: disabled command=%s duration_ms=%s", command, duration_ms)
        return GameControlResult(ok=False, reason="disabled")

    if cfg.dry_run:
        logging.info("game_control dry-run command=%s duration_ms=%s", command, duration_ms)
        return GameControlResult(ok=True, reason="dry_run")

    started = time.perf_counter()
    ok, reason = _execute_command_stub(command=command, duration_ms=duration_ms)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if ok:
        logging.info(
            "game_control executed command=%s duration_ms=%s elapsed_ms=%s",
            command,
            duration_ms,
            elapsed_ms,
        )
    else:
        logging.warning(
            "game_control failed command=%s duration_ms=%s elapsed_ms=%s reason=%s",
            command,
            duration_ms,
            elapsed_ms,
            reason,
        )
    return GameControlResult(ok=ok, reason=reason)


def _execute_command_stub(*, command: str, duration_ms: int) -> Tuple[bool, str]:
    # Placeholder for the real keyboard/mouse injector integration.
    if not command:
        return False, "empty_command"
    if duration_ms <= 0:
        return False, "invalid_duration"
    return False, "executor_not_implemented"
