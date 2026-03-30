# server/environment.py
import uuid
from datetime import datetime

from models.action import SAPAction, ActionType, FixMethod
from models.observation import SAPObservation, SystemHealth, SAPAlert, LogEntry, BackgroundJob
from models.state import EpisodeState
from server.data import get_scenario, get_red_herring
from server.reward import compute_reward
from server.cascade import check_cascade
from server.tasks import get_task, grade_episode


class SAPBasisEnvironment:
    """
    Core OpenEnv environment.
    Implements reset() / step() / state() pattern.
    """

    def __init__(self):
        self.scenario        = None
        self.episode_state   = None
        self.actions_taken   = []
        self.fixes_taken     = []
        self.current_alerts  = []
        self.task_meta       = None

    # ── RESET ────────────────────────────────────────────────────

    def reset(self, task_id: str = "task_1_job_failure") -> SAPObservation:
        """Start a fresh episode. Returns initial observation."""

        # Load scenario and task metadata
        self.scenario      = get_scenario(task_id)
        self.task_meta     = get_task(task_id)
        self.actions_taken = []
        self.fixes_taken   = []

        # Build initial alert queue
        self.current_alerts = self._build_initial_alerts()

        # Initialise episode state
        self.episode_state = EpisodeState(
            episode_id          = str(uuid.uuid4())[:8],
            task_id             = task_id,
            step_number         = 0,
            max_steps           = self.task_meta["max_steps"],
            done                = False,
            sla_total_seconds   = self.task_meta["sla_seconds"],
            sla_seconds_remaining = self.task_meta["sla_seconds"],
            sla_breached        = False,
            current_reward      = 0.0,
            actions_taken       = [],
            episode_history     = [],
            termination_reason  = None,
        )

        return self._build_observation()

    # ── STEP ─────────────────────────────────────────────────────

    def step(self, action: SAPAction) -> tuple[SAPObservation, float, bool, dict]:
        """
        Agent takes an action.
        Returns (observation, reward, done, info)
        """

        if self.episode_state is None:
            raise RuntimeError("No active episode. Call reset() first.")
        if self.episode_state.done:
            raise RuntimeError("Episode is done. Call reset() first.")

        # Advance step counter
        self.episode_state.step_number += 1

        # Decay SLA — lose 30-60 seconds per step
        sla_cost = 45 + (self.episode_state.step_number * 5)
        self.episode_state.sla_seconds_remaining = max(
            0,
            self.episode_state.sla_seconds_remaining - sla_cost
        )

        # Record action
        self.actions_taken.append(action)
        self.episode_state.actions_taken.append(action.action_type)

        if action.fix_method:
            self.fixes_taken.append(action.fix_method)

        # Compute reward
        reward, breakdown = compute_reward(
            action         = action,
            scenario       = self.scenario,
            step_number    = self.episode_state.step_number,
            sla_total      = self.episode_state.sla_total_seconds,
            sla_remaining  = self.episode_state.sla_seconds_remaining,
            previous_actions = self.fixes_taken,
        )

        self.episode_state.current_reward += reward

        # Check cascade
        cascade_alert = None
        if action.fix_method:
            cascade_alert = check_cascade(
                fix_method      = action.fix_method,
                task_id         = self.scenario["task_id"],
                previous_fixes  = self.fixes_taken,
            )
            if cascade_alert:
                self.current_alerts.append(cascade_alert)
                self.episode_state.cascade_triggered = True

        # Update episode history
        history_entry = self._summarise_action(action, reward, cascade_alert)
        self.episode_state.episode_history.append(history_entry)

        # Check done conditions
        done, reason = self._check_done(action)
        self.episode_state.done = done
        self.episode_state.termination_reason = reason

        if self.episode_state.sla_seconds_remaining <= 0:
            self.episode_state.sla_breached = True

        # Build info dict
        info = {
            "reward_breakdown":  breakdown,
            "cascade_triggered": cascade_alert is not None,
            "cascade_alert":     cascade_alert,
            "sla_remaining":     self.episode_state.sla_seconds_remaining,
            "step":              self.episode_state.step_number,
            "termination_reason": reason,
        }

        return self._build_observation(), reward, done, info

    # ── STATE ────────────────────────────────────────────────────

    def state(self) -> EpisodeState:
        """Return current episode state."""
        if self.episode_state is None:
            raise RuntimeError("No active episode. Call reset() first.")
        return self.episode_state

    # ── GRADE ────────────────────────────────────────────────────

    def grade(self) -> tuple[float, dict]:
        """Grade the completed episode. Call after done=True."""
        return grade_episode(
            task_id  = self.scenario["task_id"],
            actions  = self.actions_taken,
            scenario = self.scenario,
        )

    # ── PRIVATE HELPERS ──────────────────────────────────────────

    def _build_initial_alerts(self) -> list:
        """Build alert queue from scenario + inject red herring."""
        alerts = []
        task_id = self.scenario["task_id"]

        if task_id == "task_1_job_failure":
            alerts.append({
                "alert_id":      self.scenario["incident_id"],
                "component":     "Background Processing",
                "error_code":    self.scenario["error_code"],
                "priority":      "high",
                "message":       self.scenario["alert_message"],
                "is_red_herring": False,
            })

        elif task_id == "task_2_transport_security":
            alerts.append({
                "alert_id":      self.scenario["incident_id"],
                "component":     "Transport Management",
                "error_code":    self.scenario["transport_error"],
                "priority":      "high",
                "message":       self.scenario["transport_alert_message"],
                "is_red_herring": False,
            })
            alerts.append({
                "alert_id":      f"SEC-{self.scenario['incident_id']}",
                "component":     "Security",
                "error_code":    self.scenario["security_threat"].upper(),
                "priority":      "high",
                "message":       self.scenario["security_alert_message"],
                "is_red_herring": False,
            })

        elif task_id == "task_3_p1_incident":
            alerts.append({
                "alert_id":  f"DB-{self.scenario['incident_id']}",
                "component": "Database",
                "error_code": self.scenario["db_error"],
                "priority":  "critical",
                "message":   self.scenario["db_alert_message"],
                "is_red_herring": False,
            })
            alerts.append({
                "alert_id":  f"MEM-{self.scenario['incident_id']}",
                "component": "Memory Management",
                "error_code": self.scenario["memory_error"],
                "priority":  "critical",
                "message":   self.scenario["memory_alert_message"],
                "is_red_herring": False,
            })
            alerts.append({
                "alert_id":  f"SEC-{self.scenario['incident_id']}",
                "component": "Security",
                "error_code": self.scenario["security_error"],
                "priority":  "critical",
                "message":   self.scenario["security_alert_message"],
                "is_red_herring": False,
            })

        # Inject red herring
        alerts.append(get_red_herring())
        return alerts

    def _build_observation(self) -> SAPObservation:
        """Build the observation object from current state."""
        s  = self.scenario
        es = self.episode_state

        # System health
        health_data = s["system_health"]
        health = SystemHealth(
            cpu_pct             = health_data["cpu_pct"],
            memory_pct          = health_data["memory_pct"],
            db_connections      = health_data["db_connections"],
            work_processes_free = health_data["work_processes_free"],
            response_time_ms    = health_data["response_time_ms"],
        )

        # Alerts
        alert_objects = [
            SAPAlert(
                alert_id        = a["alert_id"],
                component       = a["component"],
                error_code      = a["error_code"],
                priority        = a["priority"],
                message         = a["message"],
                is_red_herring  = a.get("is_red_herring", False),
            )
            for a in self.current_alerts
        ]

        # SM21 log
        sm21 = [
            LogEntry(
                timestamp = s["timestamp"],
                severity  = "ERROR",
                message   = s.get("sm21_message", s.get("db_alert_message", "System error detected"))
            )
        ]

        # SM37 background jobs
        jobs = [
            BackgroundJob(
                job_name    = s.get("job_name", "SAP_BATCH_JOB"),
                client_id   = s.get("client_id", "100"),
                status      = "ABORTED",
                return_code = s.get("return_code", 4),
                start_time  = s["timestamp"],
                end_time    = None,
            )
        ]

        # Available actions based on task
        available = self._get_available_actions()

        return SAPObservation(
            system_id             = s["system_id"],
            system_health         = health,
            alert_queue           = alert_objects,
            sm21_log              = sm21,
            sm37_jobs             = jobs,
            sla_seconds_remaining = es.sla_seconds_remaining,
            users_affected        = s["users_affected"],
            episode_history       = es.episode_history,
            task_id               = es.task_id,
            task_description      = self.task_meta["description"],
            available_actions     = available,
            step_number           = es.step_number,
        )

    def _get_available_actions(self) -> list[str]:
        """Return valid action strings for current task."""
        base = ["diagnose", "escalate", "ignore"]
        task_id = self.scenario["task_id"]

        if task_id == "task_1_job_failure":
            return base + ["fix:restart_job", "fix:delete_job", "fix:check_log"]
        elif task_id == "task_2_transport_security":
            return base + [
                "fix:release_transport", "fix:reimport_transport",
                "fix:block_ip", "fix:reset_credentials"
            ]
        elif task_id == "task_3_p1_incident":
            return base + [
                "fix:reconnect_db", "fix:clear_buffer",
                "fix:restart_icm", "fix:block_ip",
                "fix:reset_credentials", "escalate:escalate_soc"
            ]
        return base

    def _check_done(self, action: SAPAction) -> tuple[bool, str]:
        """Check if episode should end."""
        es = self.episode_state

        # SLA breach
        if es.sla_seconds_remaining <= 0:
            return True, "sla_breach"

        # Max steps reached
        if es.step_number >= es.max_steps:
            return True, "max_steps"

        # Destructive action ends episode
        if action.fix_method == FixMethod.DELETE_JOB:
            return True, "destructive_action"

        # Task solved check
        task_id = self.scenario["task_id"]
        fixes   = self.fixes_taken

        if task_id == "task_1_job_failure":
            if FixMethod.RESTART_JOB in fixes:
                return True, "solved"

        elif task_id == "task_2_transport_security":
            transport_done = FixMethod.RELEASE_TRANSPORT in fixes
            security_done  = (
                FixMethod.BLOCK_IP in fixes or
                FixMethod.RESET_CREDENTIALS in fixes
            )
            if transport_done and security_done:
                return True, "solved"

        elif task_id == "task_3_p1_incident":
            required = [
                FixMethod.RECONNECT_DB,
                FixMethod.CLEAR_BUFFER,
                FixMethod.RESTART_ICM,
                FixMethod.BLOCK_IP,
            ]
            if all(f in fixes for f in required):
                return True, "solved"

        return False, None

    def _summarise_action(
        self, action: SAPAction, reward: float, cascade: dict | None
    ) -> str:
        """Build a one-line history entry for this step."""
        summary = (
            f"Step {self.episode_state.step_number}: "
            f"{action.action_type} on {action.target_component} "
            f"→ reward {reward:+.3f}"
        )
        if cascade:
            summary += f" [CASCADE: {cascade['error_code']}]"
        return summary