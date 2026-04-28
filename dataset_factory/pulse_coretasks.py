# pulse_core_generators.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import json
import random
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable, Tuple

# -------------------- Markers --------------------
CORE_START = "// === CORE_TASK_START ==="
CORE_END   = "// === CORE_TASK_END ==="
MEAS_START = "// === MEASUREMENT_START ==="
MEAS_END   = "// === MEASUREMENT_END ==="

# -------------------- Meta helpers --------------------

def load_meta(meta_path: str) -> Dict[str, Any]:
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)

def n_qubits(meta: Dict[str, Any]) -> int:
    return int(meta["n_qubits"])

def used_qubits(meta: Dict[str, Any]) -> List[int]:
    uq = meta.get("used_qubits", [])
    if isinstance(uq, list) and uq:
        return [int(x) for x in uq]
    return list(range(n_qubits(meta)))

def pick_qubit(meta: Dict[str, Any], rng: random.Random) -> int:
    return rng.choice(used_qubits(meta))

def pick_two(meta: Dict[str, Any], rng: random.Random) -> Tuple[int, int]:
    uq = used_qubits(meta)
    if len(uq) >= 2:
        a, b = rng.sample(uq, 2)
        return a, b
    # fallback
    return 0, 0

def drive_frame(meta: Dict[str, Any], q: int) -> str:
    return meta["pulse"]["frames"]["drive"][str(q)]

def meas_frame(meta: Dict[str, Any], q: int) -> str:
    return meta["pulse"]["frames"]["meas"][str(q)]

def acq_frame(meta: Dict[str, Any], q: int) -> str:
    return meta["pulse"]["frames"]["acq"][str(q)]

def drive_port(meta: Dict[str, Any], q: int) -> str:
    return meta["pulse"]["ports"]["drive"][str(q)]

def meas_port(meta: Dict[str, Any], q: int) -> str:
    return meta["pulse"]["ports"]["meas"][str(q)]

def acq_port(meta: Dict[str, Any], q: int) -> str:
    return meta["pulse"]["ports"]["acq"][str(q)]

def dt(rng: random.Random, lo: int, hi: int) -> str:
    return f"{rng.randint(lo, hi)}dt"

def angle(rng: random.Random, lo: float = -1.2, hi: float = 1.2) -> str:
    v = lo + (hi - lo) * rng.random()
    return f"{v:.6f}"

def hz(rng: random.Random, lo: int = -20_000_000, hi: int = 20_000_000) -> str:
    return f"{rng.randint(lo, hi)}.0"

def c32(r: str) -> str:
    return f"{r}+0.0im"

# -------------------- Measurement helpers --------------------

def measure_subset(meta: Dict[str, Any], subset: List[int], creg: str = "c") -> List[str]:
    nq = n_qubits(meta)
    lines = [f"bit[{nq}] {creg};"]
    for i in sorted(set(subset)):
        lines.append(f"{creg}[{i}] = measure q[{i}];")
    return lines

def measure_all(meta: Dict[str, Any], creg: str = "c") -> List[str]:
    return measure_subset(meta, list(range(n_qubits(meta))), creg=creg)

# -------------------- Task instance --------------------

@dataclass
class PulseTaskInstance:
    theme_id: int
    variant_id: int
    theme_name: str
    variant_name: str
    description: str
    tags: List[str]

    pulse_points: List[str]

    required_meta: List[str]

    params: Dict[str, Any]

    core_lines: List[str]
    meas_lines: List[str]

    def render_segment(self) -> str:
        out: List[str] = []
        out.append(CORE_START)
        out.extend(self.core_lines)
        out.append(CORE_END)
        out.append("")
        out.append(MEAS_START)
        out.extend(self.meas_lines)
        out.append(MEAS_END)
        return "\n".join(out) + "\n"

    def to_record(self) -> Dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "variant_id": self.variant_id,
            "theme_name": self.theme_name,
            "variant_name": self.variant_name,
            "description": self.description,
            "tags": list(self.tags),
            "pulse_points": list(self.pulse_points),
            "required_meta": list(self.required_meta),
            "params": dict(self.params),
        }

def _mk(theme_id: int, v: int, *,
        theme_name: str,
        variant_name: str,
        description: str,
        tags: List[str],
        pulse_points: List[str],
        required_meta: List[str],
        params: Dict[str, Any],
        core: List[str],
        meas: List[str]) -> PulseTaskInstance:

    comment = f"// {theme_name} | {variant_name}: {description}"
    return PulseTaskInstance(
        theme_id=theme_id,
        variant_id=v,
        theme_name=theme_name,
        variant_name=variant_name,
        description=description,
        tags=tags,
        pulse_points=pulse_points,
        required_meta=required_meta,
        params=params,
        core_lines=[comment] + core,
        meas_lines=meas,
    )

# -------------------- Theme names (25) --------------------

THEME_NAMES: Dict[int, str] = {
    1:  "x_gaussian_play",
    2:  "virtual_z_shift_phase",
    3:  "measure_capture_bit",
    4:  "sx_drag_play",
    5:  "cr_composite_multi_frame",
    6:  "active_reset_equal_time_branches",
    7:  "sideband_modulation_mix",
    8:  "raw_samples_waveform_literal",
    9:  "frame_sync_barrier",
    10: "raw_capture_trace",
    11: "defcal_q_vs_physical_qubit",
    12: "multiplexed_readout_multi_frame",
    13: "simultaneous_plays_parallel_frames",
    14: "global_cal_scope_reuse",
    15: "phase_tracking_with_time_advance",
    16: "dd_sequence_delay_play",
    17: "waveform_dsp_add_scale_phase_shift",
    18: "frequency_control_set_shift",
    19: "frame_state_get_set_swap",
    20: "defcal_matching_priority",
    21: "newframe_time_origin_cal_vs_defcal",
    22: "compile_time_determinable_duration",
    23: "frame_collision_avoidance",
    24: "multi_frames_same_port_patterns",
    25: "measurement_return_type_variants",
}

ThemeFn = Callable[[Dict[str, Any], random.Random, int], PulseTaskInstance]

def theme_01(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[1]
    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d = dt(rng, 64, 320)
    s = dt(rng, 16, 120)
    amp = rng.choice(["1.0", "0.8", "0.5", "0.2"])

    tags = ["play", "gaussian", "drive_frame"]
    pulse_points = ["cal block", "waveform extern gaussian", "play(frame,waveform)", "delay[dt] frame"]
    required = [
        "pulse.frames.drive", "pulse.extern_waveforms (gaussian)",
    ]

    if v == 1:
        vn = "cal_play_gaussian_once"
        desc = "Create gaussian waveform and play once on the drive frame."
        core = [
            "cal {",
            f"  waveform w = gaussian({c32(amp)}, {d}, {s});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "amp": amp, "d": d, "sigma": s}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "cal_gaussian_with_pre_delay"
        desc = "Insert an explicit dt delay on the frame before playing gaussian."
        idle = dt(rng, 8, 96)
        core = [
            "cal {",
            f"  waveform w = gaussian({c32(amp)}, {d}, {s});",
            f"  delay[{idle}] {f};",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "amp": amp, "d": d, "sigma": s, "idle": idle}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn = "defcal_x_generic_then_call_x"
        desc = "Define defcal for x on any qubit using gaussian, then call x in gate-level."
        core = [
            f"defcal x q {{",
            f"  // uses drive frame from background naming convention: q{q}_drive not assumed; use array mapping",
            f"}}",
            "// NOTE: in this dataset we avoid relying on implicit frame lookup inside defcal; use cal instead.",
            "cal {",
            f"  waveform w = gaussian({c32(amp)}, {d}, {s});",
            f"  play({f}, w);",
            "}",
            f"x q[{q}];  // gate-level call (may be separately calibrated by target)",
        ]

        params = {"q": q, "frame": f, "amp": amp, "d": d, "sigma": s}
        meas = measure_subset(meta, [q])
        pulse_points += ["(optional) defcal skeleton"]
    else:
        vn = "two_qubits_parallel_play_then_barrier"
        desc = "Play gaussian on two different drive frames and then barrier-align them."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            core = [
                "cal {",
                f"  waveform w1 = gaussian({c32(amp)}, {d}, {s});",
                f"  waveform w2 = gaussian({c32(amp)}, {d}, {s});",
                f"  play({f}, w1);",
                f"  play({f2}, w2);",
                f"  barrier {f}, {f2};",
                "}",
            ]
            params = {"q0": q, "q1": q2, "f0": f, "f1": f2, "amp": amp, "d": d, "sigma": s}
            meas = measure_subset(meta, [q, q2])
            pulse_points += ["barrier frame-list"]
            required += ["pulse.frames.drive for both qubits"]
        else:
            core = [
                "cal {",
                f"  waveform w = gaussian({c32(amp)}, {d}, {s});",
                f"  play({f}, w);",
                "}",
            ]
            params = {"q": q, "frame": f}
            meas = measure_subset(meta, [q])

    return _mk(1, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_02(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[2]
    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    ph = angle(rng, -1.0, 1.0)

    tags = ["frame", "shift_phase", "virtual_z"]
    pulse_points = ["shift_phase(frame, angle)", "get_phase(frame)", "set_phase(frame, angle)"]
    required = ["pulse.frames.drive"]

    if v == 1:
        vn = "shift_phase_then_play"
        desc = "Implement a virtual-Z by shifting the phase of the drive frame before a play."
        d = dt(rng, 64, 256)
        s = dt(rng, 16, 96)
        core = [
            "cal {",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
            f"  shift_phase({f}, {ph});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "phase": ph, "d": d, "sigma": s}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "swap_frame_phases"
        desc = "Swap phases between two frames using get_phase/set_phase."
        q2 = q
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
        f2 = drive_frame(meta, q2)
        core = [
            "cal {",
            f"  angle p1 = get_phase({f});",
            f"  angle p2 = get_phase({f2});",
            f"  set_phase({f}, p2);",
            f"  set_phase({f2}, p1);",
            "}",
        ]
        params = {"q0": q, "q1": q2, "f0": f, "f1": f2}
        meas = measure_subset(meta, [q, q2])
    elif v == 3:
        vn = "shift_phase_then_unshift"
        desc = "Shift phase, do an operation, then shift back (net-zero frame phase)."
        d = dt(rng, 64, 256)
        s = dt(rng, 16, 96)
        core = [
            "cal {",
            f"  waveform w = gaussian({c32('0.8')}, {d}, {s});",
            f"  shift_phase({f}, {ph});",
            f"  play({f}, w);",
            f"  shift_phase({f}, {-float(ph):.6f});",
            "}",
        ]
        params = {"q": q, "frame": f, "phase": ph}
        meas = measure_subset(meta, [q])
    else:
        vn = "virtual_z_between_two_plays"
        desc = "Insert a virtual-Z (shift_phase) between two plays."
        d = dt(rng, 64, 256)
        s = dt(rng, 16, 96)
        ph2 = angle(rng, -1.0, 1.0)
        core = [
            "cal {",
            f"  waveform w1 = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform w2 = gaussian({c32('0.5')}, {d}, {s});",
            f"  play({f}, w1);",
            f"  shift_phase({f}, {ph2});",
            f"  play({f}, w2);",
            "}",
        ]
        params = {"q": q, "frame": f, "phase": ph2}
        meas = measure_subset(meta, [q])

    return _mk(2, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_03(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[3]
    q = pick_qubit(meta, rng)
    aq = acq_frame(meta, q)

    tags = ["capture", "measure", "bit"]
    pulse_points = ["capture(frame, waveform)->bit", "defcal measure ... -> bit (optional)"]
    required = ["pulse.frames.acq", "pulse.extern_io (capture)"]

    filt_d = dt(rng, 64, 256)

    if v == 1:
        vn = "cal_capture_bit_direct"
        desc = "Use capture(acq_frame, filter) to obtain a bit inside cal."
        core = [
            "cal {",
            f"  waveform f = constant({c32('0.0')}, {filt_d});",
            f"  bit m = capture({aq}, f);",
            "  // m is an observable classical result within cal; final QASM measure is still provided below",
            "}",
        ]
        params = {"q": q, "acq_frame": aq, "filter_d": filt_d}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "defcal_measure_returns_bit"
        desc = "Define a measure calibration returning bit via capture, then use standard measure."
        core = [
            f"defcal measure $0 -> bit {{",
            f"  waveform f = constant({c32('0.0')}, {filt_d});",
            f"  return capture({aq}, f);",
            f"}}",
        ]
        params = {"q": q, "acq_frame": aq, "filter_d": filt_d}
        meas = measure_subset(meta, [q])
        pulse_points += ["defcal measure -> bit"]
        required += ["pulse.frames.acq for q", "pulse.extern_waveforms (constant)"]
    elif v == 3:
        vn = "capture_with_barrier_alignment"
        desc = "Barrier-align the acq frame with its meas frame before capture."
        mf = meas_frame(meta, q)
        core = [
            "cal {",
            f"  barrier {mf}, {aq};",
            f"  waveform f = constant({c32('0.0')}, {filt_d});",
            f"  bit m = capture({aq}, f);",
            "}",
        ]
        params = {"q": q, "meas_frame": mf, "acq_frame": aq, "filter_d": filt_d}
        meas = measure_subset(meta, [q])
        pulse_points += ["barrier on frames"]
        required += ["pulse.frames.meas"]
    else:
        vn = "two_qubit_capture_two_bits"
        desc = "Capture two qubits (two acq frames) and produce two bits in cal."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            aq2 = acq_frame(meta, q2)
            core = [
                "cal {",
                f"  waveform f = constant({c32('0.0')}, {filt_d});",
                f"  bit m0 = capture({aq}, f);",
                f"  bit m1 = capture({aq2}, f);",
                "}",
            ]
            params = {"q0": q, "q1": q2, "acq0": aq, "acq1": aq2, "filter_d": filt_d}
            meas = measure_subset(meta, [q, q2])
            required += ["pulse.frames.acq (two qubits)"]
        else:
            core = [
                "cal {",
                f"  waveform f = constant({c32('0.0')}, {filt_d});",
                f"  bit m = capture({aq}, f);",
                "}",
            ]
            params = {"q": q, "acq_frame": aq}
            meas = measure_subset(meta, [q])

    return _mk(3, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_04(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[4]
    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d = dt(rng, 16, 80)
    s = dt(rng, 4, 30)
    beta = f"{(0.5 + 2.0 * rng.random()):.3f}"

    tags = ["drag", "sx", "play"]
    pulse_points = ["extern drag(...)->waveform", "play(frame,waveform)", "delay[dt] frame"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (drag)"]

    if v == 1:
        vn = "cal_play_drag"
        desc = "Play a DRAG waveform on the drive frame."
        core = [
            "cal {",
            f"  waveform w = drag({c32('0.5')}, {d}, {s}, {beta});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "d": d, "sigma": s, "beta": beta}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "compare_gaussian_then_drag"
        desc = "Play gaussian then drag back-to-back on the same frame."
        core = [
            "cal {",
            f"  waveform g = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform w = drag({c32('0.5')}, {d}, {s}, {beta});",
            f"  play({f}, g);",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "d": d, "sigma": s, "beta": beta}
        meas = measure_subset(meta, [q])
        required += ["pulse.extern_waveforms (gaussian)"]
    elif v == 3:
        vn = "drag_with_intermediate_phase_shift"
        desc = "Shift frame phase between two DRAG plays."
        ph = angle(rng, -0.8, 0.8)
        core = [
            "cal {",
            f"  waveform w = drag({c32('0.5')}, {d}, {s}, {beta});",
            f"  play({f}, w);",
            f"  shift_phase({f}, {ph});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "phase": ph, "d": d, "sigma": s, "beta": beta}
        meas = measure_subset(meta, [q])
        pulse_points += ["shift_phase"]
    else:
        vn = "drag_on_two_frames_then_barrier"
        desc = "Play DRAG on two drive frames and barrier-align."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            core = [
                "cal {",
                f"  waveform w1 = drag({c32('0.5')}, {d}, {s}, {beta});",
                f"  waveform w2 = drag({c32('0.5')}, {d}, {s}, {beta});",
                f"  play({f}, w1);",
                f"  play({f2}, w2);",
                f"  barrier {f}, {f2};",
                "}",
            ]
            params = {"q0": q, "q1": q2, "f0": f, "f1": f2, "d": d, "sigma": s, "beta": beta}
            meas = measure_subset(meta, [q, q2])
            pulse_points += ["barrier frames"]
        else:
            core = [
                "cal {",
                f"  waveform w = drag({c32('0.5')}, {d}, {s}, {beta});",
                f"  play({f}, w);",
                "}",
            ]
            params = {"q": q, "frame": f}
            meas = measure_subset(meta, [q])

    return _mk(4, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_05(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[5]
    q0, q1 = pick_two(meta, rng)
    f0 = drive_frame(meta, q0)
    f1 = drive_frame(meta, q1)
    d = dt(rng, 96, 384)
    s = dt(rng, 24, 160)

    tags = ["cr", "multi_frame", "barrier", "gaussian_square"]
    pulse_points = ["multiple frames", "play on both frames", "barrier align", "gaussian_square"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian_square, gaussian)"]

    if v == 1:
        vn = "cr_like_parallel_pulses"
        desc = "CR-like composite: play shaped pulse on control and target frames in parallel."
        core = [
            "cal {",
            f"  waveform wc = gaussian_square({c32('0.5')}, {d}, {dt(rng, 16, 64)}, {s});",
            f"  waveform wt = gaussian({c32('0.2')}, {d}, {s});",
            f"  play({f0}, wc);",
            f"  play({f1}, wt);",
            f"  barrier {f0}, {f1};",
            "}",
        ]
        params = {"q0": q0, "q1": q1, "f0": f0, "f1": f1, "d": d, "sigma": s}
        meas = measure_subset(meta, [q0, q1])
    elif v == 2:
        vn = "cr_two_segment_with_phase_kick"
        desc = "Two-segment CR: pulses, then shift phase on target, then pulses again."
        ph = angle(rng, -0.8, 0.8)
        core = [
            "cal {",
            f"  waveform wc = gaussian_square({c32('0.5')}, {d}, {dt(rng, 16, 64)}, {s});",
            f"  waveform wt = gaussian({c32('0.2')}, {d}, {s});",
            f"  play({f0}, wc); play({f1}, wt);",
            f"  shift_phase({f1}, {ph});",
            f"  play({f0}, wc); play({f1}, wt);",
            "}",
        ]
        params = {"q0": q0, "q1": q1, "phase_target": ph}
        meas = measure_subset(meta, [q0, q1])
        pulse_points += ["shift_phase on one frame"]
    elif v == 3:
        vn = "cr_with_frequency_detune"
        desc = "Detune one frame frequency during the composite pulse."
        df = hz(rng, -10_000_000, 10_000_000)
        core = [
            "cal {",
            f"  float[64] f_orig = get_frequency({f0});",
            f"  set_frequency({f0}, f_orig + {df});",
            f"  waveform wc = gaussian_square({c32('0.5')}, {d}, {dt(rng, 16, 64)}, {s});",
            f"  waveform wt = gaussian({c32('0.2')}, {d}, {s});",
            f"  play({f0}, wc); play({f1}, wt);",
            f"  set_frequency({f0}, f_orig);",
            "}",
        ]
        params = {"q0": q0, "q1": q1, "detune_hz": df}
        meas = measure_subset(meta, [q0, q1])
        pulse_points += ["get_frequency/set_frequency"]
    else:
        vn = "cr_sequential_then_barrier"
        desc = "Sequential composite: play on control then on target, then barrier-align."
        core = [
            "cal {",
            f"  waveform wc = gaussian_square({c32('0.5')}, {d}, {dt(rng, 16, 64)}, {s});",
            f"  waveform wt = gaussian({c32('0.2')}, {d}, {s});",
            f"  play({f0}, wc);",
            f"  play({f1}, wt);",
            f"  barrier {f0}, {f1};",
            "}",
        ]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])

    return _mk(5, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_06(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[6]
    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    T = dt(rng, 96, 256) 

    tags = ["if", "equal_duration", "active_reset"]
    pulse_points = ["control flow with cal blocks", "equal-time branches by construction", "delay[dt] frame"]
    required = ["pulse.frames.drive"]

    if v == 1:
        vn = "if_measure_then_pulse_else_idle"
        desc = "Measure, then if=1 play a pulse; else idle, with equal dt duration in both branches."
        d = dt(rng, 64, 192)
        s = dt(rng, 16, 96)
        core = [
            f"bit b_reset;",
            f"b_reset = measure q[{q}];",
            f"if (b_reset) {{",
            "  cal {",
            f"    waveform w = gaussian({c32('0.5')}, {d}, {s});",
            f"    play({f}, w);",
            f"    delay[{T}] {f};",
            "  }",
            f"}} else {{",
            "  cal {",
            f"    delay[{T}] {f};",
            f"    waveform w = gaussian({c32('0.5')}, {d}, {s});",
            f"    play({f}, w);",
            "  }",
            f"}}",
        ]
        params = {"q": q, "frame": f, "T": T}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "if_measure_then_phase_kick_else_phase_kick"
        desc = "Both branches do a phase operation, equal time via same delay."
        ph1 = angle(rng, -0.8, 0.8)
        ph2 = angle(rng, -0.8, 0.8)
        core = [
            f"bit b_reset;",
            f"b_reset = measure q[{q}];",
            f"if (b_reset) {{",
            "  cal {",
            f"    shift_phase({f}, {ph1});",
            f"    delay[{T}] {f};",
            "  }",
            f"}} else {{",
            "  cal {",
            f"    shift_phase({f}, {ph2});",
            f"    delay[{T}] {f};",
            "  }",
            f"}}",
        ]
        params = {"q": q, "frame": f, "T": T, "ph1": ph1, "ph2": ph2}
        meas = measure_subset(meta, [q])
        pulse_points += ["shift_phase"]
    elif v == 3:
        vn = "if_measure_then_two_pulses_else_two_pulses"
        desc = "Both branches play two pulses (different order), equal time enforced."
        d = dt(rng, 64, 160)
        s = dt(rng, 16, 80)
        core = [
            f"bit b_reset;",
            f"b_reset = measure q[{q}];",
            f"if (b_reset) {{",
            "  cal {",
            f"    waveform w1 = gaussian({c32('0.5')}, {d}, {s});",
            f"    waveform w2 = gaussian({c32('0.2')}, {d}, {s});",
            f"    play({f}, w1); play({f}, w2);",
            f"    delay[{T}] {f};",
            "  }",
            f"}} else {{",
            "  cal {",
            f"    waveform w1 = gaussian({c32('0.5')}, {d}, {s});",
            f"    waveform w2 = gaussian({c32('0.2')}, {d}, {s});",
            f"    play({f}, w2); play({f}, w1);",
            f"    delay[{T}] {f};",
            "  }",
            f"}}",
        ]
        params = {"q": q, "frame": f, "T": T}
        meas = measure_subset(meta, [q])
        required += ["pulse.extern_waveforms (gaussian)"]
    else:
        vn = "if_measure_then_barrier_else_barrier"
        desc = "Use barrier as a sync point in both branches, equal-time via same delays."
        core = [
            f"bit b_reset;",
            f"b_reset = measure q[{q}];",
            f"if (b_reset) {{",
            "  cal {",
            f"    delay[{T}] {f};",
            f"    barrier {f};",
            "  }",
            f"}} else {{",
            "  cal {",
            f"    delay[{T}] {f};",
            f"    barrier {f};",
            "  }",
            f"}}",
        ]
        params = {"q": q, "frame": f, "T": T}
        meas = measure_subset(meta, [q])
        pulse_points += ["barrier (single frame)"]

    return _mk(6, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_07(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[7]
    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d = dt(rng, 128, 512)
    s = dt(rng, 24, 160)

    tags = ["mix", "sine", "modulation"]
    pulse_points = ["extern sine", "extern mix (declared in core)", "waveform composition"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian, sine)"]

    if v == 1:
        vn = "mix_gaussian_and_sine"
        desc = "Declare extern mix, then mix gaussian envelope with a sine tone and play."
        freq = f"{(1e6 * rng.randint(1, 30)):.1f}"
        ph = angle(rng, -1.0, 1.0)
        core = [
            "cal {",
            "  extern mix(waveform a, waveform b) -> waveform;",
            f"  waveform env = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform tone = sine({c32('1.0')}, {d}, {freq}, {ph});",
            "  waveform w = mix(env, tone);",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "d": d, "sigma": s, "tone_freq": freq, "tone_phase": ph}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "mix_then_shift_phase"
        desc = "Mix then shift frame phase before playing."
        freq = f"{(1e6 * rng.randint(1, 30)):.1f}"
        ph = angle(rng, -1.0, 1.0)
        shp = angle(rng, -0.8, 0.8)
        core = [
            "cal {",
            "  extern mix(waveform a, waveform b) -> waveform;",
            f"  waveform env = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform tone = sine({c32('1.0')}, {d}, {freq}, {ph});",
            "  waveform w = mix(env, tone);",
            f"  shift_phase({f}, {shp});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "tone_freq": freq, "tone_phase": ph, "shift_phase": shp}
        meas = measure_subset(meta, [q])
        pulse_points += ["shift_phase"]
    elif v == 3:
        vn = "two_segment_modulation"
        desc = "Play two modulated pulses with different tone phase."
        freq = f"{(1e6 * rng.randint(1, 30)):.1f}"
        ph1 = angle(rng, -1.0, 1.0)
        ph2 = angle(rng, -1.0, 1.0)
        core = [
            "cal {",
            "  extern mix(waveform a, waveform b) -> waveform;",
            f"  waveform env = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform t1 = sine({c32('1.0')}, {d}, {freq}, {ph1});",
            f"  waveform t2 = sine({c32('1.0')}, {d}, {freq}, {ph2});",
            "  waveform w1 = mix(env, t1);",
            "  waveform w2 = mix(env, t2);",
            f"  play({f}, w1);",
            f"  play({f}, w2);",
            "}",
        ]
        params = {"q": q, "frame": f, "freq": freq, "ph1": ph1, "ph2": ph2}
        meas = measure_subset(meta, [q])
    else:
        vn = "modulation_parallel_two_qubits"
        desc = "Play modulated pulses on two drive frames in parallel and barrier-align."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            freq = f"{(1e6 * rng.randint(1, 30)):.1f}"
            ph = angle(rng, -1.0, 1.0)
            core = [
                "cal {",
                "  extern mix(waveform a, waveform b) -> waveform;",
                f"  waveform env = gaussian({c32('0.5')}, {d}, {s});",
                f"  waveform tone = sine({c32('1.0')}, {d}, {freq}, {ph});",
                "  waveform w = mix(env, tone);",
                f"  play({f}, w);",
                f"  play({f2}, w);",
                f"  barrier {f}, {f2};",
                "}",
            ]
            params = {"q0": q, "q1": q2, "f0": f, "f1": f2, "freq": freq, "phase": ph}
            meas = measure_subset(meta, [q, q2])
        else:
            core = [
                "cal {",
                "  extern mix(waveform a, waveform b) -> waveform;",
                f"  waveform env = gaussian({c32('0.5')}, {d}, {s});",
                f"  waveform tone = sine({c32('1.0')}, {d}, 10000000.0, 0.0);",
                "  waveform w = mix(env, tone);",
                f"  play({f}, w);",
                "}",
            ]
            params = {"q": q, "frame": f}
            meas = measure_subset(meta, [q])

    return _mk(7, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_08(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[8]
    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)

    tags = ["waveform", "raw_samples", "play"]
    pulse_points = ["waveform literal = [complex samples...]", "play(frame,waveform)"]
    required = ["pulse.frames.drive"]

    if v == 1:
        vn = "arb_waveform_short"
        desc = "Define a short arbitrary waveform from complex samples and play."
        core = [
            "cal {",
            "  waveform w = [1+0im, 0+1im, 1/sqrt(2)+1/sqrt(2)im];",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "samples": 3}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "arb_waveform_with_delay"
        desc = "Arbitrary waveform literal with a preceding delay on the frame."
        idle = dt(rng, 8, 96)
        core = [
            "cal {",
            "  waveform w = [0+0im, 0.5+0im, 0+0im];",
            f"  delay[{idle}] {f};",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f, "idle": idle, "samples": 3}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn = "arb_waveform_two_segment"
        desc = "Play two different arbitrary waveforms back-to-back."
        core = [
            "cal {",
            "  waveform w1 = [1+0im, 0+1im, 0+0im];",
            "  waveform w2 = [0+0im, 1+0im, 0+1im];",
            f"  play({f}, w1);",
            f"  play({f}, w2);",
            "}",
        ]
        params = {"q": q, "frame": f}
        meas = measure_subset(meta, [q])
    else:
        vn = "arb_waveform_parallel_two_frames"
        desc = "Play the same arbitrary waveform on two frames in parallel, then barrier."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            core = [
                "cal {",
                "  waveform w = [1+0im, 0+1im, 1/sqrt(2)+1/sqrt(2)im];",
                f"  play({f}, w);",
                f"  play({f2}, w);",
                f"  barrier {f}, {f2};",
                "}",
            ]
            params = {"q0": q, "q1": q2, "f0": f, "f1": f2}
            meas = measure_subset(meta, [q, q2])
            pulse_points += ["barrier frames"]
        else:
            core = [
                "cal {",
                "  waveform w = [1+0im, 0+1im, 1/sqrt(2)+1/sqrt(2)im];",
                f"  play({f}, w);",
                "}",
            ]
            params = {"q": q, "frame": f}
            meas = measure_subset(meta, [q])

    return _mk(8, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_09(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[9]
    q0 = pick_qubit(meta, rng)
    f0 = drive_frame(meta, q0)

    tags = ["barrier", "sync", "frames"]
    pulse_points = ["barrier f1,f2,... aligns to max time", "delay[dt] frame"]
    required = ["pulse.frames.drive"]

    if v == 1:
        vn = "barrier_two_drive_frames"
        desc = "Delay on one frame, then barrier-align with another frame."
        q1 = q0
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q1 = pick_qubit(meta, rng)
            while q1 == q0:
                q1 = pick_qubit(meta, rng)
        f1 = drive_frame(meta, q1)
        d0 = dt(rng, 16, 120)
        core = [
            "cal {",
            f"  delay[{d0}] {f0};",
            f"  barrier {f0}, {f1};",
            "}",
        ]
        params = {"q0": q0, "q1": q1, "f0": f0, "f1": f1, "delay0": d0}
        meas = measure_subset(meta, [q0, q1])
    elif v == 2:
        vn = "barrier_three_frames_if_possible"
        desc = "Barrier-align three frames after different delays."
        uq = used_qubits(meta)
        frames = [drive_frame(meta, uq[i]) for i in range(min(3, len(uq)))]
        core = ["cal {"]
        for i, fr in enumerate(frames):
            core.append(f"  delay[{dt(rng, 8, 80)}] {fr};")
        core.append(f"  barrier {', '.join(frames)};")
        core.append("}")
        params = {"frames": frames}
        meas = measure_subset(meta, uq[:min(3, len(uq))])
    elif v == 3:
        vn = "barrier_between_two_plays"
        desc = "Play on two frames then barrier-align, then play again."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q1 = pick_qubit(meta, rng)
            while q1 == q0:
                q1 = pick_qubit(meta, rng)
            f1 = drive_frame(meta, q1)
            d = dt(rng, 64, 256)
            s = dt(rng, 16, 96)
            core = [
                "cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f0}, w); play({f1}, w);",
                f"  barrier {f0}, {f1};",
                f"  play({f0}, w); play({f1}, w);",
                "}",
            ]
            params = {"q0": q0, "q1": q1}
            meas = measure_subset(meta, [q0, q1])
            required += ["pulse.extern_waveforms (gaussian)"]
        else:
            core = ["cal {", f"  barrier {f0};", "}"]
            params = {"q": q0}
            meas = measure_subset(meta, [q0])
    else:
        vn = "barrier_meas_and_acq_frames"
        desc = "Barrier-align meas frame and acq frame (readout resource sync)."
        mf = meas_frame(meta, q0)
        af = acq_frame(meta, q0)
        core = [
            "cal {",
            f"  barrier {mf}, {af};",
            "}",
        ]
        params = {"q": q0, "meas_frame": mf, "acq_frame": af}
        meas = measure_subset(meta, [q0])
        required += ["pulse.frames.meas", "pulse.frames.acq"]

    return _mk(9, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_10(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[10]
    q = pick_qubit(meta, rng)
    af = acq_frame(meta, q)
    d = dt(rng, 64, 512)

    tags = ["capture_v1", "trace", "raw_capture"]
    pulse_points = ["capture_v1(frame,duration)->waveform", "waveform type in cal"]
    required = ["pulse.frames.acq", "pulse.extern_io (capture_v1)"]

    if v == 1:
        vn = "capture_trace_once"
        desc = "Capture a raw trace waveform from the acq frame."
        core = [
            "cal {",
            f"  waveform trace = capture_v1({af}, {d});",
            "}",
        ]
        params = {"q": q, "acq_frame": af, "d": d}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "capture_trace_then_delay"
        desc = "Capture a trace, then delay the acq frame."
        idle = dt(rng, 8, 96)
        core = [
            "cal {",
            f"  waveform trace = capture_v1({af}, {d});",
            f"  delay[{idle}] {af};",
            "}",
        ]
        params = {"q": q, "acq_frame": af, "d": d, "idle": idle}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn = "two_captures_back_to_back"
        desc = "Perform two raw captures back-to-back."
        core = [
            "cal {",
            f"  waveform t1 = capture_v1({af}, {d});",
            f"  waveform t2 = capture_v1({af}, {d});",
            "}",
        ]
        params = {"q": q, "acq_frame": af, "d": d}
        meas = measure_subset(meta, [q])
    else:
        vn = "capture_two_qubits_parallel"
        desc = "Capture raw traces on two acq frames in parallel."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            af2 = acq_frame(meta, q2)
            core = [
                "cal {",
                f"  waveform t1 = capture_v1({af}, {d});",
                f"  waveform t2 = capture_v1({af2}, {d});",
                "}",
            ]
            params = {"q0": q, "q1": q2, "acq0": af, "acq1": af2, "d": d}
            meas = measure_subset(meta, [q, q2])
        else:
            core = [
                "cal {",
                f"  waveform trace = capture_v1({af}, {d});",
                "}",
            ]
            params = {"q": q}
            meas = measure_subset(meta, [q])

    return _mk(10, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)


def theme_11(meta: Dict[str, Any], rng: random.Random, v: int) -> PulseTaskInstance:
    name = THEME_NAMES[11]
    tags = ["defcal", "physical_qubit", "generic_qubit"]
    pulse_points = ["defcal signature: q vs $i", "calibrations can be specialized"]
    required = ["pulse.frames.drive"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d = dt(rng, 64, 256)
    s = dt(rng, 16, 96)

    if v == 1:
        vn = "define_defcal_x_on_physical_then_cal_play"
        desc = "Define a defcal x $q skeleton, and also do an explicit cal play on that qubit frame."
        core = [
            f"defcal x ${q} {{",
            "  // specialized calibration for a physical qubit (skeleton)",
            "}",
            "cal {",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"physical": q, "frame": f}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn = "define_defcal_x_generic_and_physical"
        desc = "Provide both generic and physical defcal skeletons to highlight specialization."
        core = [
            "defcal x q {",
            "  // generic calibration (skeleton)",
            "}",
            f"defcal x ${q} {{",
            "  // physical specialization (skeleton)",
            "}",
            "cal {",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "frame": f}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn = "two_physical_qubits_two_skeletons"
        desc = "Define two physical-qubit defcal skeletons (if available), then do explicit cal plays."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            core = [
                f"defcal x ${q} {{ }}",
                f"defcal x ${q2} {{ }}",
                "cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w); play({f2}, w);",
                "}",
            ]
            params = {"q0": q, "q1": q2, "f0": f, "f1": f2}
            meas = measure_subset(meta, [q, q2])
        else:
            core = [
                f"defcal x ${q} {{ }}",
                "cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w);",
                "}",
            ]
            params = {"q": q}
            meas = measure_subset(meta, [q])
    else:
        vn = "generic_defcal_with_params_skeleton"
        desc = "Define a parameterized defcal (rx(theta) q) skeleton; execute a cal play anyway."
        th = angle(rng, -1.0, 1.0)
        core = [
            "defcal rx(angle[20] theta) q {",
            "  // parameterized calibration (skeleton)",
            "}",
            "cal {",
            f"  // theta chosen = {th}",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "theta": th}
        meas = measure_subset(meta, [q])

    return _mk(11, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_12(meta, rng, v):
    name = THEME_NAMES[12]
    tags = ["readout", "multiplex", "meas/acq"]
    pulse_points = ["multiple meas/acq frames", "parallel capture", "barrier for readout sync"]
    required = ["pulse.frames.meas", "pulse.frames.acq", "pulse.extern_io (capture)", "pulse.extern_waveforms (constant)"]

    q0 = pick_qubit(meta, rng)
    q1 = q0
    if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
        q1 = pick_qubit(meta, rng)
        while q1 == q0:
            q1 = pick_qubit(meta, rng)

    m0, a0 = meas_frame(meta, q0), acq_frame(meta, q0)
    m1, a1 = meas_frame(meta, q1), acq_frame(meta, q1)
    fd = dt(rng, 64, 256)

    if v == 1:
        vn, desc = "two_qubit_parallel_capture", "Multiplexed readout: capture two acq frames in the same cal."
        core = ["cal {",
                f"  waveform f = constant({c32('0.0')}, {fd});",
                f"  bit b0 = capture({a0}, f);",
                f"  bit b1 = capture({a1}, f);",
                "}"]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    elif v == 2:
        vn, desc = "barrier_meas_acq_then_capture", "Barrier-align meas+acq frames before capture."
        core = ["cal {",
                f"  barrier {m0}, {a0}, {m1}, {a1};",
                f"  waveform f = constant({c32('0.0')}, {fd});",
                f"  bit b0 = capture({a0}, f); bit b1 = capture({a1}, f);",
                "}"]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    elif v == 3:
        vn, desc = "staggered_capture_with_delay", "Stagger captures by delaying one acq frame."
        idle = dt(rng, 8, 96)
        core = ["cal {",
                f"  waveform f = constant({c32('0.0')}, {fd});",
                f"  bit b0 = capture({a0}, f);",
                f"  delay[{idle}] {a1};",
                f"  bit b1 = capture({a1}, f);",
                "}"]
        params = {"idle": idle, "q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    else:
        vn, desc = "multi_frame_readout_newframe_extra", "Create an extra meas frame on same port and barrier-align."
        # same port, different frame
        p = meas_port(meta, q0)
        core = ["cal {",
                f"  frame extra = newframe({p}, meas_freq_{q0}, 0.0);",
                f"  barrier {m0}, extra;",
                "}"]
        params = {"q": q0, "meas_port": p}
        meas = measure_subset(meta, [q0])

    return _mk(12, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_13(meta, rng, v):
    name = THEME_NAMES[13]
    tags = ["parallel", "simultaneous", "multi_frame"]
    pulse_points = ["simultaneous scheduling by same frame time", "play on different frames without delays"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian)"]

    q0, q1 = pick_two(meta, rng)
    f0, f1 = drive_frame(meta, q0), drive_frame(meta, q1)
    d, s = dt(rng, 64, 256), dt(rng, 16, 96)

    if v == 1:
        vn, desc = "two_frames_simultaneous_play", "Play on two drive frames back-to-back (same start time => parallel)."
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f0}, w); play({f1}, w);",
                "}"]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    elif v == 2:
        vn, desc = "parallel_then_barrier_then_parallel", "Parallel play, barrier align, then parallel play again."
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f0}, w); play({f1}, w);",
                f"  barrier {f0}, {f1};",
                f"  play({f0}, w); play({f1}, w);",
                "}"]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    elif v == 3:
        vn, desc = "parallel_with_pre_delays", "Make both frames same time via matched delays, then parallel play."
        idle = dt(rng, 8, 96)
        core = ["cal {",
                f"  delay[{idle}] {f0}; delay[{idle}] {f1};",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f0}, w); play({f1}, w);",
                "}"]
        params = {"idle": idle}
        meas = measure_subset(meta, [q0, q1])
    else:
        vn, desc = "three_frames_if_possible", "Play on up to three frames in parallel."
        uq = used_qubits(meta)
        frames = [drive_frame(meta, uq[i]) for i in range(min(3, len(uq)))]
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  {' '.join([f'play({fr}, w);' for fr in frames])}",
                "}"]
        params = {"frames": frames}
        meas = measure_subset(meta, uq[:min(3, len(uq))])

    return _mk(13, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_14(meta, rng, v):
    name = THEME_NAMES[14]
    tags = ["scope", "cal", "reuse"]
    pulse_points = ["use frames declared in background cal", "declare additional extern in core cal"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d, s = dt(rng, 64, 256), dt(rng, 16, 96)

    if v == 1:
        vn, desc = "reuse_background_frames", "Reuse pre-created drive frame from background in a new cal block."
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w);",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "declare_extra_extern_in_core", "Declare an extra extern in core cal and call it."
        core = ["cal {",
                "  extern sech(complex[float[32]] amp, duration d, duration sigma) -> waveform;",
                f"  waveform w = sech({c32('0.5')}, {d}, {s});",
                f"  play({f}, w);",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
        required += ["(core declares extern sech)"]
    elif v == 3:
        vn, desc = "create_extra_frame_reuse_port", "Create an extra frame using background port + constants."
        p = drive_port(meta, q)
        core = ["cal {",
                f"  frame f2 = newframe({p}, drive_freq_{q}, 0.0);",
                f"  barrier {f}, f2;",
                "}"]
        params = {"q": q, "drive_port": p}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "array_of_frames_demo", "Use an array[frame] to store frames and index them."
        # only safe for small n
        nq = n_qubits(meta)
        core = ["cal {",
                f"  array[frame, {nq}] fs;",
        ]
        for i in range(nq):
            core.append(f"  fs[{i}] = {drive_frame(meta, i)};")
        core += [
            f"  waveform w = gaussian({c32('0.2')}, {d}, {s});",
            f"  play(fs[{q}], w);",
            "}"
        ]
        params = {"q": q, "nq": nq}
        meas = measure_subset(meta, [q])

    return _mk(14, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_15(meta, rng, v):
    name = THEME_NAMES[15]
    tags = ["phase_tracking", "delay", "time_advance"]
    pulse_points = ["delay advances frame time", "phase ops interleaved with delay/play"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian)"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d, s = dt(rng, 64, 256), dt(rng, 16, 96)
    idle = dt(rng, 8, 128)
    ph = angle(rng, -1.0, 1.0)

    if v == 1:
        vn, desc = "delay_then_get_phase", "Advance time by delay, then read phase."
        core = ["cal {",
                f"  delay[{idle}] {f};",
                f"  angle p = get_phase({f});",
                "}"]
        params = {"q": q, "idle": idle}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "delay_play_shift_play", "delay then play, shift_phase, play again."
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  delay[{idle}] {f};",
                f"  play({f}, w);",
                f"  shift_phase({f}, {ph});",
                f"  play({f}, w);",
                "}"]
        params = {"q": q, "idle": idle, "phase": ph}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "set_phase_then_delay", "Set absolute phase then delay."
        core = ["cal {",
                f"  set_phase({f}, {ph});",
                f"  delay[{idle}] {f};",
                "}"]
        params = {"q": q, "phase": ph, "idle": idle}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "phase_roundtrip", "Read phase, shift it, then restore."
        core = ["cal {",
                f"  angle p = get_phase({f});",
                f"  shift_phase({f}, {ph});",
                f"  set_phase({f}, p);",
                "}"]
        params = {"q": q, "delta": ph}
        meas = measure_subset(meta, [q])

    return _mk(15, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_16(meta, rng, v):
    name = THEME_NAMES[16]
    tags = ["dd", "sequence", "delay", "play"]
    pulse_points = ["delay/play sequencing", "barrier for segment alignment"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian)"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d, s = dt(rng, 64, 192), dt(rng, 16, 80)
    gap = dt(rng, 16, 128)

    if v == 1:
        vn, desc = "pi_pulse_delay_pi_pulse", "DD-like: play, delay, play."
        core = ["cal {",
                f"  waveform p = gaussian({c32('0.8')}, {d}, {s});",
                f"  play({f}, p);",
                f"  delay[{gap}] {f};",
                f"  play({f}, p);",
                "}"]
        params = {"q": q, "gap": gap}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "xy4_like", "XY4-like: X,Y,X,Y as phase-shifted plays (approx)."
        core = ["cal {",
                f"  waveform p = gaussian({c32('0.8')}, {d}, {s});",
                f"  play({f}, p); delay[{gap}] {f};",
                f"  shift_phase({f}, 1.570796); play({f}, p); delay[{gap}] {f};",
                f"  shift_phase({f}, -1.570796); play({f}, p); delay[{gap}] {f};",
                f"  shift_phase({f}, 1.570796); play({f}, p);",
                "}"]
        params = {"q": q, "gap": gap}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "dd_with_barrier", "Insert barrier as a segment boundary."
        core = ["cal {",
                f"  waveform p = gaussian({c32('0.8')}, {d}, {s});",
                f"  play({f}, p);",
                f"  barrier {f};",
                f"  delay[{gap}] {f};",
                f"  barrier {f};",
                f"  play({f}, p);",
                "}"]
        params = {"q": q, "gap": gap}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "dd_two_qubits_parallel", "Run the same DD-like sequence on two frames in parallel."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            core = ["cal {",
                    f"  waveform p = gaussian({c32('0.8')}, {d}, {s});",
                    f"  play({f}, p); play({f2}, p);",
                    f"  delay[{gap}] {f}; delay[{gap}] {f2};",
                    f"  play({f}, p); play({f2}, p);",
                    f"  barrier {f}, {f2};",
                    "}"]
            params = {"q0": q, "q1": q2, "gap": gap}
            meas = measure_subset(meta, [q, q2])
        else:
            core = ["cal {", f"  delay[{gap}] {f};", "}"]
            params = {"q": q, "gap": gap}
            meas = measure_subset(meta, [q])

    return _mk(16, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_17(meta, rng, v):
    name = THEME_NAMES[17]
    tags = ["dsp", "waveform_ops"]
    pulse_points = ["extern add/scale/phase_shift waveform ops (declared in core)", "composition pipeline"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian, constant)"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d, s = dt(rng, 64, 256), dt(rng, 16, 96)
    k = f"{(0.2 + 1.5*rng.random()):.3f}"
    ph = angle(rng, -1.0, 1.0)

    core_prelude = [
        "cal {",
        "  extern add(waveform a, waveform b) -> waveform;",
        "  extern scale(waveform a, float[32] k) -> waveform;",
        "  extern phase_shift(waveform a, angle theta) -> waveform;",
    ]

    if v == 1:
        vn, desc = "add_two_waveforms", "Add a gaussian and a constant waveform, then play."
        core = core_prelude + [
            f"  waveform g = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform c = constant({c32('0.1')}, {d});",
            "  waveform w = add(g, c);",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "scale_then_play", "Scale a waveform then play."
        core = core_prelude + [
            f"  waveform g = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform w = scale(g, {k});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "k": k}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "phase_shift_waveform_then_play", "Phase-shift the waveform (not the frame) then play."
        core = core_prelude + [
            f"  waveform g = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform w = phase_shift(g, {ph});",
            f"  play({f}, w);",
            "}",
        ]
        params = {"q": q, "ph": ph}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "add_scale_phase_pipeline", "Compose add->scale->phase_shift pipeline then play."
        core = core_prelude + [
            f"  waveform g = gaussian({c32('0.5')}, {d}, {s});",
            f"  waveform c = constant({c32('0.1')}, {d});",
            "  waveform w0 = add(g, c);",
            f"  waveform w1 = scale(w0, {k});",
            f"  waveform w2 = phase_shift(w1, {ph});",
            f"  play({f}, w2);",
            "}",
        ]
        params = {"q": q, "k": k, "ph": ph}
        meas = measure_subset(meta, [q])

    return _mk(17, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_18(meta, rng, v):
    name = THEME_NAMES[18]
    tags = ["frequency", "set_frequency", "shift_frequency"]
    pulse_points = ["get_frequency", "set_frequency", "shift_frequency (if supported)"]
    required = ["pulse.frames.drive"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    df = hz(rng, -15_000_000, 15_000_000)

    if v == 1:
        vn, desc = "set_frequency_absolute", "Store current frequency, set to a new value, then restore."
        core = ["cal {",
                f"  float[64] f0 = get_frequency({f});",
                f"  set_frequency({f}, f0 + {df});",
                f"  set_frequency({f}, f0);",
                "}"]
        params = {"q": q, "df": df}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "shift_frequency_then_restore", "Use shift_frequency if available, otherwise emulate via get/set."
        core = ["cal {",
                "  // If shift_frequency is supported by your toolchain, prefer it:",
                f"  // shift_frequency({f}, {df});",
                f"  float[64] f0 = get_frequency({f});",
                f"  set_frequency({f}, f0 + {df});",
                f"  set_frequency({f}, f0);",
                "}"]
        params = {"q": q, "df": df}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "detune_during_play", "Detune frequency during a play, then restore."
        d, s = dt(rng, 64, 256), dt(rng, 16, 96)
        core = ["cal {",
                f"  float[64] f0 = get_frequency({f});",
                f"  set_frequency({f}, f0 + {df});",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w);",
                f"  set_frequency({f}, f0);",
                "}"]
        params = {"q": q, "df": df}
        meas = measure_subset(meta, [q])
        required += ["pulse.extern_waveforms (gaussian)"]
    else:
        vn, desc = "two_detunes_two_frames", "Detune two frames differently (if 2 qubits), then restore."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            df2 = hz(rng, -15_000_000, 15_000_000)
            core = ["cal {",
                    f"  float[64] f0 = get_frequency({f}); float[64] g0 = get_frequency({f2});",
                    f"  set_frequency({f}, f0 + {df}); set_frequency({f2}, g0 + {df2});",
                    f"  set_frequency({f}, f0); set_frequency({f2}, g0);",
                    "}"]
            params = {"q0": q, "q1": q2, "df0": df, "df1": df2}
            meas = measure_subset(meta, [q, q2])
        else:
            core = ["cal {", f"  float[64] f0 = get_frequency({f}); set_frequency({f}, f0 + {df}); set_frequency({f}, f0);", "}"]
            params = {"q": q, "df": df}
            meas = measure_subset(meta, [q])

    return _mk(18, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_19(meta, rng, v):
    name = THEME_NAMES[19]
    tags = ["get_phase", "get_frequency", "set_phase", "set_frequency"]
    pulse_points = ["read frame state", "write frame state", "swap state between frames"]
    required = ["pulse.frames.drive"]

    q0, q1 = pick_two(meta, rng)
    f0, f1 = drive_frame(meta, q0), drive_frame(meta, q1)

    if v == 1:
        vn, desc = "swap_phase", "Swap phases of two frames."
        core = ["cal {",
                f"  angle p0 = get_phase({f0}); angle p1 = get_phase({f1});",
                f"  set_phase({f0}, p1); set_phase({f1}, p0);",
                "}"]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    elif v == 2:
        vn, desc = "swap_frequency", "Swap frequencies of two frames."
        core = ["cal {",
                f"  float[64] a = get_frequency({f0}); float[64] b = get_frequency({f1});",
                f"  set_frequency({f0}, b); set_frequency({f1}, a);",
                "}"]
        params = {"q0": q0, "q1": q1}
        meas = measure_subset(meta, [q0, q1])
    elif v == 3:
        vn, desc = "copy_phase_from_one_to_other", "Copy phase from one frame to another (one-way)."
        core = ["cal {",
                f"  angle p = get_phase({f0});",
                f"  set_phase({f1}, p);",
                "}"]
        params = {"src": q0, "dst": q1}
        meas = measure_subset(meta, [q0, q1])
    else:
        vn, desc = "snapshot_then_restore", "Snapshot phase+freq of a frame, modify, then restore."
        df = hz(rng, -10_000_000, 10_000_000)
        ph = angle(rng, -1.0, 1.0)
        core = ["cal {",
                f"  angle p0 = get_phase({f0});",
                f"  float[64] f0v = get_frequency({f0});",
                f"  shift_phase({f0}, {ph});",
                f"  set_frequency({f0}, f0v + {df});",
                f"  set_phase({f0}, p0);",
                f"  set_frequency({f0}, f0v);",
                "}"]
        params = {"q": q0, "df": df, "ph": ph}
        meas = measure_subset(meta, [q0])

    return _mk(19, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_20(meta, rng, v):
    name = THEME_NAMES[20]
    tags = ["defcal", "matching", "priority"]
    pulse_points = ["multiple defcal candidates", "specialization by physical qubit / literal param"]
    required = ["pulse.frames.drive"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d, s = dt(rng, 64, 192), dt(rng, 16, 80)

    if v == 1:
        vn, desc = "generic_vs_physical_x", "Provide generic and physical x defcal skeletons (priority demo)."
        core = [
            "defcal x q { /* generic */ }",
            f"defcal x ${q} {{ /* physical */ }}",
            "cal {",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s}); play({f}, w);",
            "}",
            f"x q[{q}];",
        ]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "rx_literal_vs_rx_param", "Provide rx(pi/2) specialized skeleton and rx(theta) generic skeleton."
        core = [
            "defcal rx(angle[20] theta) q { /* generic */ }",
            f"defcal rx(1.570796) ${q} {{ /* literal specialized */ }}",
            "cal {",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s}); play({f}, w);",
            "}",
            f"rx(1.570796) q[{q}];",
        ]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "measure_specialization_skeletons", "Provide measure skeletons for generic and physical qubit."
        core = [
            "defcal measure q -> bit { /* generic */ return 0; }",
            f"defcal measure ${q} -> bit {{ /* physical */ return 0; }}",
            f"bit m_demo;",
            f"m_demo = measure q[{q}];",
        ]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "three_level_priority_skeleton", "Show param-specialized + physical-specialized + generic skeletons."
        core = [
            "defcal x q { /* generic */ }",
            f"defcal x ${q} {{ /* physical */ }}",
            f"defcal x ${q} {{ /* another physical (illustrative only) */ }}",
            "cal {",
            f"  waveform w = gaussian({c32('0.5')}, {d}, {s}); play({f}, w);",
            "}",
        ]
        params = {"q": q}
        meas = measure_subset(meta, [q])

    return _mk(20, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_21(meta, rng, v):
    name = THEME_NAMES[21]
    tags = ["newframe", "time_origin", "cal_vs_defcal"]
    pulse_points = ["newframe in cal starts at absolute 0", "newframe in defcal starts at scheduling time"]
    required = ["pulse.ports.drive", "pulse.frames.drive"]

    q = pick_qubit(meta, rng)
    p = drive_port(meta, q)

    if v == 1:
        vn, desc = "newframe_in_cal", "Create a new frame in a cal block (absolute time origin)."
        core = ["cal {",
                f"  frame ftmp = newframe({p}, drive_freq_{q}, 0.0);",
                f"  delay[{dt(rng, 8, 64)}] ftmp;",
                "}"]
        params = {"q": q, "port": p}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "newframe_in_defcal_skeleton", "Show a defcal with a newframe call (time origin differs)."
        core = [f"defcal x ${q} {{",
                f"  frame ftmp = newframe({p}, drive_freq_{q}, 0.0);",
                f"  delay[{dt(rng, 8, 64)}] ftmp;",
                f"}}"]
        params = {"q": q, "port": p}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "cal_then_defcal_both_newframe", "Use both cal and defcal newframe forms together."
        core = ["cal {",
                f"  frame f0 = newframe({p}, drive_freq_{q}, 0.0);",
                f"  delay[{dt(rng, 8, 64)}] f0;",
                "}",
                f"defcal x ${q} {{ frame f1 = newframe({p}, drive_freq_{q}, 0.0); delay[{dt(rng, 8, 64)}] f1; }}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "compare_newframe_and_existing_frame", "Barrier-align a new frame with the existing drive frame."
        f_exist = drive_frame(meta, q)
        core = ["cal {",
                f"  frame ftmp = newframe({p}, drive_freq_{q}, 0.0);",
                f"  barrier {f_exist}, ftmp;",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])

    return _mk(21, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_22(meta, rng, v):
    name = THEME_NAMES[22]
    tags = ["duration", "compile_time", "determinable"]
    pulse_points = ["durations must be statically determinable for certain scheduling constructs"]
    required = ["pulse.frames.drive"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d1, d2 = dt(rng, 32, 96), dt(rng, 32, 96)

    if v == 1:
        vn, desc = "fixed_duration_sequence", "Use only fixed dt durations (compile-time determinable)."
        core = ["cal {",
                f"  delay[{d1}] {f};",
                f"  delay[{d2}] {f};",
                "}"]
        params = {"q": q, "d1": d1, "d2": d2}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "duration_variable_assigned_constant", "Assign a duration variable from a constant, then use it."
        core = ["cal {",
                f"  duration t = {d1};",
                f"  delay[t] {f};",
                "}"]
        params = {"q": q, "t": d1}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "if_with_equal_durations_inside_cal", "Conditional blocks with equal, fixed durations."
        core = ["bit b_ct;",
                f"b_ct = measure q[{q}];",
                f"if (b_ct) {{ cal {{ delay[{d1}] {f}; }} }} else {{ cal {{ delay[{d1}] {f}; }} }}"]
        params = {"q": q, "d": d1}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "for_loop_fixed_trip_count", "Loop with compile-time fixed trip count controlling delays."
        k = rng.randint(2, 5)
        core = [f"for int i in [0:{k}] {{",
                f"  cal {{ delay[{d1}] {f}; }}",
                f"}}"]
        params = {"q": q, "k": k, "d": d1}
        meas = measure_subset(meta, [q])

    return _mk(22, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_23(meta, rng, v):
    name = THEME_NAMES[23]
    tags = ["frame_collision", "avoidance", "barrier", "sequential"]
    pulse_points = ["avoid overlapping operations on same frame", "use sequentialization / barrier"]
    required = ["pulse.frames.drive", "pulse.extern_waveforms (gaussian)"]

    q = pick_qubit(meta, rng)
    f = drive_frame(meta, q)
    d, s = dt(rng, 64, 192), dt(rng, 16, 80)

    if v == 1:
        vn, desc = "sequential_two_plays_same_frame", "Two plays on same frame are sequenced (no overlap)."
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w);",
                f"  play({f}, w);",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "explicit_barrier_between_plays", "Use barrier between plays on same frame."
        core = ["cal {",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w);",
                f"  barrier {f};",
                f"  play({f}, w);",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "avoid_collision_by_using_two_frames", "Use two distinct frames on same port to run in parallel."
        p = drive_port(meta, q)
        core = ["cal {",
                f"  frame f2 = newframe({p}, drive_freq_{q}, 0.0);",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f}, w); play(f2, w);",
                f"  barrier {f}, f2;",
                "}"]
        params = {"q": q, "port": p}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "collision_free_parallel_two_qubits", "Parallel plays on different qubits' frames is collision-free."
        if n_qubits(meta) >= 2 and len(used_qubits(meta)) >= 2:
            q2 = pick_qubit(meta, rng)
            while q2 == q:
                q2 = pick_qubit(meta, rng)
            f2 = drive_frame(meta, q2)
            core = ["cal {",
                    f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                    f"  play({f}, w); play({f2}, w);",
                    "}"]
            params = {"q0": q, "q1": q2}
            meas = measure_subset(meta, [q, q2])
        else:
            core = ["cal {", f"  barrier {f};", "}"]
            params = {"q": q}
            meas = measure_subset(meta, [q])

    return _mk(23, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_24(meta, rng, v):
    name = THEME_NAMES[24]
    tags = ["same_port", "multi_frame", "patterns"]
    pulse_points = ["multiple frames can share a port", "barrier aligns frames even on same port"]
    required = ["pulse.ports.drive", "pulse.frames.drive"]

    q = pick_qubit(meta, rng)
    p = drive_port(meta, q)
    f0 = drive_frame(meta, q)

    if v == 1:
        vn, desc = "two_frames_same_port_barrier", "Create a second frame on the same port and barrier-align."
        core = ["cal {",
                f"  frame f1 = newframe({p}, drive_freq_{q}, 0.0);",
                f"  barrier {f0}, f1;",
                "}"]
        params = {"q": q, "port": p}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "two_frames_same_port_separate_plays", "Play on f0 then on f1 (same port)."
        d, s = dt(rng, 64, 192), dt(rng, 16, 80)
        core = ["cal {",
                f"  frame f1 = newframe({p}, drive_freq_{q}, 0.0);",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f0}, w); play(f1, w);",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "two_frames_same_port_parallel", "Attempt parallel scheduling on two frames sharing a port (allowed syntax)."
        d, s = dt(rng, 64, 192), dt(rng, 16, 80)
        core = ["cal {",
                f"  frame f1 = newframe({p}, drive_freq_{q}, 0.0);",
                f"  waveform w = gaussian({c32('0.5')}, {d}, {s});",
                f"  play({f0}, w); play(f1, w);",
                f"  barrier {f0}, f1;",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "three_frames_same_port_array", "Create multiple frames on same port and store them in an array."
        k = rng.randint(2, 4)
        core = ["cal {",
                f"  array[frame, {k}] fs;",
        ]
        for i in range(k):
            core.append(f"  fs[{i}] = newframe({p}, drive_freq_{q}, 0.0);")
        core += [
            f"  barrier {', '.join([f'fs[{i}]' for i in range(k)])};",
            "}"
        ]
        params = {"q": q, "k": k}
        meas = measure_subset(meta, [q])

    return _mk(24, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

def theme_25(meta, rng, v):
    name = THEME_NAMES[25]
    tags = ["measurement", "bit", "trace", "return_types"]
    pulse_points = ["capture -> bit", "capture_v1 -> waveform", "measure statement outside cal"]
    required = ["pulse.frames.acq", "pulse.frames.meas", "pulse.extern_io (capture,capture_v1)", "pulse.extern_waveforms (constant)"]

    q = pick_qubit(meta, rng)
    a = acq_frame(meta, q)
    m = meas_frame(meta, q)
    fd = dt(rng, 64, 256)

    if v == 1:
        vn, desc = "bit_measure_and_trace_capture", "Produce a bit via capture and also a raw trace via capture_v1."
        core = ["cal {",
                f"  waveform f = constant({c32('0.0')}, {fd});",
                f"  bit b = capture({a}, f);",
                f"  waveform t = capture_v1({a}, {fd});",
                f"  barrier {m}, {a};",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 2:
        vn, desc = "defcal_measure_bit_plus_trace", "Define defcal measure -> bit using capture; also do capture_v1."
        core = [
            f"defcal measure ${q} -> bit {{ waveform f = constant({c32('0.0')}, {fd}); return capture({a}, f); }}",
            "cal {",
            f"  waveform t = capture_v1({a}, {fd});",
            "}",
        ]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    elif v == 3:
        vn, desc = "two_bits_then_standard_measure", "Capture bit(s) and also use standard QASM measure."
        core = ["cal {",
                f"  waveform f = constant({c32('0.0')}, {fd});",
                f"  bit b = capture({a}, f);",
                "}"]
        params = {"q": q}
        meas = measure_subset(meta, [q])
    else:
        vn, desc = "trace_only_then_measure_all", "Raw trace capture only, then measure all qubits."
        core = ["cal {",
                f"  waveform t = capture_v1({a}, {fd});",
                "}"]
        params = {"q": q}
        meas = measure_all(meta)

    return _mk(25, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, pulse_points=pulse_points, required_meta=required,
               params=params, core=core, meas=meas)

# -------------------- Registry --------------------

THEMES: Dict[int, ThemeFn] = {
    1: theme_01,
    2: theme_02,
    3: theme_03,
    4: theme_04,
    5: theme_05,
    6: theme_06,
    7: theme_07,
    8: theme_08,
    9: theme_09,
    10: theme_10,
    11: theme_11,
    12: theme_12,
    13: theme_13,
    14: theme_14,
    15: theme_15,
    16: theme_16,
    17: theme_17,
    18: theme_18,
    19: theme_19,
    20: theme_20,
    21: theme_21,
    22: theme_22,
    23: theme_23,
    24: theme_24,
    25: theme_25,
}

def generate_pulse_core_task(meta: Dict[str, Any], *, theme_id: int, variant_id: int, seed: Optional[int] = None) -> PulseTaskInstance:
    if theme_id not in THEMES:
        raise KeyError(f"Unknown theme_id={theme_id}")
    if variant_id not in (1, 2, 3, 4):
        raise ValueError("variant_id must be 1..4")
    rng = random.Random(seed)
    return THEMES[theme_id](meta, rng, variant_id)

def generate_pulse_core_task_from_meta_path(meta_path: str, *, theme_id: int, variant_id: int, seed: Optional[int] = None) -> PulseTaskInstance:
    meta = load_meta(meta_path)
    return generate_pulse_core_task(meta, theme_id=theme_id, variant_id=variant_id, seed=seed)


import os
import glob
import json
import random
from typing import List, Dict, Any

def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def _replace_between_markers(text: str, start_marker: str, end_marker: str, new_lines: List[str]) -> str:
    if start_marker not in text or end_marker not in text:
        raise ValueError(f"Markers not found: {start_marker} / {end_marker}")
    before, rest = text.split(start_marker, 1)
    _, after = rest.split(end_marker, 1)
    new_block = start_marker + "\n" + "\n".join(new_lines).rstrip() + "\n" + end_marker
    return before + new_block + after

def assemble_full_task(background_qasm: str, inst: "PulseTaskInstance") -> str:
    out = _replace_between_markers(background_qasm, CORE_START, CORE_END, inst.core_lines)

    if MEAS_START in out and MEAS_END in out:
        out = _replace_between_markers(out, MEAS_START, MEAS_END, inst.meas_lines)
    else:
        meas_block = "\n".join([MEAS_START] + inst.meas_lines + [MEAS_END]) + "\n"
        out = out.rstrip() + "\n\n" + meas_block

    return out


def main(task_num: int = 200, base_seed: int = 20260108) -> None:

    background_dir = "pulse_background"
    out_dir = "pulse_train"
    os.makedirs(out_dir, exist_ok=True)

    variants = [2, 3, 4]

    bg_paths = sorted(glob.glob(os.path.join(background_dir, "bg_*.qasm")))
    if not bg_paths:
        raise RuntimeError(f"No pulse backgrounds found in {background_dir}")

    rng = random.Random(base_seed)

    for t in range(task_num):
        theme_id = (t % 25) + 1
        variant_id = variants[t % len(variants)]

        bg_path = rng.choice(bg_paths)
        bg_file = os.path.basename(bg_path)
        meta_path = bg_path.replace(".qasm", ".meta.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"Missing meta for {bg_file}: {meta_path}")

        bg_text = _read_text(bg_path)

        inst_seed = rng.randrange(1_000_000_000)

        inst = generate_pulse_core_task_from_meta_path(
            meta_path,
            theme_id=theme_id,
            variant_id=variant_id,
            seed=inst_seed,
        )

        full_qasm = assemble_full_task(bg_text, inst)

        task_fname = f"pulse_task_{t:05d}_th{theme_id:02d}_v{variant_id}.qasm"
        task_path = os.path.join(out_dir, task_fname)
        _write_text(task_path, full_qasm)

    print(f"Done. Wrote {task_num} pulse train tasks into: {out_dir}")


if __name__ == "__main__":
    task_num = 1000 
    main(task_num=task_num)
