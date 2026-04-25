"""
Train a lightweight policy for the SAP Enterprise Ops environment.

This script uses tabular Q-learning over symbolic observations. It does not
need GPU libraries or external ML dependencies, which keeps it usable in the
hackathon/runtime environment while still producing a saved "model" artifact.

Usage:
    python train.py --episodes 500 --eval-episodes 50
    python train.py --episodes 1000 --output artifacts/trained_policy.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

from models.action import SAPAction, ActionType, FixMethod
from models.observation import SAPObservation
from server.environment import SAPBasisEnvironment
from server.tasks import list_tasks


TASK_IDS = [task["id"] for task in list_tasks()]
DEFAULT_OUTPUT = Path("artifacts/trained_policy.json")


def _all_text(obs: SAPObservation) -> str:
    parts = [obs.task_description]
    parts.extend(alert.message for alert in obs.alert_queue)
    parts.extend(log.message for log in obs.sm21_log)
    parts.extend(obs.episode_history)
    return " ".join(parts).lower()


def _infer_diagnosis(obs: SAPObservation) -> str:
    text = _all_text(obs)
    if "variant" in text:
        return "missing_variant caused the background job abort"
    if "authorization" in text:
        return "authorization_failure caused the background job abort"
    if "lock" in text:
        return "db_lock_timeout caused the incident"
    if "memory" in text or "storage" in text:
        return "memory_exceeded caused the incident"
    if "transport" in text and ("rfc" in text or "logon" in text):
        return "transport issue with a concurrent security anomaly"
    if "database" in text or "db_" in text:
        return "database outage with memory and security impact"
    return "work_process_timeout caused the background job abort"


def _target_component(obs: SAPObservation) -> str:
    if obs.task_id == "task_1_job_failure":
        return "background_jobs"
    if obs.task_id == "task_2_transport_security":
        return "transport"
    return "db"


def _attacker_ip(obs: SAPObservation) -> str | None:
    text = " ".join(alert.message for alert in obs.alert_queue)
    match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    return match.group(0) if match else None


def action_from_id(action_id: str, obs: SAPObservation) -> SAPAction:
    """Build a concrete SAPAction for the current observation."""
    if action_id == "diagnose":
        return SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component=_target_component(obs),
            diagnosis=_infer_diagnosis(obs),
            reasoning="Diagnose the real high-priority incident before applying fixes.",
        )

    if action_id == "ignore":
        return SAPAction(
            action_type=ActionType.IGNORE,
            target_component="red_herring",
            reasoning="Ignore low-priority false-positive alert.",
        )

    if action_id == "escalate":
        return SAPAction(
            action_type=ActionType.ESCALATE,
            target_component="security",
            reasoning="Escalate unresolved incident to the responsible operations team.",
        )

    if action_id == "escalate:escalate_soc":
        ip = _attacker_ip(obs)
        reasoning = "Escalate contained brute force activity to SOC."
        if ip:
            reasoning = f"Escalate attacker IP {ip} to SOC after containment."
        return SAPAction(
            action_type=ActionType.ESCALATE,
            target_component="security",
            security_action="escalate_soc",
            reasoning=reasoning,
        )

    if not action_id.startswith("fix:"):
        raise ValueError(f"Unknown action id: {action_id}")

    fix_method = action_id.split(":", 1)[1]
    if fix_method == "restart_job":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            transaction_code="SM37",
            fix_method=FixMethod.RESTART_JOB,
            reasoning="Restart the aborted background job from SM37.",
        )
    if fix_method == "release_transport":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="transport",
            transaction_code="STMS",
            fix_method=FixMethod.RELEASE_TRANSPORT,
            reasoning="Release the stuck transport in STMS.",
        )
    if fix_method in {"block_ip", "reset_credentials"} and obs.task_id == "task_2_transport_security":
        security_action = "block_ip" if fix_method == "block_ip" else "reset_credentials"
        return SAPAction(
            action_type=ActionType.ESCALATE,
            target_component="security",
            fix_method=FixMethod(fix_method),
            security_action=security_action,
            reasoning=f"Apply security response {security_action} for the suspicious activity.",
        )
    if fix_method == "reconnect_db":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="db",
            transaction_code="DB13",
            fix_method=FixMethod.RECONNECT_DB,
            reasoning="Reconnect database services first to stabilize PRD.",
        )
    if fix_method == "clear_buffer":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="memory",
            transaction_code="SM50",
            fix_method=FixMethod.CLEAR_BUFFER,
            reasoning="Clear memory buffers after database connectivity is restored.",
        )
    if fix_method == "restart_icm":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="icm",
            transaction_code="SMICM",
            fix_method=FixMethod.RESTART_ICM,
            reasoning="Restart ICM after core services are stable.",
        )
    if fix_method == "block_ip":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="security",
            transaction_code="SM21",
            fix_method=FixMethod.BLOCK_IP,
            reasoning="Block the attacker IP from the security alert.",
        )
    if fix_method == "reset_credentials":
        return SAPAction(
            action_type=ActionType.FIX,
            target_component="security",
            transaction_code="SM21",
            fix_method=FixMethod.RESET_CREDENTIALS,
            reasoning="Reset compromised credentials from the security alert.",
        )
    if fix_method == "check_log":
        return SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs",
            transaction_code="SM21",
            fix_method=FixMethod.CHECK_LOG,
            reasoning="Check SM21 logs for supporting incident details.",
        )

    raise ValueError(f"Unsupported fix method: {fix_method}")


def available_action_ids(obs: SAPObservation, include_destructive: bool = False) -> list[str]:
    """Convert environment action strings into trainable symbolic actions."""
    action_ids: list[str] = []
    destructive = {"fix:delete_job", "fix:reimport_transport"}

    for raw in obs.available_actions:
        if raw in destructive and not include_destructive:
            continue
        if raw in {"diagnose", "ignore", "escalate"}:
            action_ids.append(raw)
        elif raw.startswith("fix:"):
            action_ids.append(raw)
        elif raw == "escalate:escalate_soc":
            action_ids.append(raw)

    # Task 3 can receive SOC credit before the final block_ip action ends the episode.
    if obs.task_id == "task_3_p1_incident" and "escalate:escalate_soc" not in action_ids:
        action_ids.append("escalate:escalate_soc")

    return action_ids


def encode_state(obs: SAPObservation) -> str:
    """Compress an observation into a stable tabular-learning state key."""
    history = " ".join(obs.episode_history)
    flags = {
        "diagnosed": "diagnose" in history,
        "restart_job": "restart_job" in history,
        "release_transport": "release_transport" in history,
        "reconnect_db": "reconnect_db" in history,
        "clear_buffer": "clear_buffer" in history,
        "restart_icm": "restart_icm" in history,
        "block_ip": "block_ip" in history,
        "escalate_soc": "escalate_soc" in history,
    }
    return json.dumps(
        {
            "task_id": obs.task_id,
            "step": min(obs.step_number, 6),
            "flags": flags,
        },
        sort_keys=True,
    )


QTable = dict[str, dict[str, float]]


def choose_action(
    q_table: QTable,
    state_key: str,
    action_ids: list[str],
    epsilon: float,
    rng: random.Random,
) -> str:
    if not action_ids:
        return "diagnose"
    if rng.random() < epsilon:
        return rng.choice(action_ids)

    values = q_table.get(state_key, {})
    best_value = max(values.get(action_id, 0.0) for action_id in action_ids)
    best_actions = [action_id for action_id in action_ids if values.get(action_id, 0.0) == best_value]
    return rng.choice(best_actions)


def train_policy(
    episodes: int,
    alpha: float,
    gamma: float,
    epsilon: float,
    min_epsilon: float,
    epsilon_decay: float,
    seed: int,
) -> QTable:
    rng = random.Random(seed)
    q_table: defaultdict[str, dict[str, float]] = defaultdict(dict)

    for episode in range(episodes):
        env = SAPBasisEnvironment()
        task_id = TASK_IDS[episode % len(TASK_IDS)]
        obs = env.reset(task_id)
        current_epsilon = max(min_epsilon, epsilon * (epsilon_decay ** episode))

        while True:
            state_key = encode_state(obs)
            action_ids = available_action_ids(obs)
            action_id = choose_action(q_table, state_key, action_ids, current_epsilon, rng)
            action = action_from_id(action_id, obs)
            next_obs, reward, done, _info = env.step(action)

            if done:
                final_score, _breakdown = env.grade()
                reward += final_score
                target = reward
            else:
                next_state_key = encode_state(next_obs)
                next_actions = available_action_ids(next_obs)
                next_best = max(
                    (q_table[next_state_key].get(next_action, 0.0) for next_action in next_actions),
                    default=0.0,
                )
                target = reward + gamma * next_best

            old_value = q_table[state_key].get(action_id, 0.0)
            q_table[state_key][action_id] = old_value + alpha * (target - old_value)
            obs = next_obs

            if done:
                break

    return {state: dict(values) for state, values in q_table.items()}


def greedy_policy(q_table: QTable) -> Callable[[SAPObservation], SAPAction]:
    def policy(obs: SAPObservation) -> SAPAction:
        state_key = encode_state(obs)
        action_ids = available_action_ids(obs)
        action_id = choose_action(q_table, state_key, action_ids, epsilon=0.0, rng=random.Random(0))
        return action_from_id(action_id, obs)

    return policy


def evaluate_policy(q_table: QTable, episodes_per_task: int) -> dict:
    policy = greedy_policy(q_table)
    task_scores: dict[str, list[float]] = {task_id: [] for task_id in TASK_IDS}

    for task_id in TASK_IDS:
        for _ in range(episodes_per_task):
            env = SAPBasisEnvironment()
            obs = env.reset(task_id)

            while True:
                action = policy(obs)
                obs, _reward, done, _info = env.step(action)
                if done:
                    final_score, _breakdown = env.grade()
                    task_scores[task_id].append(final_score)
                    break

    task_averages = {
        task_id: round(sum(scores) / len(scores), 4) if scores else 0.0
        for task_id, scores in task_scores.items()
    }
    overall = round(sum(task_averages.values()) / len(task_averages), 4)
    return {"task_averages": task_averages, "average_score": overall}


def save_artifact(artifact: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True))


def load_artifact(input_path: Path) -> dict:
    return json.loads(input_path.read_text())


def build_artifact(q_table: QTable, evaluation: dict, args: argparse.Namespace) -> dict:
    policy = {
        state: max(values.items(), key=lambda item: item[1])[0]
        for state, values in q_table.items()
        if values
    }
    return {
        "model_type": "tabular_q_learning",
        "environment": "sap-enterprise-ops-env",
        "training": {
            "episodes": args.episodes,
            "alpha": args.alpha,
            "gamma": args.gamma,
            "epsilon": args.epsilon,
            "min_epsilon": args.min_epsilon,
            "epsilon_decay": args.epsilon_decay,
            "seed": args.seed,
        },
        "evaluation": evaluation,
        "policy": policy,
        "q_table": q_table,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a tabular policy for sap-enterprise-ops-env.")
    parser.add_argument("--episodes", type=int, default=500, help="Number of training episodes.")
    parser.add_argument("--eval-episodes", type=int, default=50, help="Evaluation episodes per task.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write the trained policy JSON.")
    parser.add_argument("--input", type=Path, help="Existing trained policy JSON for --evaluate-only.")
    parser.add_argument("--evaluate-only", action="store_true", help="Load --input and evaluate without training.")
    parser.add_argument("--alpha", type=float, default=0.25, help="Q-learning update rate.")
    parser.add_argument("--gamma", type=float, default=0.90, help="Discount factor.")
    parser.add_argument("--epsilon", type=float, default=0.35, help="Initial exploration rate.")
    parser.add_argument("--min-epsilon", type=float, default=0.03, help="Minimum exploration rate.")
    parser.add_argument("--epsilon-decay", type=float, default=0.995, help="Per-episode exploration decay.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.evaluate_only:
        if args.input is None:
            raise SystemExit("--evaluate-only requires --input")
        artifact = load_artifact(args.input)
        q_table = artifact.get("q_table", {})
        evaluation = evaluate_policy(q_table, episodes_per_task=args.eval_episodes)
        print(json.dumps(evaluation, indent=2, sort_keys=True))
        return

    q_table = train_policy(
        episodes=args.episodes,
        alpha=args.alpha,
        gamma=args.gamma,
        epsilon=args.epsilon,
        min_epsilon=args.min_epsilon,
        epsilon_decay=args.epsilon_decay,
        seed=args.seed,
    )
    evaluation = evaluate_policy(q_table, episodes_per_task=args.eval_episodes)
    artifact = build_artifact(q_table, evaluation, args)

    save_artifact(artifact, args.output)

    print(f"Saved trained policy to {args.output}")
    print(json.dumps(evaluation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
