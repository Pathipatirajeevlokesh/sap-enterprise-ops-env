# server/cascade.py
import random
from models.action import FixMethod


# ── CASCADE RULES ────────────────────────────────────────────────
# If agent takes a wrong action, a new alert spawns in the queue.
# This tests whether the agent can handle consequences of mistakes.

CASCADE_RULES = [
    {
        "trigger_fix":    FixMethod.DELETE_JOB,
        "trigger_task":   "task_1_job_failure",
        "new_alert": {
            "component":  "Audit Log",
            "error_code": "JOB_DELETED",
            "priority":   "high",
            "message":    "Critical background job permanently deleted. Manual recreation required.",
            "is_red_herring": False,
        },
        "description": "Deleting a job instead of restarting causes audit alert"
    },
    {
        "trigger_fix":    FixMethod.REIMPORT_TRANSPORT,
        "trigger_task":   "task_2_transport_security",
        "new_alert": {
            "component":  "Transport Management",
            "error_code": "BUFFER_LOCKED",
            "priority":   "critical",
            "message":    "Transport buffer locked after failed reimport. All imports halted.",
            "is_red_herring": False,
        },
        "description": "Reimporting instead of releasing locks the entire transport buffer"
    },
    {
        "trigger_fix":    FixMethod.CLEAR_BUFFER,
        "trigger_task":   "task_3_p1_incident",
        "condition":      "db_not_fixed_first",
        "new_alert": {
            "component":  "Database",
            "error_code": "DB_CORRUPTION_RISK",
            "priority":   "critical",
            "message":    "Buffer cleared before DB reconnect. Data consistency at risk. Immediate DBA escalation required.",
            "is_red_herring": False,
        },
        "description": "Clearing buffer before fixing DB risks data corruption"
    },
    {
        "trigger_fix":    FixMethod.RESTART_ICM,
        "trigger_task":   "task_3_p1_incident",
        "condition":      "db_not_fixed_first",
        "new_alert": {
            "component":  "ICM",
            "error_code": "ICM_RESTART_FAILED",
            "priority":   "high",
            "message":    "ICM restart failed. DB must be reconnected before ICM can initialise.",
            "is_red_herring": False,
        },
        "description": "Restarting ICM before DB fix causes ICM to fail on startup"
    },
]


def check_cascade(
    fix_method: str,
    task_id: str,
    previous_fixes: list,
) -> dict | None:
    """
    Check if the current fix action triggers a cascade failure.
    Returns a new alert dict if cascade triggered, else None.
    """
    for rule in CASCADE_RULES:
        # Must match fix and task
        if rule["trigger_fix"] != fix_method:
            continue
        if rule["trigger_task"] != task_id:
            continue

        # Check conditional rules
        condition = rule.get("condition")
        if condition == "db_not_fixed_first":
            if FixMethod.RECONNECT_DB in previous_fixes:
                continue  # DB already fixed — no cascade

        # Cascade triggered — build the alert
        alert = rule["new_alert"].copy()
        alert["alert_id"] = f"CAS-{random.randint(1000,9999)}"
        alert["cascade"] = True
        return alert

    return None


def get_cascade_description(fix_method: str, task_id: str) -> str:
    """Return human readable description of what cascade was triggered."""
    for rule in CASCADE_RULES:
        if rule["trigger_fix"] == fix_method and rule["trigger_task"] == task_id:
            return rule["description"]
    return "Unknown cascade"