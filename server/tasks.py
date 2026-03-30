# server/tasks.py
from models.action import SAPAction, ActionType, FixMethod


# ── TASK METADATA ────────────────────────────────────────────────

TASKS = [
    {
        "id":          "task_1_job_failure",
        "name":        "Background Job Failure Resolution",
        "description": "A critical SAP background job has aborted in PRD. Diagnose the root cause and restart it using the correct transaction.",
        "difficulty":  "easy",
        "max_steps":   5,
        "sla_seconds": 300,
        "target_score": 0.85,
    },
    {
        "id":          "task_2_transport_security",
        "name":        "Transport Error + Security Anomaly",
        "description": "A transport request is stuck in STMS and a suspicious RFC call has been detected. Resolve the transport AND flag the security threat.",
        "difficulty":  "medium",
        "max_steps":   8,
        "sla_seconds": 480,
        "target_score": 0.60,
    },
    {
        "id":          "task_3_p1_incident",
        "name":        "P1 Full Crisis Response",
        "description": "System down. DB timeout, memory dump, and brute force attack simultaneously. Prioritise correctly and resolve all three before SLA breach.",
        "difficulty":  "hard",
        "max_steps":   12,
        "sla_seconds": 600,
        "target_score": 0.30,
    },
]


def get_task(task_id: str) -> dict:
    for t in TASKS:
        if t["id"] == task_id:
            return t
    raise ValueError(f"Unknown task_id: {task_id}")


def list_tasks() -> list:
    return TASKS


# ── GRADERS ──────────────────────────────────────────────────────

def grade_task1(actions: list[SAPAction], scenario: dict) -> tuple[float, dict]:
    """
    Grade a complete Task 1 episode.
    Returns (final_score 0.0-1.0, breakdown dict)
    """
    score = 0.0
    breakdown = {
        "diagnosed":       False,
        "correct_tx":      False,
        "correct_fix":     False,
        "no_destructive":  True,
        "reasoning_given": False,
        "final_score":     0.0,
    }

    correct_fix = scenario.get("correct_fix", "restart_job")
    correct_tx  = scenario.get("correct_transaction", "SM37")
    wrong_fixes = scenario.get("wrong_fixes", [])

    for action in actions:

        # Check diagnosis
        if action.action_type == ActionType.DIAGNOSE:
            root_cause = scenario.get("root_cause", "")
            if action.diagnosis and root_cause in action.diagnosis.lower():
                breakdown["diagnosed"] = True
            if action.reasoning and len(action.reasoning) > 15:
                breakdown["reasoning_given"] = True

        # Check fix
        if action.action_type == ActionType.FIX:
            if action.transaction_code == correct_tx:
                breakdown["correct_tx"] = True
            if action.fix_method == correct_fix:
                breakdown["correct_fix"] = True
            if action.fix_method in wrong_fixes:
                breakdown["no_destructive"] = False

    # Score calculation
    if breakdown["diagnosed"]:
        score += 0.25
    elif breakdown["reasoning_given"]:
        score += 0.10

    if breakdown["correct_tx"]:
        score += 0.25

    if breakdown["correct_fix"]:
        score += 0.40

    if not breakdown["no_destructive"]:
        score -= 0.30

    # Clamp
    score = max(0.0, min(1.0, round(score, 4)))
    breakdown["final_score"] = score
    return score, breakdown


def grade_task2(actions: list[SAPAction], scenario: dict) -> tuple[float, dict]:
    """
    Grade a complete Task 2 episode.
    Weighted: 60% transport fix + 40% security detection.
    """
    score = 0.0
    breakdown = {
        "transport_fixed":    False,
        "correct_tx":         False,
        "security_detected":  False,
        "correct_sec_action": False,
        "red_herring_caught": False,
        "cascade_triggered":  False,
        "final_score":        0.0,
    }

    correct_fix = scenario.get("correct_transport_fix", "release_transport")
    correct_tx  = scenario.get("correct_transaction", "STMS")
    correct_sec = scenario.get("correct_security_action", "block_ip")

    for action in actions:

        # Transport fix check
        if action.action_type == ActionType.FIX:
            if action.fix_method == correct_fix:
                breakdown["transport_fixed"] = True
            if action.transaction_code == correct_tx:
                breakdown["correct_tx"] = True
            if action.fix_method == FixMethod.REIMPORT_TRANSPORT:
                breakdown["cascade_triggered"] = True

        # Security detection check
        if action.action_type == ActionType.ESCALATE:
            breakdown["security_detected"] = True
            if action.security_action == correct_sec:
                breakdown["correct_sec_action"] = True

    # Score calculation — 60% transport, 40% security
    if breakdown["transport_fixed"] and breakdown["correct_tx"]:
        score += 0.60
    elif breakdown["transport_fixed"]:
        score += 0.35
    elif breakdown["correct_tx"]:
        score += 0.20

    if breakdown["correct_sec_action"]:
        score += 0.40
    elif breakdown["security_detected"]:
        score += 0.15

    # Penalties
    if breakdown["cascade_triggered"]:
        score -= 0.25

    # Clamp
    score = max(0.0, min(1.0, round(score, 4)))
    breakdown["final_score"] = score
    return score, breakdown


def grade_task3(actions: list[SAPAction], scenario: dict) -> tuple[float, dict]:
    """
    Grade a complete Task 3 episode.
    7 sub-components, each worth partial score.
    """
    score = 0.0
    breakdown = {
        "db_fixed":            False,
        "memory_fixed":        False,
        "icm_restarted":       False,
        "attacker_blocked":    False,
        "soc_escalated":       False,
        "correct_order":       False,
        "memory_test_passed":  False,
        "cascade_triggered":   False,
        "final_score":         0.0,
    }

    correct_order  = scenario.get("correct_order", [])
    attacker_ip    = scenario.get("attacker_ip", "")
    fixes_taken    = []

    for action in actions:

        if action.action_type == ActionType.FIX:
            if action.fix_method == FixMethod.RECONNECT_DB:
                breakdown["db_fixed"] = True
                fixes_taken.append(FixMethod.RECONNECT_DB)

            if action.fix_method == FixMethod.CLEAR_BUFFER:
                breakdown["memory_fixed"] = True
                fixes_taken.append(FixMethod.CLEAR_BUFFER)
                # Cascade check — buffer before DB
                if not breakdown["db_fixed"]:
                    breakdown["cascade_triggered"] = True

            if action.fix_method == FixMethod.RESTART_ICM:
                breakdown["icm_restarted"] = True
                fixes_taken.append(FixMethod.RESTART_ICM)

            if action.fix_method == FixMethod.BLOCK_IP:
                breakdown["attacker_blocked"] = True
                fixes_taken.append(FixMethod.BLOCK_IP)

        if action.action_type == ActionType.ESCALATE:
            if action.security_action == "escalate_soc":
                breakdown["soc_escalated"] = True

            # Memory test — did agent mention attacker IP from Task 1?
            if attacker_ip and action.reasoning:
                if attacker_ip in action.reasoning:
                    breakdown["memory_test_passed"] = True

    # Check order correctness
    if fixes_taken and fixes_taken == correct_order[:len(fixes_taken)]:
        breakdown["correct_order"] = True

    # Score calculation — 7 components
    component_score = 1.0 / 7

    for key in [
        "db_fixed", "memory_fixed", "icm_restarted",
        "attacker_blocked", "soc_escalated",
        "correct_order", "memory_test_passed"
    ]:
        if breakdown[key]:
            score += component_score

    # Cascade penalty
    if breakdown["cascade_triggered"]:
        score -= 0.25

    # Clamp
    score = max(0.0, min(1.0, round(score, 4)))
    breakdown["final_score"] = score
    return score, breakdown


def grade_episode(
    task_id: str,
    actions: list[SAPAction],
    scenario: dict
) -> tuple[float, dict]:
    """Main grader entry point."""
    if task_id == "task_1_job_failure":
        return grade_task1(actions, scenario)
    elif task_id == "task_2_transport_security":
        return grade_task2(actions, scenario)
    elif task_id == "task_3_p1_incident":
        return grade_task3(actions, scenario)
    else:
        raise ValueError(f"Unknown task_id: {task_id}")