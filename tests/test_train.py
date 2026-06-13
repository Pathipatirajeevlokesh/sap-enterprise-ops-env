import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.environment import SAPBasisEnvironment
from train import (
    action_from_id,
    available_action_ids,
    build_artifact,
    choose_action,
    encode_state,
    evaluate_policy,
    load_artifact,
    save_artifact,
    train_policy,
)


def test_training_produces_policy_for_all_tasks():
    q_table = train_policy(
        episodes=30,
        alpha=0.25,
        gamma=0.90,
        epsilon=0.35,
        min_epsilon=0.03,
        epsilon_decay=0.995,
        seed=7,
    )

    learned_tasks = {json.loads(state)["task_id"] for state in q_table}
    assert learned_tasks == {
        "task_1_job_failure",
        "task_2_transport_security",
        "task_3_p1_incident",
    }
    assert all(actions for actions in q_table.values())


def test_trained_policy_runs_without_errors():
    q_table = train_policy(
        episodes=40,
        alpha=0.25,
        gamma=0.90,
        epsilon=0.35,
        min_epsilon=0.03,
        epsilon_decay=0.995,
        seed=11,
    )
    results = evaluate_policy(q_table, episodes_per_task=2)

    assert len(results["task_averages"]) == 3
    assert results["average_score"] >= 0.0


def test_policy_round_trip(tmp_path):
    q_table = train_policy(
        episodes=10,
        alpha=0.25,
        gamma=0.90,
        epsilon=0.35,
        min_epsilon=0.03,
        epsilon_decay=0.995,
        seed=3,
    )
    path = tmp_path / "policy.json"
    evaluation = evaluate_policy(q_table, episodes_per_task=1)

    artifact = build_artifact(
        q_table,
        evaluation,
        argparse_namespace(
            episodes=10,
            alpha=0.25,
            gamma=0.90,
            epsilon=0.35,
            min_epsilon=0.03,
            epsilon_decay=0.995,
            seed=3,
        ),
    )
    save_artifact(artifact, path)
    loaded = load_artifact(path)

    assert loaded == artifact
    payload = json.loads(path.read_text())
    assert payload["model_type"] == "tabular_q_learning"


def test_policy_can_solve_task1_episode():
    env = SAPBasisEnvironment()
    obs = env.reset("task_1_job_failure")
    q_table = {
        encode_state(obs): {"diagnose": 1.0},
    }

    diagnose = action_from_id("diagnose", obs)
    obs, _, done, _ = env.step(diagnose)
    assert done is False

    q_table[encode_state(obs)] = {"fix:restart_job": 1.0}

    for _ in range(5):
        state_key = encode_state(obs)
        action_id = choose_action(
            q_table,
            state_key,
            available_action_ids(obs),
            epsilon=0.0,
            rng=__import__("random").Random(0),
        )
        action = action_from_id(action_id, obs)
        obs, _, done, info = env.step(action)
        if done:
            break

    assert done is True
    assert info["termination_reason"] == "solved"


def argparse_namespace(**kwargs):
    class Namespace:
        pass

    namespace = Namespace()
    for key, value in kwargs.items():
        setattr(namespace, key, value)
    return namespace
