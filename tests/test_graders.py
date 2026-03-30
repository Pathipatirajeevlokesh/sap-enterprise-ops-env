# tests/test_graders.py
"""
Grader correctness tests.
Run with: python -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from models.action import SAPAction, ActionType, FixMethod
from server.tasks import grade_task1, grade_task2, grade_task3
from server.data import get_scenario


# ── TASK 1 GRADER TESTS ──────────────────────────────────────────

class TestTask1Grader:

    def setup_method(self):
        self.scenario = get_scenario("task_1_job_failure")
        # Force known values for deterministic testing
        self.scenario["root_cause"]           = "work_process_timeout"
        self.scenario["correct_fix"]          = "restart_job"
        self.scenario["correct_transaction"]  = "SM37"
        self.scenario["wrong_fixes"]          = ["delete_job", "ignore"]

    def test_perfect_score(self):
        """Agent diagnoses correctly AND fixes correctly → near 1.0"""
        actions = [
            SAPAction(
                action_type      = ActionType.DIAGNOSE,
                target_component = "background_jobs",
                diagnosis        = "work_process_timeout caused the abort",
                reasoning        = "Return code 4 indicates work process was killed"
            ),
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "background_jobs",
                transaction_code = "SM37",
                fix_method       = FixMethod.RESTART_JOB,
                reasoning        = "Restart the aborted job via SM37"
            ),
        ]
        score, breakdown = grade_task1(actions, self.scenario)
        assert score >= 0.85, f"Perfect actions should score >= 0.85, got {score}"
        assert breakdown["correct_fix"]  == True
        assert breakdown["correct_tx"]   == True
        assert breakdown["diagnosed"]    == True

    def test_fix_only_no_diagnosis(self):
        """Agent fixes correctly but skips diagnosis → partial score"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "background_jobs",
                transaction_code = "SM37",
                fix_method       = FixMethod.RESTART_JOB,
            ),
        ]
        score, breakdown = grade_task1(actions, self.scenario)
        assert 0.0 < score < 1.0
        assert breakdown["correct_fix"] == True
        assert breakdown["diagnosed"]   == False

    def test_wrong_transaction_code(self):
        """Right fix method but wrong transaction → partial credit"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "background_jobs",
                transaction_code = "SM21",  # Wrong TX
                fix_method       = FixMethod.RESTART_JOB,
            ),
        ]
        score, breakdown = grade_task1(actions, self.scenario)
        assert breakdown["correct_fix"] == True
        assert breakdown["correct_tx"]  == False
        assert score < 0.7

    def test_destructive_action_penalty(self):
        """delete_job should cause heavy penalty"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "background_jobs",
                transaction_code = "SM37",
                fix_method       = FixMethod.DELETE_JOB,
            ),
        ]
        score, breakdown = grade_task1(actions, self.scenario)
        assert breakdown["no_destructive"] == False
        assert score <= 0.0

    def test_wrong_fix_zero_score(self):
        """Completely wrong action → 0.0"""
        actions = [
            SAPAction(
                action_type      = ActionType.IGNORE,
                target_component = "background_jobs",
            ),
        ]
        score, breakdown = grade_task1(actions, self.scenario)
        assert score == 0.0

    def test_score_in_valid_range(self):
        """Score must always be between 0.0 and 1.0"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "background_jobs",
                transaction_code = "SM37",
                fix_method       = FixMethod.RESTART_JOB,
                diagnosis        = "work_process_timeout",
                reasoning        = "Clear evidence of timeout in SM21 log"
            ),
        ]
        score, _ = grade_task1(actions, self.scenario)
        assert 0.0 <= score <= 1.0


# ── TASK 2 GRADER TESTS ──────────────────────────────────────────

class TestTask2Grader:

    def setup_method(self):
        self.scenario = get_scenario("task_2_transport_security")
        self.scenario["correct_transport_fix"]  = "release_transport"
        self.scenario["correct_transaction"]    = "STMS"
        self.scenario["correct_security_action"] = "block_ip"

    def test_perfect_score(self):
        """Both transport fix AND security detection → ~1.0"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "transport",
                transaction_code = "STMS",
                fix_method       = FixMethod.RELEASE_TRANSPORT,
            ),
            SAPAction(
                action_type      = ActionType.ESCALATE,
                target_component = "security",
                security_action  = "block_ip",
                reasoning        = "Suspicious RFC call from external IP"
            ),
        ]
        score, breakdown = grade_task2(actions, self.scenario)
        assert score >= 0.90
        assert breakdown["transport_fixed"]    == True
        assert breakdown["correct_sec_action"] == True

    def test_transport_only(self):
        """Only transport fixed → 0.60 max"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "transport",
                transaction_code = "STMS",
                fix_method       = FixMethod.RELEASE_TRANSPORT,
            ),
        ]
        score, breakdown = grade_task2(actions, self.scenario)
        assert breakdown["transport_fixed"]   == True
        assert breakdown["security_detected"] == False
        assert score <= 0.65

    def test_security_only(self):
        """Only security detected → 0.40 max"""
        actions = [
            SAPAction(
                action_type     = ActionType.ESCALATE,
                target_component = "security",
                security_action  = "block_ip",
            ),
        ]
        score, breakdown = grade_task2(actions, self.scenario)
        assert breakdown["transport_fixed"]    == False
        assert breakdown["correct_sec_action"] == True
        assert score <= 0.45

    def test_cascade_penalty(self):
        """reimport_transport triggers cascade penalty"""
        actions = [
            SAPAction(
                action_type      = ActionType.FIX,
                target_component = "transport",
                transaction_code = "STMS",
                fix_method       = FixMethod.REIMPORT_TRANSPORT,
            ),
        ]
        score, breakdown = grade_task2(actions, self.scenario)
        assert breakdown["cascade_triggered"] == True
        assert score < 0.20

    def test_score_in_valid_range(self):
        for fix in [FixMethod.RELEASE_TRANSPORT, FixMethod.REIMPORT_TRANSPORT]:
            actions = [SAPAction(
                action_type=ActionType.FIX,
                target_component="transport",
                fix_method=fix
            )]
            score, _ = grade_task2(actions, self.scenario)
            assert 0.0 <= score <= 1.0


# ── TASK 3 GRADER TESTS ──────────────────────────────────────────

class TestTask3Grader:

    def setup_method(self):
        self.scenario = get_scenario("task_3_p1_incident")
        self.scenario["correct_order"] = [
            "reconnect_db", "clear_buffer",
            "restart_icm", "block_ip", "escalate_soc"
        ]
        self.scenario["attacker_ip"] = "192.168.4.21"

    def test_all_components_resolved(self):
        """All 7 grader components resolved → high score"""
        actions = [
            SAPAction(action_type=ActionType.FIX,
                target_component="db", fix_method=FixMethod.RECONNECT_DB),
            SAPAction(action_type=ActionType.FIX,
                target_component="memory", fix_method=FixMethod.CLEAR_BUFFER),
            SAPAction(action_type=ActionType.FIX,
                target_component="icm", fix_method=FixMethod.RESTART_ICM),
            SAPAction(action_type=ActionType.FIX,
                target_component="security", fix_method=FixMethod.BLOCK_IP),
            SAPAction(action_type=ActionType.ESCALATE,
                target_component="security", security_action="escalate_soc",
                reasoning="Attacker IP 192.168.4.21 seen earlier in episode"),
        ]
        score, breakdown = grade_task3(actions, self.scenario)
        assert score >= 0.70
        assert breakdown["db_fixed"]         == True
        assert breakdown["memory_fixed"]     == True
        assert breakdown["icm_restarted"]    == True
        assert breakdown["attacker_blocked"] == True
        assert breakdown["soc_escalated"]    == True
        assert breakdown["correct_order"]    == True
        assert breakdown["memory_test_passed"] == True

    def test_cascade_penalty_buffer_before_db(self):
        """clear_buffer before reconnect_db triggers cascade penalty"""
        actions = [
            SAPAction(action_type=ActionType.FIX,
                target_component="memory", fix_method=FixMethod.CLEAR_BUFFER),
        ]
        score, breakdown = grade_task3(actions, self.scenario)
        assert breakdown["cascade_triggered"] == True

    def test_db_fixed_no_cascade(self):
        """DB fixed first then buffer → no cascade"""
        actions = [
            SAPAction(action_type=ActionType.FIX,
                target_component="db", fix_method=FixMethod.RECONNECT_DB),
            SAPAction(action_type=ActionType.FIX,
                target_component="memory", fix_method=FixMethod.CLEAR_BUFFER),
        ]
        score, breakdown = grade_task3(actions, self.scenario)
        assert breakdown["cascade_triggered"] == False
        assert breakdown["db_fixed"]          == True
        assert breakdown["memory_fixed"]      == True

    def test_memory_test_ip_detection(self):
        """Agent mentions attacker IP in reasoning → memory test passed"""
        actions = [
            SAPAction(action_type=ActionType.ESCALATE,
                target_component="security", security_action="escalate_soc",
                reasoning="Attacker IP 192.168.4.21 matches earlier recon alert"),
        ]
        score, breakdown = grade_task3(actions, self.scenario)
        assert breakdown["memory_test_passed"] == True

    def test_empty_actions_zero_score(self):
        """No actions taken → 0.0"""
        score, breakdown = grade_task3([], self.scenario)
        assert score == 0.0
        assert breakdown["db_fixed"]      == False
        assert breakdown["memory_fixed"]  == False
        assert breakdown["soc_escalated"] == False

    def test_score_always_in_range(self):
        """Score must always be 0.0–1.0 regardless of actions"""
        actions = [
            SAPAction(action_type=ActionType.FIX,
                target_component="memory", fix_method=FixMethod.CLEAR_BUFFER),
            SAPAction(action_type=ActionType.FIX,
                target_component="memory", fix_method=FixMethod.CLEAR_BUFFER),
            SAPAction(action_type=ActionType.FIX,
                target_component="memory", fix_method=FixMethod.CLEAR_BUFFER),
        ]
        score, _ = grade_task3(actions, self.scenario)
        assert 0.0 <= score <= 1.0