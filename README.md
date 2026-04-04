---
title: SAP Enterprise Ops Env
emoji: 🏭
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
tags:
  - openenv
  - sap
  - enterprise
  - rl-environment
  - basis
  - incident-response
---

# sap-enterprise-ops-env

> An OpenEnv-compliant RL environment where an AI agent acts as an SAP Basis Administrator resolving production incidents under SLA pressure.

**Team:** BasisForce — Rajeev Lokesh & Vignesh P
**Hackathon:** Scaler × Meta × Hugging Face OpenEnv Hackathon 2026

---

## Overview

SAP ERP systems power 77% of global transaction revenue across banking, manufacturing, healthcare, and logistics. When SAP production systems fail, companies lose $300,000–$1M per hour.

`sap-enterprise-ops-env` places an AI agent in the role of an on-call SAP Basis Administrator. The agent receives a live dashboard of system health metrics, alert queues, SM21 logs, and an SLA countdown — and must triage, diagnose, and resolve production incidents before SLA breach.

This is the **first SAP Basis operations environment** in the OpenEnv ecosystem.

---

## Key Features

| Feature | Description |
|---|---|
| 🔄 Dynamic episodes | No two episodes identical — IPs, timestamps, job names all randomise |
| 💥 Cascading failures | Wrong fix spawns new alerts, testing causal reasoning |
| ⏱️ SLA decay reward | Reward degrades over time, mirroring real enterprise pressure |
| 🎭 Red herring alerts | One false positive per episode penalises pattern matching |
| 🧠 Agent memory test | Task 3 references attacker IP from earlier in episode |
| 📊 Rich partial rewards | Credit for correct diagnosis even if fix is wrong |

---

## Environment Description

The agent operates on a simulated SAP production system (PRD). Each episode loads one of three task scenarios with increasing difficulty. The agent observes the system state and must select appropriate SAP Basis actions to restore system health before the SLA timer expires.

---

## Action Space
```json
{
  "action_type": "diagnose | fix | escalate | ignore",
  "target_component": "background_jobs | transport | db | security | memory",
  "transaction_code": "SM37 | STMS | DB13 | SM21 | SMICM",
  "fix_method": "restart_job | release_transport | reconnect_db | clear_buffer | restart_icm | block_ip | reset_credentials | escalate_soc",
  "diagnosis": "agent stated root cause",
  "security_action": "block_ip | reset_credentials | escalate_soc",
  "reasoning": "agent explanation — used for partial reward scoring"
}
```

---

## Observation Space
```json
{
  "system_id": "PRD",
  "system_health": {
    "cpu_pct": 94,
    "memory_pct": 87,
    "db_connections": 2,
    "work_processes_free": 0,
    "response_time_ms": 18000
  },
  "alert_queue": [
    {
      "alert_id": "INC-4823",
      "component": "Background Processing",
      "error_code": "JOB_ABORTED",
      "priority": "high",
      "message": "Job SAP_REORG_JOBS aborted in client 200. RC=4.",
      "is_red_herring": false
    },
    {
      "alert_id": "ALT-7712",
      "component": "Memory Management",
      "error_code": "MEM_WARNING",
      "priority": "low",
      "message": "Memory at 68%. Normal for batch window.",
      "is_red_herring": true
    }
  ],
  "sm21_log": [...],
  "sm37_jobs": [...],
  "sla_seconds_remaining": 255,
  "users_affected": 234,
  "episode_history": [...],
  "task_description": "Resolve the aborted background job in PRD.",
  "available_actions": [...]
}
```

---

## Tasks

### Task 1 — Background Job Failure (Easy)
- **Scenario:** A critical SAP background job aborted in PRD with return code 4
- **Agent must:** Diagnose root cause → restart via SM37
- **Max steps:** 5 | **SLA:** 300 seconds
- **Baseline score:** 0.75

### Task 2 — Transport Error + Security Anomaly (Medium)
- **Scenario:** Transport stuck in STMS + suspicious RFC call in security log
- **Agent must:** Release transport AND flag/block security threat
- **Max steps:** 8 | **SLA:** 480 seconds
- **Baseline score:** 1.00

### Task 3 — P1 Full Crisis Response (Hard)
- **Scenario:** System down — DB timeout + memory dump + brute force attack simultaneously
- **Agent must:** Fix in correct order: DB → memory → ICM → block attacker → escalate SOC
- **Max steps:** 18 | **SLA:** 600 seconds
- **Baseline score:** 0.71

---

## Reward Function
reward = diagnosis_score  × 0.25   # Correct root cause
+ fix_score        × 0.25   # Correct fix action
+ sequence_score   × 0.15   # Correct order (Task 3)
+ security_score   × 0.15   # Security threat caught
+ sla_score        × 0.20   # Speed (decays over time)
penalties:
-0.30  destructive action (delete_job)
-0.25  cascade triggered (wrong order)
-0.15  false positive flagged (red herring)
-0.20  wrong system targeted
reward_range: [-0.75, +1.10]

---

## Baseline Scores

| Model | Task 1 | Task 2 | Task 3 | Average |
|---|---|---|---|---|
| meta/llama-3.3-70b-instruct (NVIDIA NIM) | 0.75 | 1.00 | 0.71 | **0.82** |
| Random baseline | ~0.15 | ~0.08 | ~0.03 | ~0.09 |

---

## Setup & Usage

### Requirements
- Python 3.11+
- Docker Desktop
- NVIDIA NIM API key (or any OpenAI-compatible API)

### Local Setup
```bash
git clone https://github.com/Pathipatirajeevlokesh/sap-enterprise-ops-env
cd sap-enterprise-ops-env
pip install -r requirements.txt

# Start server
uvicorn server.app:app --host 0.0.0.0 --port 7860

# Run baseline inference
export API_BASE_URL=http://localhost:7860
export LLM_BASE_URL=https://integrate.api.nvidia.com/v1
export MODEL_NAME=meta/llama-3.3-70b-instruct
export OPENAI_API_KEY=your_nvidia_key
python inference.py
```

### Docker
```bash
docker build -t sap-ops-env .
docker run -p 7860:7860 sap-ops-env
```

### Run Tests
```bash
python -m pytest tests/ -v
# 43 passed
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /health | Health check — returns 200 |
| POST | /reset | Start new episode |
| POST | /step | Take action |
| GET | /state | Episode metadata |
| GET | /tasks | List all 3 tasks |
| WS | /ws | WebSocket real-time |
| GET | /docs | Swagger UI |

---

## Project Structure
sap-enterprise-ops-env/
├── inference.py          # Baseline agent script
├── openenv.yaml          # OpenEnv spec metadata
├── Dockerfile            # Container definition
├── server/
│   ├── app.py            # FastAPI endpoints
│   ├── environment.py    # reset() / step() / state()
│   ├── tasks.py          # 3 tasks + graders
│   ├── data.py           # 60 synthetic scenarios
│   ├── reward.py         # Reward formula + SLA decay
│   └── cascade.py        # Cascading failure engine
├── models/
│   ├── action.py         # SAPAction (Pydantic)
│   ├── observation.py    # SAPObservation (Pydantic)
│   └── state.py          # EpisodeState (Pydantic)
├── client/
│   └── client.py         # Typed env client
└── tests/
├── test_environment.py
└── test_graders.py

---

## Links

- **GitHub:** https://github.com/Pathipatirajeevlokesh/sap-enterprise-ops-env
- **HF Space:** https://huggingface.co/spaces/Rajeevlokesh/sap-enterprise-ops-env
- **Health:** https://Rajeevlokesh-sap-enterprise-ops-env.hf.space/health
- **API Docs:** https://Rajeevlokesh-sap-enterprise-ops-env.hf.space/docs

---

## Authors

**Rajeev Lokesh** — SAP Basis GET at HCLTech, Bengaluru. 7 months hands-on SAP Basis experience.
**Vignesh P** — Teammate.

Built for the Scaler × Meta × Hugging Face OpenEnv Hackathon 2026.