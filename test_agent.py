import json
import re
import requests
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

BASE_URL = "http://127.0.0.1:7860"  # change if needed

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

print("Loading model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16,
    device_map="auto"
)

# ---------------- PROMPT ----------------
def build_prompt(obs):
    return f"""You are an SAP Basis agent.

STRICT RULES:
- Output ONLY valid JSON
- No explanation
- No extra text

FORMAT:
{{"action_type":"diagnose","target_component":"background_jobs","transaction_code":"SM37","fix_method":null}}

OBSERVATION:
{json.dumps(obs)}

RETURN ONLY JSON:
"""

# ---------------- GENERATE ----------------
def generate(prompt):
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    output = model.generate(
        **inputs,
        max_new_tokens=100,
        do_sample=True,
        temperature=0.2,
        pad_token_id=tokenizer.eos_token_id
    )

    decoded = tokenizer.decode(output[0], skip_special_tokens=True)

    # remove prompt
    return decoded[len(prompt):].strip()

# ---------------- PARSE ----------------
def extract_json(text):
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            return None
    return None

# ---------------- LOOP ----------------
def run_once(task_id):
    print("\n--- NEW TASK ---")

    r = requests.post(f"{BASE_URL}/reset", json={"task_id": task_id})
    obs = r.json()["observation"]

    print("OBS:", obs)

    prompt = build_prompt(obs)
    output = generate(prompt)

    print("\nMODEL OUTPUT:\n", output)

    action = extract_json(output)

    if action is None:
        print("❌ Invalid JSON")
        return

    print("ACTION:", action)

    result = requests.post(f"{BASE_URL}/step", json={"action": action}).json()

    print("REWARD:", result.get("reward"))
    print("DONE:", result.get("done"))

# ---------------- RUN ----------------
run_once("task_1_job_failure")