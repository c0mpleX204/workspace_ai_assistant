from datetime import datetime
import logging
import threading
import time

from infra.repo import list_due_reminders, mark_reminder_sent
from services.model_service import warmup_model


def reminder_worker(poll_interval_seconds: int = 60, window_minutes: int = 60) -> None:
    while True:
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
                    logging.warning(f"标记提醒已发送失败: {exc}")
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
            logging.warning(f"提醒工作线程出错: {exc}")
        time.sleep(poll_interval_seconds)


def run_startup_tasks() -> None:
    try:
        warmup_model()
    except Exception as exc:
        print(f"[startup] warmup failed: {exc}")

    try:
        thread = threading.Thread(
            target=reminder_worker,
            kwargs={"poll_interval_seconds": 60, "window_minutes": 60},
            daemon=True,
        )
        thread.start()
        logging.info("Reminder worker thread started.")
    except Exception as exc:
        logging.warning(f"Failed to start reminder worker thread: {exc}")
