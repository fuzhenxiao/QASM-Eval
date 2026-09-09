#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List


CORE_START = "// === CORE_TASK_START ==="
CORE_END = "// === CORE_TASK_END ==="
MEAS_START = "// === MEASUREMENT_START ==="
MEAS_END = "// === MEASUREMENT_END ==="


def _mkdir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _write_text(path: str, text: str) -> None:
    _mkdir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    _mkdir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _pick_subset(rng: random.Random, n: int, min_k: int = 1) -> List[int]:
    k = rng.randint(min_k, max(min_k, n))
    return sorted(rng.sample(list(range(n)), k))


def _float_e9(rng: random.Random, lo: float, hi: float) -> str:
    v = lo + (hi - lo) * rng.random()
    return f"{v:.6f}e9"


def _angle(rng: random.Random, lo: float = -0.8, hi: float = 0.8) -> str:
    v = lo + (hi - lo) * rng.random()
    return f"{v:.6f}"


def _dt(rng: random.Random, lo: int, hi: int) -> str:
    return f"{rng.randint(lo, hi)}dt"


@dataclass
class ComplexBackground:
    qasm: str
    meta: Dict[str, Any]


def build_one_complex_background(bg_index: int, rng: random.Random, *,
                                 min_qubits: int = 2,
                                 max_qubits: int = 8,
                                 min_depth: int = 10,
                                 max_depth: int = 24) -> ComplexBackground:

    n_qubits = rng.randint(min_qubits, max_qubits)
    used = _pick_subset(rng, n_qubits, min_k=1)

    drive_ports = {str(i): f"d{i}" for i in range(n_qubits)}
    meas_ports = {str(i): f"m{i}" for i in range(n_qubits)}
    acq_ports = {str(i): f"a{i}" for i in range(n_qubits)}

    drive_frames = {str(i): f"q{i}_drive" for i in range(n_qubits)}
    meas_frames = {str(i): f"q{i}_meas" for i in range(n_qubits)}
    acq_frames = {str(i): f"q{i}_acq" for i in range(n_qubits)}

    drive_freq = {str(i): _float_e9(rng, 4.6, 6.8) for i in range(n_qubits)}
    meas_freq = {str(i): _float_e9(rng, 6.0, 7.4) for i in range(n_qubits)}

    amp = rng.choice(["1.0", "0.8", "0.5", "0.25"])
    dur = _dt(rng, 64, 320)
    sig = _dt(rng, 16, 120)

    bg_actions: List[Dict[str, Any]] = []
    if used and rng.random() < 0.85: 
        qi = rng.choice(used)
        bg_actions.append({
            "qubit": qi,
            "frame": drive_frames[str(qi)],
            "phase_shift": _angle(rng),
            "freq_shift_hz": rng.randint(-5_000_000, 5_000_000),
            "idle_dt": int(_dt(rng, 8, 40).replace("dt", "")),
        })

    L: List[str] = []
    L.append("OPENQASM 3;")
    L.append('include "stdgates.inc";')
    L.append("")
    L.append(f"// Complex background {bg_index:06d}")
    L.append("// Contains: timing + classical + openpulse resources")
    L.append("")
    L.append(f"qubit[{n_qubits}] q;")
    L.append("")

    L.append("// ---- classical registers / counters (available to core tasks) ----")
    L.append(f"bit[{n_qubits}] bg_m;")
    L.append(f"bit[{n_qubits}] bg_m2;")
    L.append(f"bit[{n_qubits}] syndrome_b;")
    L.append("bool flag;")
    L.append("int[32] i;")
    L.append("int[32] step;")
    L.append("int[32] tries;")
    L.append("int[32] pc;")
    L.append("uint[32] mask;")
    L.append("float[64] gain;")
    L.append("")
    L.append("// One generic extern hook for 'controller-side' update logic")
    L.append("extern adaptive_update(int[32], int[32], float[64]) -> float[64];")
    L.append("")

    L.append("// ---- timing-friendly constants (core tasks may reuse) ----")
    L.append("const duration BG_IDLE  = 52ns;")
    L.append("const duration RO_RING  = 37us;")
    L.append("const duration BOX_WIN  = 251dt;")
    L.append("")

    L.append('defcalgrammar "openpulse";')
    L.append("")
    for i_q in range(n_qubits):
        L.append(f"const float drive_freq_{i_q} = {drive_freq[str(i_q)]};")
        L.append(f"const float meas_freq_{i_q}  = {meas_freq[str(i_q)]};")
    L.append("")

    L.append("cal {")
    L.append("  // --- declare ports ---")
    for i_q in range(n_qubits):
        L.append(f"  extern port {drive_ports[str(i_q)]};")
        L.append(f"  extern port {meas_ports[str(i_q)]};")
        L.append(f"  extern port {acq_ports[str(i_q)]};")
    L.append("")

    L.append("  // --- extern waveform templates (common) ---")
    L.append("  extern gaussian(complex[float[32]] amp, duration d, duration sigma) -> waveform;")
    L.append("  extern drag(complex[float[32]] amp, duration d, duration sigma, float[32] beta) -> waveform;")
    L.append("  extern constant(complex[float[32]] amp, duration d) -> waveform;")
    L.append("  extern sine(complex[float[32]] amp, duration d, float[64] frequency, angle phase) -> waveform;")
    L.append("  extern gaussian_square(complex[float[32]] amp, duration d, duration square_width, duration sigma) -> waveform;")
    L.append("")

    L.append("  // --- extern capture/discriminate hooks (for measure-style tasks) ---")
    L.append("  extern capture(frame capture_frame, waveform filter) -> bit;")
    L.append("  extern capture_v1(frame capture_frame, duration d) -> waveform;")
    L.append("  extern discriminate(complex[float[64]] iq) -> bit;")
    L.append("")

    L.append("  // --- create frames ---")
    for i_q in range(n_qubits):
        L.append(f"  frame {drive_frames[str(i_q)]} = newframe({drive_ports[str(i_q)]}, drive_freq_{i_q}, 0.0);")
        L.append(f"  frame {meas_frames[str(i_q)]}  = newframe({meas_ports[str(i_q)]},  meas_freq_{i_q},  0.0);")
        L.append(f"  frame {acq_frames[str(i_q)]}   = newframe({acq_ports[str(i_q)]},   meas_freq_{i_q},  0.0);")
    L.append("")

    L.append("  // --- background pulse actions (VERY LIGHTWEIGHT; no play) ---")
    for act in bg_actions:
        fr = act["frame"]
        ph = act["phase_shift"]
        df = act["freq_shift_hz"]
        idle = f"{act['idle_dt']}dt"

        L.append(f"  shift_phase({fr}, {ph});")
        L.append(f"  set_frequency({fr}, (get_frequency({fr}) + {df}.0));")

        L.append(f"  delay[{idle}] {fr};")


    if len(used) >= 2:
        frames_list = ", ".join(drive_frames[str(i_q)] for i_q in used)
        L.append(f"  barrier {frames_list};")
    L.append("}")
    L.append("")


    L.append("// --- classical init (lightweight) ---")
    L.append("flag = false;")
    L.append("step = 0;")
    L.append("tries = 0;")
    L.append("pc = 0;")
    L.append("mask = 0;")
    L.append("gain = 1.0;")

    for qi in range(n_qubits):
        L.append(f"bg_m[{qi}] = 0;")
        L.append(f"bg_m2[{qi}] = 0;")
        L.append(f"syndrome_b[{qi}] = 0;")
    L.append("")


    L.append("// --- gate-level + timing background circuit ---")
    depth = rng.randint(min_depth, max_depth)
    for _ in range(depth):
        r = rng.random()

        if r < 0.12:
            qi = rng.randrange(n_qubits)
            if rng.random() < 0.75:

                unit = rng.choice(["ns", "dt"])
                val = rng.randint(1, 80)
                L.append(f"delay[{val}{unit}] q[{qi}];")
            else:
                L.append("barrier q;")
            continue


        if r < 0.12 + 0.30 and n_qubits >= 2:
            a, b = rng.sample(range(n_qubits), 2)
            g2 = rng.choice(["cx", "cz", "swap"])
            if g2 == "swap":
                L.append(f"swap q[{a}], q[{b}];")
            else:
                L.append(f"{g2} q[{a}], q[{b}];")
            continue

        # param gate
        if r < 0.12 + 0.30 + 0.30:
            qi = rng.randrange(n_qubits)
            g1 = rng.choice(["rx", "ry", "rz"])
            ang = _angle(rng, -1.2, 1.2)
            L.append(f"{g1}({ang}) q[{qi}];")
            continue

        # single gate
        qi = rng.randrange(n_qubits)
        g0 = rng.choice(["h", "x", "y", "z", "s", "sdg", "t", "tdg"])
        L.append(f"{g0} q[{qi}];")

    L.append("")

    L.append("// --- timing context: a fixed control window (for DD / readout ring) ---")

    L.append("box[BOX_WIN] {")
    L.append("  delay[BG_IDLE] q[0];")
    if n_qubits >= 2:
        L.append("  // independent idle on another qubit to encourage parallel scheduling")
        L.append("  delay[BG_IDLE] q[1];")
    L.append("}")
    L.append("")


    L.append(CORE_START)
    L.append("// (core complex task will be inserted here)")
    L.append(CORE_END)
    L.append("")
    L.append(MEAS_START)
    L.append("// (measurement block will be inserted here)")
    L.append(MEAS_END)
    L.append("")

    qasm_text = "\n".join(L).rstrip() + "\n"

    meta: Dict[str, Any] = {
        "bg_id": f"bg_{bg_index:06d}",
        "n_qubits": n_qubits,
        "used_qubits": used,
        "core_markers": {"start": CORE_START, "end": CORE_END},
        "meas_markers": {"start": MEAS_START, "end": MEAS_END},
        "timing": {
            "constants": {
                "BG_IDLE": "52ns",
                "RO_RING": "37us",
                "BOX_WIN": "251dt",
            },
            "background": {
                "depth": depth,
                "delay_units": ["ns", "dt"],
                "delay_range": [1, 80],
            },
        },
        "classical": {
            "workspace": {
                "bg_m": f"bit[{n_qubits}]",
                "bg_m2": f"bit[{n_qubits}]",
                "syndrome_b": f"bit[{n_qubits}]",
                "flag": "bool",
                "i": "int[32]",
                "step": "int[32]",
                "tries": "int[32]",
                "pc": "int[32]",
                "mask": "uint[32]",
                "gain": "float[64]",
            },
            "extern": ["adaptive_update(int[32], int[32], float[64]) -> float[64]"],
        },
        "pulse": {
            "preferred_duration_unit": "dt",
            "ports": {"drive": drive_ports, "meas": meas_ports, "acq": acq_ports},
            "frames": {"drive": drive_frames, "meas": meas_frames, "acq": acq_frames},
            "freq": {"drive_hz": drive_freq, "meas_hz": meas_freq},
            "extern_waveforms": [
                "extern gaussian(complex[float[32]] amp, duration d, duration sigma) -> waveform;",
                "extern drag(complex[float[32]] amp, duration d, duration sigma, float[32] beta) -> waveform;",
                "extern constant(complex[float[32]] amp, duration d) -> waveform;",
                "extern sine(complex[float[32]] amp, duration d, float[64] frequency, angle phase) -> waveform;",
                "extern gaussian_square(complex[float[32]] amp, duration d, duration square_width, duration sigma) -> waveform;",
            ],
            "extern_io": [
                "extern capture(frame capture_frame, waveform filter) -> bit;",
                "extern capture_v1(frame capture_frame, duration d) -> waveform;",
                "extern discriminate(complex[float[64]] iq) -> bit;",
            ],
            "background_pulse_actions": bg_actions,
        },
    }

    return ComplexBackground(qasm=qasm_text, meta=meta)


def generate_complex_backgrounds(
    out_dir: str = "complex_background",
    n: int = 500,
    seed: int = 20260115,
    *,
    min_qubits: int = 3,
    max_qubits: int = 5,
    min_depth: int = 6,
    max_depth: int = 14,
) -> None:
    rng = random.Random(seed)
    _mkdir(out_dir)

    for i in range(1, n + 1):
        bg = build_one_complex_background(
            i,
            rng,
            min_qubits=min_qubits,
            max_qubits=max_qubits,
            min_depth=min_depth,
            max_depth=max_depth,
        )
        qasm_path = os.path.join(out_dir, f"bg_{i:06d}.qasm")
        meta_path = os.path.join(out_dir, f"bg_{i:06d}.meta.json")
        _write_text(qasm_path, bg.qasm)
        _write_json(meta_path, bg.meta)

    index_path = os.path.join(out_dir, "index.json")
    index = {
        "count": n,
        "seed": seed,
        "pattern_qasm": "bg_%06d.qasm",
        "pattern_meta": "bg_%06d.meta.json",
        "markers": {
            "core": {"start": CORE_START, "end": CORE_END},
            "measurement": {"start": MEAS_START, "end": MEAS_END},
        },
        "defaults": {
            "min_qubits": min_qubits,
            "max_qubits": max_qubits,
            "min_depth": min_depth,
            "max_depth": max_depth,
        },
    }
    _write_json(index_path, index)


def main() -> None:
    generate_complex_backgrounds(out_dir="complex_background", n=25, seed=20260115)
    print("Done. Wrote complex backgrounds to complex_background/")


if __name__ == "__main__":
    main()
