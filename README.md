# QASM-Eval

QASM-Eval is an OpenQASM 3 dataset for evaluating and training language models on hardware-facing quantum programming tasks. It focuses on capabilities that matter in near-term quantum workflows, including timing-aware programming, classical control, pulse-level operations, and mixed workflows that combine these elements in a single program.

This repository is designed for benchmark release and anonymous paper review. It contains the released dataset, evaluation scripts, and a lightweight test runner for model benchmarking on QASM core-block completion tasks.

Two models fine-tuned on QASM-Eval are also released here (latest releases) and on Hugging Face (anonymous):
- [Llama-3.1-8B-Instruct-QASM-Eval](https://huggingface.co/AnonymousORG01/Llama-3.1-8B-Instruct-QASM-Eval)
- [Llama-3.3-70B-Instruct-QASM-Eval](https://huggingface.co/AnonymousORG01/Llama-3.3-70B-Instruct-QASM-Eval)

## 1. Project Overview

QASM-Eval studies code generation for advanced OpenQASM 3 programs rather than only static gate-level circuits. Each task presents a full QASM program with one missing core block. The model is asked to reconstruct only that missing region from the provided natural-language description and surrounding program context.

The benchmark is intended to test whether a model can generate functionally correct QASM 3 code with advanced features under realistic constraints:

| split | records | domain composition |
| --- | ---: | --- |
| train | 4,000 | 1,000 timing, 1,000 classical, 1,000 pulse, 1,000 complex |
| test | 100 | 25 timing, 25 classical, 25 pulse, 25 complex |

- `timing`: tasks involving delays, durations, schedule-sensitive structure, and timeline behavior
- `classical`: tasks involving measurement, bits, registers, conditionals, and classical control
- `pulse`: tasks involving frames, waveforms, `defcal`, and pulse-level calibration logic
- `complex`: mixed tasks combining quantum gates, timing, pulse logic, and classical behavior

This repository includes:

- released dataset files in JSONL and Parquet format
- evaluation scripts for syntax&semantic checking through simulation
- a runnable `run_test.py` script for LLM-based benchmarking
- local dataset-generation utilities kept here for reproducibility and workflow support

## 2. Usage

This repository supports three main usage patterns.

### 1. Evaluate an LLM on QASM-Eval

Use `run_test.py` for end-to-end model benchmarking on the released test split.

The script is configured directly at the top of the file rather than through command-line arguments.

Important configuration fields include:

- `RUN_MODE`: choose `"random_sample"` or `"all"`
- `NUM_RANDOM_SAMPLES`: total number of randomly selected test tasks when using random mode
- `PASS_AT_K`: number of model samples generated per task, and the maximum `k` reported in pass@k
- `LLM_CHOICE`: model name
- `LLM_PROVIDER`: backend provider such as `nebius`, `openai`, `nscale`, or `huggingface`
- `LLM_KEY`: API key for the chosen provider
- `LLM_TEMPERATURE`: generation temperature
- `LLM_MAX_TOKENS`: max response length

The script reads `data/test.jsonl`, queries the model repeatedly for each selected task, evaluates every generated answer, and writes run artifacts into `test_runs/`.

To launch an evaluation run:

```bash
python3 run_test.py
```

The output includes a detailed report with the overall pass@k metric and pass rates for each task category. Per-sample error types is also available, the scripts in ./scripts contain the full simulator implementations and the associated evaluation logic.

### 2. Use QASM-Eval as a training dataset

Load the released JSONL or Parquet files directly for supervised fine-tuning, analysis, or prompt construction. Typical field usage:

- `prompt`: model input
- `completion`: target core block only
- `canonical_solution`: full reference program

You can also load the Parquet files if that better fits your training stack.

### 3. Generate your own dataset in bulk

```bash
python3 dataset_factory/generate_dataset.py
```

The bulk dataset-generation workflow is implemented in `dataset_factory/generate_dataset.py`.

That script is designed for creating new QASM task corpora, generating prompt files, and building dataset artifacts in JSONL and Parquet format. At the top of the file, you can configure:

- number of training samples per domain
- number of test samples per domain
- model choice for prompt generation
- provider and API key
- output directory

This path is useful if you want to create a new benchmark variant, regenerate prompt-based task files, or produce a custom train/test dataset with the same overall workflow.

## 3. Evaluation Protocol

For each selected task, `run_test.py` generates `PASS_AT_K` independent model completions. These are evaluated against the corresponding golden program using `scripts/evaluator.py`.

The reported `pass@k` follows the standard benchmark-style interpretation used here:

- a task counts as passed at `k` if at least one of the first `k` sampled completions is correct
- overall `pass@k` is the fraction of selected tasks that satisfy the condition above

The evaluation output includes the following boolean fields:

- `ok`: overall correctness decision
- `syntax_ok`: whether the generated QASM can be parsed
- `element_ok`: whether required critical structures are present
- `dist_ok`: whether the generated program matches the target output distribution
- `timeline_ok`: whether the generated program matches the target timing behavior

`None` appears when a particular check is not required for that specific task. If you want to change the evaluation rule so that the check is enforced, you can modify the corresponding logic in `decide_ok()` at `scripts/judge.py`.

## 4. Task Format

Each example follows a HumanEval-style completion setup. A task includes:

- `prompt`: a full OpenQASM 3 program with the target region replaced by a TODO-style description
- `canonical_solution`: the complete reference OpenQASM 3 program
- `completion`: only the missing core block
- `test`: a minimal evaluation snippet showing how to call the evaluator

The central structure looks like this:

```qasm
// === CORE_TASK_START ===

// TODO(core task): natural-language description of the missing QASM behavior

// === CORE_TASK_END ===
```

Models are expected to output only the statements that belong between these two markers.

## 5. Repository Layout

```text
data/
  train.parquet
  test.parquet
  train.jsonl
  test.jsonl

scripts/
  evaluator.py
  judge.py
  QASM_simulator.py
  pulse_simulator.py

dataset_factory/
  generate_dataset.py
  generate_prompt_test.py
  ...

run_test.py
README.md
```

Key paths:

- `data/`: released benchmark data
- `scripts/`: scripts needed to evaluate LLM generated answers against a golden program
- `run_test.py`: configurable script for sampling test tasks, querying an LLM, and computing pass@k
- `dataset_factory/`: auxiliary generation and prompt-building code used in the broader workflow

## 6. Installation

Recommended environment:

| library | version | used for |
| --- | --- | --- |
| `numpy` | `2.2.4` | numerical arrays, state vectors, sampling, simulator internals |
| `scipy` | `1.15.2` | matrix exponential and numerical routines in pulse simulation |
| `openqasm3` | `1.0.1` | OpenQASM 3 parsing |
| `qiskit` | `2.0.2` | gate matrices, operators, and Statevector-based simulation |
| `qutip` | `5.2.2` | waveform / Hamiltonian-style pulse simulation support |
| `pyarrow` | `22.0.0` | reading and writing Parquet dataset files |

## 7. Output Files

Each run creates a timestamped directory under `test_runs/`, typically containing:

- `summary.json`: run-level configuration, overall pass@k, per-domain pass@k, and token usage
- `details.jsonl`: one row per generated sample, including raw model output and normalized evaluation results

This makes it easy to inspect both aggregate results and individual failures.

## 8. Notes and Caveats

- Quantum-program simulation can be stochastic. The evaluator internally fixes seeds for key checks, but simulation-heavy workflows can still be computationally expensive.
- Some models may emit reasoning traces or thinking content in different output formats. The current code does not include dedicated handling for these variations, and support for them has been left as future work.
- Some models may prepend explanations, markdown fences, or full-program rewrites. These can hurt evaluation even if parts of the generated code are reasonable.

## 9. Citation

To be implemented
