"""Guard: every Celery Beat periodic task must be routed to a queue the
worker actually consumes.

The worker is started with `-Q whatsapp,campaigns,processing` (Dockerfile.worker,
railway.json, start.sh) and does NOT consume the default "celery" queue. A beat
task with no `task_routes` entry is published to "celery" and silently never
runs — this happened in production to 8 tasks (appointment reminders, closer
reminders, automation drips, meta quality poll, quota replenish, ...).
"""

from app.workers.celery_app import celery_app

# Keep in sync with Dockerfile.worker / railway.json / start.sh
CONSUMED_QUEUES = {"whatsapp", "campaigns", "processing"}


def _queue_for(task_name: str) -> str | None:
    route = celery_app.conf.task_routes.get(task_name)
    return route.get("queue") if route else None


def test_every_beat_task_is_routed_to_a_consumed_queue():
    schedule = celery_app.conf.beat_schedule
    assert schedule, "beat_schedule is empty — did the import path change?"

    unrouted = []
    for entry_name, entry in schedule.items():
        task_name = entry["task"]
        queue = _queue_for(task_name)
        if queue not in CONSUMED_QUEUES:
            unrouted.append((entry_name, task_name, queue))

    assert not unrouted, (
        "These beat tasks are not routed to a queue the worker consumes "
        f"({sorted(CONSUMED_QUEUES)}); they will never execute: {unrouted}"
    )
