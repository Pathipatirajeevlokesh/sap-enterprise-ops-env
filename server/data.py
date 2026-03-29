# server/data.py
import random
import uuid
from datetime import datetime, timedelta


# ── HELPER ──────────────────────────────────────────────────────

def _rand_time(minutes_ago_max=120):
    dt = datetime.now() - timedelta(minutes=random.randint(1, minutes_ago_max))
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _rand_ip():
    return f"{random.randint(10,192)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def _rand_incident_id():
    return f"INC-{random.randint(1000,9999)}"

def _rand_alert_id():
    return f"ALT-{random.randint(1000,9999)}"

def _rand_job_name():
    return random.choice([
        "SAP_REORG_JOBS", "SAP_COLLECTOR_FOR_PERFMONITOR",
        "RDDIMPDP", "SAP_CCMS_MONI_BATCH_DP",
        "RSBTCDEL2", "SAP_REORG_SPOOL", "RSUSR406",
        "SAP_SYSTEM_HEALTH_CHECK", "RBDAPP01", "RSEOUT00"
    ])

def _rand_client():
    return random.choice(["100", "200", "300", "400"])

def _rand_server():
    return random.choice([
        "sapprd01", "sapprd02", "sapprd03",
        "sapprd-app1", "sapprd-db1"
    ])

def _rand_user():
    return random.choice([
        "BASIS_ADM", "SAP_ADMIN", "PRD_USER",
        "BATCH_USR", "RFC_USER", "SUPPORT01"
    ])


# ── RED HERRINGS (false positives) ──────────────────────────────

RED_HERRING_POOL = [
    {
        "component": "Memory Management",
        "error_code": "MEM_WARNING",
        "priority": "low",
        "message": "Memory usage at 68%. Normal for current batch processing window.",
        "is_red_herring": True
    },
    {
        "component": "Background Processing",
        "error_code": "JOB_DELAY",
        "priority": "low",
        "message": "Job SAP_REORG_SPOOL delayed by 4 minutes. Within acceptable threshold.",
        "is_red_herring": True
    },
    {
        "component": "System Performance",
        "error_code": "CPU_SPIKE",
        "priority": "low",
        "message": "CPU spike to 72% detected. Caused by scheduled CCMS monitor run.",
        "is_red_herring": True
    },
    {
        "component": "Dialog Processing",
        "error_code": "DIALOG_SLOW",
        "priority": "low",
        "message": "Dialog response time 1200ms. Elevated due to month-end reporting.",
        "is_red_herring": True
    },
    {
        "component": "Spool System",
        "error_code": "SPOOL_SIZE",
        "priority": "low",
        "message": "Spool usage at 61%. Auto-cleanup scheduled in 2 hours.",
        "is_red_herring": True
    },
]


def get_red_herring():
    rh = random.choice(RED_HERRING_POOL).copy()
    rh["alert_id"] = _rand_alert_id()
    return rh


# ── TASK 1: BACKGROUND JOB FAILURE (EASY) ───────────────────────

TASK1_TEMPLATES = [
    {
        "error_code": "JOB_ABORTED",
        "return_code": 4,
        "root_cause": "work_process_timeout",
        "correct_transaction": "SM37",
        "correct_fix": "restart_job",
        "wrong_fixes": ["delete_job", "ignore"],
        "message_template": "Job {job} aborted in client {client}. Return code: 4. Work process timeout.",
        "sm21_message": "Work process {wp} killed after exceeding maximum runtime",
        "difficulty_score": 0.85
    },
    {
        "error_code": "JOB_ABORTED",
        "return_code": 8,
        "root_cause": "missing_variant",
        "correct_transaction": "SM37",
        "correct_fix": "restart_job",
        "wrong_fixes": ["delete_job", "ignore"],
        "message_template": "Job {job} aborted in client {client}. Return code: 8. Variant not found.",
        "sm21_message": "ABAP runtime error: VARIANT_DOES_NOT_EXIST in program {job}",
        "difficulty_score": 0.80
    },
    {
        "error_code": "JOB_ABORTED",
        "return_code": 4,
        "root_cause": "authorization_failure",
        "correct_transaction": "SM37",
        "correct_fix": "restart_job",
        "wrong_fixes": ["delete_job", "check_log"],
        "message_template": "Job {job} aborted in client {client}. Return code: 4. Authorization check failed.",
        "sm21_message": "Authorization failure for object S_BTCH_ADM in job {job}",
        "difficulty_score": 0.78
    },
    {
        "error_code": "JOB_ABORTED",
        "return_code": 16,
        "root_cause": "db_lock_timeout",
        "correct_transaction": "SM37",
        "correct_fix": "restart_job",
        "wrong_fixes": ["delete_job", "reimport_transport"],
        "message_template": "Job {job} aborted in client {client}. Return code: 16. DB lock timeout.",
        "sm21_message": "Database lock timeout in job {job}. Table VBAK locked by user {user}.",
        "difficulty_score": 0.75
    },
    {
        "error_code": "JOB_ABORTED",
        "return_code": 4,
        "root_cause": "memory_exceeded",
        "correct_transaction": "SM37",
        "correct_fix": "restart_job",
        "wrong_fixes": ["delete_job", "clear_buffer"],
        "message_template": "Job {job} aborted in client {client}. Return code: 4. Memory limit exceeded.",
        "sm21_message": "ABAP runtime error STORAGE_PARAMETERS_WRONG_SET in job {job}",
        "difficulty_score": 0.82
    },
]


def get_task1_scenario():
    t = random.choice(TASK1_TEMPLATES).copy()
    job = _rand_job_name()
    client = _rand_client()
    wp = random.randint(0, 9)
    user = _rand_user()
    server = _rand_server()

    return {
        "task_id": "task_1_job_failure",
        "incident_id": _rand_incident_id(),
        "system_id": "PRD",
        "server": server,
        "component": "Background Processing",
        "error_code": t["error_code"],
        "return_code": t["return_code"],
        "root_cause": t["root_cause"],
        "correct_transaction": t["correct_transaction"],
        "correct_fix": t["correct_fix"],
        "wrong_fixes": t["wrong_fixes"],
        "alert_message": t["message_template"].format(
            job=job, client=client, user=user
        ),
        "sm21_message": t["sm21_message"].format(
            wp=wp, job=job, user=user
        ),
        "job_name": job,
        "client_id": client,
        "timestamp": _rand_time(),
        "users_affected": random.randint(0, 50),
        "sla_seconds": 300,
        "max_steps": 5,
        "difficulty_score": t["difficulty_score"],
        "system_health": {
            "cpu_pct": random.randint(40, 70),
            "memory_pct": random.randint(50, 75),
            "db_connections": random.randint(15, 40),
            "work_processes_free": random.randint(2, 8),
            "response_time_ms": random.randint(300, 800)
        }
    }


# ── TASK 2: TRANSPORT + SECURITY (MEDIUM) ───────────────────────

TASK2_TEMPLATES = [
    {
        "transport_error": "TRANSPORT_STUCK",
        "transport_cause": "buffer_not_refreshed",
        "correct_transport_fix": "release_transport",
        "correct_transaction": "STMS",
        "security_threat": "suspicious_rfc_call",
        "security_action": "block_ip",
        "rfc_program": "Z_RFC_DATA_EXTRACT",
        "message_template": "Transport {tr} stuck in import queue on {system}. Buffer not refreshed.",
        "security_message": "RFC call from {ip} to function {prog} outside business hours.",
    },
    {
        "transport_error": "TRANSPORT_FAILED",
        "transport_cause": "object_locked",
        "correct_transport_fix": "release_transport",
        "correct_transaction": "STMS",
        "security_threat": "unauthorized_logon",
        "security_action": "reset_credentials",
        "rfc_program": "RFC_READ_TABLE",
        "message_template": "Transport {tr} failed. Object locked by another transport in {system}.",
        "security_message": "Failed logon attempts from {ip} for user {user}. Count: {count}.",
    },
    {
        "transport_error": "TRANSPORT_STUCK",
        "transport_cause": "tp_step_failed",
        "correct_transport_fix": "release_transport",
        "correct_transaction": "STMS",
        "security_threat": "suspicious_rfc_call",
        "security_action": "block_ip",
        "rfc_program": "SUSR_USER_CHANGE_PASSWORD_RFC",
        "message_template": "Transport {tr} tp step R failed in {system}. Return code 0012.",
        "security_message": "Unusual RFC call to {prog} from external IP {ip}.",
    },
]


def get_task2_scenario():
    t = random.choice(TASK2_TEMPLATES).copy()
    transport_id = f"PRD K{random.randint(100000,999999)}"
    ip = _rand_ip()
    user = _rand_user()
    count = random.randint(15, 200)

    return {
        "task_id": "task_2_transport_security",
        "incident_id": _rand_incident_id(),
        "system_id": "PRD",
        "transport_id": transport_id,
        "transport_error": t["transport_error"],
        "transport_cause": t["transport_cause"],
        "correct_transport_fix": t["correct_transport_fix"],
        "correct_transaction": t["correct_transaction"],
        "security_threat": t["security_threat"],
        "correct_security_action": t["security_action"],
        "attacker_ip": ip,
        "transport_alert_message": t["message_template"].format(
            tr=transport_id, system="PRD"
        ),
        "security_alert_message": t["security_message"].format(
            ip=ip, prog=t["rfc_program"], user=user, count=count
        ),
        "timestamp": _rand_time(),
        "users_affected": random.randint(10, 150),
        "sla_seconds": 480,
        "max_steps": 8,
        "system_health": {
            "cpu_pct": random.randint(55, 80),
            "memory_pct": random.randint(60, 82),
            "db_connections": random.randint(20, 55),
            "work_processes_free": random.randint(1, 5),
            "response_time_ms": random.randint(800, 2000)
        }
    }


# ── TASK 3: P1 FULL CRISIS (HARD) ───────────────────────────────

TASK3_TEMPLATES = [
    {
        "db_error": "DB_CONNECTION_TIMEOUT",
        "memory_error": "MEMORY_DUMP",
        "security_error": "BRUTE_FORCE",
        "correct_order": ["reconnect_db", "clear_buffer", "restart_icm", "block_ip", "escalate_soc"],
        "correct_transactions": ["DB13", "SM50", "SMICM", "SM21"],
        "cascade_trigger": "clear_buffer_before_db",
        "db_message": "Database connection pool exhausted. {connections} connections timeout.",
        "memory_message": "ABAP memory dump {dump_id} on server {server}. STORAGE_PARAMETERS_WRONG_SET.",
        "security_message": "Brute force attack from {ip}. {attempts} failed attempts on user {user}.",
    },
    {
        "db_error": "DB_LOCK_ESCALATION",
        "memory_error": "ROLL_AREA_OVERFLOW",
        "security_error": "PRIVILEGE_ESCALATION",
        "correct_order": ["reconnect_db", "clear_buffer", "restart_icm", "block_ip", "escalate_soc"],
        "correct_transactions": ["DB13", "SM50", "SMICM", "SM21"],
        "cascade_trigger": "clear_buffer_before_db",
        "db_message": "DB lock escalation detected. {connections} sessions waiting. System near deadlock.",
        "memory_message": "Roll area overflow on {server}. Extended memory exhausted.",
        "security_message": "Privilege escalation attempt from {ip}. User {user} granted SAP_ALL.",
    },
]


def get_task3_scenario():
    t = random.choice(TASK3_TEMPLATES).copy()
    ip = _rand_ip()
    # Store attacker IP — same IP will appear in Task 1 for memory test
    user = _rand_user()
    server = _rand_server()
    connections = random.randint(80, 200)
    attempts = random.randint(500, 2000)
    dump_id = f"DUMP_{random.randint(10000,99999)}"

    return {
        "task_id": "task_3_p1_incident",
        "incident_id": _rand_incident_id(),
        "system_id": "PRD",
        "db_error": t["db_error"],
        "memory_error": t["memory_error"],
        "security_error": t["security_error"],
        "correct_order": t["correct_order"],
        "correct_transactions": t["correct_transactions"],
        "cascade_trigger": t["cascade_trigger"],
        "attacker_ip": ip,
        "db_alert_message": t["db_message"].format(connections=connections),
        "memory_alert_message": t["memory_message"].format(
            dump_id=dump_id, server=server
        ),
        "security_alert_message": t["security_message"].format(
            ip=ip, attempts=attempts, user=user
        ),
        "timestamp": _rand_time(),
        "users_affected": random.randint(200, 500),
        "sla_seconds": 600,
        "max_steps": 12,
        "system_health": {
            "cpu_pct": random.randint(88, 99),
            "memory_pct": random.randint(90, 99),
            "db_connections": random.randint(0, 3),
            "work_processes_free": 0,
            "response_time_ms": random.randint(8000, 30000)
        }
    }


# ── PUBLIC API ───────────────────────────────────────────────────

def get_scenario(task_id: str) -> dict:
    """Main entry point — returns a randomised scenario for the given task."""
    if task_id == "task_1_job_failure":
        return get_task1_scenario()
    elif task_id == "task_2_transport_security":
        return get_task2_scenario()
    elif task_id == "task_3_p1_incident":
        return get_task3_scenario()
    else:
        raise ValueError(f"Unknown task_id: {task_id}")