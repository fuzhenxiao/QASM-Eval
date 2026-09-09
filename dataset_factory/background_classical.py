#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate OpenQASM 3 background circuits + per-circuit metadata object.

Outputs in out_dir:
  - bg_000001.qasm
  - bg_000001.meta.json
  - ...
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict, Any, Optional


# ---------------- Gate pools ----------------

SINGLE_Q_GATES = ["h", "x", "y", "z", "s", "sdg", "t", "tdg"]
PARAM_GATES = ["rx", "ry", "rz"]  # angle in radians
TWO_Q_GATES = ["cx", "cz", "swap"]
TIMING_OPS = ["delay", "barrier"]


# ---------------- Data structures ----------------

@dataclass(frozen=True)
class GenSpec:
    n_qubits: int
    depth: int
    p_two_qubit: float
    p_param_gate: float
    p_timing_op: float
    allow_timing: bool
    delay_units: Tuple[str, ...]
    delay_min: int
    delay_max: int


@dataclass(frozen=True)
class BackgroundCircuit:
    file: str
    meta_file: str
    seed: int
    n_qubits: int
    depth: int
    allow_timing: bool
    delay_units: Tuple[str, ...]
    delay_min: int
    delay_max: int

    init_qubits: Tuple[int, ...]
    op_count: int
    op_counts_by_kind: Dict[str, int]   # {"1q":..., "1q_param":..., "2q":..., "delay":..., "barrier":...}
    used_qubits: Tuple[int, ...]        # qubits that appear in any op
    qasm_text: str                      # background qasm containing core markers

    core_start_marker: str = "// === CORE_TASK_START ==="
    core_end_marker: str = "// === CORE_TASK_END ==="

    def with_core(self,
                  core_lines: List[str],
                  *,
                  add_measure_all: bool = False,
                  measure_creg_name: str = "c") -> str:

        core_block = "\n".join(core_lines).rstrip() + "\n"
        if self.core_start_marker not in self.qasm_text or self.core_end_marker not in self.qasm_text:
            raise ValueError("Core markers not found in qasm_text.")

        before, rest = self.qasm_text.split(self.core_start_marker, 1)
        _, after = rest.split(self.core_end_marker, 1)
        new_text = (
            before
            + self.core_start_marker + "\n"
            + core_block
            + self.core_end_marker
            + after
        )

        if add_measure_all:
            meas_lines = []
            meas_lines.append(f"bit[{self.n_qubits}] {measure_creg_name};")
            for i in range(self.n_qubits):
                meas_lines.append(f"{measure_creg_name}[{i}] = measure q[{i}];")
            new_text = new_text.rstrip() + "\n\n// === MEASUREMENT ===\n" + "\n".join(meas_lines) + "\n"

        return new_text

    def to_meta_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------------- Helpers ----------------

def fmt_angle(rad: float) -> str:
    return f"{rad:.10g}"


def rand_angle(rng: random.Random) -> float:
    choices = [
        0.0,
        math.pi / 12,
        math.pi / 8,
        math.pi / 6,
        math.pi / 4,
        math.pi / 3,
        math.pi / 2,
        2 * math.pi / 3,
        3 * math.pi / 4,
        math.pi,
        -math.pi / 2,
        -math.pi / 4,
    ]
    if rng.random() < 0.7:
        return rng.choice(choices)
    return (rng.random() * 2 - 1) * math.pi


def pick_two_distinct(rng: random.Random, n: int) -> Tuple[int, int]:
    a = rng.randrange(n)
    b = rng.randrange(n - 1)
    if b >= a:
        b += 1
    return a, b


def gen_delay_stmt(rng: random.Random, spec: GenSpec) -> Tuple[str, int]:
    q = rng.randrange(spec.n_qubits)
    unit = rng.choice(spec.delay_units)
    val = rng.randint(spec.delay_min, spec.delay_max)
    return f"delay[{val}{unit}] q[{q}];", q


def gen_barrier_stmt(spec: GenSpec) -> Tuple[str, Tuple[int, ...]]:
    return "barrier q;", tuple(range(spec.n_qubits))


def gen_single_stmt(rng: random.Random, spec: GenSpec) -> Tuple[str, int]:
    q = rng.randrange(spec.n_qubits)
    g = rng.choice(SINGLE_Q_GATES)
    return f"{g} q[{q}];", q


def gen_param_stmt(rng: random.Random, spec: GenSpec) -> Tuple[str, int]:
    q = rng.randrange(spec.n_qubits)
    g = rng.choice(PARAM_GATES)
    ang = fmt_angle(rand_angle(rng))
    return f"{g}({ang}) q[{q}];", q


def gen_twoq_stmt(rng: random.Random, spec: GenSpec) -> Tuple[str, Tuple[int, int]]:
    a, b = pick_two_distinct(rng, spec.n_qubits)
    g = rng.choice(TWO_Q_GATES)
    if g in ("cx", "cz"):
        return f"{g} q[{a}], q[{b}];", (a, b)
    return f"swap q[{a}], q[{b}];", (a, b)


def sample_spec(rng: random.Random,
                *,
                min_qubits: int,
                max_qubits: int,
                min_depth: int,
                max_depth: int,
                p_two_qubit: float,
                p_param_gate: float,
                p_timing_op: float,
                allow_timing: bool,
                delay_units: Tuple[str, ...],
                delay_min: int,
                delay_max: int) -> GenSpec:
    n_qubits = rng.randint(min_qubits, max_qubits)
    depth = rng.randint(min_depth, max_depth)
    return GenSpec(
        n_qubits=n_qubits,
        depth=depth,
        p_two_qubit=p_two_qubit,
        p_param_gate=p_param_gate,
        p_timing_op=p_timing_op,
        allow_timing=allow_timing,
        delay_units=delay_units,
        delay_min=delay_min,
        delay_max=delay_max,
    )


def generate_background_qasm(rng: random.Random, spec: GenSpec) -> Tuple[str, Dict[str, Any]]:

    lines: List[str] = []
    used_qubits = set()

    op_counts_by_kind = {"1q": 0, "1q_param": 0, "2q": 0, "delay": 0, "barrier": 0}

    lines.append("OPENQASM 3;")
    lines.append('include "stdgates.inc";')
    lines.append("")
    lines.append(f"qubit[{spec.n_qubits}] q;")
    lines.append("")

    init_count = max(1, spec.n_qubits // 4)
    init_idxs = rng.sample(range(spec.n_qubits), k=init_count)
    for i, q in enumerate(init_idxs):
        stmt = f"h q[{q}];" if (i % 2 == 0) else f"x q[{q}];"
        lines.append(stmt)
        used_qubits.add(q)
        op_counts_by_kind["1q"] += 1

    lines.append("")

    for _ in range(spec.depth):
        r = rng.random()

        if spec.allow_timing and r < spec.p_timing_op:
            t = rng.choice(TIMING_OPS)
            if t == "delay":
                stmt, q = gen_delay_stmt(rng, spec)
                lines.append(stmt)
                used_qubits.add(q)
                op_counts_by_kind["delay"] += 1
            else:
                stmt, qs = gen_barrier_stmt(spec)
                lines.append(stmt)
                used_qubits.update(qs)
                op_counts_by_kind["barrier"] += 1
            continue

        if r < spec.p_timing_op + spec.p_two_qubit and spec.n_qubits >= 2:
            stmt, qs = gen_twoq_stmt(rng, spec)
            lines.append(stmt)
            used_qubits.update(qs)
            op_counts_by_kind["2q"] += 1
            continue

        if r < spec.p_timing_op + spec.p_two_qubit + spec.p_param_gate:
            stmt, q = gen_param_stmt(rng, spec)
            lines.append(stmt)
            used_qubits.add(q)
            op_counts_by_kind["1q_param"] += 1
            continue

        stmt, q = gen_single_stmt(rng, spec)
        lines.append(stmt)
        used_qubits.add(q)
        op_counts_by_kind["1q"] += 1

    lines.append("")
    lines.append("// === CORE_TASK_START ===")
    lines.append("// (append your timing core-task here)")
    lines.append("// === CORE_TASK_END ===")
    lines.append("")
 

    qasm_text = "\n".join(lines) + "\n"
    stats = {
        "init_qubits": tuple(init_idxs),
        "used_qubits": tuple(sorted(used_qubits)),
        "op_counts_by_kind": op_counts_by_kind,
        "op_count": sum(op_counts_by_kind.values()),
    }
    return qasm_text, stats


def generate_background_pool(out_dir: str,
                             num: int,
                             seed: int,
                             *,
                             min_qubits: int = 2,
                             max_qubits: int = 8,
                             min_depth: int = 10,
                             max_depth: int = 30,
                             p_two_qubit: float = 0.30,
                             p_param_gate: float = 0.30,
                             p_timing_op: float = 0.12,
                             allow_timing: bool = True,
                             delay_units: Tuple[str, ...] = ("ns", "dt"),
                             delay_min: int = 1,
                             delay_max: int = 80,
                             file_prefix: str = "bg_",
                             manifest_name: str = "manifest.jsonl",
                             overwrite: bool = True,
                             write_meta_json: bool = True,
                             meta_suffix: str = ".meta.json") -> List[BackgroundCircuit]:

    if min_qubits < 1 or max_qubits < min_qubits:
        raise ValueError("Invalid qubit range.")
    if min_depth < 0 or max_depth < min_depth:
        raise ValueError("Invalid depth range.")
    if not delay_units:
        raise ValueError("delay_units must be non-empty.")
    if delay_min < 0 or delay_max < delay_min:
        raise ValueError("Invalid delay range. (delay_min must be >=0 and <= delay_max)")
    if num < 1:
        raise ValueError("num must be >= 1")

    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, manifest_name)
    if (not overwrite) and os.path.exists(manifest_path):
        raise FileExistsError(f"Manifest already exists: {manifest_path}")

    base_rng = random.Random(seed)
    circuits: List[BackgroundCircuit] = []

    with open(manifest_path, "w", encoding="utf-8") as mf:
        for i in range(1, num + 1):
            circ_seed = base_rng.randrange(1_000_000_000)
            rng = random.Random(circ_seed)

            spec = sample_spec(
                rng,
                min_qubits=min_qubits,
                max_qubits=max_qubits,
                min_depth=min_depth,
                max_depth=max_depth,
                p_two_qubit=p_two_qubit,
                p_param_gate=p_param_gate,
                p_timing_op=p_timing_op,
                allow_timing=allow_timing,
                delay_units=delay_units,
                delay_min=delay_min,
                delay_max=delay_max,
            )

            qasm_text, stats = generate_background_qasm(rng, spec)

            fname = f"{file_prefix}{i:06d}.qasm"
            meta_name = f"{file_prefix}{i:06d}{meta_suffix}"
            qasm_path = os.path.join(out_dir, fname)
            meta_path = os.path.join(out_dir, meta_name)

            if (not overwrite) and os.path.exists(qasm_path):
                raise FileExistsError(f"File already exists: {qasm_path}")
            if write_meta_json and (not overwrite) and os.path.exists(meta_path):
                raise FileExistsError(f"File already exists: {meta_path}")

            with open(qasm_path, "w", encoding="utf-8") as f:
                f.write(qasm_text)

            bc = BackgroundCircuit(
                file=fname,
                meta_file=meta_name,
                seed=circ_seed,
                n_qubits=spec.n_qubits,
                depth=spec.depth,
                allow_timing=spec.allow_timing,
                delay_units=spec.delay_units,
                delay_min=spec.delay_min,
                delay_max=spec.delay_max,
                init_qubits=stats["init_qubits"],
                op_count=stats["op_count"],
                op_counts_by_kind=stats["op_counts_by_kind"],
                used_qubits=stats["used_qubits"],
                qasm_text=qasm_text,
            )

            if write_meta_json:
                with open(meta_path, "w", encoding="utf-8") as jf:
                    json.dump(bc.to_meta_dict(), jf, ensure_ascii=False, indent=2)

            manifest_record = {
                "file": fname,
                "meta_file": meta_name if write_meta_json else None,
                "seed": circ_seed,
                "n_qubits": spec.n_qubits,
                "depth": spec.depth,
                "allow_timing": spec.allow_timing,
                "delay_units": list(spec.delay_units),
                "delay_min": spec.delay_min,
                "delay_max": spec.delay_max,
                "op_count": bc.op_count,
                "op_counts_by_kind": bc.op_counts_by_kind,
                "used_qubits": list(bc.used_qubits),
                "init_qubits": list(bc.init_qubits),
            }
            mf.write(json.dumps(manifest_record, ensure_ascii=False) + "\n")

            circuits.append(bc)

    return circuits


def main() -> None:

    out_dir = "classical_background"
    num = 500
    seed = 123

    circuits = generate_background_pool(
        out_dir=out_dir,
        num=num,
        seed=seed,
        min_qubits=3,
        max_qubits=6,
        min_depth=10,
        max_depth=30,
        # op mixture
        p_two_qubit=0.30,
        p_param_gate=0.30,
        p_timing_op=0.12,
        allow_timing=True,           # set False to forbid delay/barrier in background

        delay_units=("ns", "dt"),
        delay_min=1,
        delay_max=80,
        overwrite=True,
        write_meta_json=True,
    )

    print(f"Done. Generated {len(circuits)} backgrounds into: {out_dir}")
    if circuits:
        print("Example meta fields:", {
            "file": circuits[0].file,
            "n_qubits": circuits[0].n_qubits,
            "used_qubits": circuits[0].used_qubits,
            "op_counts_by_kind": circuits[0].op_counts_by_kind
        })


if __name__ == "__main__":
    main()
