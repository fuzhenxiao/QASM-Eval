#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from dataset_factory import background_classical
    from dataset_factory import background_complex
    from dataset_factory import background_pulse
    from dataset_factory import background_timing
    from dataset_factory import build_parquet_dataset
    from dataset_factory import classical_coretasks
    from dataset_factory import complex_coretasks
    from dataset_factory import pulse_coretasks
    from dataset_factory import timing_coretasks
else:
    from . import background_classical
    from . import background_complex
    from . import background_pulse
    from . import background_timing
    from . import build_parquet_dataset
    from . import classical_coretasks
    from . import complex_coretasks
    from . import pulse_coretasks
    from . import timing_coretasks

#============== CONFIGURATION ==============

DOMAIN_ORDER = ("timing", "classical", "pulse", "complex")


TRAIN_NUM_PER_DOMAIN = 4000
TEST_NUM_PER_DOMAIN = 100
LLM_CHOICE = "openai/gpt-oss-120b" #was "Qwen/Qwen3-Coder-480B-A35B-Instruct" in the paper, but this model is no longer available in nebius, maybe still available in nscale or openroute
LLM_PROVIDER = "nebius" # or openai/nscale
LLM_KEY='YOUR OWN KEY HERE' # or use os.environ.get("LLM_KEY")
OUTPUT_DIR = "testdata"

#============== CONFIGURATION END ==============

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _resolve_generation_root(base_dir: str | Path | None, output_dir: str | Path) -> Path:
    base_path = Path(base_dir or Path.cwd()).resolve()
    output_path = Path(output_dir)
    if output_path.is_absolute():
        return output_path.resolve()
    return (base_path / output_path).resolve()


def _solution_to_prompt_path(solution_path: str) -> str:
    return build_parquet_dataset.prompt_path_for_solution(solution_path)


def _build_chat_record(solution_path: str, prompt_text: str, completion_text: str) -> dict[str, Any]:
    return {
        "id": solution_path,
        "messages": [
            {"role": "user", "content": prompt_text},
            {"role": "assistant", "content": completion_text.strip() + "\n"},
        ],
    }


def _generate_backgrounds(domain: str, root: Path, count: int, seed: int) -> Path:
    out_dir = root / f"{domain}_background"
    if domain == "timing":
        background_timing.generate_background_pool(out_dir=str(out_dir), num=count, seed=seed)
    elif domain == "classical":
        background_classical.generate_background_pool(out_dir=str(out_dir), num=count, seed=seed)
    elif domain == "pulse":
        background_pulse.generate_pulse_backgrounds(out_dir=str(out_dir), n=count, seed=seed)
    elif domain == "complex":
        background_complex.generate_complex_backgrounds(out_dir=str(out_dir), n=count, seed=seed)
    else:
        raise KeyError(f"Unsupported domain: {domain}")
    return out_dir


def _generate_one_task(domain: str, background_qasm: str, meta_path: Path, theme_id: int, variant_id: int, seed: int) -> str:
    if domain == "timing":
        inst = timing_coretasks.generate_core_task_from_meta_path(
            str(meta_path), theme_id=theme_id, variant_id=variant_id, seed=seed
        )
        return timing_coretasks.assemble_full_task(background_qasm, inst)
    if domain == "classical":
        inst = classical_coretasks.generate_core_task_from_meta_path(
            str(meta_path), theme_id=theme_id, variant_id=variant_id, seed=seed
        )
        return classical_coretasks.assemble_full_task(background_qasm, inst)
    if domain == "pulse":
        inst = pulse_coretasks.generate_pulse_core_task_from_meta_path(
            str(meta_path), theme_id=theme_id, variant_id=variant_id, seed=seed
        )
        return pulse_coretasks.assemble_full_task(background_qasm, inst)
    if domain == "complex":
        inst = complex_coretasks.generate_core_task_from_meta_path(
            str(meta_path), theme_id=theme_id, variant_id=variant_id, seed=seed
        )
        return complex_coretasks.assemble_full_task(background_qasm, inst)
    raise KeyError(f"Unsupported domain: {domain}")


def generate_domain_qasm_split(
    *,
    domain: str,
    split: str,
    count: int,
    root: str | Path | None = None,
    background_dir: str | Path,
    base_seed: int,
    variants: tuple[int, ...] = (2, 3, 4),
) -> list[str]:
    root_path = Path(root or Path.cwd()).resolve()
    background_path = Path(background_dir)
    if not background_path.is_absolute():
        background_path = root_path / background_path

    out_dir = root_path / f"{domain}_{split}"
    out_dir.mkdir(parents=True, exist_ok=True)

    background_paths = sorted(background_path.glob("bg_*.qasm"))
    if not background_paths:
        raise FileNotFoundError(f"No backgrounds found in {background_path}")

    rng = random.Random(base_seed)
    solution_paths: list[str] = []

    for idx in range(count):
        theme_id = (idx % 25) + 1
        variant_id = variants[idx % len(variants)]
        bg_path = rng.choice(background_paths)
        meta_path = bg_path.with_suffix(".meta.json")
        if not meta_path.exists():
            raise FileNotFoundError(f"Missing background meta file: {meta_path}")

        full_qasm = _generate_one_task(
            domain=domain,
            background_qasm=_read_text(bg_path),
            meta_path=meta_path,
            theme_id=theme_id,
            variant_id=variant_id,
            seed=rng.randrange(1_000_000_000),
        )

        file_name = f"{domain}_task_{idx:05d}_th{theme_id:02d}_v{variant_id}.qasm"
        out_path = out_dir / file_name
        _write_text(out_path, full_qasm)
        solution_paths.append(out_path.relative_to(root_path).as_posix())

    return solution_paths


def generate_qasm_corpora(
    task_num: int,
    *,
    test_num: int = 25,
    root: str | Path | None = None,
    background_count_per_domain: int | None = None,
    base_seed: int = 20260108,
    variants: tuple[int, ...] = (2, 3, 4),
) -> dict[str, dict[str, list[str]]]:
    root_path = Path(root or Path.cwd()).resolve()
    bg_count = background_count_per_domain or max(25, min(max(task_num, test_num), 200))

    outputs: dict[str, dict[str, list[str]]] = {"train": {}, "test": {}}
    for offset, domain in enumerate(DOMAIN_ORDER):
        domain_seed = base_seed + offset * 10_000
        background_dir = _generate_backgrounds(domain, root_path, bg_count, domain_seed)
        outputs["train"][domain] = generate_domain_qasm_split(
            domain=domain,
            split="train",
            count=task_num,
            root=root_path,
            background_dir=background_dir,
            base_seed=domain_seed + 1_000,
            variants=variants,
        )
        outputs["test"][domain] = generate_domain_qasm_split(
            domain=domain,
            split="test",
            count=test_num,
            root=root_path,
            background_dir=background_dir,
            base_seed=domain_seed + 2_000,
            variants=variants,
        )
    return outputs


def generate_prompt_qasm(
    solution_paths: list[str],
    *,
    root: str | Path | None = None,
    skip_existing: bool = False,
    llm_choice: str = LLM_CHOICE,
    llm_provider: str = LLM_PROVIDER,
    llm_key: str = LLM_KEY,
) -> list[tuple[str, str, int]]:
    if __package__ in (None, ""):
        from dataset_factory import generate_prompt_train
    else:
        from . import generate_prompt_train

    root_path = Path(root or Path.cwd()).resolve()
    original_cwd = Path.cwd().resolve()
    try:
        if root_path != original_cwd:
            os.chdir(root_path)
        return generate_prompt_train.generate_prompt_files(
            solution_paths,
            skip_existing=skip_existing,
            llm_choice=llm_choice,
            llm_provider=llm_provider,
            llm_key=llm_key,
        )
    finally:
        if Path.cwd().resolve() != original_cwd:
            os.chdir(original_cwd)


def build_compatibility_files(
    *,
    train_solution_paths: list[str],
    test_solution_paths_by_domain: dict[str, list[str]],
    root: str | Path | None = None,
    train_jsonl_name: str = "lora_sft_train.jsonl",
    tasks_index_name: str = "tasks_index.json",
) -> dict[str, Path]:
    root_path = Path(root or Path.cwd()).resolve()

    chat_records: list[dict[str, Any]] = []
    for solution_path in train_solution_paths:
        prompt_path = root_path / _solution_to_prompt_path(solution_path)
        solution_file = root_path / solution_path
        prompt_text = build_parquet_dataset.ensure_task_instruction(_read_text(prompt_path))
        completion_text = build_parquet_dataset.extract_core(_read_text(solution_file))
        chat_records.append(_build_chat_record(solution_path, prompt_text, completion_text))

    train_jsonl_path = root_path / train_jsonl_name
    tasks_index_path = root_path / tasks_index_name
    _write_jsonl(train_jsonl_path, chat_records)
    _write_json(tasks_index_path, test_solution_paths_by_domain)

    return {
        "train_jsonl": train_jsonl_path,
        "tasks_index": tasks_index_path,
    }


def build_dataset_records(
    *,
    train_solution_paths: list[str],
    test_solution_paths: list[str],
    root: str | Path | None = None,
    out_dir: str | Path = "data",
    include_extra_metadata: bool = False,
    write_jsonl_copy: bool = True,
) -> dict[str, Path]:
    root_path = Path(root or Path.cwd()).resolve()
    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = root_path / out_path

    train_records = build_parquet_dataset.build_records_from_solution_paths(
        root_path, train_solution_paths, split="train"
    )
    test_records = build_parquet_dataset.build_records_from_solution_paths(
        root_path, test_solution_paths, split="test"
    )
    build_parquet_dataset.write_dataset_splits(
        train_records=train_records,
        test_records=test_records,
        out_dir=out_path,
        write_jsonl_copy=write_jsonl_copy,
        include_extra_metadata=include_extra_metadata,
    )

    return {
        "train_parquet": out_path / "train.parquet",
        "test_parquet": out_path / "test.parquet",
        "train_jsonl": out_path / "train.jsonl",
        "test_jsonl": out_path / "test.jsonl",
    }


def build_dataset(
    task_num: int,
    *,
    test_num: int = 25,
    root: str | Path | None = None,
    out_dir: str | Path = "data",
    background_count_per_domain: int | None = None,
    base_seed: int = 20260108,
    variants: tuple[int, ...] = (2, 3, 4),
    include_extra_metadata: bool = False,
    write_jsonl_copy: bool = True,
    skip_existing_prompts: bool = False,
    write_compatibility_files: bool = True,
    train_jsonl_name: str = "lora_sft_train.jsonl",
    tasks_index_name: str = "tasks_index.json",
    llm_choice: str = LLM_CHOICE,
    llm_provider: str = LLM_PROVIDER,
    llm_key: str = LLM_KEY,
) -> dict[str, Any]:
    root_path = Path(root or Path.cwd()).resolve()

    outputs = generate_qasm_corpora(
        task_num,
        test_num=test_num,
        root=root_path,
        background_count_per_domain=background_count_per_domain,
        base_seed=base_seed,
        variants=variants,
    )
    train_solution_paths = [path for domain in DOMAIN_ORDER for path in outputs["train"][domain]]
    test_solution_paths = [path for domain in DOMAIN_ORDER for path in outputs["test"][domain]]

    prompt_results = generate_prompt_qasm(
        train_solution_paths + test_solution_paths,
        root=root_path,
        skip_existing=skip_existing_prompts,
        llm_choice=llm_choice,
        llm_provider=llm_provider,
        llm_key=llm_key,
    )

    compatibility_paths: dict[str, Path] = {}
    if write_compatibility_files:
        compatibility_paths = build_compatibility_files(
            train_solution_paths=train_solution_paths,
            test_solution_paths_by_domain=outputs["test"],
            root=root_path,
            train_jsonl_name=train_jsonl_name,
            tasks_index_name=tasks_index_name,
        )

    dataset_paths = build_dataset_records(
        train_solution_paths=train_solution_paths,
        test_solution_paths=test_solution_paths,
        root=root_path,
        out_dir=out_dir,
        include_extra_metadata=include_extra_metadata,
        write_jsonl_copy=write_jsonl_copy,
    )

    return {
        "root": root_path,
        "train_solution_paths": train_solution_paths,
        "test_solution_paths": test_solution_paths,
        "prompt_files_generated": len(prompt_results),
        "dataset_paths": dataset_paths,
        "compatibility_paths": compatibility_paths,
        "outputs_by_split": outputs,
    }


def main() -> dict[str, Any]:
    generation_root = _resolve_generation_root(Path.cwd(), OUTPUT_DIR)
    generation_root.mkdir(parents=True, exist_ok=True)

    return build_dataset(
        task_num=TRAIN_NUM_PER_DOMAIN,
        test_num=TEST_NUM_PER_DOMAIN,
        root=generation_root,
        out_dir=generation_root,
        llm_choice=LLM_CHOICE,
        llm_provider=LLM_PROVIDER,
        llm_key=LLM_KEY,
    )


if __name__ == "__main__":
    main()
