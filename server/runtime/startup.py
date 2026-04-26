from datetime import datetime
import logging
import threading

from server.infra.repo import list_due_reminders, mark_reminder_sent
from server.services.model_service import warmup_model


_STOP = threading.Event()
_WORKER: threading.Thread | None = None


def reminder_worker(
    stop_event: threading.Event,
    poll_interval_seconds: int = 60,
    window_minutes: int = 60,
) -> None:
    while not stop_event.is_set():
        try:
            due = list_due_reminders(window_minutes=window_minutes)
            now = datetime.utcnow()
            for reminder in due:
                try:
                    mark_reminder_sent(
                        reminder["user_id"],
                        reminder["course_id"],
                        reminder["topic"],
                        now,
                    )
                except Exception as exc:
                    logging.warning("mark reminder sent failed: %s", exc)
                logging.info(
                    {
                        "action": "reminder_sent",
                        "user_id": reminder["user_id"],
                        "course_id": reminder["course_id"],
                        "topic": reminder["topic"],
                        "next_review_at": reminder["next_review_at"],
                    }
                )
        except Exception as exc:
            logging.warning("reminder worker failed: %s", exc)
        stop_event.wait(poll_interval_seconds)


def run_startup_tasks() -> None:
    global _WORKER
    try:
        warmup_model()
    except Exception as exc:
        print(f"[startup] warmup failed: {exc}")

    try:
        if _WORKER and _WORKER.is_alive():
            return
        _STOP.clear()
        thread = threading.Thread(
            target=reminder_worker,
            kwargs={
                "stop_event": _STOP,
                "poll_interval_seconds": 60,
                "window_minutes": 60,
            },
            daemon=True,
        )
        thread.start()
        _WORKER = thread
        logging.info("Reminder worker thread started.")
    except Exception as exc:
        logging.warning("Failed to start reminder worker thread: %s", exc)


def shutdown_workers() -> None:
    _STOP.set()
    thread = _WORKER
    if thread and thread.is_alive():
        thread.join(timeout=2)
