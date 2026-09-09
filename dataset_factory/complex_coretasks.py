# complex_coretasks.py
# -*- coding: utf-8 -*-


from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Callable, Optional


# -------------------- Markers --------------------

CORE_START = "// === CORE_TASK_START ==="
CORE_END   = "// === CORE_TASK_END ==="
MEAS_START = "// === MEASUREMENT_START ==="
MEAS_END   = "// === MEASUREMENT_END ==="


# -------------------- Meta helpers --------------------

def n_qubits(meta: Dict[str, Any]) -> int:
    return int(meta.get("n_qubits", 1))


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
    return uq[0], uq[0]


def _pulse_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    p = meta.get("pulse", {})
    if not isinstance(p, dict):
        return {}
    return p


def drive_frame(meta: Dict[str, Any], q: int) -> str:
    return _pulse_meta(meta)["frames"]["drive"][str(q)]


def meas_frame(meta: Dict[str, Any], q: int) -> str:
    return _pulse_meta(meta)["frames"]["meas"][str(q)]


def acq_frame(meta: Dict[str, Any], q: int) -> str:
    return _pulse_meta(meta)["frames"]["acq"][str(q)]


def choose_delay_unit(meta: Dict[str, Any], rng: random.Random, *, prefer_dt: bool = False) -> str:
    # background_complex.py puts units at meta["timing"]["background"]["delay_units"]
    units = []
    timing = meta.get("timing", {})
    if isinstance(timing, dict):
        bg = timing.get("background", {})
        if isinstance(bg, dict):
            units = bg.get("delay_units", [])
    units = [u for u in units if isinstance(u, str) and u]
    if not units:
        units = ["ns"]
    if prefer_dt and "dt" in units:
        return "dt"
    # prefer physical time if available
    phys = [u for u in units if u in ("ns", "us", "ms", "s")]
    if phys:
        return rng.choice(phys)
    return rng.choice(units)


def rand_time(rng: random.Random, lo: int, hi: int, unit: str) -> str:
    return f"{rng.randint(lo, hi)}{unit}"


def rand_dt(rng: random.Random, lo: int, hi: int) -> str:
    return f"{rng.randint(lo, hi)}dt"


def rand_angle(rng: random.Random, lo: float = -1.2, hi: float = 1.2) -> str:
    v = lo + (hi - lo) * rng.random()
    return f"{v:.6f}"


def rand_hz(rng: random.Random, lo: int = -20_000_000, hi: int = 20_000_000) -> str:
    return f"{rng.randint(lo, hi)}.0"


def c32(real: str) -> str:
    # OpenPulse complex literal style (a + bim)
    return f"{real}+0.0im"


# -------------------- Measurement helpers --------------------

def measure_all_block(meta: Dict[str, Any], creg: str = "c") -> List[str]:
    nq = n_qubits(meta)
    lines = [f"bit[{nq}] {creg};"]
    for i in range(nq):
        lines.append(f"{creg}[{i}] = measure q[{i}];")
    return lines


# -------------------- Task instance --------------------

@dataclass
class ComplexTaskInstance:
    theme_id: int
    variant_id: int

    theme_name: str
    variant_name: str
    description: str
    tags: List[str]

    timing_points: List[str]
    classical_points: List[str]
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
            "timing_points": list(self.timing_points),
            "classical_points": list(self.classical_points),
            "pulse_points": list(self.pulse_points),
            "required_meta": list(self.required_meta),
            "params": dict(self.params),
        }


def _mk(theme_id: int, v: int, *,
        theme_name: str,
        variant_name: str,
        description: str,
        tags: List[str],
        timing_points: List[str],
        classical_points: List[str],
        pulse_points: List[str],
        required_meta: List[str],
        params: Dict[str, Any],
        core: List[str],
        meas: List[str]) -> ComplexTaskInstance:
    comment = f"// {theme_name} | {variant_name}: {description}"
    return ComplexTaskInstance(
        theme_id=theme_id,
        variant_id=v,
        theme_name=theme_name,
        variant_name=variant_name,
        description=description,
        tags=tags,
        timing_points=timing_points,
        classical_points=classical_points,
        pulse_points=pulse_points,
        required_meta=required_meta,
        params=params,
        core_lines=[comment] + core,
        meas_lines=meas,
    )


# -------------------- Theme names (first 5) --------------------

THEME_NAMES: Dict[int, str] = {
    1: "active_reset_loop",
    2: "ramsey_feedback_phase_comp",
    3: "hahn_echo_characterization",
    4: "t1_relaxation_gated_readout",
    5: "rabi_amplitude_scan",
    6: "qubit_spectroscopy_scan",
    7: "echoed_cr_gate_verification",
    8: "dynamic_cnot_spectator_comp",
    9: "multiplexed_readout",
    10: "raw_waveform_capture_and_filter",
    11: "measurement_crosstalk_calibration",
    12: "realtime_feedback_correction",
    13: "pipeline_measure_reset_prep",
    14: "randomized_benchmarking_controller",
    15: "repeat_until_success_prep",
    16: "leakage_detection_and_recovery",
    17: "virtual_z_phase_tracking_test",
    18: "calibration_hot_swap_local_override",
    19: "durationof_alignment_scheduling",
    20: "boxed_dynamic_decoupling",
    21: "switch_routed_feedforward",
    22: "in_shot_micro_averaging",
    23: "late_as_possible_conditional",
    24: "timeout_active_reset_with_update",
    25: "syndrome_feedforward_idle_scheduling",

}

ThemeFn = Callable[[Dict[str, Any], random.Random, int], ComplexTaskInstance]


# ==================== Theme 01: Active Reset Loop ====================

def theme_01(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[1]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    # pulse params
    d_pi = rand_dt(rng, 80, 240)
    s_pi = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 480)

    tags = ["active_reset", "feedback", "pulse", "timing", "classical"]
    timing_points = ["box", "stretch", "delay", "const_duration"]
    classical_points = ["if_else", "while_or_for", "measure", "counter", "extern_optional"]
    pulse_points = ["play", "capture", "barrier_frames", "shift_phase_optional"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq", "timing.constants.BOX_WIN"]

    # variant logic
    if v == 1:
        vn = "single_shot_reset_equalized_box"
        desc = "Single-shot active reset: capture -> if 1 then apply X pulse; equalize branch time in a fixed box."
        core = [
            "bit __cx_m;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = gaussian_square({c32('0.35')}, {d_ro}, {rand_dt(rng, 64, 200)}, {rand_dt(rng, 16, 80)});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "  if (__cx_m) {",
            "    cal {",
            f"      waveform __cx_pi = gaussian({c32('0.8')}, {d_pi}, {s_pi});",
            f"      play({df}, __cx_pi);",
            "    }",
            "  }",
            "  // fill remaining time to keep deterministic schedule",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        params = {"q": q, "d_pi": d_pi, "d_ro": d_ro}

    elif v == 2:
        vn = "repeat_until_zero_with_try_cap"
        desc = "Repeat capture+conditional X until measurement is 0 or tries reaches a cap; uses while loop and timing boxes."
        cap = rng.randint(2, 5)
        core = [
            "bit __cx_m;",
            f"tries = 0;",
            f"while (tries < {cap}) {{",
            "  stretch __cx_g;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "    if (__cx_m) {",
            "      cal {",
            f"        waveform __cx_pi = gaussian({c32('0.9')}, {d_pi}, {s_pi});",
            f"        play({df}, __cx_pi);",
            "      }",
            "    }",
            f"    delay[__cx_g] q[{q}];",
            "  }",
            "  if (!__cx_m) { break; }",
            "  tries = tries + 1;",
            "}",
        ]
        timing_points2 = timing_points + ["break"]
        classical_points2 = classical_points + ["while", "break"]
        params = {"q": q, "cap": cap, "d_pi": d_pi}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(1, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "double_check_measure_then_reset"
        desc = "Double-check capture: two captures separated by a short idle; only reset if both are 1 (reduces false triggers)."
        idle = rand_dt(rng, 8, 80)
        core = [
            "bit __cx_m1;",
            "bit __cx_m2;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = gaussian_square({c32('0.3')}, {d_ro}, {rand_dt(rng, 64, 200)}, {rand_dt(rng, 16, 80)});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m1 = capture({af}, __cx_ro);",
            f"    delay[{idle}] {af};",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m2 = capture({af}, __cx_ro);",
            "    barrier " + ", ".join([mf, af]) + ";",
            "  }",
            "  if (__cx_m1 && __cx_m2) {",
            "    cal {",
            f"      waveform __cx_pi = gaussian({c32('0.85')}, {d_pi}, {s_pi});",
            f"      play({df}, __cx_pi);",
            "    }",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        params = {"q": q, "idle": idle, "d_pi": d_pi, "d_ro": d_ro}

    else:
        vn = "adaptive_gain_update_before_reset"
        desc = "Update a gain parameter with extern adaptive_update based on measured bit, then apply scaled reset pulse."
        cap = rng.randint(1, 3)
        core = [
            "bit __cx_m;",
            f"tries = {cap};",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.18')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "  // controller-side update: gain <- f(tries, m, gain)",
            "  gain = adaptive_update(tries, int(__cx_m), gain);",
            "  if (__cx_m) {",
            "    cal {",
            f"      waveform __cx_pi = gaussian(scale({c32('0.8')}, gain), {d_pi}, {s_pi});",
            f"      play({df}, __cx_pi);",
            "    }",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q": q, "d_pi": d_pi, "d_ro": d_ro, "cap": cap}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(1, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(1, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 02: Ramsey + feedback phase compensation ====================

def theme_02(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[2]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    unit = choose_delay_unit(meta, rng, prefer_dt=True)
    tau = rand_time(rng, 10, 80, unit) if unit != "dt" else rand_time(rng, 40, 320, unit)

    d_pi2 = rand_dt(rng, 64, 200)
    s_pi2 = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 480)

    tags = ["ramsey", "feedback", "phase_comp", "pulse", "timing", "classical"]
    timing_points = ["delay", "box", "barrier"]
    classical_points = ["if_else", "float_update", "extern_optional", "measure"]
    pulse_points = ["play", "shift_phase", "set_frequency_optional", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    phi_step = rand_angle(rng, -0.6, 0.6)
    df_hz = rand_hz(rng, -5_000_000, 5_000_000)

    if v == 1:
        vn = "ramsey_fixed_tau_readout"
        desc = "Basic Ramsey: pi/2 - delay(tau) - pi/2 with phase shift; capture for fringe." 
        core = [
            "bit __cx_m;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            f"    shift_phase({df}, {phi_step});",
            f"    waveform __cx_pi2b = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    play({df}, __cx_pi2b);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
        ]
        params = {"q": q, "tau": tau, "phi_step": phi_step}

    elif v == 2:
        vn = "ramsey_feedback_update_phase"
        desc = "Ramsey with classical feedback: if captured 1 then advance phase accumulator; apply phase next shot." 
        core = [
            "bit __cx_m;",
            "// gain is used as a phase accumulator here",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            "    // apply current phase estimate",
            "    shift_phase(" + df + ", gain);",
            f"    waveform __cx_pi2b = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    play({df}, __cx_pi2b);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "if (__cx_m) { gain = gain + 0.05; } else { gain = gain - 0.02; }",
        ]
        classical_points2 = classical_points + ["float_arith"]
        params = {"q": q, "tau": tau}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(2, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "ramsey_for_loop_tau_scan"
        desc = "On-controller tau scan: for-loop over a small set of delays; accumulate hits into a counter." 
        steps = rng.randint(3, 5)
        core = [
            f"int __cx_hits = 0;",
            f"for int __cx_k in {{1,2,3}} {{",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"      play({df}, __cx_pi2);",
            "    }",
            f"    delay[{tau}*__cx_k] q[{q}];",
            "    cal {",
            f"      shift_phase({df}, {phi_step});",
            f"      waveform __cx_pi2b = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"      play({df}, __cx_pi2b);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  if (__cx_m) { __cx_hits = __cx_hits + 1; }",
            "}",
            "if (__cx_hits > 1) { x q[" + str(q) + "]; }",
        ]
        timing_points2 = timing_points + ["break"]
        classical_points2 = classical_points + ["for", "break", "counter"]
        params = {"q": q, "tau": tau, "steps": steps, "phi_step": phi_step}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(2, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "ramsey_update_freq_then_phase"
        desc = "Estimate drift coarsely: if capture=1 shift drive frequency a bit, then apply a phase step." 
        core = [
            "bit __cx_m;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            f"    waveform __cx_pi2b = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    play({df}, __cx_pi2b);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "// frequency nudging (controller logic): apply to frame in pulse domain",
            "if (__cx_m) {",
            f"  cal {{ set_frequency({df}, get_frequency({df}) + {df_hz}); }}",
            "} else {",
            f"  cal {{ set_frequency({df}, get_frequency({df}) - {df_hz}); }}",
            "}",
            f"cal {{ shift_phase({df}, {phi_step}); }}",
        ]
        classical_points2 = classical_points + ["extern_optional"]
        pulse_points2 = pulse_points + ["get_frequency", "set_frequency"]
        params = {"q": q, "tau": tau, "df_hz": df_hz, "phi_step": phi_step}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(2, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(2, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 03: Hahn Echo ====================

def theme_03(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[3]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)

    unit = choose_delay_unit(meta, rng, prefer_dt=True)
    tau = rand_time(rng, 20, 120, unit) if unit != "dt" else rand_time(rng, 80, 480, unit)

    d_pi2 = rand_dt(rng, 64, 200)
    s_pi2 = rand_dt(rng, 16, 80)
    d_pi = rand_dt(rng, 80, 240)
    s_pi = rand_dt(rng, 16, 80)

    tags = ["echo", "timing_alignment", "pulse", "classical"]
    timing_points = ["delay", "box", "stretch"]
    classical_points = ["int_arith", "for_optional", "if_optional"]
    pulse_points = ["play", "shift_phase_optional"]
    required_meta = ["pulse.frames.drive"]

    if v == 1:
        vn = "echo_fixed_tau"
        desc = "Hahn echo: pi/2 - tau/2 - pi - tau/2 - pi/2 (pulse-level), scheduled inside a fixed box." 
        core = [
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    waveform __cx_pi  = gaussian({c32('0.9')}, {d_pi}, {s_pi});",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            f"    play({df}, __cx_pi);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        params = {"q": q, "tau": tau}

    elif v == 2:
        vn = "echo_tau_scan_for_loop"
        desc = "Echo scan: for-loop over a small set of tau values (controller-side), reusing the same pulse shapes." 
        steps = rng.randint(3, 5)
        core = [
            f"int __cx_hits = 0;",
            f"cal {{ waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2}); waveform __cx_pi = gaussian({c32('0.9')}, {d_pi}, {s_pi}); }}",
            f"for int __cx_k in {{1,2,3}} {{",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  stretch __cx_g;",
            "  box[BOX_WIN] {",
            "    cal { play(" + df + ", __cx_pi2); }",
            f"    delay[{tau}*__cx_k] q[{q}];",
            "    cal { play(" + df + ", __cx_pi); }",
            f"    delay[{tau}] q[{q}];",
            "    cal { play(" + df + ", __cx_pi2); }",
            f"    delay[__cx_g] q[{q}];",
            "  }",
            "  // count iterations as a stand-in metric",
            "  __cx_hits = __cx_hits + 1;",
            "}",
            "if (__cx_hits > 2) { z q[" + str(q) + "]; }",
        ]
        timing_points2 = timing_points + ["break"]
        classical_points2 = classical_points + ["for", "break", "counter"]
        params = {"q": q, "tau": tau, "steps": steps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(3, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "echo_conditional_extra_pi"
        desc = "Echo with conditional refocus: if a probe measurement bit is 1, insert an extra pi pulse (still within a box)." 
        mf = meas_frame(meta, q)
        af = acq_frame(meta, q)
        d_ro = rand_dt(rng, 160, 480)
        core = [
            "bit __cx_probe;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    waveform __cx_pi  = gaussian({c32('0.9')}, {d_pi}, {s_pi});",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            f"    play({df}, __cx_pi);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_probe = capture({af}, __cx_ro);",
            "  }",
            "  if (__cx_probe) { cal { play(" + df + ", gaussian(" + c32('0.9') + ", " + d_pi + ", " + s_pi + ")); } }",
            f"  delay[{tau}] q[{q}];",
            "  cal { play(" + df + ", gaussian(" + c32('0.5') + ", " + d_pi2 + ", " + s_pi2 + ")); }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        pulse_points2 = pulse_points + ["capture"]
        classical_points2 = classical_points + ["if_else", "measure"]
        required_meta2 = required_meta + ["pulse.frames.meas", "pulse.frames.acq"]
        params = {"q": q, "tau": tau}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(3, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points2, required_meta=required_meta2, params=params, core=core, meas=meas)

    else:
        vn = "echo_virtual_z_compensation"
        desc = "Echo with a virtual-Z compensation: shift_phase before the final pi/2, phase computed from step counter." 
        core = [
            "step = step + 1;",
            "float[64] __cx_phi = 0.01 * float(step);",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.5')}, {d_pi2}, {s_pi2});",
            f"    waveform __cx_pi  = gaussian({c32('0.9')}, {d_pi}, {s_pi});",
            f"    play({df}, __cx_pi2);",
            "  }",
            f"  delay[{tau}] q[{q}];",
            "  cal { play(" + df + ", __cx_pi); }",
            f"  delay[{tau}] q[{q}];",
            "  cal {",
            "    shift_phase(" + df + ", __cx_phi);",
            "    play(" + df + ", __cx_pi2);",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        classical_points2 = classical_points + ["float_cast", "arith"]
        pulse_points2 = pulse_points + ["shift_phase"]
        params = {"q": q, "tau": tau}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(3, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(3, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 04: T1 relaxation measurement ====================

def theme_04(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[4]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    unit = choose_delay_unit(meta, rng, prefer_dt=False)
    t_wait = rand_time(rng, 20, 200, unit)

    d_pi = rand_dt(rng, 80, 240)
    s_pi = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["t1", "relaxation", "timing", "gated_readout", "pulse", "classical"]
    timing_points = ["delay", "box", "const_duration"]
    classical_points = ["for", "counter", "if_optional"]
    pulse_points = ["play", "capture", "barrier_frames"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "single_t1_point"
        desc = "T1 single point: excite with pi pulse, wait, then gated readout inside RO_RING-like box." 
        core = [
            "bit __cx_m;",
            "// excite",
            "cal { waveform __cx_pi = gaussian(" + c32('0.9') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_pi); }",
            f"delay[{t_wait}] q[{q}];",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "    barrier " + ", ".join([mf, af]) + ";",
            "  }",
            "}",
            "if (__cx_m) { syndrome_b[" + str(q) + "] = 1; }",
        ]
        params = {"q": q, "t_wait": t_wait}

    elif v == 2:
        vn = "t1_scan_small_loop"
        desc = "T1 scan: loop over a small set of wait times, accumulate number of excited outcomes." 
        steps = rng.randint(3, 6)
        core = [
            "int __cx_excited = 0;",
            "for int __cx_k in {2,3,4} {",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  bit __cx_m;",
            "  cal { waveform __cx_pi = gaussian(" + c32('0.9') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_pi); }",
            f"  delay[{t_wait}*__cx_k] q[{q}];",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  __cx_excited = __cx_excited + int(__cx_m);",
            "}",
            "if (__cx_excited > 2) { x q[" + str(q) + "]; }",
        ]
        timing_points2 = timing_points + ["break"]
        classical_points2 = classical_points + ["break", "cast_int"]
        params = {"q": q, "t_wait": t_wait, "steps": steps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(4, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "t1_conditional_reexcite"
        desc = "T1 point with conditional re-excitation: if outcome is 0 (already relaxed), reapply pi and measure again." 
        core = [
            "bit __cx_m;",
            "bit __cx_m2;",
            "cal { waveform __cx_pi = gaussian(" + c32('0.9') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_pi); }",
            f"delay[{t_wait}] q[{q}];",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "if (!__cx_m) {",
            "  cal { waveform __cx_pi = gaussian(" + c32('0.9') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_pi); }",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m2 = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["if_else"]
        params = {"q": q, "t_wait": t_wait}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(4, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "t1_adaptive_update_wait"
        desc = "T1 adaptive: use adaptive_update to adjust a wait-time factor (stored in gain) based on capture bit." 
        wait_dt = rand_dt(rng, 40, 300)
        core = [
            "bit __cx_m;",
            "cal { waveform __cx_pi = gaussian(" + c32('0.9') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_pi); }",
            f"delay[{t_wait}] q[{q}];",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "gain = adaptive_update(step, int(__cx_m), gain);",
            "// use gain as a coarse wait adjustment on the acquisition frame",
            "cal { delay[" + wait_dt + "] " + af + "; }",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q": q, "t_wait": t_wait, "wait_dt": wait_dt}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(4, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(4, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 05: Rabi amplitude scan ====================

def theme_05(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[5]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_drv = rand_dt(rng, 80, 280)
    s_drv = rand_dt(rng, 16, 100)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["rabi", "scan", "pulse", "classical", "timing"]
    timing_points = ["delay", "box"]
    classical_points = ["for", "counter", "float_update", "extern_optional"]
    pulse_points = ["play", "scale", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    amps_int=[0.1,0.2,0.3,0.4]
    rand_scaler= rng.uniform(0.5,1.5)
    amps = [f"{a * rand_scaler:.2f}" for a in amps_int]

    if v == 1:
        vn = "simple_amp_loop"
        desc = "Rabi scan: loop over 4 amplitudes, play gaussian drive, capture each time; count number of 1s." 
        core = [
                    "int __cx_hits = 0;",
                    "for int __cx_k in {0,1,2,3} {",
                    "  bit __cx_m;",
                    "  box[BOX_WIN] {",
                    "    // Select amplitude based on loop index",
                    "    switch (__cx_k) {",
                    f"      case 0 {{ cal {{ play({df}, gaussian({c32(amps[0])}, {d_drv}, {s_drv})); }} }}",
                    f"      case 1 {{ cal {{ play({df}, gaussian({c32(amps[1])}, {d_drv}, {s_drv})); }} }}",
                    f"      case 2 {{ cal {{ play({df}, gaussian({c32(amps[2])}, {d_drv}, {s_drv})); }} }}",
                    f"      case 3 {{ cal {{ play({df}, gaussian({c32(amps[3])}, {d_drv}, {s_drv})); }} }}",
                    "    }",
                    "    cal {",
                    f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
                    f"      play({mf}, __cx_ro);",
                    f"      __cx_m = capture({af}, __cx_ro);",
                    "    }",
                    "  }",
                    "  __cx_hits = __cx_hits + int(__cx_m);",
                    "}",
                    "if (__cx_hits > 1) { h q[" + str(q) + "]; }",
                ]
        params = {"q": q, "amps": amps}

    elif v == 2:
        vn = "amp_loop_with_padding_delay"
        desc = "Rabi scan with explicit timing padding: after each shot, delay a random idle to emulate duty-cycle constraints." 
        unit = choose_delay_unit(meta, rng, prefer_dt=False)
        pad = rand_time(rng, 5, 40, unit)
        core = [
            "int __cx_hits = 0;",
            "for int __cx_k in {0,1,2,3} {",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    switch (__cx_k) {",
            f"      case 0 {{ cal {{ play({df}, gaussian({c32(amps[0])}, {d_drv}, {s_drv})); }} }}",
            f"      case 1 {{ cal {{ play({df}, gaussian({c32(amps[1])}, {d_drv}, {s_drv})); }} }}",
            f"      case 2 {{ cal {{ play({df}, gaussian({c32(amps[2])}, {d_drv}, {s_drv})); }} }}",
            f"      case 3 {{ cal {{ play({df}, gaussian({c32(amps[3])}, {d_drv}, {s_drv})); }} }}",
            "    }",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            f"  delay[{pad}] q[{q}];",
            "  __cx_hits = __cx_hits + int(__cx_m);",
            "}",
        ]
        timing_points2 = timing_points + ["duty_cycle_delay"]
        classical_points2 = classical_points + ["cast_int"]
        params = {"q": q, "pad": pad, "amps": amps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(5, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "adaptive_gain_scaled_drive"
        desc = "Use adaptive_update to update gain, then scale drive amplitude in pulse domain each iteration." 
        core = [
            "for int __cx_k in {0,1,2,3} {",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_drv = gaussian(scale({c32(amps[2])}, gain), {d_drv}, {s_drv});",
            f"      play({df}, __cx_drv);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  gain = adaptive_update(__cx_k, int(__cx_m), gain);",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q": q, "amps": amps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(5, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "two_qubit_parallel_rabi_and_measure"
        desc = "Parallel-looking Rabi: drive on q0, while padding delay on another qubit in same box to test scheduler parallelism." 
        q0, q1 = pick_two(meta, rng)
        df0 = drive_frame(meta, q0)
        mf0 = meas_frame(meta, q0)
        af0 = acq_frame(meta, q0)
        unit = choose_delay_unit(meta, rng, prefer_dt=True)
        idle = rand_time(rng, 20, 120, unit)
        core = [
            "bit __cx_m;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  // drive on one qubit",
            "  cal {",
            f"    waveform __cx_drv = gaussian({c32(amps[3])}, {d_drv}, {s_drv});",
            f"    play({df0}, __cx_drv);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro);",
            f"    __cx_m = capture({af0}, __cx_ro);",
            "  }",
            f"  // independent padding on another qubit",
            f"  delay[{idle}] q[{q1}];",
            f"  delay[__cx_g] q[{q0}];",
            "}",
            "if (__cx_m) { x q[" + str(q0) + "]; }",
        ]
        timing_points2 = timing_points + ["stretch"]
        classical_points2 = classical_points + ["if_else"]
        params = {"q0": q0, "q1": q1, "idle": idle}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(5, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(5, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

# ==================== Theme 06: Qubit Spectroscopy Scan ====================

def theme_06(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[6]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_spec = rand_dt(rng, 96, 360)
    s_spec = rand_dt(rng, 16, 120)
    d_ro = rand_dt(rng, 160, 520)

    # small scan: <= 7 points
    npts = rng.randint(3, 7)
    step_hz = rng.randint(500_000, 3_000_000)
    tags = ["spectroscopy", "scan", "pulse", "timing", "classical"]
    timing_points = ["box", "delay", "barrier"]
    classical_points = ["for", "break", "counter", "if_else"]
    pulse_points = ["set_frequency", "get_frequency", "play", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "coarse_scan_break_on_hit"
        desc = "Coarse spectroscopy scan over a few frequency offsets; break early when excitation is detected."
        core = [
            "int __cx_hits = 0;",
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {npts}) {{ break; }}",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      set_frequency({df}, get_frequency({df}) + float(__cx_k - {npts//2}) * {float(step_hz):.1f});",
            f"      waveform __cx_spec = gaussian({c32('0.25')}, {d_spec}, {s_spec});",
            f"      play({df}, __cx_spec);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "      barrier " + ", ".join([df, mf, af]) + ";",
            "    }",
            "  }",
            "  __cx_hits = __cx_hits + int(__cx_m);",
            "  if (__cx_m) { break; }",
            "}",
            "if (__cx_hits > 0) { syndrome_b[" + str(q) + "] = 1; }",
        ]
        params = {"q": q, "npts": npts, "step_hz": step_hz}

    elif v == 2:
        vn = "scan_with_duty_cycle_padding"
        desc = "Spectroscopy scan with explicit duty-cycle padding delay after each point."
        unit = choose_delay_unit(meta, rng, prefer_dt=False)
        pad = rand_time(rng, 5, 40, unit)
        core = [
            "int __cx_hits = 0;",
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {npts}) {{ break; }}",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      set_frequency({df}, get_frequency({df}) + float(__cx_k) * {float(step_hz):.1f});",
            f"      waveform __cx_spec = gaussian({c32('0.22')}, {d_spec}, {s_spec});",
            f"      play({df}, __cx_spec);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            f"  delay[{pad}] q[{q}];",
            "  __cx_hits = __cx_hits + int(__cx_m);",
            "}",
            "if (__cx_hits > 1) { x q[" + str(q) + "]; }",
        ]
        timing_points2 = timing_points + ["duty_cycle_delay"]
        params = {"q": q, "npts": npts, "step_hz": step_hz, "pad": pad}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(6, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "scan_with_adaptive_step"
        desc = "Use adaptive_update to nudge a gain-like value and apply it as an additional frequency offset each point."
        core = [
            "int __cx_hits = 0;",
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {npts}) {{ break; }}",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    cal {",
            "      // gain is reused as a coarse offset scalar",
            f"      set_frequency({df}, get_frequency({df}) + float(__cx_k - {npts//2}) * {float(step_hz):.1f} + gain * 1.0e5);",
            f"      waveform __cx_spec = gaussian({c32('0.24')}, {d_spec}, {s_spec});",
            f"      play({df}, __cx_spec);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  gain = adaptive_update(__cx_k, int(__cx_m), gain);",
            "  __cx_hits = __cx_hits + int(__cx_m);",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q": q, "npts": npts, "step_hz": step_hz}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(6, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "scan_two_qubits_parallel"
        desc = "Do a small spectroscopy scan on one qubit while idling another in the same timing box to test parallel scheduling."
        q0, q1 = pick_two(meta, rng)
        df0 = drive_frame(meta, q0)
        mf0 = meas_frame(meta, q0)
        af0 = acq_frame(meta, q0)
        unit = choose_delay_unit(meta, rng, prefer_dt=True)
        idle = rand_time(rng, 40, 240, unit)
        core = [
            "bit __cx_m;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    set_frequency({df0}, get_frequency({df0}) + {float(step_hz):.1f});",
            f"    waveform __cx_spec = gaussian({c32('0.25')}, {d_spec}, {s_spec});",
            f"    play({df0}, __cx_spec);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro);",
            f"    __cx_m = capture({af0}, __cx_ro);",
            "  }",
            f"  delay[{idle}] q[{q1}];",
            f"  delay[__cx_g] q[{q0}];",
            "}",
            "if (__cx_m) { z q[" + str(q0) + "]; }",
        ]
        timing_points2 = timing_points + ["stretch"]
        params = {"q0": q0, "q1": q1, "idle": idle, "step_hz": step_hz}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(6, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(6, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 07: Echoed CR Gate Verification ====================

def theme_07(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[7]
    qc, qt = pick_two(meta, rng)
    dfc = drive_frame(meta, qc)
    dft = drive_frame(meta, qt)
    mft = meas_frame(meta, qt)
    aft = acq_frame(meta, qt)

    d_cr = rand_dt(rng, 120, 420)
    s_cr = rand_dt(rng, 24, 140)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["two_qubit", "cr", "echo", "pulse", "timing", "classical"]
    timing_points = ["box", "stretch", "barrier", "delay"]
    classical_points = ["if_else", "counter", "measure"]
    pulse_points = ["play", "shift_phase", "capture", "barrier_frames"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "echoed_cr_basic"
        desc = "Echoed CR-style verification: CR(+phase) - X(control) - CR(-phase) then read target."
        core = [
            "bit __cx_m;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  // echoed CR pulses on control drive frame",
            "  cal {",
            f"    waveform __cx_cr = gaussian({c32('0.18')}, {d_cr}, {s_cr});",
            f"    shift_phase({dfc}, 0.25);",
            f"    play({dfc}, __cx_cr);",
            "    barrier " + ", ".join([dfc, dft]) + ";",
            "  }",
            f"  x q[{qc}];",
            "  cal {",
            f"    shift_phase({dfc}, -0.25);",
            f"    play({dfc}, __cx_cr);",
            "  }",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mft}, __cx_ro);",
            f"    __cx_m = capture({aft}, __cx_ro);",
            "  }",
            f"  delay[__cx_g] q[{qt}];",
            "}",
            "if (__cx_m) { syndrome_b[" + str(qt) + "] = 1; }",
        ]
        params = {"qc": qc, "qt": qt, "d_cr": d_cr}

    elif v == 2:
        vn = "echoed_cr_with_interleaved_idle"
        desc = "Echoed CR with a small interleaved idle delay to emulate hardware timing constraints."
        unit = choose_delay_unit(meta, rng, prefer_dt=True)
        idle = rand_time(rng, 40, 220, unit)
        core = [
            "bit __cx_m;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_cr = gaussian({c32('0.16')}, {d_cr}, {s_cr});",
            f"    play({dfc}, __cx_cr);",
            "  }",
            f"  delay[{idle}] q[{qt}];",
            f"  x q[{qc}];",
            "  cal {",
            f"    shift_phase({dfc}, 0.5);",
            f"    play({dfc}, __cx_cr);",
            "  }",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mft}, __cx_ro);",
            f"    __cx_m = capture({aft}, __cx_ro);",
            "  }",
            f"  delay[__cx_g] q[{qt}];",
            "}",
            "if (__cx_m) { z q[" + str(qc) + "]; }",
        ]
        params = {"qc": qc, "qt": qt, "idle": idle}

    elif v == 3:
        vn = "echoed_cr_two_shot_consistency"
        desc = "Run two short echoed-CR checks (<=2 iterations) and compare outcomes; flip a flag if inconsistent."
        core = [
            "bit __cx_m1;",
            "bit __cx_m2;",
            "flag = false;",
            "for int __cx_k in {0,1} {",
            "  bit __cx_m;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_cr = gaussian({c32('0.17')}, {d_cr}, {s_cr});",
            f"      shift_phase({dfc}, float(__cx_k) * 0.3);",
            f"      play({dfc}, __cx_cr);",
            "    }",
            f"    x q[{qc}];",
            "    cal { play(" + dfc + ", gaussian(" + c32('0.17') + ", " + d_cr + ", " + s_cr + ")); }",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mft}, __cx_ro);",
            f"      __cx_m = capture({aft}, __cx_ro);",
            "    }",
            "  }",
            "  if (__cx_k == 0) { __cx_m1 = __cx_m; } else { __cx_m2 = __cx_m; }",
            "}",
            "if (__cx_m1 != __cx_m2) { flag = true; }",
        ]
        classical_points2 = classical_points + ["for"]
        params = {"qc": qc, "qt": qt}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(7, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "echoed_cr_with_freq_nudge"
        desc = "Echoed CR where controller nudges target drive frequency based on readout outcome."
        df_hz = rand_hz(rng, -2_000_000, 2_000_000)
        core = [
            "bit __cx_m;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_cr = gaussian({c32('0.16')}, {d_cr}, {s_cr});",
            f"    play({dfc}, __cx_cr);",
            "  }",
            f"  x q[{qc}];",
            "  cal {",
            f"    shift_phase({dfc}, -0.4);",
            f"    play({dfc}, __cx_cr);",
            "  }",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mft}, __cx_ro);",
            f"    __cx_m = capture({aft}, __cx_ro);",
            "  }",
            "}",
            "if (__cx_m) {",
            f"  cal {{ set_frequency({dft}, get_frequency({dft}) + {df_hz}); }}",
            "} else {",
            f"  cal {{ set_frequency({dft}, get_frequency({dft}) - {df_hz}); }}",
            "}",
        ]
        pulse_points2 = pulse_points + ["set_frequency", "get_frequency"]
        params = {"qc": qc, "qt": qt, "df_hz": df_hz}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(7, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(7, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 08: Dynamic CNOT with Spectator Compensation ====================

def theme_08(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[8]
    uq = used_qubits(meta)
    allq = list(range(n_qubits(meta)))
    cand = uq if len(uq) >= 2 else allq

    if len(cand) >= 3:
        qc, qt, qs = rng.sample(cand, 3)
    elif len(cand) == 2:
        qc, qt = rng.sample(cand, 2)
        qs = qc
    else:
        qc = qt = qs = cand[0]


    dfc = drive_frame(meta, qc)
    dft = drive_frame(meta, qt)
    dfs = drive_frame(meta, qs)

    d_rot = rand_dt(rng, 120, 420)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["cnot", "spectator", "compensation", "pulse", "timing", "classical"]
    timing_points = ["box", "stretch", "barrier"]
    classical_points = ["if_else", "counter"]
    pulse_points = ["play", "shift_phase", "barrier_frames"]
    required_meta = ["pulse.frames.drive"]

    if v == 1:
        vn = "spectator_rotary_overlap"
        desc = "Run a CNOT-like gate sequence while playing a low-amplitude rotary tone on a spectator drive frame within the same box."
        core = [
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  // logical gate domain interaction",
            f"  cx q[{qc}], q[{qt}];",
            "  cal {",
            f"    waveform __cx_rot = sine({c32('0.05')}, {d_rot}, 5.0e6, 0.0);",
            f"    play({dfs}, __cx_rot);",
            "    barrier " + ", ".join([dfc, dft, dfs]) + ";",
            "  }",
            f"  delay[__cx_g] q[{qs}];",
            "}",
        ]
        params = {"qc": qc, "qt": qt, "qs": qs}

    elif v == 2:
        vn = "conditional_extra_comp_phase"
        desc = "Conditionally apply an extra spectator phase shift based on a cheap parity estimate, still inside a fixed box."
        core = [
            "mask = mask ^ 1;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            f"  cx q[{qc}], q[{qt}];",
            "  cal {",
            f"    waveform __cx_rot = constant({c32('0.04')}, {d_rot});",
            f"    play({dfs}, __cx_rot);",
            "  }",
            "  if ((mask & 1) == 1) {",
            f"    cal {{ shift_phase({dfs}, 0.15); }}",
            "  }",
            f"  delay[__cx_g] q[{qs}];",
            "}",
        ]
        params = {"qc": qc, "qt": qt, "qs": qs}

    elif v == 3:
        vn = "two_pulse_comp_bracket"
        desc = "Bracket a two-qubit gate with two small compensation pulses on the spectator to mimic echoed cancellation."
        core = [
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_c1 = gaussian({c32('0.06')}, {d_rot}, {rand_dt(rng, 16, 120)});",
            f"    play({dfs}, __cx_c1);",
            "  }",
            f"  cx q[{qc}], q[{qt}];",
            "  cal {",
            f"    shift_phase({dfs}, 3.141592);",
            f"    play({dfs}, gaussian({c32('0.06')}, {d_rot}, {rand_dt(rng, 16, 120)}));",
            "  }",
            f"  delay[__cx_g] q[{qs}];",
            "}",
        ]
        params = {"qc": qc, "qt": qt, "qs": qs}

    else:
        vn = "compensation_then_readout"
        desc = "Apply spectator compensation during CNOT and then immediately do a quick readout of the target for sanity."
        mft = meas_frame(meta, qt)
        aft = acq_frame(meta, qt)
        core = [
            "bit __cx_m;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            f"  cx q[{qc}], q[{qt}];",
            "  cal {",
            f"    waveform __cx_rot = constant({c32('0.04')}, {d_rot});",
            f"    play({dfs}, __cx_rot);",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mft}, __cx_ro);",
            f"    __cx_m = capture({aft}, __cx_ro);",
            "  }",
            f"  delay[__cx_g] q[{qt}];",
            "}",
            "if (__cx_m) { x q[" + str(qt) + "]; }",
        ]
        pulse_points2 = pulse_points + ["capture"]
        required_meta2 = required_meta + ["pulse.frames.meas", "pulse.frames.acq"]
        params = {"qc": qc, "qt": qt, "qs": qs}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(8, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta2, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(8, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 09: Multiplexed Readout ====================

def theme_09(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[9]
    q0, q1 = pick_two(meta, rng)
    mf0, mf1 = meas_frame(meta, q0), meas_frame(meta, q1)
    af0, af1 = acq_frame(meta, q0), acq_frame(meta, q1)

    d_ro = rand_dt(rng, 200, 520)

    tags = ["readout", "multiplex", "pulse", "timing", "classical"]
    timing_points = ["box", "barrier", "delay"]
    classical_points = ["bit_ops", "if_else", "counter"]
    pulse_points = ["play", "capture", "barrier_frames"]
    required_meta = ["pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "simultaneous_dual_capture"
        desc = "Simultaneous readout on two qubits: play both RO pulses and capture both bits in the same timing box."
        core = [
            "bit __cx_m0;",
            "bit __cx_m1;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro0 = constant({c32('0.2')}, {d_ro});",
            f"    waveform __cx_ro1 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro0);",
            f"    play({mf1}, __cx_ro1);",
            f"    __cx_m0 = capture({af0}, __cx_ro0);",
            f"    __cx_m1 = capture({af1}, __cx_ro1);",
            "    barrier " + ", ".join([mf0, mf1, af0, af1]) + ";",
            "  }",
            "}",
            f"bg_m[{q0}] = __cx_m0;",
            f"bg_m[{q1}] = __cx_m1;",
        ]
        params = {"q0": q0, "q1": q1}

    elif v == 2:
        vn = "mux_readout_then_parity_flag"
        desc = "Compute a simple parity flag from two simultaneous captures; store into syndrome_b."
        core = [
            "bit __cx_m0;",
            "bit __cx_m1;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro0 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro0);",
            f"    play({mf1}, __cx_ro0);",
            f"    __cx_m0 = capture({af0}, __cx_ro0);",
            f"    __cx_m1 = capture({af1}, __cx_ro0);",
            "  }",
            "}",
            f"syndrome_b[{q0}] = (__cx_m0 != __cx_m1);",
        ]
        params = {"q0": q0, "q1": q1}

    elif v == 3:
        vn = "mux_readout_loop_averaging"
        desc = "Do <=3 multiplexed readouts and count ones as a crude in-shot averaging."
        reps = rng.randint(2, 3)
        core = [
            "int __cx_cnt = 0;",
            f"for int __cx_k in {{0,1,2}} {{",
            f"  if (__cx_k >= {reps}) {{ break; }}",
            "  bit __cx_m0;",
            "  bit __cx_m1;",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf0}, __cx_ro);",
            f"      play({mf1}, __cx_ro);",
            f"      __cx_m0 = capture({af0}, __cx_ro);",
            f"      __cx_m1 = capture({af1}, __cx_ro);",
            "    }",
            "  }",
            "  __cx_cnt = __cx_cnt + int(__cx_m0) + int(__cx_m1);",
            "}",
            "if (__cx_cnt > 2) { x q[" + str(q0) + "]; }",
        ]
        classical_points2 = classical_points + ["for", "break", "cast_int"]
        params = {"q0": q0, "q1": q1, "reps": reps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(9, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "mux_readout_conditional_reset_one"
        desc = "Do multiplexed readout; if one qubit is 1 apply a quick X reset on that qubit (gate domain) and pad timing."
        df0 = drive_frame(meta, q0)
        core = [
            "bit __cx_m0;",
            "bit __cx_m1;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro);",
            f"    play({mf1}, __cx_ro);",
            f"    __cx_m0 = capture({af0}, __cx_ro);",
            f"    __cx_m1 = capture({af1}, __cx_ro);",
            "  }",
            "  if (__cx_m0) { x q[" + str(q0) + "]; }",
            "  if (__cx_m1) { x q[" + str(q1) + "]; }",
            f"  delay[__cx_g] q[{q0}];",
            "}",
        ]
        timing_points2 = timing_points + ["stretch"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(9, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(9, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 10: Raw Waveform Capture + Filter ====================

def theme_10(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[10]
    q = pick_qubit(meta, rng)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_ro = rand_dt(rng, 200, 520)
    raw_d = rand_dt(rng, 96, 320)

    tags = ["capture", "raw", "filter", "pulse", "timing", "classical"]
    timing_points = ["box", "delay"]
    classical_points = ["if_else", "counter", "cast_int"]
    pulse_points = ["capture_v1", "capture", "play", "discriminate_optional"]
    required_meta = ["pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "raw_capture_plus_bit_capture"
        desc = "Capture a raw waveform (capture_v1) and also do a filtered capture returning a bit; store bit into bg_m."
        core = [
            "bit __cx_m;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    waveform __cx_raw = capture_v1({af}, {raw_d});",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            f"bg_m[{q}] = __cx_m;",
        ]
        params = {"q": q, "raw_d": raw_d}

    elif v == 2:
        vn = "raw_capture_then_dummy_discriminate"
        desc = "Raw capture then a toy discriminate() call on a synthetic IQ (for feature coverage); combine with filtered bit."
        core = [
            "bit __cx_m;",
            "bit __cx_b;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    waveform __cx_raw = capture_v1({af}, {raw_d});",
            f"    __cx_m = capture({af}, __cx_ro);",
            "    complex[float[64]] __cx_iq = 0.10+0.00im;",
            "    __cx_b = discriminate(__cx_iq);",
            "  }",
            "}",
            "if (__cx_m || __cx_b) { syndrome_b[" + str(q) + "] = 1; }",
        ]
        params = {"q": q}

    elif v == 3:
        vn = "short_repeated_raw_capture"
        desc = "Do <=3 short raw captures and count how many times the filtered bit is 1 (micro-averaging)."
        reps = rng.randint(2, 3)
        core = [
            "int __cx_cnt = 0;",
            f"for int __cx_k in {{0,1,2}} {{",
            f"  if (__cx_k >= {reps}) {{ break; }}",
            "  bit __cx_m;",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      waveform __cx_raw = capture_v1({af}, {raw_d});",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  __cx_cnt = __cx_cnt + int(__cx_m);",
            "}",
            "if (__cx_cnt > 1) { x q[" + str(q) + "]; }",
        ]
        classical_points2 = classical_points + ["for", "break"]
        params = {"q": q, "reps": reps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(10, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "raw_capture_with_timing_gate"
        desc = "Gate the acquisition with an extra delay on the acquisition frame to emulate a timing window."
        gate_dt = rand_dt(rng, 8, 80)
        core = [
            "bit __cx_m;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    delay[{gate_dt}] {af};",
            f"    waveform __cx_raw = capture_v1({af}, {raw_d});",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "if (__cx_m) { z q[" + str(q) + "]; }",
        ]
        params = {"q": q, "gate_dt": gate_dt}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(10, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 11: Measurement Crosstalk Calibration ====================

def theme_11(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[11]
    q0, q1 = pick_two(meta, rng)
    mf0, af0 = meas_frame(meta, q0), acq_frame(meta, q0)
    df1, mf1, af1 = drive_frame(meta, q1), meas_frame(meta, q1), acq_frame(meta, q1)

    d_ro = rand_dt(rng, 200, 520)
    d_drv = rand_dt(rng, 96, 320)
    s_drv = rand_dt(rng, 16, 120)

    tags = ["crosstalk", "stark_shift", "calibration", "pulse", "timing", "classical"]
    timing_points = ["box", "barrier", "delay"]
    classical_points = ["if_else", "counter", "bit_ops"]
    pulse_points = ["play", "capture", "shift_phase"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "meas_on_q0_drive_on_q1"
        desc = "Apply readout on q0 while driving q1; then read out q1 to observe crosstalk-like effect."
        core = [
            "bit __cx_m0;",
            "bit __cx_m1;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro0 = constant({c32('0.2')}, {d_ro});",
            f"    waveform __cx_drv1 = gaussian({c32('0.18')}, {d_drv}, {s_drv});",
            f"    play({mf0}, __cx_ro0);",
            f"    __cx_m0 = capture({af0}, __cx_ro0);",
            f"    play({df1}, __cx_drv1);",
            f"    waveform __cx_ro1 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf1}, __cx_ro1);",
            f"    __cx_m1 = capture({af1}, __cx_ro1);",
            "    barrier " + ", ".join([mf0, df1, mf1]) + ";",
            "  }",
            "}",
            "if (__cx_m0 && __cx_m1) { syndrome_b[" + str(q1) + "] = 1; }",
        ]
        params = {"q0": q0, "q1": q1}

    elif v == 2:
        vn = "phase_compensation_sweep_small"
        desc = "Try a small phase compensation on q1 drive while q0 is being measured; choose branch based on outcome."
        ph = rand_angle(rng, -0.4, 0.4)
        core = [
            "bit __cx_m1;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro0 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro0);",
            f"    capture({af0}, __cx_ro0);",
            f"    shift_phase({df1}, {ph});",
            f"    play({df1}, gaussian({c32('0.18')}, {d_drv}, {s_drv}));",
            f"    waveform __cx_ro1 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf1}, __cx_ro1);",
            f"    __cx_m1 = capture({af1}, __cx_ro1);",
            "  }",
            "}",
            "if (__cx_m1) { x q[" + str(q1) + "]; } else { z q[" + str(q1) + "]; }",
        ]
        params = {"q0": q0, "q1": q1, "ph": ph}

    elif v == 3:
        vn = "two_point_compare_flag"
        desc = "Run two short conditions (<=2) and flag if results differ; models a crosstalk calibration compare."
        core = [
            "bit __cx_a;",
            "bit __cx_b;",
            "for int __cx_k in {0,1} {",
            "  bit __cx_m1;",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro0 = constant({c32('0.2')}, {d_ro});",
            f"      play({mf0}, __cx_ro0);",
            f"      capture({af0}, __cx_ro0);",
            f"      play({df1}, gaussian({c32('0.18')}, {d_drv}, {s_drv}));",
            f"      waveform __cx_ro1 = constant({c32('0.2')}, {d_ro});",
            f"      play({mf1}, __cx_ro1);",
            f"      __cx_m1 = capture({af1}, __cx_ro1);",
            "    }",
            "  }",
            "  if (__cx_k == 0) { __cx_a = __cx_m1; } else { __cx_b = __cx_m1; }",
            "}",
            "if (__cx_a != __cx_b) { flag = true; }",
        ]
        classical_points2 = classical_points + ["for"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(11, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "adaptive_update_comp_gain"
        desc = "Use adaptive_update on the controller side to update a gain-like value based on measurement outcome."
        core = [
            "bit __cx_m1;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro0 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro0);",
            f"    capture({af0}, __cx_ro0);",
            f"    waveform __cx_comp = gaussian(scale({c32('0.12')}, gain), {d_drv}, {s_drv});",
            f"    play({df1}, __cx_comp);",
            f"    waveform __cx_ro1 = constant({c32('0.2')}, {d_ro});",
            f"    play({mf1}, __cx_ro1);",
            f"    __cx_m1 = capture({af1}, __cx_ro1);",
            "  }",
            "}",
            "gain = adaptive_update(step, int(__cx_m1), gain);",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(11, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(11, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 12: Realtime Feedback Correction ====================

def theme_12(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[12]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_pi = rand_dt(rng, 80, 240)
    s_pi = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["feedback", "correction", "classical", "pulse", "timing"]
    timing_points = ["box", "delay", "stretch"]
    classical_points = ["if_else", "majority_vote", "counter"]
    pulse_points = ["capture", "play"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "two_shot_majority_vote"
        desc = "Measure twice and do a majority-like vote (2 samples); if both are 1 apply an X correction pulse."
        core = [
            "bit __cx_m1;",
            "bit __cx_m2;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m1 = capture({af}, __cx_ro);",
            f"    delay[{rand_dt(rng, 8, 80)}] {af};",
            f"    __cx_m2 = capture({af}, __cx_ro);",
            "  }",
            "  if (__cx_m1 && __cx_m2) {",
            "    cal {",
            f"      waveform __cx_pi = gaussian({c32('0.85')}, {d_pi}, {s_pi});",
            f"      play({df}, __cx_pi);",
            "    }",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        params = {"q": q}

    elif v == 2:
        vn = "three_sample_vote_cap"
        desc = "Take up to 3 samples (loop <=3) and apply correction if count>=2; demonstrates bounded loop."
        reps = 3
        core = [
            "int __cx_cnt = 0;",
            f"for int __cx_k in {{0,1,2}} {{",
            "  bit __cx_m;",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  __cx_cnt = __cx_cnt + int(__cx_m);",
            "}",
            "if (__cx_cnt >= 2) {",
            "  cal { waveform __cx_pi = gaussian(" + c32('0.85') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_pi); }",
            "}",
        ]
        classical_points2 = classical_points + ["for", "cast_int"]
        params = {"q": q, "reps": reps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(12, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "conditional_phase_kick"
        desc = "If measurement indicates error, apply a virtual phase kick (shift_phase) instead of a full X pulse."
        ph = rand_angle(rng, -0.6, 0.6)
        core = [
            "bit __cx_m;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "if (__cx_m) {",
            f"  cal {{ shift_phase({df}, {ph}); }}",
            "}",
        ]
        pulse_points2 = pulse_points + ["shift_phase"]
        params = {"q": q, "ph": ph}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(12, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "adaptive_update_then_scaled_correction"
        desc = "Update gain via adaptive_update and apply a scaled correction pulse when error bit is 1."
        core = [
            "bit __cx_m;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            "gain = adaptive_update(step, int(__cx_m), gain);",
            "if (__cx_m) {",
            "  cal {",
            f"    waveform __cx_pi = gaussian(scale({c32('0.85')}, gain), {d_pi}, {s_pi});",
            f"    play({df}, __cx_pi);",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(12, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(12, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 13: Pipeline Measure-Reset-Prep ====================

def theme_13(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[13]
    q0, q1 = pick_two(meta, rng)
    df0, df1 = drive_frame(meta, q0), drive_frame(meta, q1)
    mf0, af0 = meas_frame(meta, q0), acq_frame(meta, q0)

    d_pi = rand_dt(rng, 80, 240)
    s_pi = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["pipeline", "parallel", "timing", "pulse", "classical"]
    timing_points = ["box", "delay", "barrier"]
    classical_points = ["if_else", "counter"]
    pulse_points = ["play", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "measure_q0_prep_q1_parallel"
        desc = "Pipeline: measure q0 while preparing q1 in the same timing box (parallel-friendly scheduling)."
        core = [
            "bit __cx_m0;",
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro);",
            f"    __cx_m0 = capture({af0}, __cx_ro);",
            "  }",
            "  // in parallel: prepare q1 with a pulse-level pi/2 (approx)",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.45')}, {d_pi}, {s_pi});",
            f"    play({df1}, __cx_pi2);",
            "  }",
            f"  delay[__cx_g] q[{q0}];",
            "}",
            "if (__cx_m0) { x q[" + str(q0) + "]; }",
        ]
        params = {"q0": q0, "q1": q1}

    elif v == 2:
        vn = "measure_then_active_reset_then_prep"
        desc = "Pipeline with active reset: measure q0, conditionally apply X, then prep q1; all within bounded boxes."
        core = [
            "bit __cx_m0;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro);",
            f"    __cx_m0 = capture({af0}, __cx_ro);",
            "  }",
            "  if (__cx_m0) { x q[" + str(q0) + "]; }",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.45')}, {d_pi}, {s_pi});",
            f"    play({df1}, __cx_pi2);",
            "  }",
            "}",
        ]
        params = {"q0": q0, "q1": q1}

    elif v == 3:
        vn = "two_stage_pipeline_small_loop"
        desc = "Run <=2 pipeline stages in a small loop (bounded) to emulate streaming control."
        core = [
            "for int __cx_k in {0,1} {",
            "  bit __cx_m0;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf0}, __cx_ro);",
            f"      __cx_m0 = capture({af0}, __cx_ro);",
            "    }",
            "    cal {",
            f"      waveform __cx_pi2 = gaussian({c32('0.45')}, {d_pi}, {s_pi});",
            f"      play({df1}, __cx_pi2);",
            "    }",
            "  }",
            "  if (__cx_m0) { syndrome_b[" + str(q0) + "] = 1; }",
            "}",
        ]
        classical_points2 = classical_points + ["for"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(13, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "pipeline_with_barrier_alignment"
        desc = "Pipeline with explicit frame barrier alignment to show timing control across frames."
        core = [
            "bit __cx_m0;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro);",
            f"    __cx_m0 = capture({af0}, __cx_ro);",
            "    barrier " + ", ".join([mf0, af0]) + ";",
            "  }",
            "  cal {",
            f"    waveform __cx_pi2 = gaussian({c32('0.45')}, {d_pi}, {s_pi});",
            f"    play({df1}, __cx_pi2);",
            "    barrier " + ", ".join([df0, df1]) + ";",
            "  }",
            "}",
            "if (__cx_m0) { x q[" + str(q0) + "]; }",
        ]
        pulse_points2 = pulse_points + ["barrier_frames"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(13, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(13, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 14: Randomized Benchmarking (Controller-side) ====================

def theme_14(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[14]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)

    steps = rng.randint(4, 7)  # <= 7
    tags = ["rb", "clifford", "controller", "classical", "timing", "pulse"]
    timing_points = ["delay", "box"]
    classical_points = ["for", "switch", "bitwise", "counter"]
    pulse_points = ["shift_phase_optional"]
    required_meta = ["pulse.frames.drive"]

    if v == 1:
        vn = "rb_switch_on_mask"
        desc = "Controller-side RB: update mask and use switch on low bits to choose simple Clifford-like gates (<=7 steps)."
        unit = choose_delay_unit(meta, rng, prefer_dt=False)
        pad = rand_time(rng, 5, 25, unit)
        core = [
            "mask = mask ^ 0x9e3779b9;",
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  mask = mask * 1664525 + 1013904223;",
            "  int __cx_sel = int(mask & 3);",
            "  switch (__cx_sel) {",
            f"    case 0 {{ h q[{q}]; }}",
            f"    case 1 {{ x q[{q}]; }}",
            f"    case 2 {{ s q[{q}]; }}",
            f"    default {{ sdg q[{q}]; }}",
            "  }",
            f"  delay[{pad}] q[{q}];",
            "}",
        ]
        params = {"q": q, "steps": steps}

    elif v == 2:
        vn = "rb_with_virtual_z_tracking"
        desc = "RB with virtual-Z tracking: shift_phase on the drive frame based on step counter between random gates."
        core = [
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  mask = mask * 1103515245 + 12345;",
            "  int __cx_sel = int((mask >> 1) & 3);",
            "  switch (__cx_sel) {",
            f"    case 0 {{ h q[{q}]; }}",
            f"    case 1 {{ x q[{q}]; }}",
            f"    case 2 {{ y q[{q}]; }}",
            f"    default {{ z q[{q}]; }}",
            "  }",
            "  cal { shift_phase(" + df + ", 0.02 * float(__cx_k)); }",
            "}",
        ]
        pulse_points2 = pulse_points + ["shift_phase"]
        params = {"q": q, "steps": steps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(14, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "rb_boxed_equal_length"
        desc = "RB in fixed-length boxes: each step placed inside BOX_WIN with stretch padding to emulate deterministic timing."
        d_pi2 = rand_dt(rng, 64, 200)
        s_pi2 = rand_dt(rng, 16, 80)
        core = [
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  stretch __cx_g;",
            "  box[BOX_WIN] {",
            "    mask = mask * 1664525 + 1013904223;",
            "    int __cx_sel = int(mask & 3);",
            "    if (__cx_sel == 0) { h q[" + str(q) + "]; }",
            "    if (__cx_sel == 1) { x q[" + str(q) + "]; }",
            "    if (__cx_sel == 2) { s q[" + str(q) + "]; }",
            "    if (__cx_sel == 3) { sdg q[" + str(q) + "]; }",
            "    cal { waveform __cx_pi2 = gaussian(" + c32('0.45') + ", " + d_pi2 + ", " + s_pi2 + "); play(" + df + ", __cx_pi2); }",
            f"    delay[__cx_g] q[{q}];",
            "  }",
            "}",
        ]
        timing_points2 = timing_points + ["stretch", "box"]
        classical_points2 = classical_points + ["if_else", "break"]
        pulse_points2 = pulse_points + ["play"]
        params = {"q": q, "steps": steps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(14, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points2, classical_points=classical_points2,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "rb_then_measure_and_reset"
        desc = "Run a short RB chain then measure and conditionally reset (active reset), demonstrating classical feedback."
        mf = meas_frame(meta, q)
        af = acq_frame(meta, q)
        d_ro = rand_dt(rng, 160, 520)
        core = [
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {steps}) {{ break; }}",
            "  mask = mask * 1103515245 + 12345;",
            "  int __cx_sel = int(mask & 3);",
            "  switch (__cx_sel) {",
            f"    case 0 {{ h q[{q}]; }}",
            f"    case 1 {{ x q[{q}]; }}",
            f"    case 2 {{ s q[{q}]; }}",
            f"    default {{ sdg q[{q}]; }}",
            "  }",
            "}",
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "if (__cx_m) { x q[" + str(q) + "]; }",
        ]
        required_meta2 = required_meta + ["pulse.frames.meas", "pulse.frames.acq"]
        params = {"q": q, "steps": steps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(14, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points, required_meta=required_meta2, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(14, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 15: Repeat-Until-Success State Preparation ====================

def theme_15(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[15]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_prep = rand_dt(rng, 80, 240)
    s_prep = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 520)

    cap = rng.randint(2, 7)  # bounded

    tags = ["repeat_until_success", "prep", "feedback", "pulse", "timing", "classical"]
    timing_points = ["box", "stretch", "delay"]
    classical_points = ["while", "break", "counter", "if_else"]
    pulse_points = ["play", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "while_loop_until_success"
        desc = "Repeat preparation + measurement until success (m=0) or tries hits cap (<=7)."
        core = [
            "bit __cx_m;",
            "tries = 0;",
            f"while (tries < {cap}) {{",
            "  stretch __cx_g;",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_prep = gaussian({c32('0.55')}, {d_prep}, {s_prep});",
            f"      play({df}, __cx_prep);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            f"    delay[__cx_g] q[{q}];",
            "  }",
            "  if (!__cx_m) { break; }",
            "  tries = tries + 1;",
            "}",
        ]
        params = {"q": q, "cap": cap}

    elif v == 2:
        vn = "until_success_with_adaptive_gain"
        desc = "Repeat-until-success while updating gain each attempt via adaptive_update; use it to scale prep pulse."
        core = [
            "bit __cx_m;",
            "tries = 0;",
            f"while (tries < {cap}) {{",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_prep = gaussian(scale({c32('0.55')}, gain), {d_prep}, {s_prep});",
            f"      play({df}, __cx_prep);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  gain = adaptive_update(tries, int(__cx_m), gain);",
            "  if (!__cx_m) { break; }",
            "  tries = tries + 1;",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call", "cast_int"]
        params = {"q": q, "cap": cap}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(15, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "for_loop_fixed_attempts"
        desc = "Fixed attempts (<=7) in a for-loop; stop early on success using break."
        core = [
            "bit __cx_m;",
            f"for int __cx_k in {{0,1,2,3,4,5,6}} {{",
            f"  if (__cx_k >= {cap}) {{ break; }}",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_prep = gaussian({c32('0.55')}, {d_prep}, {s_prep});",
            f"      play({df}, __cx_prep);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  if (!__cx_m) { break; }",
            "}",
        ]
        classical_points2 = ["for", "break", "if_else", "measure"]
        params = {"q": q, "cap": cap}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(15, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "success_then_finalize_phase"
        desc = "Repeat-until-success; when success, apply a small virtual-Z finalization shift_phase on the drive frame."
        ph = rand_angle(rng, -0.5, 0.5)
        core = [
            "bit __cx_m;",
            "tries = 0;",
            f"while (tries < {cap}) {{",
            "  box[BOX_WIN] {",
            "    cal {",
            f"      waveform __cx_prep = gaussian({c32('0.55')}, {d_prep}, {s_prep});",
            f"      play({df}, __cx_prep);",
            f"      waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_m = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  if (!__cx_m) { break; }",
            "  tries = tries + 1;",
            "}",
            "if (!__cx_m) { cal { shift_phase(" + df + ", " + str(float(ph)) + "); } }",
        ]
        pulse_points2 = pulse_points + ["shift_phase"]
        params = {"q": q, "cap": cap, "ph": ph}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(15, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(15, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 16: Leakage Detection and Recovery ====================

def theme_16(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[16]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_ro = rand_dt(rng, 160, 520)
    d_rec = rand_dt(rng, 120, 360)
    s_rec = rand_dt(rng, 16, 120)

    tags = ["leakage", "detection", "recovery", "pulse", "timing", "classical"]
    timing_points = ["box", "delay", "stretch"]
    classical_points = ["if_else", "and_or", "counter"]
    pulse_points = ["capture", "play", "drag_optional"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "double_capture_leak_flag"
        desc = "Two captures separated by a short idle; if both are 1, treat as leakage flag and apply recovery pulse."
        idle = rand_dt(rng, 8, 80)
        core = [
            "bit __cx_m1;",
            "bit __cx_m2;",
            "stretch __cx_g;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m1 = capture({af}, __cx_ro);",
            f"    delay[{idle}] {af};",
            f"    __cx_m2 = capture({af}, __cx_ro);",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
            "if (__cx_m1 && __cx_m2) {",
            "  cal {",
            f"    waveform __cx_rec = gaussian({c32('0.9')}, {d_rec}, {s_rec});",
            f"    play({df}, __cx_rec);",
            "  }",
            "}",
        ]
        params = {"q": q, "idle": idle}

    elif v == 2:
        vn = "leakage_then_drag_recovery"
        desc = "If capture bit is 1, apply a DRAG-style recovery pulse (beta randomized) then re-measure once."
        beta = f"{(rng.random()*1.2 - 0.6):.4f}"
        core = [
            "bit __cx_m;",
            "bit __cx_m2;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "if (__cx_m) {",
            "  cal {",
            f"    waveform __cx_rec = drag({c32('0.75')}, {d_rec}, {s_rec}, {beta});",
            f"    play({df}, __cx_rec);",
            "  }",
            "  box[RO_RING] { cal { waveform __cx_ro2 = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro2); __cx_m2 = capture(" + af + ", __cx_ro2); } }",
            "}",
        ]
        params = {"q": q, "beta": beta}

    elif v == 3:
        vn = "bounded_recovery_attempts"
        desc = "Bounded recovery attempts (<=3): if still flagged, repeat a short recovery + remeasure."
        reps = 3
        core = [
            "bit __cx_m;",
            "for int __cx_k in {0,1,2} {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "  if (!__cx_m) { break; }",
            "  cal { waveform __cx_rec = gaussian(" + c32('0.85') + ", " + d_rec + ", " + s_rec + "); play(" + df + ", __cx_rec); }",
            "}",
            "if (__cx_m) { syndrome_b[" + str(q) + "] = 1; }",
        ]
        classical_points2 = classical_points + ["for", "break"]
        params = {"q": q, "reps": reps}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(16, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "leakage_flag_updates_gain"
        desc = "If leakage suspected, call adaptive_update and adjust gain; then apply scaled recovery pulse."
        core = [
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "if (__cx_m) {",
            "  gain = adaptive_update(step, 1, gain);",
            "  cal {",
            f"    waveform __cx_rec = gaussian(scale({c32('0.85')}, gain), {d_rec}, {s_rec});",
            f"    play({df}, __cx_rec);",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(16, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(16, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 17: Virtual Z Phase Tracking Consistency Test ====================

def theme_17(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[17]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_pi2 = rand_dt(rng, 60, 200)
    s_pi2 = rand_dt(rng, 16, 80)
    d_ro = rand_dt(rng, 160, 520)
    idle = rand_dt(rng, 10, 90)

    tags = ["virtual_z", "phase_tracking", "pulse", "timing", "classical"]
    timing_points = ["delay", "barrier", "box"]
    classical_points = ["for", "float_accum", "if_else"]
    pulse_points = ["shift_phase", "play", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "phase_walk_then_measure"
        desc = "Accumulate small virtual-Z steps (<=7) and then measure; checks consistent phase tracking under timing gaps."
        step_phi = f"{(rng.random()*0.18 + 0.02):.5f}"
        core = [
            "float[64] __cx_phi;",
            "__cx_phi = 0.0;",
            "for int __cx_k in {0,1,2,3,4,5} {",
            f"  __cx_phi = __cx_phi + {step_phi};",
            f"  cal {{ shift_phase({df}, __cx_phi); }}",
            f"  delay[{idle}] q[{q}];",
            "}",
            "barrier q;",
            "bit __cx_m;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            f"bg_m[{q}] = __cx_m;",
        ]
        params = {"q": q, "step_phi": float(step_phi)}

    elif v == 2:
        vn = "feedback_phase_kick"
        desc = "Measure once, then conditionally apply a phase kick; re-measure to validate conditional virtual-Z."
        ph = rand_angle(rng, -0.8, 0.8)
        core = [
            "bit __cx_m1;",
            "bit __cx_m2;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m1 = capture(" + af + ", __cx_ro); } }",
            "if (__cx_m1) {",
            f"  cal {{ shift_phase({df}, {ph}); }}",
            "} else {",
            f"  cal {{ shift_phase({df}, -({ph})); }}",
            "}",
            f"delay[{idle}] q[{q}];",
            "box[RO_RING] { cal { waveform __cx_ro2 = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro2); __cx_m2 = capture(" + af + ", __cx_ro2); } }",
            f"bg_m[{q}] = __cx_m2;",
        ]
        params = {"q": q, "ph": float(ph)}

    elif v == 3:
        vn = "phase_accum_with_update"
        desc = "Use adaptive_update to tweak phase accumulator (<=7); apply shift_phase each step under a fixed box."
        step_phi = f"{(rng.random()*0.10 + 0.03):.5f}"
        core = [
            "float[64] __cx_phi;",
            "__cx_phi = 0.0;",
            "box[BOX_WIN] {",
            "  for int __cx_k in {0,1,2,3,4,5,6} {",
            f"    __cx_phi = __cx_phi + {step_phi};",
            "    gain = adaptive_update(step, __cx_k, gain);",
            f"    cal {{ shift_phase({df}, __cx_phi + 0.01 * gain); }}",
            f"    delay[{rand_dt(rng, 2, 22)}] q[{q}];",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["extern_call", "box"]
        params = {"q": q, "step_phi": float(step_phi)}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(17, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points + ["box"], classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "two_frame_phase_balance"
        desc = "Apply opposite phase shifts on drive vs meas frame then capture; tests multi-frame phase bookkeeping."
        ph = rand_angle(rng, -0.6, 0.6)
        core = [
            "bit __cx_m;",
            f"cal {{ shift_phase({df}, {ph}); shift_phase({mf}, -({ph})); barrier {df}, {mf}; }}",
            f"delay[{idle}] q[{q}];",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf}, __cx_ro);",
            f"    __cx_m = capture({af}, __cx_ro);",
            "  }",
            "}",
            f"bg_m[{q}] = __cx_m;",
        ]
        classical_points2 = classical_points + ["barrier"]
        params = {"q": q, "ph": float(ph)}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(17, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points + ["barrier"], classical_points=classical_points2,
                   pulse_points=pulse_points + ["barrier_frames"], required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(17, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 18: Calibration Hot Swap (Local Override) ====================

def theme_18(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[18]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_probe = rand_dt(rng, 80, 260)
    s_probe = rand_dt(rng, 16, 90)
    d_ro = rand_dt(rng, 160, 520)
    df_hz = rand_hz(rng, -8_000_000, 8_000_000)

    tags = ["calibration", "frame_update", "pulse", "timing", "classical"]
    timing_points = ["delay", "box"]
    classical_points = ["float_temp", "if_else", "extern_optional"]
    pulse_points = ["get_frequency", "set_frequency", "shift_phase", "play", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "retune_frequency_then_probe"
        desc = "Temporarily retune drive frequency, play a probe pulse, then measure in a gated window."
        core = [
            "float[64] __cx_f0;",
            f"cal {{ __cx_f0 = get_frequency({df}); set_frequency({df}, __cx_f0 + {df_hz}); }}",
            "cal {",
            f"  waveform __cx_p = gaussian({c32('0.35')}, {d_probe}, {s_probe});",
            f"  play({df}, __cx_p);",
            "}",
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            f"cal {{ set_frequency({df}, __cx_f0); }}",
            f"bg_m[{q}] = __cx_m;",
        ]
        params = {"q": q, "df_hz": float(df_hz)}

    elif v == 2:
        vn = "phase_zeroing_roundtrip"
        desc = "Apply a phase offset then undo it (hot-swap style), verifying that the net effect cancels."
        ph = rand_angle(rng, -0.9, 0.9)
        core = [
            "bit __cx_m;",
            f"cal {{ shift_phase({df}, {ph}); }}",
            f"delay[{rand_dt(rng, 8, 80)}] q[{q}];",
            f"cal {{ shift_phase({df}, -({ph})); }}",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            f"bg_m[{q}] = __cx_m;",
        ]
        params = {"q": q, "ph": float(ph)}

    elif v == 3:
        vn = "gain_driven_override"
        desc = "Use adaptive_update to adjust gain, then apply a probe under a fixed box before measuring."
        core = [
            "gain = adaptive_update(step, 2, gain);",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_p = gaussian({c32('0.35')}, {d_probe}, {s_probe});",
            f"    play({df}, __cx_p);",
            "  }",
            f"  delay[{rand_dt(rng, 6, 40)}] q[{q}];",
            "}",
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            f"bg_m[{q}] = __cx_m;",
        ]
        classical_points2 = classical_points + ["extern_call"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(18, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points + ["stretch_optional"], classical_points=classical_points2,
                   pulse_points=pulse_points + ["scale"], required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "save_restore_frequency"
        desc = "Save current frequency, offset it briefly, and always restore; uses classical guard flag."
        core = [
            "float[64] __cx_f0;",
            "bool __cx_ok;",
            "__cx_ok = true;",
            f"cal {{ __cx_f0 = get_frequency({df}); set_frequency({df}, __cx_f0 + {df_hz}); }}",
            "if (__cx_ok) {",
            "  cal {",
            f"    waveform __cx_p = gaussian({c32('0.30')}, {d_probe}, {s_probe});",
            f"    play({df}, __cx_p);",
            "  }",
            "}",
            f"cal {{ set_frequency({df}, __cx_f0); }}",
        ]
        params = {"q": q, "df_hz": float(df_hz)}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(18, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 19: durationof-driven Alignment Scheduling ====================

def theme_19(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[19]
    q0 = pick_qubit(meta, rng)
    q1 = pick_qubit(meta, rng)
    if q1 == q0 and n_qubits(meta) > 1:
        uq = used_qubits(meta)
        q1 = rng.choice([x for x in uq if x != q0] or [q0])

    df0 = drive_frame(meta, q0)
    df1 = drive_frame(meta, q1)

    tags = ["durationof", "alignment", "scheduling", "timing", "pulse", "classical"]
    timing_points = ["durationof", "box", "stretch", "delay", "barrier"]
    classical_points = ["duration_type", "for_or_if"]
    pulse_points = ["play", "barrier_frames", "shift_phase_optional"]
    required_meta = ["pulse.frames.drive"]

    ang = rand_angle(rng, -1.1, 1.1)

    if v == 1:
        vn = "match_rotary_to_gate_duration"
        desc = "Compute durationof a parametric gate, then stretch a pulse box to match that duration (rotary fill)."
        core = [
            "duration __cx_d;",
            # durationof({ <stmt>; })
            f"__cx_d = durationof({{ rx({ang}) q[{q0}]; }});",
            f"rx({ang}) q[{q0}];",
            "stretch __cx_s;",
            "box[__cx_d] {",
            "  cal {",
            f"    waveform __cx_w = gaussian({c32('0.25')}, __cx_d, 20dt);",
            f"    play({df0}, __cx_w);",
            "  }",
            f"  delay[__cx_s] q[{q1}];",
            "}",
            "barrier q;",
        ]
        params = {"q0": q0, "q1": q1, "ang": float(ang)}

    elif v == 2:
        vn = "align_two_gates_with_padding"
        desc = "Measure durationof two gates and pad the shorter path with delay inside a fixed box for alignment."
        core = [
            "duration __cx_d0;",
            "duration __cx_d1;",
            f"__cx_d0 = durationof({{ x q[{q0}]; }});",
            f"__cx_d1 = durationof({{ h q[{q1}]; }});",
            "box[BOX_WIN] {",
            f"  x q[{q0}];",
            f"  h q[{q1}];",
            f"  if (__cx_d0 < __cx_d1) {{ delay[__cx_d1 - __cx_d0] q[{q0}]; }}",
            f"  if (__cx_d1 < __cx_d0) {{ delay[__cx_d0 - __cx_d1] q[{q1}]; }}",
            "}",
        ]
        classical_points2 = classical_points + ["duration_compare", "duration_arith", "if_else"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(
            19, v, theme_name=name, variant_name=vn, description=desc,
            tags=tags, timing_points=timing_points, classical_points=classical_points2,
            pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas
        )

    elif v == 3:
        vn = "metronome_slots"
        desc = "Create <=7 metronome slots using durationof a primitive gate as the slot size; schedule alternating pulses."
        core = [
            "duration __cx_slot;",
            f"__cx_slot = durationof({{ z q[{q0}]; }});",
            "for int __cx_k in {0,1,2,3,4,5,6} {",
            "  box[__cx_slot] {",
            "    cal {",
            f"      waveform __cx_w = constant({c32('0.05')}, __cx_slot);",
            f"      play({df0}, __cx_w);",
            "    }",
            f"    delay[__cx_slot] q[{q1}];",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["for"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(
            19, v, theme_name=name, variant_name=vn, description=desc,
            tags=tags, timing_points=timing_points, classical_points=classical_points2,
            pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas
        )

    else:
        vn = "duration_guarded_phase"
        desc = "Use durationof to gate a phase update: only apply shift_phase if a gate duration exceeds a threshold."
        thr = rand_dt(rng, 10, 40)
        ph = rand_angle(rng, -0.4, 0.4)
        core = [
            "duration __cx_d;",
            f"__cx_d = durationof({{ rx({ang}) q[{q0}]; }});",
            f"rx({ang}) q[{q0}];",
            f"if (__cx_d > {thr}) {{ cal {{ shift_phase({df0}, {ph}); }} }}",
            f"delay[{rand_dt(rng, 8, 60)}] q[{q0}];",
        ]
        classical_points2 = classical_points + ["if_else", "duration_compare"]
        params = {"q0": q0, "thr": thr}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(
            19, v, theme_name=name, variant_name=vn, description=desc,
            tags=tags, timing_points=timing_points, classical_points=classical_points2,
            pulse_points=pulse_points + ["shift_phase"], required_meta=required_meta, params=params, core=core, meas=meas
        )

    meas = measure_all_block(meta, "__cc_out")
    return _mk(
        19, v, theme_name=name, variant_name=vn, description=desc,
        tags=tags, timing_points=timing_points, classical_points=classical_points,
        pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas
    )


# ==================== Theme 20: Box-contained Dynamic Decoupling ====================

def theme_20(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[20]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)

    d_pi = rand_dt(rng, 60, 220)
    s_pi = rand_dt(rng, 16, 90)

    tags = ["dd", "decoupling", "box", "stretch", "timing", "pulse", "classical"]
    timing_points = ["box", "stretch", "delay"]
    classical_points = ["for", "if_else"]
    pulse_points = ["play", "shift_phase_optional"]
    required_meta = ["pulse.frames.drive"]

    if v == 1:
        vn = "xy4_in_box"
        desc = "XY4-like decoupling sequence inside a fixed box using stretch to equalize gaps (<=4 pulses)."
        core = [
            "stretch __cx_g;",
            "box[BOX_WIN] {",
            "  cal {",
            f"    waveform __cx_x = gaussian({c32('0.85')}, {d_pi}, {s_pi});",
            f"    waveform __cx_y = gaussian({c32('0.85')}, {d_pi}, {s_pi});",
            f"    play({df}, __cx_x);",
            f"    delay[__cx_g] {df};",
            f"    shift_phase({df}, 1.570796); play({df}, __cx_y);",
            f"    delay[__cx_g] {df};",
            f"    shift_phase({df}, -1.570796); play({df}, __cx_x);",
            f"    delay[__cx_g] {df};",
            f"    shift_phase({df}, 1.570796); play({df}, __cx_y);",
            "  }",
            f"  delay[__cx_g] q[{q}];",
            "}",
        ]
        params = {"q": q}

    elif v == 2:
        vn = "cpmg_repeats"
        desc = "CPMG-like decoupling: <=7 pi pulses scheduled in a box; loop count fixed at 6."
        core = [
            "box[BOX_WIN] {",
            "  for int __cx_k in {0,1,2,3,4,5} {",
            "    cal {",
            f"      waveform __cx_p = gaussian({c32('0.80')}, {d_pi}, {s_pi});",
            f"      play({df}, __cx_p);",
            "    }",
            f"    delay[{rand_dt(rng, 6, 28)}] q[{q}];",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["for"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(20, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "dd_with_idle_guard"
        desc = "Insert DD only if a computed idle counter indicates long idle; otherwise keep a short delay."
        thr = rng.randint(2, 6)
        core = [
            "int[32] __cx_idle;",
            f"__cx_idle = {rng.randint(0,6)};",
            f"if (__cx_idle >= {thr}) {{",
            "  box[BOX_WIN] {",
            "    cal { waveform __cx_p = gaussian(" + c32('0.80') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_p); }",
            f"    delay[{rand_dt(rng, 10, 40)}] q[{q}];",
            "    cal { waveform __cx_p2 = gaussian(" + c32('0.80') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_p2); }",
            "  }",
            "} else {",
            f"  delay[{rand_dt(rng, 10, 60)}] q[{q}];",
            "}",
        ]
        classical_points2 = classical_points + ["int", "compare"]
        params = {"q": q, "thr": thr}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(20, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "dd_phase_alternation"
        desc = "Alternate X/Y phases in a <=7-step loop, using shift_phase to emulate axis switching."
        core = [
            "for int __cx_k in {0,1,2,3,4,5,6} {",
            "  cal {",
            f"    waveform __cx_p = gaussian({c32('0.75')}, {d_pi}, {s_pi});",
            "  }",
            "  if ((__cx_k & 1) == 0) {",
            f"    cal {{ shift_phase({df}, 0.0); play({df}, __cx_p); }}",
            "  } else {",
            f"    cal {{ shift_phase({df}, 1.570796); play({df}, __cx_p); shift_phase({df}, -1.570796); }}",
            "  }",
            f"  delay[{rand_dt(rng, 6, 26)}] q[{q}];",
            "}",
        ]
        classical_points2 = classical_points + ["bitwise", "for"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(20, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points + ["shift_phase"], required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(20, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 21: switch-routed Feedforward ====================

def theme_21(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[21]
    q0, q1 = pick_two(meta, rng)
    df0 = drive_frame(meta, q0)
    df1 = drive_frame(meta, q1)
    mf0 = meas_frame(meta, q0)
    af0 = acq_frame(meta, q0)
    mf1 = meas_frame(meta, q1)
    af1 = acq_frame(meta, q1)

    d_ro = rand_dt(rng, 160, 520)

    tags = ["switch", "routing", "feedforward", "measurement", "pulse", "timing", "classical"]
    timing_points = ["box", "delay", "barrier"]
    classical_points = ["switch", "bitwise", "int_cast"]
    pulse_points = ["capture", "play", "shift_phase_optional"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "two_bit_code_switch"
        desc = "Capture two bits, encode into int, and route to different corrective pulses via switch/case."
        core = [
            "bit __cx_m0;",
            "bit __cx_m1;",
            "int[32] __cx_code;",
            "box[RO_RING] {",
            "  cal {",
            f"    waveform __cx_ro = constant({c32('0.2')}, {d_ro});",
            f"    play({mf0}, __cx_ro); __cx_m0 = capture({af0}, __cx_ro);",
            f"    play({mf1}, __cx_ro); __cx_m1 = capture({af1}, __cx_ro);",
            "  }",
            "}",
            f"__cx_code = (int(__cx_m0) << 1) | int(__cx_m1);",
            "switch (__cx_code) {",
            "  case 0 { x q[" + str(q0) + "]; }",
            "  case 1 { z q[" + str(q0) + "]; }",
            "  case 2 { x q[" + str(q1) + "]; }",
            "  default { z q[" + str(q1) + "]; }",
            "}",
        ]
        params = {"q0": q0, "q1": q1}

    elif v == 2:
        vn = "switch_selects_phase_kick"
        desc = "Use switch to select a phase kick on a drive frame (virtual-Z) based on measurement code."
        ph = rand_angle(rng, -0.7, 0.7)
        core = [
            "bit __cx_m0; bit __cx_m1; int[32] __cx_code;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf0 + ", __cx_ro); __cx_m0 = capture(" + af0 + ", __cx_ro); play(" + mf1 + ", __cx_ro); __cx_m1 = capture(" + af1 + ", __cx_ro); } }",
            f"__cx_code = (int(__cx_m0) << 1) | int(__cx_m1);",
            "switch (__cx_code) {",
            f"  case 0 {{ cal {{ shift_phase({df0}, {ph}); }} }}",
            f"  case 1 {{ cal {{ shift_phase({df0}, -({ph})); }} }}",
            f"  case 2 {{ cal {{ shift_phase({df1}, {ph}); }} }}",
            f"  default {{ cal {{ shift_phase({df1}, -({ph})); }} }}",
            "}",
            "barrier q;",
        ]
        params = {"q0": q0, "q1": q1, "ph": float(ph)}

    elif v == 3:
        vn = "switch_with_timing_padding"
        desc = "Route to branches with different gate depths but equalize total time using a fixed box and padding delay."
        pad = rand_time(rng, 10, 60, choose_delay_unit(meta, rng))
        core = [
            "bit __cx_m0; bit __cx_m1; int[32] __cx_code;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf0 + ", __cx_ro); __cx_m0 = capture(" + af0 + ", __cx_ro); play(" + mf1 + ", __cx_ro); __cx_m1 = capture(" + af1 + ", __cx_ro); } }",
            f"__cx_code = (int(__cx_m0) << 1) | int(__cx_m1);",
            "box[BOX_WIN] {",
            "  switch (__cx_code) {",
            "    case 0 { x q[" + str(q0) + "]; }",
            "    case 1 { x q[" + str(q0) + "]; z q[" + str(q0) + "]; }",
            "    case 2 { x q[" + str(q1) + "]; }",
            "    default { z q[" + str(q1) + "]; x q[" + str(q1) + "]; }",
            "  }",
            f"  delay[{pad}] q[{q0}];",
            "}",
        ]
        classical_points2 = classical_points + ["box"]
        params = {"q0": q0, "q1": q1, "pad": pad}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(21, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points + ["box"], classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "switch_updates_syndrome"
        desc = "Use switch/case to update a syndrome bit array and then apply a corrective pulse on the selected qubit."
        core = [
            "bit __cx_m0; bit __cx_m1; int[32] __cx_code;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf0 + ", __cx_ro); __cx_m0 = capture(" + af0 + ", __cx_ro); play(" + mf1 + ", __cx_ro); __cx_m1 = capture(" + af1 + ", __cx_ro); } }",
            f"__cx_code = (int(__cx_m0) << 1) | int(__cx_m1);",
            "switch (__cx_code) {",
            f"  case 0 {{ syndrome_b[{q0}] = 0; syndrome_b[{q1}] = 0; }}",
            f"  case 1 {{ syndrome_b[{q0}] = 1; syndrome_b[{q1}] = 0; x q[{q0}]; }}",
            f"  case 2 {{ syndrome_b[{q0}] = 0; syndrome_b[{q1}] = 1; x q[{q1}]; }}",
            f"  default {{ syndrome_b[{q0}] = 1; syndrome_b[{q1}] = 1; z q[{q0}]; z q[{q1}]; }}",
            "}",
        ]
        params = {"q0": q0, "q1": q1}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(21, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 22: In-shot Micro-averaging ====================

def theme_22(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[22]
    q = pick_qubit(meta, rng)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_ro = rand_dt(rng, 120, 420)

    tags = ["micro_averaging", "readout", "accumulate", "pulse", "timing", "classical"]
    timing_points = ["box", "delay"]
    classical_points = ["for", "int_accum", "compare"]
    pulse_points = ["capture", "play"]
    required_meta = ["pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "majority_vote_5"
        desc = "Take <=5 short readouts in one shot, sum bits, and majority-vote into bg_m."
        core = [
            "int[32] __cx_sum;",
            "bit __cx_b;",
            "__cx_sum = 0;",
            "for int __cx_k in {0,1,2,3,4} {",
            "  box[RO_RING] {",
            "    cal {",
            f"      waveform __cx_ro = constant({c32('0.18')}, {d_ro});",
            f"      play({mf}, __cx_ro);",
            f"      __cx_b = capture({af}, __cx_ro);",
            "    }",
            "  }",
            "  __cx_sum = __cx_sum + int(__cx_b);",
            f"  delay[{rand_dt(rng, 4, 22)}] q[{q}];",
            "}",
            f"bg_m[{q}] = (__cx_sum >= 3);",
        ]
        params = {"q": q}

    elif v == 2:
        vn = "early_stop_threshold"
        desc = "Accumulate up to 6 readouts; if sum reaches threshold early, break to save time."
        thr = rng.randint(2, 4)
        core = [
            "int[32] __cx_sum; bit __cx_b;",
            "__cx_sum = 0;",
            "for int __cx_k in {0,1,2,3,4,5} {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.18') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_b = capture(" + af + ", __cx_ro); } }",
            "  __cx_sum = __cx_sum + int(__cx_b);",
            f"  if (__cx_sum >= {thr}) {{ break; }}",
            f"  delay[{rand_dt(rng, 4, 22)}] q[{q}];",
            "}",
            f"bg_m[{q}] = (__cx_sum >= {thr});",
        ]
        classical_points2 = classical_points + ["break"]
        params = {"q": q, "thr": thr}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(22, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "weighted_update"
        desc = "Update a float score using adaptive_update and convert to final bit; <=4 iterations."
        core = [
            "float[64] __cx_score; bit __cx_b;",
            "__cx_score = 0.0;",
            "for int __cx_k in {0,1,2,3} {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.18') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_b = capture(" + af + ", __cx_ro); } }",
            "  gain = adaptive_update(step, __cx_k, gain);",
            "  __cx_score = __cx_score + float(int(__cx_b)) * (0.5 + 0.01 * gain);",
            "}",
            f"bg_m[{q}] = (__cx_score > 2.5);",
        ]
        classical_points2 = classical_points + ["extern_call", "float"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(22, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "two_window_average"
        desc = "Split micro-averaging into two windows (3+3); compare both to guard against transient glitches."
        core = [
            "int[32] __cx_a; int[32] __cx_bsum; bit __cx_b;",
            "__cx_a = 0; __cx_bsum = 0;",
            "for int __cx_k in {0,1,2} {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.18') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_b = capture(" + af + ", __cx_ro); } }",
            "  __cx_a = __cx_a + int(__cx_b);",
            "}",
            "for int __cx_k in {0,1,2} {",
            "  box[RO_RING] { cal { waveform __cx_ro2 = constant(" + c32('0.18') + ", " + d_ro + "); play(" + mf + ", __cx_ro2); __cx_b = capture(" + af + ", __cx_ro2); } }",
            "  __cx_bsum = __cx_bsum + int(__cx_b);",
            "}",
            f"bg_m[{q}] = ((__cx_a + __cx_bsum) > 2) && (__cx_bsum >= 1);",
        ]
        classical_points2 = classical_points + ["two_loops", "and_or"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(22, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(22, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 23: Late-as-possible Conditional Operation ====================

def theme_23(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[23]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_pi = rand_dt(rng, 60, 220)
    s_pi = rand_dt(rng, 16, 90)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["late", "conditional", "box", "stretch", "pulse", "timing", "classical"]
    timing_points = ["box", "stretch", "delay"]
    classical_points = ["if_else", "bit"]
    pulse_points = ["play", "capture"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq", "timing.constants.BOX_WIN"]

    if v == 1:
        vn = "right_align_correction"
        desc = "Measure first, then in a fixed BOX_WIN right-align a corrective pulse using stretch (late as possible)."
        core = [
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "stretch __cx_pad;",
            "box[BOX_WIN] {",
            f"  delay[__cx_pad] q[{q}];",
            "  if (__cx_m) {",
            "    cal {",
            f"      waveform __cx_p = gaussian({c32('0.85')}, {d_pi}, {s_pi});",
            f"      play({df}, __cx_p);",
            "    }",
            "  }",
            "}",
        ]
        params = {"q": q}

    elif v == 2:
        vn = "late_virtual_z"
        desc = "Use a late virtual-Z (shift_phase) inside BOX_WIN; only applied if measurement indicates 1."
        ph = rand_angle(rng, -0.8, 0.8)
        core = [
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "stretch __cx_pad;",
            "box[BOX_WIN] {",
            f"  delay[__cx_pad] q[{q}];",
            f"  if (__cx_m) {{ cal {{ shift_phase({df}, {ph}); }} }}",
            "}",
        ]
        pulse_points2 = pulse_points + ["shift_phase"]
        params = {"q": q, "ph": float(ph)}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(23, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points,
                   pulse_points=pulse_points2, required_meta=required_meta, params=params, core=core, meas=meas)

    elif v == 3:
        vn = "late_branch_equalized"
        desc = "Two branches with different pulse bodies but both scheduled late in a fixed box; includes padding delay."
        core = [
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "stretch __cx_pad;",
            "box[BOX_WIN] {",
            f"  delay[__cx_pad] q[{q}];",
            "  if (__cx_m) {",
            "    cal { waveform __cx_p = gaussian(" + c32('0.85') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_p); }",
            "  } else {",
            "    cal { waveform __cx_p2 = gaussian(" + c32('0.60') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_p2); }",
            "  }",
            "}",
        ]
        params = {"q": q}

    else:
        vn = "late_updates_syndrome"
        desc = "Late conditional pulse also updates syndrome_b and a try counter, mimicking controller bookkeeping."
        core = [
            "bit __cx_m;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "tries = tries + 1;",
            "stretch __cx_pad;",
            "box[BOX_WIN] {",
            f"  delay[__cx_pad] q[{q}];",
            "  if (__cx_m) {",
            f"    syndrome_b[{q}] = 1;",
            "    cal { waveform __cx_p = gaussian(" + c32('0.85') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_p); }",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["counter"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(23, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(23, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 24: Timeout Active Reset with adaptive_update ====================

def theme_24(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[24]
    q = pick_qubit(meta, rng)
    df = drive_frame(meta, q)
    mf = meas_frame(meta, q)
    af = acq_frame(meta, q)

    d_pi = rand_dt(rng, 80, 240)
    s_pi = rand_dt(rng, 16, 90)
    d_ro = rand_dt(rng, 160, 520)

    tags = ["timeout", "active_reset", "feedback", "adaptive_update", "pulse", "timing", "classical"]
    timing_points = ["delay", "box", "stretch"]
    classical_points = ["while", "counter", "extern_call", "if_else"]
    pulse_points = ["capture", "play", "scale"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "bounded_tries_timeout"
        desc = "Try active reset up to 6 times; each iteration updates gain via adaptive_update; stop early on success."
        core = [
            "bit __cx_m;",
            "int[32] __cx_left;",
            "__cx_left = 6;",
            "while (__cx_left > 0) {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "  if (!__cx_m) { break; }",
            "  gain = adaptive_update(step, __cx_left, gain);",
            "  cal { waveform __cx_x = gaussian(scale(" + c32('0.85') + ", gain), " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_x); }",
            "  __cx_left = __cx_left - 1;",
            f"  delay[{rand_dt(rng, 6, 40)}] q[{q}];",
            "}",
            f"bg_m[{q}] = __cx_m;",
        ]
        params = {"q": q}

    elif v == 2:
        vn = "timeout_budget_counter"
        desc = "Use a simple budget counter (<=7) to emulate a timeout window; apply corrective pulses while budget remains."
        budget = rng.randint(4, 7)
        core = [
            "bit __cx_m;",
            "int[32] __cx_budget;",
            f"__cx_budget = {budget};",
            "while (__cx_budget > 0) {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "  if (!__cx_m) { break; }",
            "  cal { waveform __cx_x = gaussian(" + c32('0.80') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_x); }",
            "  __cx_budget = __cx_budget - 1;",
            "}",
            f"bg_m[{q}] = __cx_m;",
        ]
        params = {"q": q, "budget": budget}

    elif v == 3:
        vn = "timeout_with_stretch_padding"
        desc = "Active reset attempts placed into a fixed box with stretch padding between attempts; <=5 attempts."
        core = [
            "bit __cx_m;",
            "stretch __cx_gap;",
            "for int __cx_k in {0,1,2,3,4} {",
            "  box[BOX_WIN] {",
            "    box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "    if (!__cx_m) { break; }",
            "    cal { waveform __cx_x = gaussian(" + c32('0.80') + ", " + d_pi + ", " + s_pi + "); play(" + df + ", __cx_x); }",
            f"    delay[__cx_gap] q[{q}];",
            "  }",
            "}",
        ]
        classical_points2 = classical_points + ["for", "break"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(24, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points + ["for"], classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "timeout_updates_syndrome"
        desc = "If repeated failures happen, set syndrome_b and record tries; mimics controller-level error escalation."
        core = [
            "bit __cx_m;",
            "int[32] __cx_left;",
            "__cx_left = 5;",
            "while (__cx_left > 0) {",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mf + ", __cx_ro); __cx_m = capture(" + af + ", __cx_ro); } }",
            "  if (!__cx_m) { break; }",
            "  tries = tries + 1;",
            "  __cx_left = __cx_left - 1;",
            "}",
            "if (__cx_m) {",
            f"  syndrome_b[{q}] = 1;",
            "}",
        ]
        classical_points2 = classical_points + ["syndrome_update"]
        params = {"q": q}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(24, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(24, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)


# ==================== Theme 25: Syndrome + Feedforward + Idle Scheduling ====================

def theme_25(meta: Dict[str, Any], rng: random.Random, v: int) -> ComplexTaskInstance:
    name = THEME_NAMES[25]
    uq = used_qubits(meta)
    allq = list(range(n_qubits(meta)))
    cand = uq if len(uq) >= 2 else allq

    if len(cand) >= 3:
        d0, d1, anc = rng.sample(cand, 3)
    elif len(cand) == 2:
        d0, anc = rng.sample(cand, 2)  
        d1 = d0
    else:
        d0 = d1 = anc = cand[0]



    df0 = drive_frame(meta, d0)
    df1 = drive_frame(meta, d1)
    mfA = meas_frame(meta, anc)
    afA = acq_frame(meta, anc)

    d_ro = rand_dt(rng, 160, 520)
    d_pi = rand_dt(rng, 60, 220)
    s_pi = rand_dt(rng, 16, 90)

    tags = ["syndrome", "feedforward", "idle", "scheduling", "pulse", "timing", "classical"]
    timing_points = ["barrier", "delay", "box", "stretch"]
    classical_points = ["if_else", "bit_to_int", "syndrome_update"]
    pulse_points = ["capture", "play"]
    required_meta = ["pulse.frames.drive", "pulse.frames.meas", "pulse.frames.acq"]

    if v == 1:
        vn = "parity_check_like"
        desc = "Toy parity-check: entangle ancilla, measure syndrome, feedforward X on a data qubit; schedule idle padding."
        core = [
            f"h q[{anc}];",
            f"cx q[{anc}], q[{d0}];",
            f"cx q[{anc}], q[{d1}];",
            "barrier q;",
            "bit __cx_s;",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mfA + ", __cx_ro); __cx_s = capture(" + afA + ", __cx_ro); } }",
            f"syndrome_b[{anc}] = __cx_s;",
            "if (__cx_s) {",
            f"  x q[{d0}];",
            "}",
            f"delay[{rand_dt(rng, 10, 60)}] q[{d1}];",
        ]
        params = {"d0": d0, "d1": d1, "anc": anc}

    elif v == 2:
        vn = "idle_dd_during_syndrome"
        desc = "While ancilla is measured, apply a short DD pulse on idle data frame inside a box to mimic idle scheduling."
        core = [
            "bit __cx_s;",
            "stretch __cx_gap;",
            "box[BOX_WIN] {",
            f"  cx q[{anc}], q[{d0}];",
            f"  delay[__cx_gap] q[{d1}];",
            "  cal {",
            f"    waveform __cx_p = gaussian({c32('0.70')}, {d_pi}, {s_pi});",
            f"    play({df1}, __cx_p);",
            "  }",
            "}",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mfA + ", __cx_ro); __cx_s = capture(" + afA + ", __cx_ro); } }",
            "if (__cx_s) { z q[" + str(d0) + "]; }",
        ]
        params = {"d0": d0, "d1": d1, "anc": anc}

    elif v == 3:
        vn = "syndrome_code_routing"
        desc = "Compute a small syndrome code and route corrections; keeps operations shallow and aligned with delays."
        core = [
            "bit __cx_s; int[32] __cx_code;",
            f"cx q[{d0}], q[{anc}];",
            f"cx q[{d1}], q[{anc}];",
            "box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mfA + ", __cx_ro); __cx_s = capture(" + afA + ", __cx_ro); } }",
            "__cx_code = int(__cx_s);",
            "switch (__cx_code) {",
            "  case 0 { delay[BG_IDLE] q[" + str(d0) + "]; }",
            "  default { x q[" + str(d0) + "]; }",
            "}",
            f"syndrome_b[{anc}] = __cx_s;",
        ]
        classical_points2 = classical_points + ["switch"]
        params = {"d0": d0, "d1": d1, "anc": anc}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(25, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    else:
        vn = "bounded_repetition_cycle"
        desc = "A bounded (<=3) syndrome cycle loop with simple feedforward; mimics a short QEC repetition block."
        core = [
            "bit __cx_s;",
            "for int __cx_k in {0,1,2} {",
            f"  cx q[{d0}], q[{anc}];",
            f"  cx q[{d1}], q[{anc}];",
            "  box[RO_RING] { cal { waveform __cx_ro = constant(" + c32('0.2') + ", " + d_ro + "); play(" + mfA + ", __cx_ro); __cx_s = capture(" + afA + ", __cx_ro); } }",
            "  if (__cx_s) { x q[" + str(d0) + "]; }",
            f"  delay[{rand_dt(rng, 6, 30)}] q[{d1}];",
            "}",
        ]
        classical_points2 = classical_points + ["for"]
        params = {"d0": d0, "d1": d1, "anc": anc}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(25, v, theme_name=name, variant_name=vn, description=desc,
                   tags=tags, timing_points=timing_points, classical_points=classical_points2,
                   pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    return _mk(25, v, theme_name=name, variant_name=vn, description=desc,
               tags=tags, timing_points=timing_points, classical_points=classical_points,
               pulse_points=pulse_points, required_meta=required_meta, params=params, core=core, meas=meas)
# -------------------- Registry (first 5) --------------------

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


def generate_core_task(meta: Dict[str, Any], *, theme_id: int, variant_id: int, seed: Optional[int] = None) -> ComplexTaskInstance:
    if theme_id not in THEMES:
        raise KeyError(f"Unknown theme_id={theme_id} (implemented: {sorted(THEMES)})")
    if variant_id not in (1, 2, 3, 4):
        raise ValueError("variant_id must be 1..4")
    rng = random.Random(seed)
    return THEMES[theme_id](meta, rng, variant_id)


def generate_core_task_from_meta_path(meta_path: str, *, theme_id: int, variant_id: int, seed: Optional[int] = None) -> ComplexTaskInstance:
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return generate_core_task(meta, theme_id=theme_id, variant_id=variant_id, seed=seed)



def _replace_between_markers(text: str, start_marker: str, end_marker: str, new_lines: List[str]) -> str:
    if start_marker not in text or end_marker not in text:
        raise ValueError("Markers not found in background")
    start = text.index(start_marker)
    end = text.index(end_marker)

    # find line boundaries
    start_line_end = text.find("\n", start)
    if start_line_end < 0:
        raise ValueError("start marker line not terminated")
    end_line_start = text.rfind("\n", 0, end)
    if end_line_start < 0:
        end_line_start = 0
    else:
        end_line_start += 1

    before = text[:start_line_end + 1]
    after = text[end_line_start:]
    middle = "\n".join(new_lines) + ("\n" if new_lines else "")
    return before + middle + after


def assemble_full_task(background_qasm: str, inst: ComplexTaskInstance) -> str:

    text = background_qasm
    # core
    core_lines = inst.core_lines
    text = _replace_between_markers(text, CORE_START, CORE_END, core_lines)
    # measurement
    meas_lines = inst.meas_lines
    text = _replace_between_markers(text, MEAS_START, MEAS_END, meas_lines)
    return text


def main(task_num: int = 200, base_seed: int = 20260108) -> None:

    import os
    import glob
    import random

    background_dir = "complex_background_qasm"
    out_dir = "complex_train"
    os.makedirs(out_dir, exist_ok=True)

    variants = [2, 3, 4]

    bg_qasms = sorted(glob.glob(os.path.join(background_dir, "*.qasm")))
    if not bg_qasms:
        raise FileNotFoundError(f"No .qasm found under: {background_dir}")

    def find_meta_for_bg(bg_qasm_path: str) -> str:

        base = bg_qasm_path[:-5]  
        cand1 = base + ".meta.json"
        cand2 = bg_qasm_path + ".meta.json"
        if os.path.exists(cand1):
            return cand1
        if os.path.exists(cand2):
            return cand2
        raise FileNotFoundError(f"Meta json not found for background: {bg_qasm_path}")

    rng = random.Random(base_seed)

    for t in range(task_num):
        theme_id = (t % 25) + 1
        variant_id = variants[t % len(variants)]

        bg_path = rng.choice(bg_qasms)          
        meta_path = find_meta_for_bg(bg_path)

        with open(bg_path, "r", encoding="utf-8") as f:
            bg_text = f.read()

        inst_seed = rng.randrange(1_000_000_000)

        inst = generate_core_task_from_meta_path(
            meta_path,
            theme_id=theme_id,
            variant_id=variant_id,
            seed=inst_seed,
        )

        full_qasm = assemble_full_task(bg_text, inst)

        out_name = f"complex_task_{t:05d}_th{theme_id:02d}_v{variant_id}.qasm"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_qasm)

    print(f"Done. Wrote {task_num} train tasks into: {out_dir}")


if __name__ == "__main__":
    task_num = 1000 
    main(task_num=task_num)
