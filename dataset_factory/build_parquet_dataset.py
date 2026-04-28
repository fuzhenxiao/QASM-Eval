#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CORE_START = "// === CORE_TASK_START ==="
CORE_END = "// === CORE_TASK_END ==="
MEASUREMENT_END = "// === MEASUREMENT_END ==="
TASK_INSTRUCTION = (
    "// Task: Fill in the core task. Output ONLY the QASM statements that should appear\n"
    "// between CORE_TASK_START and CORE_TASK_END. Do not output the markers or any explanation.\n"
)
TEST_FIELD_SOURCE = '''from scripts.evaluator import evaluate_qasm_completion


def check(returned_code, golden_code, domain=None):
    """Return True when returned_code has the correct QASM timeline/distribution."""
    return evaluate_qasm_completion(
        golden_code=golden_code,
        returned_code=returned_code,
        domain=domain,
    ).ok
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def strip_task_instruction(text: str) -> str:
    marker_pos = text.find(MEASUREMENT_END)
    if marker_pos == -1:
        return text
    end_pos = marker_pos + len(MEASUREMENT_END)
    next_newline = text.find("\n", end_pos)
    if next_newline != -1:
        end_pos = next_newline + 1
    return text[:end_pos].rstrip() + "\n"


def ensure_task_instruction(text: str) -> str:
    if TASK_INSTRUCTION.strip() in text:
        return text
    return strip_task_instruction(text).rstrip() + "\n\n" + TASK_INSTRUCTION


def extract_core(text: str) -> str:
    start = text.find(CORE_START)
    end = text.find(CORE_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("Could not find CORE_TASK_START/CORE_TASK_END markers")
    body_start = start + len(CORE_START)
    return text[body_start:end].strip("\n")


def split_context(text: str) -> tuple[str, str]:
    qasm = strip_task_instruction(text)
    start = qasm.find(CORE_START)
    end = qasm.find(CORE_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("Could not find CORE_TASK_START/CORE_TASK_END markers")
    context_before = qasm[: start + len(CORE_START)].rstrip() + "\n"
    context_after = qasm[end:].lstrip("\n")
    return context_before, context_after


def fill_core(prompt_qasm: str, completion: str) -> str:
    qasm = strip_task_instruction(prompt_qasm)
    start = qasm.find(CORE_START)
    end = qasm.find(CORE_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("Could not find CORE_TASK_START/CORE_TASK_END markers")
    body_start = start + len(CORE_START)
    return qasm[:body_start].rstrip() + "\n" + completion.strip() + "\n" + qasm[end:].lstrip()


def extract_instruction_comment(prompt_qasm: str) -> str:
    core = extract_core(prompt_qasm)
    lines = []
    for line in core.splitlines():
        stripped = line.strip()
        if not stripped.startswith("//"):
            continue
        comment = stripped[2:].strip()
        if comment.startswith("TODO(core task):"):
            comment = comment.removeprefix("TODO(core task):").strip()
        lines.append(comment)
    return " ".join(lines).strip()


def parse_solution_header(completion: str) -> tuple[str, str, str]:
    first_line = completion.strip().splitlines()[0] if completion.strip() else ""
    if not first_line.startswith("//"):
        return "", "", ""
    header = first_line[2:].strip()
    match = re.match(r"(?P<family>[^|:]+)\s*\|\s*(?P<name>[^:]+):\s*(?P<desc>.*)", header)
    if not match:
        return "", "", header
    return (
        match.group("family").strip(),
        match.group("name").strip(),
        match.group("desc").strip(),
    )


def parse_num_qubits(qasm: str) -> int | None:
    match = re.search(r"\bqubit\[(\d+)\]\s+q\s*;", qasm)
    return int(match.group(1)) if match else None


def infer_domain_from_path(path: str) -> str:
    first = Path(path).parts[0]
    for domain in ("timing", "classical", "pulse", "complex"):
        if first.startswith(domain):
            return domain
    return ""


def prompt_path_for_solution(solution_path: str) -> str:
    path = Path(solution_path)
    parts = list(path.parts)
    if not parts:
        raise ValueError(f"Invalid solution path: {solution_path}")
    parts[0] = "prompt_" + parts[0]
    return str(Path(*parts))


def make_test_spec(domain: str) -> str:
    return TEST_FIELD_SOURCE


def make_record(
    *,
    split: str,
    task_id: str,
    domain: str,
    prompt: str,
    completion: str,
    canonical_solution: str,
    source_prompt_path: str,
    source_solution_path: str,
) -> dict[str, Any]:
    context_before, context_after = split_context(prompt)
    task_family, task_name, task_description = parse_solution_header(completion)
    qasm_for_metadata = strip_task_instruction(prompt)
    full_record = {
        "task_id": task_id,
        "domain": domain,
        "split": split,
        "language": "openqasm3",
        "prompt": prompt,
        "canonical_solution": canonical_solution,
        "completion": completion.strip() + "\n",
        "test": make_test_spec(domain),
        "instruction_comment": extract_instruction_comment(prompt),
        "context_before": context_before,
        "context_after": context_after,
        "task_family": task_family,
        "task_name": task_name,
        "task_description": task_description,
        "num_qubits": parse_num_qubits(qasm_for_metadata),
        "source_prompt_path": source_prompt_path,
        "source_solution_path": source_solution_path,
    }
    return full_record


def minimal_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "domain": record["domain"],
        "prompt": record["prompt"],
        "canonical_solution": record["canonical_solution"],
        "completion": record["completion"],
        "test": record["test"],
    }


def build_train_records(root: Path, train_jsonl: Path) -> list[dict[str, Any]]:
    records = []
    with train_jsonl.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            messages = item.get("messages", [])
            if len(messages) < 2:
                raise ValueError(f"{train_jsonl}:{line_no}: expected user and assistant messages")
            solution_path = item["id"]
            prompt_path = prompt_path_for_solution(solution_path)
            prompt = ensure_task_instruction(messages[0]["content"])
            completion = messages[1]["content"]
            solution_file = root / solution_path
            if solution_file.exists():
                canonical_solution = read_text(solution_file)
            else:
                canonical_solution = fill_core(prompt, completion)
            records.append(
                make_record(
                    split="train",
                    task_id=Path(solution_path).with_suffix("").as_posix(),
                    domain=infer_domain_from_path(solution_path),
                    prompt=prompt,
                    completion=completion,
                    canonical_solution=canonical_solution,
                    source_prompt_path=prompt_path,
                    source_solution_path=solution_path,
                )
            )
    return records


def build_test_records(root: Path, tasks_index: Path) -> list[dict[str, Any]]:
    records = []
    index = load_json(tasks_index)
    for domain, solution_paths in index.items():
        for solution_path in solution_paths:
            prompt_path = prompt_path_for_solution(solution_path)
            prompt_file = root / prompt_path
            solution_file = root / solution_path
            if not prompt_file.exists():
                raise FileNotFoundError(f"Missing prompt file for {solution_path}: {prompt_path}")
            if not solution_file.exists():
                raise FileNotFoundError(f"Missing solution file: {solution_path}")
            prompt = ensure_task_instruction(read_text(prompt_file))
            canonical_solution = read_text(solution_file)
            completion = extract_core(canonical_solution)
            records.append(
                make_record(
                    split="test",
                    task_id=Path(solution_path).with_suffix("").as_posix(),
                    domain=domain,
                    prompt=prompt,
                    completion=completion,
                    canonical_solution=canonical_solution,
                    source_prompt_path=prompt_path,
                    source_solution_path=solution_path,
                )
            )
    return records


def build_records_from_solution_paths(
    root: Path,
    solution_paths: list[str],
    *,
    split: str,
) -> list[dict[str, Any]]:
    records = []
    for solution_path in solution_paths:
        prompt_path = prompt_path_for_solution(solution_path)
        prompt_file = root / prompt_path
        solution_file = root / solution_path
        if not prompt_file.exists():
            raise FileNotFoundError(f"Missing prompt file for {solution_path}: {prompt_path}")
        if not solution_file.exists():
            raise FileNotFoundError(f"Missing solution file: {solution_path}")
        prompt = ensure_task_instruction(read_text(prompt_file))
        canonical_solution = read_text(solution_file)
        completion = extract_core(canonical_solution)
        records.append(
            make_record(
                split=split,
                task_id=Path(solution_path).with_suffix("").as_posix(),
                domain=infer_domain_from_path(solution_path),
                prompt=prompt,
                completion=completion,
                canonical_solution=canonical_solution,
                source_prompt_path=prompt_path,
                source_solution_path=solution_path,
            )
        )
    return records


def write_parquet(records: list[dict[str, Any]], path: Path) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "pyarrow is required to write Parquet. Install it with:\n"
            "  python -m pip install pyarrow\n"
            "Then rerun this script."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(records)
    pq.write_table(table, path)


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_dataset_splits(
    *,
    train_records: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    out_dir: Path,
    write_jsonl_copy: bool = True,
    include_extra_metadata: bool = False,
) -> None:
    if not include_extra_metadata:
        train_records = [minimal_record(record) for record in train_records]
        test_records = [minimal_record(record) for record in test_records]

    write_parquet(train_records, out_dir / "train.parquet")
    write_parquet(test_records, out_dir / "test.parquet")

    if write_jsonl_copy:
        write_jsonl(train_records, out_dir / "train.jsonl")
        write_jsonl(test_records, out_dir / "test.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Dataset repository root.")
    parser.add_argument(
        "--train-jsonl",
        type=Path,
        default=Path("lora_sft_train_4000.jsonl"),
        help="Training JSONL containing chat messages.",
    )
    parser.add_argument(
        "--tasks-index",
        type=Path,
        default=Path("tasks_index.json"),
        help="Test task index mapping domain names to solution paths.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data"), help="Output directory.")
    parser.add_argument(
        "--jsonl-copy",
        action="store_true",
        help="Also write JSONL copies next to the Parquet files for inspection.",
    )
    parser.add_argument(
        "--include-extra-metadata",
        action="store_true",
        help="Keep analysis/provenance fields such as split, language, contexts, and source paths.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    train_jsonl = args.train_jsonl if args.train_jsonl.is_absolute() else root / args.train_jsonl
    tasks_index = args.tasks_index if args.tasks_index.is_absolute() else root / args.tasks_index
    out_dir = args.out_dir if args.out_dir.is_absolute() else root / args.out_dir

    train_records = build_train_records(root, train_jsonl)
    test_records = build_test_records(root, tasks_index)

    write_dataset_splits(
        train_records=train_records,
        test_records=test_records,
        out_dir=out_dir,
        write_jsonl_copy=args.jsonl_copy,
        include_extra_metadata=args.include_extra_metadata,
    )

    print(f"Wrote {len(train_records)} training records to {out_dir / 'train.parquet'}")
    print(f"Wrote {len(test_records)} test records to {out_dir / 'test.parquet'}")


if __name__ == "__main__":
    main()
