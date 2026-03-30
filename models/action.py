# models/action.py
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    DIAGNOSE  = "diagnose"
    FIX       = "fix"
    ESCALATE  = "escalate"
    IGNORE    = "ignore"


class FixMethod(str, Enum):
    RESTART_JOB      = "restart_job"
    DELETE_JOB       = "delete_job"
    RELEASE_TRANSPORT = "release_transport"
    REIMPORT_TRANSPORT = "reimport_transport"
    RESTART_ICM      = "restart_icm"
    CLEAR_BUFFER     = "clear_buffer"
    RECONNECT_DB     = "reconnect_db"
    BLOCK_IP         = "block_ip"
    RESET_CREDENTIALS = "reset_credentials"
    ESCALATE_SOC     = "escalate_soc"
    CHECK_LOG        = "check_log"


class SAPAction(BaseModel):
    action_type: ActionType = Field(
        ..., description="Primary action type"
    )
    target_component: str = Field(
        ..., description="Component to act on: background_jobs / transport / db / security / memory"
    )
    transaction_code: Optional[str] = Field(
        None, description="SAP transaction code: SM37, STMS, DB13, SM21, ICM"
    )
    fix_method: Optional[FixMethod] = Field(
        None, description="Specific fix method to apply"
    )
    diagnosis: Optional[str] = Field(
        None, description="Agent stated root cause — earns partial credit"
    )
    security_action: Optional[str] = Field(
        None, description="Security response: block_ip / reset_creds / escalate_soc"
    )
    reasoning: Optional[str] = Field(
        None, description="Agent explanation — used for partial reward scoring"
    )

    model_config = {"use_enum_values": True}