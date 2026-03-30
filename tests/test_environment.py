# tests/test_environment.py
"""
Environment core tests — reset / step / state / grade.
Run with: python -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from models.action import SAPAction, ActionType, FixMethod
from server.environment import SAPBasisEnvironment


# ── FIXTURES ─────────────────────────────────────────────────────

@pytest.fixture
def env():
    return SAPBasisEnvironment()


# ── RESET TESTS ──────────────────────────────────────────────────

class TestReset:

    def test_reset_returns_observation(self, env):
        obs = env.reset("task_1_job_failure")
        assert obs is not None
        assert obs.system_id == "PRD"

    def test_reset_has_alerts(self, env):
        obs = env.reset("task_1_job_failure")
        assert len(obs.alert_queue) >= 2  # at least 1 real + 1 red herring

    def test_reset_has_red_herring(self, env):
        obs = env.reset("task_1_job_failure")
        red_herrings = [a for a in obs.alert_queue if a.is_red_herring]
        assert len(red_herrings) == 1

    def test_reset_sla_full(self, env):
        obs = env.reset("task_1_job_failure")
        assert obs.sla_seconds_remaining == 300

    def test_reset_task2_sla(self, env):
        obs = env.reset("task_2_transport_security")
        assert obs.sla_seconds_remaining == 480

    def test_reset_task3_sla(self, env):
        obs = env.reset("task_3_p1_incident")
        assert obs.sla_seconds_remaining == 600

    def test_reset_step_number_zero(self, env):
        obs = env.reset("task_1_job_failure")
        assert obs.step_number == 0

    def test_reset_task3_has_multiple_alerts(self, env):
        obs = env.reset("task_3_p1_incident")
        assert len(obs.alert_queue) >= 4  # DB + memory + security + red herring

    def test_reset_clears_previous_episode(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        env.step(action)
        # Reset again — should be clean
        obs = env.reset("task_1_job_failure")
        assert obs.step_number == 0
        assert obs.sla_seconds_remaining == 300

    def test_reset_invalid_task_raises(self, env):
        with pytest.raises(ValueError):
            env.reset("task_999_nonexistent")


# ── STEP TESTS ───────────────────────────────────────────────────

class TestStep:

    def test_step_returns_four_values(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs",
            diagnosis="work process timeout"
        )
        result = env.step(action)
        assert len(result) == 4  # obs, reward, done, info

    def test_step_increments_step_number(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs"
        )
        obs, _, _, _ = env.step(action)
        assert obs.step_number == 1

    def test_step_decays_sla(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs"
        )
        obs, _, _, _ = env.step(action)
        assert obs.sla_seconds_remaining < 300

    def test_step_reward_is_float(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        _, reward, _, _ = env.step(action)
        assert isinstance(reward, float)

    def test_step_reward_in_range(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        _, reward, _, _ = env.step(action)
        assert -0.75 <= reward <= 1.10

    def test_step_done_on_correct_fix_task1(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        _, _, done, info = env.step(action)
        assert done == True
        assert info["termination_reason"] == "solved"

    def test_step_not_done_on_diagnose(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs",
            diagnosis="timeout issue"
        )
        _, _, done, _ = env.step(action)
        assert done == False

    def test_step_info_has_breakdown(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs"
        )
        _, _, _, info = env.step(action)
        assert "reward_breakdown" in info
        assert "sla_remaining"    in info
        assert "step"             in info

    def test_step_without_reset_raises(self, env):
        with pytest.raises(RuntimeError):
            env.step(SAPAction(
                action_type=ActionType.DIAGNOSE,
                target_component="background_jobs"
            ))

    def test_step_after_done_raises(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        env.step(action)  # This solves task 1
        with pytest.raises(RuntimeError):
            env.step(action)  # Should raise — episode is done


# ── STATE TESTS ──────────────────────────────────────────────────

class TestState:

    def test_state_returns_episode_state(self, env):
        env.reset("task_1_job_failure")
        state = env.state()
        assert state.episode_id is not None
        assert state.task_id == "task_1_job_failure"

    def test_state_without_reset_raises(self, env):
        with pytest.raises(RuntimeError):
            env.state()

    def test_state_tracks_steps(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.DIAGNOSE,
            target_component="background_jobs"
        )
        env.step(action)
        state = env.state()
        assert state.step_number == 1

    def test_state_done_after_solve(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        env.step(action)
        state = env.state()
        assert state.done == True
        assert state.termination_reason == "solved"


# ── GRADE TESTS ──────────────────────────────────────────────────

class TestGrade:

    def test_grade_returns_score_and_breakdown(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        env.step(action)
        score, breakdown = env.grade()
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert "final_score" in breakdown

    def test_grade_score_matches_breakdown(self, env):
        env.reset("task_1_job_failure")
        action = SAPAction(
            action_type=ActionType.FIX,
            target_component="background_jobs",
            fix_method=FixMethod.RESTART_JOB,
            transaction_code="SM37"
        )
        env.step(action)
        score, breakdown = env.grade()
        assert score == breakdown["final_score"]