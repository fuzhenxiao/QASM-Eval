# pulse_background_gen.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import os
import json
import random
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional


CORE_START = "// === CORE_TASK_START ==="
CORE_END   = "// === CORE_TASK_END ==="


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
    # returns like "5.123e9"
    v = lo + (hi - lo) * rng.random()
    return f"{v:.6f}e9"

def _angle(rng: random.Random, lo: float = -0.6, hi: float = 0.6) -> str:
    v = lo + (hi - lo) * rng.random()
    return f"{v:.6f}"

def _dt(rng: random.Random, lo: int, hi: int) -> str:
    return f"{rng.randint(lo, hi)}dt"



@dataclass
class PulseBackground:
    qasm: str
    meta: Dict[str, Any]



def build_one_pulse_background(bg_index: int, rng: random.Random) -> PulseBackground:


    # Choose qubit count (tune as you like)
    n_qubits = rng.choice([3, 4, 5])
    used = _pick_subset(rng, n_qubits, min_k=1)

    # Names (ports/frames)
    drive_ports = {str(i): f"d{i}" for i in range(n_qubits)}
    meas_ports  = {str(i): f"m{i}" for i in range(n_qubits)}
    acq_ports   = {str(i): f"a{i}" for i in range(n_qubits)}

    drive_frames = {str(i): f"q{i}_drive" for i in range(n_qubits)}
    meas_frames  = {str(i): f"q{i}_meas"  for i in range(n_qubits)}
    acq_frames   = {str(i): f"q{i}_acq"   for i in range(n_qubits)}

    # Frequencies (strings so you can round-trip exactly)
    drive_freq = {str(i): _float_e9(rng, 4.6, 6.8) for i in range(n_qubits)}
    meas_freq  = {str(i): _float_e9(rng, 6.0, 7.2) for i in range(n_qubits)}

    # Pulse params
    amp_choices = ["1.0", "0.8", "0.5", "0.2"]
    amp = rng.choice(amp_choices)
    dur = _dt(rng, 16, 80)
    sig = _dt(rng, 4, 30)

    # Background pulse actions (applied only on used qubits to create “state/timing/phase context”)
    bg_actions: List[Dict[str, Any]] = []
    for qi in used:
        act = {
            "qubit": qi,
            "frame": drive_frames[str(qi)],
            "phase_shift": _angle(rng),
            "freq_shift_hz": (rng.randint(-20_000_000, 20_000_000)),  # +/- 20 MHz
            "idle_dt": int(_dt(rng, 8, 80).replace("dt", "")),
        }
        bg_actions.append(act)

    L: List[str] = []
    L.append("OPENQASM 3;")
    L.append('include "stdgates.inc";')
    L.append("")
    L.append(f"// Pulse background {bg_index:06d}")
    L.append(f"qubit[{n_qubits}] q;")
    L.append("")
    L.append('defcalgrammar "openpulse";')
    L.append("")

    for i in range(n_qubits):
        L.append(f"const float drive_freq_{i} = {drive_freq[str(i)]};")
        L.append(f"const float meas_freq_{i}  = {meas_freq[str(i)]};")
    L.append("")

    L.append("cal {")
    L.append("  // --- declare ports ---")
    for i in range(n_qubits):
        L.append(f"  extern port {drive_ports[str(i)]};")
        L.append(f"  extern port {meas_ports[str(i)]};")
        L.append(f"  extern port {acq_ports[str(i)]};")
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
    for i in range(n_qubits):
        L.append(f"  frame {drive_frames[str(i)]} = newframe({drive_ports[str(i)]}, drive_freq_{i}, 0.0);")
        L.append(f"  frame {meas_frames[str(i)]}  = newframe({meas_ports[str(i)]},  meas_freq_{i},  0.0);")
        L.append(f"  frame {acq_frames[str(i)]}   = newframe({acq_ports[str(i)]},   meas_freq_{i},  0.0);")
    L.append("")


    L.append("  // --- background pulse actions (phase/freq/time context) ---")
    L.append(f"  waveform _bg_wf = gaussian({amp}, {dur}, {sig});")
    for act in bg_actions:
        fr = act["frame"]
        ph = act["phase_shift"]
        df = act["freq_shift_hz"]
        idle = f'{act["idle_dt"]}dt'

        L.append(f"  shift_phase({fr}, {ph});")
        L.append(f"  set_frequency({fr}, (get_frequency({fr}) + {df}.0));")
        L.append(f"  delay[{idle}] {fr};")
        L.append(f"  play({fr}, _bg_wf);")

    if len(used) >= 2:
        frames_list = ", ".join(drive_frames[str(i)] for i in used)
        L.append(f"  barrier {frames_list};")
    L.append("}")
    L.append("")


    L.append("// --- gate-level background circuit ---")

    depth = rng.randint(3, 10)
    for _ in range(depth):
        qi = rng.randrange(n_qubits)
        gate = rng.choice(["h", "x", "rz", "rx"])
        if gate in ("h", "x"):
            L.append(f"{gate} q[{qi}];")
        elif gate == "rz":
            ang = _angle(rng, -1.2, 1.2)
            L.append(f"rz({ang}) q[{qi}];")
        else:  # rx
            ang = _angle(rng, -1.2, 1.2)
            L.append(f"rx({ang}) q[{qi}];")

        # occasional entangling if possible
        if n_qubits >= 2 and rng.random() < 0.25:
            a, b = rng.sample(range(n_qubits), 2)
            L.append(f"cx q[{a}], q[{b}];")

    L.append("")
    L.append(CORE_START)
    L.append("// (core pulse task will be inserted here)")
    L.append(CORE_END)
    L.append("")

    qasm_text = "\n".join(L).rstrip() + "\n"

    meta: Dict[str, Any] = {
        "bg_id": f"bg_{bg_index:06d}",
        "n_qubits": n_qubits,
        "used_qubits": used,
        "pulse": {
            "preferred_duration_unit": "dt",
            "ports": {
                "drive": drive_ports,
                "meas": meas_ports,
                "acq": acq_ports,
            },
            "frames": {
                "drive": drive_frames,
                "meas": meas_frames,
                "acq": acq_frames,
            },
            "freq": {
                "drive_hz": drive_freq,
                "meas_hz": meas_freq,
            },
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
            "core_markers": {"start": CORE_START, "end": CORE_END},
        },
    }

    return PulseBackground(qasm=qasm_text, meta=meta)


def generate_pulse_backgrounds(
    out_dir: str = "pulse_background",
    n: int = 500,
    seed: int = 20260108,
) -> None:
    rng = random.Random(seed)
    _mkdir(out_dir)

    for i in range(1, n + 1):
        bg = build_one_pulse_background(i, rng)
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
        "core_markers": {"start": CORE_START, "end": CORE_END},
    }
    _write_json(index_path, index)


def main() -> None:

    generate_pulse_backgrounds(out_dir="pulse_background", n=25, seed=20260108)
    print("Done. Wrote pulse backgrounds to pulse_background/")

if __name__ == "__main__":
    main()
