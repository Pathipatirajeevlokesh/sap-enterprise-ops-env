from models.action import SAPAction, ActionType, FixMethod


def compute_reward(
    action: SAPAction,
    scenario: dict,
    step_number: int,
    sla_total: int,
    sla_remaining: int,
    previous_actions: list,
) -> tuple[float, dict]:

    reward = 0.0
    breakdown = {
        "diagnosis_score":  0.0,
        "fix_score":        0.0,
        "sequence_score":   0.0,
        "security_score":   0.0,
        "sla_multiplier":   0.0,
        "penalties":        0.0,
        "total":            0.0,
    }

    task_id = scenario["task_id"]

    # ── SLA MULTIPLIER ───────────────────────────────────────────
    sla_multiplier = max(0.1, sla_remaining / sla_total)
    breakdown["sla_multiplier"] = round(sla_multiplier, 3)

    # ── PENALTIES ────────────────────────────────────────────────
    destructive = [FixMethod.DELETE_JOB, FixMethod.REIMPORT_TRANSPORT]
    if action.fix_method in destructive:
        breakdown["penalties"] -= 0.30
        reward -= 0.30

    if action.target_component in ["QAS", "DEV"]:
        breakdown["penalties"] -= 0.20
        reward -= 0.20

    if action.action_type == ActionType.ESCALATE and action.target_component == "memory_warning":
        breakdown["penalties"] -= 0.15
        reward -= 0.15

    # ─────────────────────────────────────────────────────────────
    # TASK 1
    # ─────────────────────────────────────────────────────────────
    if task_id == "task_1_job_failure":

        if action.action_type == ActionType.DIAGNOSE:
            if action.diagnosis and len(action.diagnosis) > 10:
                breakdown["diagnosis_score"] = 0.15
                reward += 0.15

        if action.action_type == ActionType.FIX:
            if action.fix_method == scenario.get("correct_fix"):
                breakdown["fix_score"] = 0.25
                reward += 0.25

        if reward > 0:
            reward *= sla_multiplier

    # ─────────────────────────────────────────────────────────────
    # TASK 2 (FIXED VERSION)
    # ─────────────────────────────────────────────────────────────
    elif task_id == "task_2_transport_security":

        # Detect if already solved → STOP reward farming
        transport_done = "release_transport" in previous_actions
        security_done = any(x in previous_actions for x in ["block_ip", "reset_credentials"])

        if transport_done and security_done:
            return 0.0, breakdown

        # Transport fix
        if action.action_type == ActionType.FIX:
            if action.fix_method == scenario.get("correct_transport_fix"):
                breakdown["fix_score"] = 0.30
                reward += 0.30

        # Security handling (only reward properly once)
        if action.action_type == ActionType.ESCALATE:
            correct_sec = scenario.get("correct_security_action")

            if action.security_action == correct_sec:
                if correct_sec not in previous_actions:
                    breakdown["security_score"] = 0.30
                    reward += 0.30
                else:
                    breakdown["security_score"] = 0.05
                    reward += 0.05

        # Penalize excessive escalation
        if action.action_type == ActionType.ESCALATE:
            escalate_count = sum(1 for x in previous_actions if x in ["block_ip", "reset_credentials"])
            if escalate_count > 1:
                breakdown["penalties"] -= 0.10
                reward -= 0.10

        if reward > 0:
            reward *= sla_multiplier

    # ─────────────────────────────────────────────────────────────
    # TASK 3
    # ─────────────────────────────────────────────────────────────
    elif task_id == "task_3_p1_incident":

        correct_order = scenario.get("correct_order", [])

        if action.fix_method and previous_actions:
            for step in correct_order:
                if step not in previous_actions:
                    expected_next = step
                    break
            else:
                expected_next = None

            if action.fix_method == expected_next:
                breakdown["sequence_score"] = 0.20
                reward += 0.20
            elif action.fix_method in correct_order:
                breakdown["penalties"] -= 0.10
                reward -= 0.10

        if action.action_type == ActionType.FIX:
            if action.fix_method in correct_order:
                breakdown["fix_score"] = 0.15
                reward += 0.15

        if action.action_type == ActionType.ESCALATE:
            if action.security_action in ["block_ip", "escalate_soc"]:
                breakdown["security_score"] = 0.15
                reward += 0.15

        if action.action_type == ActionType.DIAGNOSE:
            if action.reasoning and len(action.reasoning) > 20:
                breakdown["diagnosis_score"] = 0.10
                reward += 0.10

        # Cascade penalty
        if action.fix_method == FixMethod.CLEAR_BUFFER and FixMethod.RECONNECT_DB not in previous_actions:
            breakdown["penalties"] -= 0.25
            reward -= 0.25

        if reward > 0:
            reward *= sla_multiplier

    # ── FINAL CLAMP ──────────────────────────────────────────────
    reward = max(-0.75, min(1.0, round(reward, 4)))
    breakdown["total"] = reward

    return reward, breakdown