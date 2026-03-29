# models/state.py
from typing import List, Optional
from pydantic import BaseModel, Field


class EpisodeState(BaseModel):
    # Episode identity
    episode_id: str = Field(..., description="Unique episode ID")
    task_id: str = Field(..., description="Current task: task_1 / task_2 / task_3")

    # Progress
    step_number: int = Field(default=0, description="Current step count")
    max_steps: int = Field(..., description="Maximum steps allowed")
    done: bool = Field(default=False, description="Is episode finished")

    # SLA tracking
    sla_total_seconds: int = Field(..., description="Total SLA time allowed")
    sla_seconds_remaining: int = Field(..., description="Remaining SLA seconds")
    sla_breached: bool = Field(default=False, description="True if SLA expired")

    # Scoring
    current_reward: float = Field(default=0.0, description="Cumulative reward so far")
    diagnosis_correct: Optional[bool] = Field(None, description="Was diagnosis correct")
    fix_correct: Optional[bool] = Field(None, description="Was fix action correct")
    security_detected: Optional[bool] = Field(None, description="Was security threat caught")
    cascade_triggered: bool = Field(default=False, description="Did wrong fix cause cascade")
    red_herring_flagged: bool = Field(default=False, description="Did agent flag the red herring")

    # History
    actions_taken: List[str] = Field(
        default_factory=list,
        description="List of action types taken this episode"
    )
    episode_history: List[str] = Field(
        default_factory=list,
        description="Human readable step summaries"
    )

    # Outcome
    termination_reason: Optional[str] = Field(
        None,
        description="Why episode ended: solved / sla_breach / max_steps / destructive_action"
    )