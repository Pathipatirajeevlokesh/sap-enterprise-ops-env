# server/reward.py
from models.action import SAPAction, ActionType, FixMethod


def compute_reward(
    action: SAPAction,
    scenario: dict,
    step_number: int,
    sla_total: int,
    sla_remaining: int,
    previous_actions: list,
) -> tuple[float, dict]:
    """
    Compute reward for a single step.
    Returns (reward_float, breakdown_dict)
    """

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
    # Reward decays linearly the longer agent takes
    sla_multiplier = max(0.1, sla_remaining / sla_total)
    breakdown["sla_multiplier"] = round(sla_multiplier, 3)

    # ── PENALTY: DESTRUCTIVE ACTION ──────────────────────────────
    destructive = [FixMethod.DELETE_JOB, FixMethod.REIMPORT_TRANSPORT]
    if action.fix_method in destructive:
        breakdown["penalties"] -= 0.30
        reward -= 0.30

    # ── PENALTY: FALSE POSITIVE (flagged red herring) ─────────────
    if action.action_type == ActionType.ESCALATE:
        if action.target_component == "memory_warning":
            breakdown["penalties"] -= 0.15
            reward -= 0.15

    # ── PENALTY: WRONG SYSTEM ────────────────────────────────────
    if action.target_component in ["QAS", "DEV"]:
        breakdown["penalties"] -= 0.20
        reward -= 0.20

    # ── TASK 1 SCORING ───────────────────────────────────────────
    if task_id == "task_1_job_failure":

        # Diagnosis score (0.25 weight)
        if action.action_type == ActionType.DIAGNOSE:
            root_cause = scenario.get("root_cause", "")
            if action.diagnosis and root_cause in action.diagnosis.lower():
                breakdown["diagnosis_score"] = 0.25
                reward += 0.25
            elif action.reasoning and len(action.reasoning) > 20:
                # Partial credit for showing reasoning
                breakdown["diagnosis_score"] = 0.10
                reward += 0.10

        # Fix score (0.25 weight)
        if action.action_type == ActionType.FIX:
            correct_fix = scenario.get("correct_fix", "")
            correct_tx  = scenario.get("correct_transaction", "")

            fix_correct = action.fix_method == correct_fix
            tx_correct  = action.transaction_code == correct_tx

            if fix_correct and tx_correct:
                breakdown["fix_score"] = 0.25
                reward += 0.25
            elif fix_correct:
                breakdown["fix_score"] = 0.15
                reward += 0.15
            elif tx_correct:
                breakdown["fix_score"] = 0.10
                reward += 0.10

        # Apply SLA multiplier to positive reward
        if reward > 0:
            reward = reward * sla_multiplier
        
        # Penalty for repeating same fix
        if action.fix_method and previous_actions.count(action.fix_method) > 1:
            breakdown["penalties"] -= 0.10
            reward -= 0.10

    # ── TASK 2 SCORING ───────────────────────────────────────────
    elif task_id == "task_2_transport_security":

        # Transport fix (0.60 of task score)
        if action.action_type == ActionType.FIX:
            correct_fix = scenario.get("correct_transport_fix", "")
            correct_tx  = scenario.get("correct_transaction", "")

            if action.fix_method == correct_fix and action.transaction_code == correct_tx:
                breakdown["fix_score"] = 0.35
                reward += 0.35
            elif action.fix_method == correct_fix:
                breakdown["fix_score"] = 0.20
                reward += 0.20

        # Security detection (0.40 of task score)
        if action.action_type == ActionType.ESCALATE:
            correct_sec = scenario.get("correct_security_action", "")
            if action.security_action == correct_sec:
                breakdown["security_score"] = 0.25
                reward += 0.25
            elif action.security_action is not None:
                # Detected threat but wrong response
                breakdown["security_score"] = 0.10
                reward += 0.10

        if reward > 0:
            reward = reward * sla_multiplier
        
        # Penalty for repeating same fix
        if action.fix_method and previous_actions.count(action.fix_method) > 1:
            breakdown["penalties"] -= 0.10
            reward -= 0.10

    # ── TASK 3 SCORING ───────────────────────────────────────────
    elif task_id == "task_3_p1_incident":

        correct_order = scenario.get("correct_order", [])

        # Sequence score — did agent act in right order?
        if action.fix_method and previous_actions:
            expected_next = None
            for step in correct_order:
                if step not in previous_actions:
                    expected_next = step
                    break

            if action.fix_method == expected_next:
                breakdown["sequence_score"] = 0.20
                reward += 0.20
            elif action.fix_method in correct_order:
                # Right action, wrong order — partial
                breakdown["sequence_score"] = 0.08
                reward += 0.08

        # Fix score
        if action.action_type == ActionType.FIX:
            if action.fix_method in correct_order:
                breakdown["fix_score"] = 0.15
                reward += 0.15

        # Security score
        if action.action_type == ActionType.ESCALATE:
            if action.security_action in ["block_ip", "escalate_soc"]:
                breakdown["security_score"] = 0.15
                reward += 0.15

        # Diagnosis score
        if action.action_type == ActionType.DIAGNOSE:
            if action.reasoning and len(action.reasoning) > 30:
                breakdown["diagnosis_score"] = 0.10
                reward += 0.10

        # Cascade penalty — fixing memory before DB
        if (action.fix_method == FixMethod.CLEAR_BUFFER and
                FixMethod.RECONNECT_DB not in previous_actions):
            breakdown["penalties"] -= 0.25
            reward -= 0.25

        if reward > 0:
            reward = reward * sla_multiplier

        # Penalty for repeating same fix
        if action.fix_method and previous_actions.count(action.fix_method) > 1:
            breakdown["penalties"] -= 0.10
            reward -= 0.10

    # ── CLAMP to [-0.75, 1.10] ───────────────────────────────────
    reward = max(-0.75, min(1.10, round(reward, 4)))
    breakdown["total"] = reward

    return reward, breakdown