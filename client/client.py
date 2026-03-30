# client/client.py
"""
SAPBasisEnvClient — typed HTTP client for sap-enterprise-ops-env.
Use this to interact with the environment from any Python script.
"""
import httpx
from models.action import SAPAction
from models.observation import SAPObservation
from models.state import EpisodeState


class SAPBasisEnvClient:
    """
    Typed client for the SAP Enterprise Ops environment.

    Usage:
        client = SAPBasisEnvClient("http://localhost:7860")
        obs    = client.reset("task_1_job_failure")
        action = SAPAction(action_type="fix", ...)
        obs, reward, done, info = client.step(action)
        state  = client.state()
    """

    def __init__(self, base_url: str = "http://localhost:7860", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.client   = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ── CORE METHODS ─────────────────────────────────────────────

    def reset(self, task_id: str = "task_1_job_failure") -> SAPObservation:
        """Start a new episode. Returns initial observation."""
        r = self.client.post("/reset", json={"task_id": task_id})
        r.raise_for_status()
        data = r.json()
        return SAPObservation(**data["observation"])

    def step(self, action: SAPAction) -> tuple[SAPObservation, float, bool, dict]:
        """Take one action. Returns (observation, reward, done, info)."""
        r = self.client.post("/step", json={"action": action.model_dump()})
        r.raise_for_status()
        data = r.json()
        obs  = SAPObservation(**data["observation"])
        return obs, data["reward"], data["done"], data["info"]

    def state(self) -> EpisodeState:
        """Return current episode state."""
        r = self.client.get("/state")
        r.raise_for_status()
        return EpisodeState(**r.json())

    def tasks(self) -> list:
        """List all available tasks."""
        r = self.client.get("/tasks")
        r.raise_for_status()
        return r.json()["tasks"]

    def health(self) -> bool:
        """Check if environment server is running."""
        try:
            r = self.client.get("/health")
            return r.status_code == 200
        except Exception:
            return False

    # ── CONVENIENCE METHODS ──────────────────────────────────────

    def run_episode(
        self,
        task_id: str,
        policy_fn,
        max_steps: int = 12,
        verbose: bool = False,
    ) -> dict:
        """
        Run a complete episode using a policy function.

        Args:
            task_id:   Which task to run
            policy_fn: Function that takes SAPObservation → SAPAction
            max_steps: Maximum steps before forcing stop
            verbose:   Print step-by-step output

        Returns:
            dict with final_score, total_reward, steps_taken
        """
        obs          = self.reset(task_id)
        total_reward = 0.0
        final_score  = 0.0
        steps        = 0

        for _ in range(max_steps):
            action              = policy_fn(obs)
            obs, reward, done, info = self.step(action)
            total_reward       += reward
            steps              += 1

            if verbose:
                print(f"  Step {steps} | reward {reward:+.4f} | done {done}")

            if done:
                final_score = info.get("final_score", 0.0)
                break

        return {
            "task_id":      task_id,
            "final_score":  final_score,
            "total_reward": round(total_reward, 4),
            "steps_taken":  steps,
        }

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()