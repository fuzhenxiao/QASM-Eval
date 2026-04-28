#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    PACKAGE_ROOT = Path(__file__).resolve().parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from dataset_factory.LLM import LLM_model
    from scripts.evaluator import evaluate_qasm_completion
else:
    from .dataset_factory.LLM import LLM_model
    from .scripts.evaluator import evaluate_qasm_completion


# ============== CONFIGURATION ==============

TEST_DATA_PATH = "data/test.jsonl"
OUTPUT_DIR = "test_runs"

# mode: "random_sample" or "all"
RUN_MODE = "all" # or "random_sample"
NUM_RANDOM_SAMPLES = 8 # if RUN_MODE is "all", then it will select all 100 test tasks
RANDOM_SEED = 20260426

# generate k candidates per task, then compute pass@k for k = 1..PASS_AT_K
PASS_AT_K = 5

LLM_CHOICE = "openai/gpt-oss-120b" # the model to be tested
LLM_PROVIDER = "nebius"
LLM_KEY='YOUR OWN KEY HERE'
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 1200

SYSTEM_PROMPT = (
    "You complete missing QASM core blocks.\n"
    "Output only the QASM statements that belong between CORE_TASK_START and CORE_TASK_END. Do\n"
    "not output the markers themselves. Do not output explanations. Do not use backticks."
)

# ============== CONFIGURATION END ==============


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def select_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if RUN_MODE == "all":
        return list(records)
    if RUN_MODE != "random_sample":
        raise ValueError(f"Unsupported RUN_MODE: {RUN_MODE}")

    sample_size = min(NUM_RANDOM_SAMPLES, len(records))
    rng = random.Random(RANDOM_SEED)
    return rng.sample(records, sample_size)


def compute_pass_at_k(per_task_ok_by_k: dict[str, dict[int, bool]], k_max: int) -> dict[int, float]:
    task_ids = sorted(per_task_ok_by_k.keys())
    if not task_ids:
        return {k: 0.0 for k in range(1, k_max + 1)}

    pass_at_k: dict[int, float] = {}
    for k_value in range(1, k_max + 1):
        passed = 0
        for task_id in task_ids:
            ok_map = per_task_ok_by_k.get(task_id, {})
            hit = any(ok for idx, ok in ok_map.items() if idx <= k_value)
            if hit:
                passed += 1
        pass_at_k[k_value] = passed / len(task_ids)
    return pass_at_k


def build_output_paths(root_dir: Path) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = root_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "summary.json", run_dir / "details.jsonl"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_user_prompt(prompt_qasm: str) -> str:
    return (
        "Here is a QASM program with a missing core block. Fill in the missing core block.\n"
        "Return only the missing core QASM statements.\n"
        "––- BEGIN PROGRAM ––-\n"
        f"{prompt_qasm}\n"
        "––- END PROGRAM ––-"
    )


def main() -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    test_data_path = root / TEST_DATA_PATH
    output_root = root / OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(test_data_path)
    selected_records = select_records(records)
    summary_path, details_path = build_output_paths(output_root)

    client = LLM_model(
        llm_choice=LLM_CHOICE,
        llm_key=LLM_KEY,
        temp=LLM_TEMPERATURE,
        provider=LLM_PROVIDER,
    )

    per_task_ok_by_k: dict[str, dict[int, bool]] = {}
    details: list[dict[str, Any]] = []
    domain_counts: dict[str, int] = {}
    domain_pass_counts_by_k: dict[str, dict[int, int]] = {}

    for task_idx, record in enumerate(selected_records, start=1):
        task_id = record["task_id"]
        domain = record["domain"]
        prompt = record["prompt"]
        golden_code = record["canonical_solution"]

        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        per_task_ok_by_k[task_id] = {}

        print(f"[task {task_idx}/{len(selected_records)}] {task_id} | domain={domain}")

        for k_idx in range(1, PASS_AT_K + 1):
            response = client.generate(
                prompt=build_user_prompt(prompt),
                system_prompt=SYSTEM_PROMPT,
                max_tokens=LLM_MAX_TOKENS,
            )
            result = evaluate_qasm_completion(
                golden_code=golden_code,
                returned_code=response,
                domain=domain,
            )
            evaluation = result.to_dict()

            per_task_ok_by_k[task_id][k_idx] = bool(result.ok)
            details.append(
                {
                    "task_id": task_id,
                    "domain": domain,
                    "sample_index": k_idx,
                    "model": LLM_CHOICE,
                    "provider": LLM_PROVIDER,
                    "response": response,
                    "evaluation": evaluation,
                }
            )

            print(
                f"  - sample {k_idx}/{PASS_AT_K}: "
                f"ok={result.ok}, "
                f"syntax_ok={result.syntax_ok}, "
                f"element_ok={result.element_ok}, "
                f"dist_ok={result.dist_ok}, "
                f"timeline_ok={result.timeline_ok}"
            )

    overall_pass_at_k = compute_pass_at_k(per_task_ok_by_k, PASS_AT_K)

    for domain, count in domain_counts.items():
        domain_task_ids = [
            record["task_id"] for record in selected_records if record["domain"] == domain
        ]
        domain_ok_map = {task_id: per_task_ok_by_k[task_id] for task_id in domain_task_ids}
        domain_pass_values = compute_pass_at_k(domain_ok_map, PASS_AT_K)
        domain_pass_counts_by_k[domain] = {
            k_value: int(round(domain_pass_values[k_value] * count)) for k_value in domain_pass_values
        }

    summary = {
        "config": {
            "test_data_path": str(test_data_path),
            "output_dir": str(output_root),
            "run_mode": RUN_MODE,
            "num_random_samples": NUM_RANDOM_SAMPLES,
            "random_seed": RANDOM_SEED,
            "pass_at_k": PASS_AT_K,
            "llm_choice": LLM_CHOICE,
            "llm_provider": LLM_PROVIDER,
            "llm_temperature": LLM_TEMPERATURE,
            "llm_max_tokens": LLM_MAX_TOKENS,
            "selected_task_count": len(selected_records),
            "total_available_task_count": len(records),
        },
        "overall": {
            "task_count": len(selected_records),
            "pass_at_k": {str(k): v for k, v in overall_pass_at_k.items()},
        },
        "by_domain": {},
        "token_usage": {
            "prompt_tokens": client.total_prompt_tokens,
            "completion_tokens": client.total_completion_tokens,
            "total_tokens": client.total_tokens,
        },
        "artifacts": {
            "summary_json": str(summary_path),
            "details_jsonl": str(details_path),
        },
    }

    for domain, count in sorted(domain_counts.items()):
        domain_task_ids = [
            record["task_id"] for record in selected_records if record["domain"] == domain
        ]
        domain_ok_map = {task_id: per_task_ok_by_k[task_id] for task_id in domain_task_ids}
        domain_pass_at_k = compute_pass_at_k(domain_ok_map, PASS_AT_K)
        summary["by_domain"][domain] = {
            "task_count": count,
            "pass_at_k": {str(k): v for k, v in domain_pass_at_k.items()},
        }

    write_json(summary_path, summary)
    write_jsonl(details_path, details)

    print("")
    print("=== Summary ===")
    print(f"selected tasks: {len(selected_records)} / {len(records)}")
    for k_value in range(1, PASS_AT_K + 1):
        print(f"pass@{k_value}: {overall_pass_at_k[k_value]:.4f}")
    print(f"summary saved to: {summary_path}")
    print(f"details saved to: {details_path}")

    return summary


if __name__ == "__main__":
    main()
