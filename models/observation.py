# models/observation.py
from typing import List, Optional
from pydantic import BaseModel, Field


class SystemHealth(BaseModel):
    cpu_pct: int = Field(..., description="CPU usage percentage 0-100")
    memory_pct: int = Field(..., description="Memory usage percentage 0-100")
    db_connections: int = Field(..., description="Active DB connections")
    work_processes_free: int = Field(..., description="Free work processes")
    response_time_ms: int = Field(..., description="Average dialog response time ms")


class SAPAlert(BaseModel):
    alert_id: str = Field(..., description="Unique alert ID e.g. INC-2041")
    component: str = Field(..., description="Affected component")
    error_code: str = Field(..., description="SAP error code")
    priority: str = Field(..., description="low / medium / high / critical")
    message: str = Field(..., description="Human readable alert message")
    is_red_herring: bool = Field(False, description="True if this is a false positive")


class LogEntry(BaseModel):
    timestamp: str
    severity: str  # INFO / WARNING / ERROR / CRITICAL
    message: str


class BackgroundJob(BaseModel):
    job_name: str
    client_id: str
    status: str       # ACTIVE / FINISHED / ABORTED / SCHEDULED
    return_code: int
    start_time: str
    end_time: Optional[str] = None


class SAPObservation(BaseModel):
    # System identity
    system_id: str = Field(..., description="SAP system: PRD / QAS / DEV")
    system_health: SystemHealth

    # Alert queue — core of what agent must resolve
    alert_queue: List[SAPAlert] = Field(
        ..., description="1-4 alerts; one may be a red herring"
    )

    # Logs and jobs
    sm21_log: List[LogEntry] = Field(..., description="System log entries")
    sm37_jobs: List[BackgroundJob] = Field(..., description="Background job queue")

    # Pressure signals
    sla_seconds_remaining: int = Field(..., description="SLA countdown in seconds")
    users_affected: int = Field(..., description="Number of users impacted")

    # Memory test support
    episode_history: List[str] = Field(
        default_factory=list,
        description="Summary of previous steps in this episode"
    )

    # Task framing
    task_id: str = Field(..., description="Current task ID")
    task_description: str = Field(..., description="What the agent must accomplish")
    available_actions: List[str] = Field(..., description="Valid actions for this step")
    step_number: int = Field(default=0, description="Current step in episode")