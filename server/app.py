# server/app.py
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json

from models.action import SAPAction
from server.environment import SAPBasisEnvironment
from server.tasks import list_tasks, get_task

# ── APP SETUP ────────────────────────────────────────────────────

app = FastAPI(
    title="SAP Enterprise Ops Environment",
    description="OpenEnv-compliant RL environment for SAP Basis incident resolution",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One environment instance per server
env = SAPBasisEnvironment()


# ── REQUEST MODELS ───────────────────────────────────────────────

class ResetRequest(BaseModel):
    task_id: Optional[str] = "task_1_job_failure"

class StepRequest(BaseModel):
    action: SAPAction


# ── ENDPOINTS ────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Phase 1 gate — must return 200."""
    return {"status": "ok", "environment": "sap-enterprise-ops-env"}


@app.get("/tasks")
def tasks():
    """List all 3 tasks with metadata."""
    return {"tasks": list_tasks()}


@app.get("/task/{task_id}")
def task_detail(task_id: str):
    """Get a single task by ID."""
    try:
        return get_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reset")
def reset(request: ResetRequest):
    """Start a new episode. Returns initial observation."""
    try:
        obs = env.reset(task_id=request.task_id)
        return {
            "observation": obs.model_dump(),
            "task_id":     request.task_id,
            "message":     "Episode started. Good luck.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/step")
def step(request: StepRequest):
    """Take one action. Returns observation, reward, done, info."""
    try:
        obs, reward, done, info = env.step(request.action)
        response = {
            "observation": obs.model_dump(),
            "reward":      reward,
            "done":        done,
            "info":        info,
        }
        # If episode ended, include final grade
        if done:
            final_score, grade_breakdown = env.grade()
            response["final_score"]      = final_score
            response["grade_breakdown"]  = grade_breakdown
        return response
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/state")
def state():
    """Return current episode metadata."""
    try:
        s = env.state()
        return s.model_dump()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/")
def root():
    """Root endpoint — Hugging Face Space landing."""
    return {
        "name":        "sap-enterprise-ops-env",
        "version":     "1.0.0",
        "description": "OpenEnv RL environment for SAP Basis incident resolution",
        "endpoints":   ["/health", "/reset", "/step", "/state", "/tasks", "/docs"],
        "tasks":       [t["id"] for t in list_tasks()],
    }


# ── WEBSOCKET ────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time WebSocket interface."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg  = json.loads(data)
            cmd  = msg.get("command")

            if cmd == "reset":
                task_id = msg.get("task_id", "task_1_job_failure")
                obs = env.reset(task_id=task_id)
                await websocket.send_text(json.dumps({
                    "type":        "observation",
                    "observation": obs.model_dump(),
                }))

            elif cmd == "step":
                action = SAPAction(**msg.get("action", {}))
                obs, reward, done, info = env.step(action)
                response = {
                    "type":        "step_result",
                    "observation": obs.model_dump(),
                    "reward":      reward,
                    "done":        done,
                    "info":        info,
                }
                if done:
                    final_score, breakdown = env.grade()
                    response["final_score"]     = final_score
                    response["grade_breakdown"] = breakdown
                await websocket.send_text(json.dumps(response))

            elif cmd == "state":
                s = env.state()
                await websocket.send_text(json.dumps({
                    "type":  "state",
                    "state": s.model_dump(),
                }))

            else:
                await websocket.send_text(json.dumps({
                    "type":  "error",
                    "detail": f"Unknown command: {cmd}"
                }))

    except WebSocketDisconnect:
        pass