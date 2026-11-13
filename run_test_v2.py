from __future__ import annotations
import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
if __package__ in (None, ''):
    PACKAGE_ROOT = Path(__file__).resolve().parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))
    from dataset_factory.LLM import LLM_model
    from scripts_v2.evaluator import evaluate_qasm_completion
else:
    from .dataset_factory.LLM import LLM_model
    from .scripts_v2.evaluator import evaluate_qasm_completion
TEST_DATA_PATH = 'data/test.jsonl'
OUTPUT_DIR = 'test_runs_v2'
RUN_MODE = 'all'
NUM_RANDOM_SAMPLES = 8
RANDOM_SEED = 20260426
PASS_AT_K = 5
LLM_CHOICE = 'openai/gpt-oss-120b'
LLM_PROVIDER = 'nebius'
LLM_KEY = 'YOUR OWN KEY HERE'
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 6000
SYSTEM_PROMPT = 'You complete missing QASM core blocks.\nOutput only the QASM statements that belong between CORE_TASK_START and CORE_TASK_END. Do\nnot output the markers themselves. Do not output explanations. Do not use backticks.'

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

def select_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if RUN_MODE == 'all':
        return list(records)
    if RUN_MODE != 'random_sample':
        raise ValueError(f'Unsupported RUN_MODE: {RUN_MODE}')
    sample_size = min(NUM_RANDOM_SAMPLES, len(records))
    rng = random.Random(RANDOM_SEED)
    return rng.sample(records, sample_size)

def compute_pass_at_k(per_task_ok_by_k: dict[str, dict[int, bool]], k_max: int) -> dict[int, float]:
    if k_max < 1:
        raise ValueError('k_max must be at least 1')
    task_ids = sorted(per_task_ok_by_k)
    if not task_ids:
        return {k: 0.0 for k in range(1, k_max + 1)}
    estimates_by_k: dict[int, list[float]] = {k: [] for k in range(1, k_max + 1)}
    for task_id in task_ids:
        outcomes = list(per_task_ok_by_k[task_id].values())
        n = len(outcomes)
        if n < k_max:
            raise ValueError(f'Task {task_id!r} has {n} samples, fewer than k_max={k_max}')
        c = sum((bool(ok) for ok in outcomes))
        for k_value in range(1, k_max + 1):
            if n - c < k_value:
                estimate = 1.0
            else:
                estimate = 1.0 - math.comb(n - c, k_value) / math.comb(n, k_value)
            estimates_by_k[k_value].append(estimate)
    return {k: sum(estimates) / len(estimates) for k, estimates in estimates_by_k.items()}

def build_output_paths(root_dir: Path) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = root_dir / f'run_{timestamp}'
    run_dir.mkdir(parents=True, exist_ok=True)
    return (run_dir / 'summary.json', run_dir / 'details.jsonl')

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

def build_user_prompt(prompt_qasm: str) -> str:
    return f'Here is a QASM program with a missing core block. Fill in the missing core block.\nReturn only the missing core QASM statements.\n––- BEGIN PROGRAM ––-\n{prompt_qasm}\n––- END PROGRAM ––-'

def main() -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    test_data_path = root / TEST_DATA_PATH
    output_root = root / OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    records = load_jsonl(test_data_path)
    selected_records = select_records(records)
    summary_path, details_path = build_output_paths(output_root)
    client = LLM_model(llm_choice=LLM_CHOICE, llm_key=LLM_KEY, temp=LLM_TEMPERATURE, provider=LLM_PROVIDER)
    per_task_ok_by_k: dict[str, dict[int, bool]] = {}
    details: list[dict[str, Any]] = []
    domain_counts: dict[str, int] = {}
    for task_idx, record in enumerate(selected_records, start=1):
        task_id = record['task_id']
        domain = record['domain']
        prompt = record['prompt']
        golden_code = record['canonical_solution']
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        per_task_ok_by_k[task_id] = {}
        for sample_index in range(1, PASS_AT_K + 1):
            response = client.generate(prompt=build_user_prompt(prompt), system_prompt=SYSTEM_PROMPT, max_tokens=LLM_MAX_TOKENS)
            result = evaluate_qasm_completion(golden_code=golden_code, returned_code=response, domain=domain)
            evaluation = result.to_dict()
            per_task_ok_by_k[task_id][sample_index] = bool(result.ok)
            details.append({'task_id': task_id, 'domain': domain, 'sample_index': sample_index, 'model': LLM_CHOICE, 'provider': LLM_PROVIDER, 'response': response, 'evaluation': evaluation})
    overall_pass_at_k = compute_pass_at_k(per_task_ok_by_k, PASS_AT_K)
    summary: dict[str, Any] = {'config': {'scoring_version': 'v2', 'test_data_path': str(test_data_path), 'output_dir': str(output_root), 'run_mode': RUN_MODE, 'num_random_samples': NUM_RANDOM_SAMPLES, 'random_seed': RANDOM_SEED, 'samples_per_task': PASS_AT_K, 'pass_at_k_max': PASS_AT_K, 'pass_at_k_estimator': 'unbiased', 'pass_at_k_formula': '1 - comb(n - c, k) / comb(n, k)', 'llm_choice': LLM_CHOICE, 'llm_provider': LLM_PROVIDER, 'llm_temperature': LLM_TEMPERATURE, 'llm_max_tokens': LLM_MAX_TOKENS, 'selected_task_count': len(selected_records), 'total_available_task_count': len(records)}, 'overall': {'task_count': len(selected_records), 'pass_at_k': {str(k): v for k, v in overall_pass_at_k.items()}}, 'by_domain': {}, 'token_usage': {'prompt_tokens': client.total_prompt_tokens, 'completion_tokens': client.total_completion_tokens, 'total_tokens': client.total_tokens}, 'artifacts': {'summary_json': str(summary_path), 'details_jsonl': str(details_path)}}
    for domain, count in sorted(domain_counts.items()):
        domain_task_ids = [record['task_id'] for record in selected_records if record['domain'] == domain]
        domain_ok_map = {task_id: per_task_ok_by_k[task_id] for task_id in domain_task_ids}
        domain_pass_at_k = compute_pass_at_k(domain_ok_map, PASS_AT_K)
        summary['by_domain'][domain] = {'task_count': count, 'pass_at_k': {str(k): v for k, v in domain_pass_at_k.items()}}
    write_json(summary_path, summary)
    write_jsonl(details_path, details)
    for k_value in range(1, PASS_AT_K + 1):
        print(f'pass@{k_value}: {overall_pass_at_k[k_value]:.4f}')
    return summary
if __name__ == '__main__':
    main()
