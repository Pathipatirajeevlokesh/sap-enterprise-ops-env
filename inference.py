"""
inference.py
============
Baseline agent for sap-enterprise-ops-env.
Mandatory submission file — must be in root directory.

Environment variables required:
    API_BASE_URL   The API endpoint for the LLM
    MODEL_NAME     The model identifier to use
    HF_TOKEN       Your Hugging Face / API key
"""

import os
import json
import time
import threading
import subprocess
import sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ───────────────────────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:7860")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.getenv("MODEL_NAME",   "meta-llama/Llama-3.3-70B-Instruct")
HF_TOKEN     = os.getenv("HF_TOKEN",     "")
MAX_STEPS    = 12
TEMPERATURE  = 0.2

# ── LLM CLIENT ───────────────────────────────────────────────────

llm = OpenAI(
    base_url = LLM_BASE_URL,
    api_key  = HF_TOKEN or "dummy",
)

# ── ENV CLIENT ───────────────────────────────────────────────────

import httpx
env_client = httpx.Client(base_url=API_BASE_URL, timeout=30)


def env_reset(task_id: str) -> dict:
    r = env_client.post("/reset", json={"task_id": task_id})
    r.raise_for_status()
    return r.json()


def env_step(action: dict) -> dict:
    r = env_client.post("/step", json={"action": action})
    r.raise_for_status()
    return r.json()


def env_health() -> bool:
    try:
        r = env_client.get("/health")
        return r.status_code == 200
    except Exception:
        return False


# ── SYSTEM PROMPT ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert SAP Basis Administrator.
You will receive a JSON observation describing a SAP production system incident.
Your job is to diagnose and resolve the incident.

You MUST respond with a single valid JSON action object.
No explanation outside the JSON. No markdown fences.

Action format:
{
  "action_type": "diagnose" | "fix" | "escalate" | "ignore",
  "target_component": "<component name>",
  "transaction_code": "<SAP TX code or null>",
  "fix_method": "<fix method or null>",
  "diagnosis": "<your diagnosis or null>",
  "security_action": "<security action or null>",
  "reasoning": "<your reasoning>"
}

Valid fix_methods:
restart_job, delete_job, release_transport, reimport_transport,
restart_icm, clear_buffer, reconnect_db, block_ip,
reset_credentials, escalate_soc, check_log

Valid transaction codes: SM37, STMS, DB13, SM21, SMICM

Rules:
- NEVER delete_job (destructive)
- NEVER reimport_transport (destructive)
- NEVER target QAS or DEV systems
- Always diagnose before fixing on first step
- For security threats: escalate with security_action
- For Task 3: fix DB first, then memory, then ICM, then block attacker
"""


# ── AGENT LOOP ───────────────────────────────────────────────────

def obs_to_prompt(obs: dict) -> str:
    """Convert observation dict to a clear prompt for the LLM."""
    alerts = obs.get("alert_queue", [])
    real_alerts = [a for a in alerts if not a.get("is_red_herring")]
    health = obs.get("system_health", {})
    history = obs.get("episode_history", [])

    prompt = f"""SYSTEM: {obs.get('system_id', 'PRD')}
TASK: {obs.get('task_description', '')}
SLA REMAINING: {obs.get('sla_seconds_remaining', 0)} seconds
USERS AFFECTED: {obs.get('users_affected', 0)}
STEP: {obs.get('step_number', 0)}

SYSTEM HEALTH:
- CPU: {health.get('cpu_pct')}%
- Memory: {health.get('memory_pct')}%
- DB Connections: {health.get('db_connections')}
- Free Work Processes: {health.get('work_processes_free')}
- Response Time: {health.get('response_time_ms')}ms

ALERTS ({len(alerts)} total, {len(real_alerts)} real):
"""
    for a in alerts:
        tag = " [POSSIBLE FALSE POSITIVE]" if a.get("is_red_herring") else ""
        prompt += f"  [{a['priority'].upper()}] {a['error_code']}: {a['message']}{tag}\n"

    if history:
        prompt += f"\nPREVIOUS STEPS:\n"
        for h in history[-3:]:
            prompt += f"  {h}\n"

    prompt += f"\nAVAILABLE ACTIONS: {obs.get('available_actions', [])}"
    prompt += "\n\nRespond with ONE JSON action object only."

    return prompt


def get_llm_action(obs: dict) -> dict:
    """Ask LLM for next action given observation."""
    prompt = obs_to_prompt(obs)
    try:
        response = llm.chat.completions.create(
            model       = MODEL_NAME,
            temperature = TEMPERATURE,
            max_tokens  = 300,
            messages    = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        action = json.loads(raw.strip())
        return action

    except Exception as e:
        print(f"    LLM error: {e} — using fallback action")
        return {
            "action_type":      "diagnose",
            "target_component": "background_jobs",
            "transaction_code": None,
            "fix_method":       None,
            "diagnosis":        "Fallback: unable to parse LLM response",
            "security_action":  None,
            "reasoning":        "LLM call failed, using safe fallback",
        }


def run_task(task_id: str) -> dict:
    """Run one full episode for a given task. Returns result dict."""
    print(f"\n{'='*55}")
    print(f"  TASK: {task_id}")
    print(f"{'='*55}")

    # Reset environment
    reset_resp = env_reset(task_id)
    obs        = reset_resp["observation"]

    total_reward = 0.0
    final_score  = 0.0
    steps_taken  = 0
    done         = False

    start_time = time.time()

    for step in range(MAX_STEPS):
        if done:
            break

        print(f"\n  Step {step+1} | SLA: {obs['sla_seconds_remaining']}s "
              f"| Alerts: {len(obs['alert_queue'])}")

        # Get action from LLM
        action = get_llm_action(obs)
        print(f"  Action: {action.get('action_type')} → "
              f"{action.get('fix_method') or action.get('diagnosis', '')[:40]}")

        # Take step
        step_resp    = env_step(action)
        obs          = step_resp["observation"]
        reward       = step_resp["reward"]
        done         = step_resp["done"]
        total_reward += reward
        steps_taken  += 1

        print(f"  Reward: {reward:+.4f} | Done: {done}")

        if done:
            final_score = step_resp.get("final_score", 0.0)
            breakdown   = step_resp.get("grade_breakdown", {})
            reason      = step_resp["info"].get("termination_reason", "unknown")
            print(f"\n  EPISODE ENDED: {reason}")
            print(f"  Final Score:   {final_score:.4f}")
            print(f"  Grade:         {breakdown}")

    elapsed = time.time() - start_time

    return {
        "task_id":      task_id,
        "final_score":  final_score,
        "total_reward": round(total_reward, 4),
        "steps_taken":  steps_taken,
        "elapsed_sec":  round(elapsed, 2),
    }


# ── SERVER LAUNCHER ──────────────────────────────────────────────

def start_server():
    """Start the FastAPI server in background thread."""
    def _run():
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "server.app:app",
            "--host", "0.0.0.0",
            "--port", "7860",
            "--log-level", "error",
        ])
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Wait for server to be ready
    for _ in range(20):
        if env_health():
            return True
        time.sleep(1)
    return False


# ── MAIN ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  SAP ENTERPRISE OPS ENV — BASELINE INFERENCE")
    print("="*55)
    print(f"  Model:    {MODEL_NAME}")
    print(f"  Env URL:  {API_BASE_URL}")

    # Start server if not already running
    if not env_health():
        print("\n  Starting environment server...")
        if not start_server():
            print("  ERROR: Server failed to start.")
            sys.exit(1)
    print("  Server: READY\n")

    # Run all 3 tasks
    TASKS = [
        "task_1_job_failure",
        "task_2_transport_security",
        "task_3_p1_incident",
    ]

    results = []
    total_start = time.time()

    for task_id in TASKS:
        result = run_task(task_id)
        results.append(result)

    total_elapsed = time.time() - total_start

    # ── FINAL REPORT ─────────────────────────────────────────────
    print("\n" + "="*55)
    print("  BASELINE RESULTS SUMMARY")
    print("="*55)
    print(f"  {'Task':<35} {'Score':>7} {'Steps':>6}")
    print(f"  {'-'*50}")
    for r in results:
        print(f"  {r['task_id']:<35} {r['final_score']:>7.4f} {r['steps_taken']:>6}")

    avg_score = sum(r["final_score"] for r in results) / len(results)
    print(f"  {'-'*50}")
    print(f"  {'AVERAGE SCORE':<35} {avg_score:>7.4f}")
    print(f"\n  Total elapsed: {total_elapsed:.1f}s")
    print("="*55)

    # Save results to file
    with open("baseline_results.json", "w") as f:
        json.dump({
            "model":         MODEL_NAME,
            "results":       results,
            "average_score": round(avg_score, 4),
            "total_elapsed": round(total_elapsed, 2),
        }, f, indent=2)

    print("\n  Results saved to baseline_results.json")
    print("  Run complete. ✓\n")