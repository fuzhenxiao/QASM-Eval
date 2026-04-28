# timing_core_generators.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import json
import random
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Callable, Optional

# -------------------- Markers --------------------

CORE_START = "// === CORE_TASK_START ==="
CORE_END = "// === CORE_TASK_END ==="
MEAS_START = "// === MEASUREMENT_START ==="
MEAS_END = "// === MEASUREMENT_END ==="

# -------------------- Utilities: meta loading --------------------

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
    uq = used_qubits(meta)
    return rng.choice(uq)

def pick_two_qubits(meta: Dict[str, Any], rng: random.Random) -> Tuple[int, int]:
    uq = used_qubits(meta)
    if len(uq) < 2:
        allq = list(range(n_qubits(meta)))
        if len(allq) < 2:
            allq = [0, 0]
        return allq[0], allq[1]
    a, b = rng.sample(uq, 2)
    return a, b

def pick_three_qubits(meta: Dict[str, Any], rng: random.Random) -> Tuple[int, int, int]:
    uq = used_qubits(meta)
    if len(uq) >= 3:
        a, b, c = rng.sample(uq, 3)
        return a, b, c
    allq = list(range(n_qubits(meta)))
    while len(allq) < 3:
        allq.append(allq[-1] if allq else 0)
    return allq[0], allq[1], allq[2]

def choose_unit(meta: Dict[str, Any], rng: random.Random, *, prefer_dt: bool = False) -> str:
    units = meta.get("delay_units", ["ns"])
    units = [u for u in units if isinstance(u, str) and u]
    if not units:
        units = ["ns"]
    if prefer_dt and "dt" in units:
        return "dt"
    phys = [u for u in units if u in ("ns", "us", "ms", "s")]
    if phys:
        return rng.choice(phys)
    return rng.choice(units)

def rand_time(rng: random.Random, lo: int, hi: int, unit: str) -> str:
    v = rng.randint(lo, hi)
    return f"{v}{unit}"

def even_rand(rng: random.Random, lo: int, hi: int) -> int:
    lo2 = lo + (lo % 2)
    if lo2 > hi:
        return lo
    k = rng.randint(0, (hi - lo2) // 2)
    return lo2 + 2 * k
def pick_two_distinct_qubits(meta: dict, rng) -> tuple[int, int]:
    uq = used_qubits(meta)
    if len(uq) < 2:
        allq = list(range(n_qubits(meta)))
        if len(allq) < 2:
            allq = [0, 0]
        return allq[0], allq[1]
    a, b = rng.sample(uq, 2)
    return a, b

# -------------------- Measurement helpers --------------------

def measure_all_block(meta: Dict[str, Any], creg: str = "c") -> List[str]:
    nq = n_qubits(meta)
    lines = [f"bit[{nq}] {creg};"]
    for i in range(nq):
        lines.append(f"{creg}[{i}] = measure q[{i}];")
    return lines

def measure_subset_block(meta: Dict[str, Any], subset: List[int], creg: str = "c") -> List[str]:
    nq = n_qubits(meta)
    lines = [f"bit[{nq}] {creg};"]
    for i in subset:
        lines.append(f"{creg}[{i}] = measure q[{i}];")
    return lines

# -------------------- Core task instance --------------------

@dataclass
class CoreTaskInstance:
    theme_id: int
    variant_id: int

    theme_name: str
    variant_name: str
    description: str
    tags: List[str]
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
            "params": dict(self.params),
        }

def _mk(theme_id: int, v: int, *,
        theme_name: str,
        variant_name: str,
        description: str,
        tags: List[str],
        params: Dict[str, Any],
        core: List[str],
        meas: List[str]) -> CoreTaskInstance:

    commented_core = [f"// {theme_name} | {variant_name}: {description}"] + core
    return CoreTaskInstance(
        theme_id=theme_id,
        variant_id=v,
        theme_name=theme_name,
        variant_name=variant_name,
        description=description,
        tags=tags,
        params=params,
        core_lines=commented_core,
        meas_lines=meas
    )

# -------------------- Theme registry --------------------

ThemeFn = Callable[[Dict[str, Any], random.Random, int], CoreTaskInstance]

THEME_NAMES: Dict[int, str] = {
    1:  "basic_delay_units",
    2:  "dt_delay",
    3:  "duration_arithmetic",
    4:  "mixed_units_duration",
    5:  "left_alignment_stretch",
    6:  "right_alignment_stretch",
    7:  "center_alignment_stretch",
    8:  "proportional_placement",
    9:  "durationof_single_gate",
    10: "durationof_subcircuit",
    11: "dynamic_padding_safe",
    12: "basic_box_boundary",
    13: "timed_box_known_duration",
    14: "box_with_stretch_fill",
    15: "barrier_ordering",
    16: "hahn_echo_midpoint",
    17: "center_align_halfdiff_known",
    18: "multi_qubit_delay_semantics",
    19: "nop_sync_in_box",
    20: "duration_update",
    21: "explicit_delay_as_structure",
    22: "delay_zero_ordering",
    23: "nested_box",
    24: "multi_stretch_solve_system",
    25: "durationof_on_box_compound",
}

# ==================== Theme implementations (25 themes × 4 variants) ====================

def theme_01(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[1]
    unit = choose_unit(meta, rng, prefer_dt=False)
    q0, q1 = pick_two_distinct_qubits(meta, rng)
    d1 = rand_time(rng, 5, 80, unit)
    d2 = rand_time(rng, 5, 80, unit)

    tags = ["delay", "units"]

    if v == 1:
        variant_name = "single_delay_then_rx"
        desc = "Apply a single delay on one qubit, then an RX rotation."
        core = [f"delay[{d1}] q[{q0}];", f"rx(1.5708) q[{q0}];"]
        meas = measure_all_block(meta)
        params = {"unit": unit, "q": q0, "d": d1}
    elif v == 2:
        variant_name = "h_delay_rz"
        desc = "Prepare with H, delay, then apply RZ."
        core = [f"h q[{q0}];", f"delay[{d1}] q[{q0}];", f"rz(0.785398) q[{q0}];"]
        meas = measure_subset_block(meta, [q0])
        params = {"unit": unit, "q": q0, "d": d1}
    elif v == 3:
        variant_name = "two_qubits_independent_delays_then_2q"
        desc = "Delay two qubits independently, then apply a 2-qubit gate."
        if n_qubits(meta) >= 2:
            core = [f"delay[{d1}] q[{q0}];", f"delay[{d2}] q[{q1}];", f"cx q[{q0}], q[{q1}];"]
        else:
            core = [f"delay[{d1}] q[{q0}];", f"x q[{q0}];"]
        meas = measure_all_block(meta)
        params = {"unit": unit, "q0": q0, "q1": q1, "d1": d1, "d2": d2}
    else:
        variant_name = "interleaved_delays_with_involutions"
        desc = "Interleave delays and gates on the same qubit."
        core = [f"h q[{q0}];", f"delay[{d1}] q[{q0}];", f"x q[{q0}];", f"delay[{d2}] q[{q0}];", f"h q[{q0}];"]
        meas = measure_subset_block(meta, [q0])
        params = {"unit": unit, "q": q0, "d1": d1, "d2": d2}

    return _mk(1, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_02(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[2]
    tags = ["delay", "dt"]

    q0, q1 = pick_two_distinct_qubits(meta, rng)
    d1 = rand_time(rng, 5, 200, "dt")
    d2 = rand_time(rng, 5, 200, "dt")

    if v == 1:
        variant_name = "dt_delay_then_x"
        desc = "Use a dt-based delay on one qubit, then apply X."
        core = [f"delay[{d1}] q[{q0}];", f"x q[{q0}];"]
        meas = measure_subset_block(meta, [q0])
        params = {"q": q0, "d": d1}
    elif v == 2:
        variant_name = "two_dt_delays_then_h"
        desc = "Apply two dt delays back-to-back, then apply H."
        core = [f"h q[{q0}];", f"delay[{d1}] q[{q0}];", f"delay[{d2}] q[{q0}];", f"h q[{q0}];"]
        meas = measure_subset_block(meta, [q0])
        params = {"q": q0, "d1": d1, "d2": d2}
    elif v == 3:
        variant_name = "dt_delay_on_all_qubits"
        desc = "Apply a dt delay on all qubits, then a single-qubit gate."
        core = [f"delay[{d1}] q;", f"rz(0.523599) q[{q0}];"]
        meas = measure_all_block(meta)
        params = {"d_all": d1, "q": q0}
    else:
        variant_name = "dt_delay_then_2q_gate"
        desc = "Delay in dt on one qubit, then apply a 2-qubit gate (if available)."
        if n_qubits(meta) >= 2:
            core = [f"h q[{q0}];", f"delay[{d1}] q[{q0}];", f"cx q[{q0}], q[{q1}];"]
        else:
            core = [f"delay[{d1}] q[{q0}];", f"z q[{q0}];"]
        meas = measure_all_block(meta)
        params = {"q0": q0, "q1": q1, "d": d1}

    return _mk(2, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_03(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[3]
    tags = ["delay", "duration_arithmetic"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    a = rng.randint(5, 40)
    b = rng.randint(5, 3*a - 1) if 3*a > 5 else 5
    c = rng.randint(2, 6)

    if v == 1:
        variant_name = "sum_of_durations"
        desc = "Delay by a+b with the same unit, then apply X."
        core = [f"delay[{a}{unit} + {b}{unit}] q[{q0}];", f"x q[{q0}];"]
        params = {"expr": f"{a}{unit}+{b}{unit}", "q": q0}
    elif v == 2:
        variant_name = "scaled_duration"
        desc = "Delay by c*a, then apply H."
        core = [f"delay[{c}*{a}{unit}] q[{q0}];", f"h q[{q0}];"]
        params = {"expr": f"{c}*{a}{unit}", "q": q0}
    elif v == 3:
        variant_name = "affine_combo"
        desc = "Delay by a+2*b, then apply RZ."
        core = [f"delay[{a}{unit} + 2*{b}{unit}] q[{q0}];", f"rz(1.0472) q[{q0}];"]
        params = {"expr": f"{a}{unit}+2*{b}{unit}", "q": q0}
    else:
        variant_name = "subtraction_expression"
        desc = "Delay by (3*a)-b, then apply Y."
        core = [f"delay[(3*{a}{unit}) - {b}{unit}] q[{q0}];", f"y q[{q0}];"]
        params = {"expr": f"(3*{a}{unit})-{b}{unit}", "q": q0}

    meas = measure_subset_block(meta, [q0])
    return _mk(3, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_04(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[4]
    tags = ["delay", "mixed_units"]

    q0 = pick_qubit(meta, rng)
    u1 = rng.choice(["ns", "us", "ms"])
    u2 = rng.choice(["ns", "us", "ms"])
    a = rng.randint(5, 80)
    b = rng.randint(1, 20)

    if v == 1:
        variant_name = "mixed_units_add"
        desc = "Delay by a*u1 + b*u2, then apply X."
        core = [f"delay[{a}{u1} + {b}{u2}] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "expr": f"{a}{u1}+{b}{u2}"}
    elif v == 2:
        variant_name = "mixed_units_sandwich_h"
        desc = "H, then mixed-units delay, then H."
        core = [f"h q[{q0}];", f"delay[{b}{u2} + {a}{u1}] q[{q0}];", f"h q[{q0}];"]
        params = {"q": q0, "expr": f"{b}{u2}+{a}{u1}"}
    elif v == 3:
        variant_name = "sequential_mixed_units"
        desc = "Apply two delays in different units sequentially, then RZ."
        core = [f"delay[{a}{u1}] q[{q0}];", f"delay[{b}{u2}] q[{q0}];", f"rz(0.392699) q[{q0}];"]
        params = {"q": q0, "d1": f"{a}{u1}", "d2": f"{b}{u2}"}
    else:
        variant_name = "mixed_units_affine"
        desc = "Delay by a*u1 + 2*b*u2, then RX."
        core = [f"delay[{a}{u1} + 2*{b}{u2}] q[{q0}];", f"rx(0.785398) q[{q0}];"]
        params = {"q": q0, "expr": f"{a}{u1}+2*{b}{u2}"}

    meas = measure_subset_block(meta, [q0])
    return _mk(4, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_05(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[5]
    tags = ["box", "stretch", "alignment_left"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T = rand_time(rng, 80, 240, unit)

    if v == 1:
        variant_name = "left_align_x_then_stretch"
        desc = "Left-align: apply X early, fill remaining time with stretch delay."
        core = ["stretch g;", f"box[{T}] {{", f"  x q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}
    elif v == 2:
        variant_name = "left_align_h_rz_then_stretch"
        desc = "Left-align: do H and RZ, then fill the rest with stretch."
        core = ["stretch g;", f"box[{T}] {{", f"  h q[{q0}];", f"  rz(1.0472) q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}
    elif v == 3:
        variant_name = "left_align_2q_then_parallel_stretch"
        desc = "Left-align: do a 2-qubit gate, then stretch both qubits to the box end."
        if n_qubits(meta) >= 2:
            q0, q1 = pick_two_distinct_qubits(meta, rng)
            core = ["stretch g;", f"box[{T}] {{", f"  cx q[{q0}], q[{q1}];", f"  delay[g] q[{q0}];", f"  delay[g] q[{q1}];", f"}}"]
            params = {"q0": q0, "q1": q1, "T": T, "unit": unit}
        else:
            core = ["stretch g;", f"box[{T}] {{", f"  x q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
            params = {"q": q0, "T": T, "unit": unit}
        meas = measure_all_block(meta)
    else:
        variant_name = "left_align_rx_then_double_stretch"
        desc = "Left-align: RX then use two stretch delays as remaining fill."
        core = ["stretch g;", f"box[{T}] {{", f"  rx(1.5708) q[{q0}];", f"  delay[g] q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}

    return _mk(5, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_06(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[6]
    tags = ["box", "stretch", "alignment_right"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T = rand_time(rng, 80, 240, unit)

    if v == 1:
        variant_name = "right_align_stretch_then_x"
        desc = "Right-align: stretch first, then X at the end of the box."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  x q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}
    elif v == 2:
        variant_name = "right_align_stretch_then_h_rz"
        desc = "Right-align: stretch, then H and RZ near the end."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  h q[{q0}];", f"  rz(0.785398) q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}
    elif v == 3:
        variant_name = "right_align_parallel_stretch_then_2q"
        desc = "Right-align: stretch both qubits, then apply a 2-qubit gate at the end."
        if n_qubits(meta) >= 2:
            q1 = pick_qubit(meta, rng)
            core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  delay[g] q[{q1}];", f"  cz q[{q0}], q[{q1}];", f"}}"]
            params = {"q0": q0, "q1": q1, "T": T, "unit": unit}
        else:
            core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  z q[{q0}];", f"}}"]
            params = {"q": q0, "T": T, "unit": unit}
        meas = measure_all_block(meta)
    else:
        variant_name = "right_align_stretch_then_rx_x"
        desc = "Right-align: stretch, then apply RX and X at the end."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  rx(0.392699) q[{q0}];", f"  x q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}

    return _mk(6, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_07(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[7]
    tags = ["box", "stretch", "alignment_center"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T = rand_time(rng, 120, 300, unit)
    gate = rng.choice(["x", "h", "y", "z"])

    if v == 1:
        variant_name = "center_align_single_gate"
        desc = "Center-align a single 1-qubit gate by symmetric stretch delays."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  {gate} q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "gate": gate, "unit": unit}
    elif v == 2:
        variant_name = "center_align_rx"
        desc = "Center-align an RX rotation by symmetric stretch delays."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  rx(1.5708) q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "center_align_2q_gate"
        desc = "Center-align a 2-qubit gate by stretching both qubits symmetrically."
        q0, q1 = pick_two_distinct_qubits(meta, rng)
        core = ["stretch g;", f"box[{T}] {{",
                f"  delay[g] q[{q0}];", f"  delay[g] q[{q1}];",
                f"  cx q[{q0}], q[{q1}];",
                f"  delay[g] q[{q0}];", f"  delay[g] q[{q1}];",
                f"}}"]
        meas = measure_all_block(meta)
        params = {"q0": q0, "q1": q1, "T": T, "unit": unit}
    else:
        variant_name = "center_align_rz"
        desc = "Center-align an RZ gate by symmetric stretch delays."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  rz(1.0472) q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        meas = measure_all_block(meta)
        params = {"q": q0, "T": T, "unit": unit}

    return _mk(7, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_08(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[8]
    tags = ["box", "stretch", "proportional"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T = rand_time(rng, 150, 360, unit)

    if v == 1:
        variant_name = "ratio_1_to_2"
        desc = "Place a gate after 1 part stretch, then leave 2 parts stretch."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  x q[{q0}];", f"  delay[2*g] q[{q0}];", f"}}"]
        params = {"ratio": "1:2", "q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])
    elif v == 2:
        variant_name = "ratio_2_to_1"
        desc = "Place a gate after 2 parts stretch, then leave 1 part stretch."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[2*g] q[{q0}];", f"  h q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        params = {"ratio": "2:1", "q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])
    elif v == 3:
        variant_name = "two_stretches_two_segments"
        desc = "Use two independent stretch variables to create a two-segment placement."
        core = ["stretch a;", "stretch b;", f"box[{T}] {{",
                f"  delay[a] q[{q0}];", f"  rz(0.785398) q[{q0}];",
                f"  delay[b] q[{q0}];", f"  x q[{q0}];",
                f"}}"]
        params = {"two_stretch": True, "q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])
    else:
        variant_name = "fixed_plus_stretch_centering"
        desc = "Use a fixed delay plus symmetric stretch delays around a gate."
        fixed = rand_time(rng, 10, 60, unit)
        core = ["stretch g;", f"box[{T}] {{",
                f"  delay[{fixed}] q[{q0}];", f"  delay[g] q[{q0}];",
                f"  y q[{q0}];",
                f"  delay[g] q[{q0}];",
                f"}}"]
        params = {"fixed": fixed, "q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])

    return _mk(8, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_09(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[9]
    tags = ["durationof", "delay"]

    q0, q1 = pick_two_distinct_qubits(meta, rng)

    if v == 1:
        variant_name = "durationof_x"
        desc = "Delay by durationof({x}), then apply H."
        core = [f"delay[durationof({{ x q[{q0}]; }})] q[{q0}];", f"h q[{q0}];"]
        params = {"q": q0, "ref": "x"}
        meas = measure_all_block(meta)
    elif v == 2:
        variant_name = "durationof_rz"
        desc = "Delay by durationof({rz}), then apply X."
        core = [f"delay[durationof({{ rz(1.0472) q[{q0}]; }})] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "ref": "rz"}
        meas = measure_all_block(meta)
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "durationof_cx"
        desc = "Delay by durationof({cx}) on one qubit, then apply CX."
        core = [f"delay[durationof({{ cx q[{q0}], q[{q1}]; }})] q[{q0}];", f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "ref": "cx"}
        meas = measure_all_block(meta)
    else:
        variant_name = "durationof_h"
        desc = "Delay by durationof({h}), then apply Z."
        core = [f"delay[durationof({{ h q[{q0}]; }})] q[{q0}];", f"z q[{q0}];"]
        params = {"q": q0, "ref": "h"}
        meas = measure_all_block(meta)

    return _mk(9, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_10(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[10]
    tags = ["durationof", "subcircuit", "delay"]

    q0, q1 = pick_two_qubits(meta, rng)

    if v == 1:
        variant_name = "durationof_two_1q_ops"
        desc = "Delay by durationof({H;X}), then apply RZ."
        core = [f"delay[durationof({{ h q[{q0}]; x q[{q0}]; }})] q[{q0}];", f"rz(0.392699) q[{q0}];"]
        params = {"q": q0, "len": 2}
        meas = measure_subset_block(meta, [q0])
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "durationof_h_then_cx"
        desc = "Delay by durationof({H;CX}), then apply X on target."
        core = [f"delay[durationof({{ h q[{q0}]; cx q[{q0}], q[{q1}]; }})] q[{q1}];", f"x q[{q1}];"]
        params = {"q0": q0, "q1": q1, "len": 2}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "durationof_three_rotations"
        desc = "Delay by durationof({RZ;RY;RX}), then apply H."
        core = [f"delay[durationof({{ rz(1.0472) q[{q0}]; ry(0.785398) q[{q0}]; rx(0.392699) q[{q0}]; }})] q[{q0}];",
                f"h q[{q0}];"]
        params = {"q": q0, "len": 3}
        meas = measure_subset_block(meta, [q0])
    else:
        variant_name = "durationof_xyz_chain"
        desc = "Delay by durationof({X;Y;Z}), then apply X."
        core = [f"delay[durationof({{ x q[{q0}]; y q[{q0}]; z q[{q0}]; }})] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "len": 3}
        meas = measure_subset_block(meta, [q0])

    return _mk(10, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_11(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[11]
    tags = ["durationof", "padding", "safe_nonnegative"]

    q0 = pick_qubit(meta, rng)
    unit = choose_unit(meta, rng, prefer_dt=False)
    pad = rand_time(rng, 5, 40, unit)

    if v == 1:
        variant_name = "padding_from_full_minus_prefix_len2"
        desc = "Safe padding: durationof(full)-durationof(prefix)+pad (2 vs 1 ops)."
        prefix = f"{{ h q[{q0}]; }}"
        full = f"{{ h q[{q0}]; x q[{q0}]; }}"
        core = [f"delay[durationof({full}) - durationof({prefix}) + {pad}] q[{q0}];", f"z q[{q0}];"]
        params = {"q": q0, "pad": pad, "full_len": 2, "prefix_len": 1}
        meas = measure_subset_block(meta, [q0])
    elif v == 2:
        variant_name = "padding_from_full_minus_prefix_len3"
        desc = "Safe padding: durationof(full)-durationof(prefix)+pad (3 vs 2 ops)."
        prefix = f"{{ x q[{q0}]; y q[{q0}]; }}"
        full = f"{{ x q[{q0}]; y q[{q0}]; z q[{q0}]; }}"
        core = [f"delay[durationof({full}) - durationof({prefix}) + {pad}] q[{q0}];", f"h q[{q0}];"]
        params = {"q": q0, "pad": pad, "full_len": 3, "prefix_len": 2}
        meas = measure_subset_block(meta, [q0])
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "padding_with_2q_in_full"
        desc = "Safe padding derived from a block that includes a 2-qubit gate."
        q0, q1 = pick_two_distinct_qubits(meta, rng)
        prefix = f"{{ h q[{q0}]; }}"
        full = f"{{ h q[{q0}]; cx q[{q0}], q[{q1}]; }}"
        core = [f"delay[durationof({full}) - durationof({prefix}) + {pad}] q[{q1}];", f"x q[{q1}];"]
        params = {"q0": q0, "q1": q1, "pad": pad}
        meas = measure_all_block(meta)
    else:
        variant_name = "padding_with_rotations"
        desc = "Safe padding using rotation-only blocks."
        prefix = f"{{ rz(1.0472) q[{q0}]; }}"
        full = f"{{ rz(1.0472) q[{q0}]; rx(0.785398) q[{q0}]; }}"
        core = [f"delay[durationof({full}) - durationof({prefix}) + {pad}] q[{q0}];", f"y q[{q0}];"]
        params = {"q": q0, "pad": pad}
        meas = measure_subset_block(meta, [q0])

    return _mk(11, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_12(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[12]
    tags = ["box", "boundary"]

    q0, q1 = pick_two_distinct_qubits(meta, rng)

    if v == 1:
        variant_name = "box_two_1q_ops_then_outside_op"
        desc = "Put two 1-qubit ops inside a box, then another op outside."
        core = ["box {", f"  h q[{q0}];", f"  x q[{q0}];", "}", f"z q[{q0}];"]
        params = {"q": q0, "kind": "1q"}
        meas = measure_all_block(meta)
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "box_2q_op_then_repeat"
        desc = "Put a 2-qubit op inside a box, then repeat outside."
        core = ["box {", f"  cx q[{q0}], q[{q1}];", "}", f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "kind": "2q"}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "box_param_chain_then_h"
        desc = "Put a small rotation chain inside a box, then H outside."
        core = ["box {", f"  rz(0.785398) q[{q0}];", f"  ry(1.0472) q[{q0}];", "}", f"h q[{q0}];"]
        params = {"q": q0, "kind": "param"}
        meas = measure_all_block(meta)
    else:
        variant_name = "box_with_barrier_inside"
        desc = "Put an X and a barrier inside a box, then apply X outside."
        core = ["box {", f"  x q[{q0}];", f"  barrier q;", "}", f"x q[{q0}];"]
        params = {"q": q0, "kind": "with_barrier"}
        meas = measure_all_block(meta)

    return _mk(12, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_13(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[13]
    tags = ["box", "timed_box", "known_duration"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T_val = rng.randint(80, 240)
    T = f"{T_val}{unit}"

    a = rng.randint(10, max(10, T_val // 2))
    b = rng.randint(10, max(10, T_val // 2))
    if a + b >= T_val:
        b = max(1, T_val - a - 1)

    if v == 1:
        variant_name = "timed_box_fixed_plus_stretch"
        desc = "Use a timed box with fixed delays and a stretch to fill the remainder."
        core = ["stretch g;",
                f"box[{T}] {{",
                f"  delay[{a}{unit}] q[{q0}];",
                f"  delay[g] q[{q0}];",
                f"  delay[{b}{unit}] q[{q0}];",
                f"}}",
                f"x q[{q0}];"]
        params = {"q": q0, "T": T, "a": f"{a}{unit}", "b": f"{b}{unit}"}
        meas = measure_subset_block(meta, [q0])
    elif v == 2:
        variant_name = "timed_box_single_delay_exact"
        desc = "Use a timed box that contains a single delay equal to the box duration."
        core = [f"box[{T}] {{", f"  delay[{T}] q[{q0}];", f"}}", f"h q[{q0}];"]
        params = {"q": q0, "T": T, "mode": "single_delay"}
        meas = measure_subset_block(meta, [q0])
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "timed_box_parallel_delays_then_2q"
        desc = "Timed box with parallel known delays on two qubits, then a 2-qubit gate."
        q1 = pick_qubit(meta, rng)
        core = ["stretch g;",
                f"box[{T}] {{",
                f"  delay[{a}{unit}] q[{q0}]; delay[{a}{unit}] q[{q1}];",
                f"  delay[g] q[{q0}]; delay[g] q[{q1}];",
                f"  delay[{b}{unit}] q[{q0}]; delay[{b}{unit}] q[{q1}];",
                f"}}",
                f"cz q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "T": T}
        meas = measure_all_block(meta)
    else:
        variant_name = "timed_box_delay_then_gate"
        desc = "Timed box with an exact delay, followed by a gate."
        core = [f"box[{T}] {{", f"  delay[{T}] q[{q0}];", f"}}", f"rx(0.392699) q[{q0}];"]
        params = {"q": q0, "T": T, "mode": "delay_then_gate"}
        meas = measure_subset_block(meta, [q0])

    return _mk(13, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_14(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[14]
    tags = ["box", "stretch", "fill"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T = rand_time(rng, 120, 300, unit)
    fixed = rand_time(rng, 10, 60, unit)

    if v == 1:
        variant_name = "fixed_then_stretch_then_gate"
        desc = "In a timed box: fixed delay, stretch fill, then gate."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[{fixed}] q[{q0}];", f"  delay[g] q[{q0}];", f"  x q[{q0}];", f"}}"]
        params = {"q": q0, "T": T, "fixed": fixed}
        meas = measure_all_block(meta)
    elif v == 2:
        variant_name = "gate_then_stretch_then_gate"
        desc = "In a timed box: gate, stretch fill, gate."
        core = ["stretch g;", f"box[{T}] {{", f"  h q[{q0}];", f"  delay[g] q[{q0}];", f"  h q[{q0}];", f"}}"]
        params = {"q": q0, "T": T}
        meas = measure_all_block(meta)
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "parallel_stretch_then_2q"
        desc = "In a timed box: stretch on both qubits then apply a 2-qubit gate."
        q0, q1 = pick_two_distinct_qubits(meta, rng)
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  delay[g] q[{q1}];", f"  cx q[{q0}], q[{q1}];", f"}}"]
        params = {"q0": q0, "q1": q1, "T": T}
        meas = measure_all_block(meta)
    else:
        variant_name = "symmetric_stretch_around_rz"
        desc = "In a timed box: stretch, RZ, stretch."
        core = ["stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  rz(1.0472) q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        params = {"q": q0, "T": T}
        meas = measure_all_block(meta)

    return _mk(14, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_15(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[15]
    tags = ["barrier", "ordering"]

    q0, q1 = pick_two_distinct_qubits(meta, rng)

    if v == 1:
        variant_name = "barrier_between_x_and_z"
        desc = "Use barrier between two single-qubit gates to enforce ordering."
        core = [f"x q[{q0}];", "barrier q;", f"z q[{q0}];"]
        params = {"q": q0}
        meas = measure_all_block(meta)
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "barrier_before_cx"
        desc = "Place barrier before a 2-qubit gate to separate preparation and entangling."
        core = [f"h q[{q0}];", f"x q[{q1}];", "barrier q;", f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "barrier_between_two_rz"
        desc = "Use barrier between identical rotations (structure preservation)."
        core = [f"rz(0.785398) q[{q0}];", "barrier q;", f"rz(0.785398) q[{q0}];"]
        params = {"q": q0, "repeat": True}
        meas = measure_all_block(meta)
    else:
        variant_name = "barrier_h_involution"
        desc = "H, barrier, H to emphasize barrier as a scheduling boundary."
        core = [f"h q[{q0}];", "barrier q;", f"h q[{q0}];"]
        params = {"q": q0}
        meas = measure_all_block(meta)

    return _mk(15, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_16(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[16]
    tags = ["echo", "box", "stretch"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T = rand_time(rng, 160, 400, unit)

    if v == 1:
        variant_name = "hahn_echo_x_mid"
        desc = "Hahn echo: H, then X at midpoint inside a timed box."
        core = [f"h q[{q0}];", "stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  x q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        params = {"q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])
    elif v == 2:
        variant_name = "hahn_echo_y_mid"
        desc = "Echo variant: use Y pulse at midpoint instead of X."
        core = [f"h q[{q0}];", "stretch g;", f"box[{T}] {{", f"  delay[g] q[{q0}];", f"  y q[{q0}];", f"  delay[g] q[{q0}];", f"}}"]
        params = {"q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])
    elif v == 3:
        variant_name = "double_echo"
        desc = "Apply two consecutive echo boxes (repeat twice)."
        core = [f"h q[{q0}];",
                "stretch g;", f"box[{T}] {{ delay[g] q[{q0}]; x q[{q0}]; delay[g] q[{q0}]; }}",
                "stretch g2;", f"box[{T}] {{ delay[g2] q[{q0}]; x q[{q0}]; delay[g2] q[{q0}]; }}"]
        params = {"q": q0, "T": T, "repeat": 2}
        meas = measure_subset_block(meta, [q0])
    else:
        variant_name = "echo_with_rx_pi"
        desc = "Echo using RX(pi) at midpoint (explicit rotation form)."
        core = [f"h q[{q0}];", "stretch g;", f"box[{T}] {{ delay[g] q[{q0}]; rx(3.14159) q[{q0}]; delay[g] q[{q0}]; }}"]
        params = {"q": q0, "T": T}
        meas = measure_subset_block(meta, [q0])

    return _mk(16, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_17(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[17]
    tags = ["alignment_center", "known_duration", "delay"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0, q1 = pick_two_qubits(meta, rng)
    A = even_rand(rng, 40, 200)
    B = even_rand(rng, 10, A)
    lead = (A - B) // 2

    if v == 1 and n_qubits(meta) >= 2:
        variant_name = "center_align_two_known_durations"
        desc = "Align centers of two known-duration delays by leading delay on the shorter one."
        core = [f"delay[{A}{unit}] q[{q0}];",
                f"delay[{lead}{unit}] q[{q1}];",
                f"delay[{B}{unit}] q[{q1}];",
                f"x q[{q0}];", f"x q[{q1}];"]
        params = {"q0": q0, "q1": q1, "A": f"{A}{unit}", "B": f"{B}{unit}", "lead": f"{lead}{unit}"}
        meas = measure_all_block(meta)
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "center_align_then_cz"
        desc = "Align by lead delay then apply CZ."
        core = [f"delay[{lead}{unit}] q[{q1}];",
                f"delay[{B}{unit}] q[{q1}];",
                f"delay[{A}{unit}] q[{q0}];",
                f"cz q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "A": f"{A}{unit}", "B": f"{B}{unit}", "lead": f"{lead}{unit}"}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "single_qubit_symmetric_known_delays"
        desc = "Use symmetric known delays around an operation (single-qubit centering)."
        q = pick_qubit(meta, rng)
        core = [f"delay[{lead}{unit}] q[{q}];",
                f"delay[{B}{unit}] q[{q}];",
                f"delay[{lead}{unit}] q[{q}];",
                f"h q[{q}];"]
        params = {"q": q, "lead": f"{lead}{unit}", "B": f"{B}{unit}"}
        meas = measure_subset_block(meta, [q])
    else:
        variant_name = "three_qubit_center_alignment"
        desc = "Align centers for multiple qubits using known-duration delays."
        q0, q1, q2 = pick_three_qubits(meta, rng)
        C = even_rand(rng, 10, B)
        lead2 = (A - C) // 2
        core = [f"delay[{A}{unit}] q[{q0}];",
                f"delay[{lead}{unit}] q[{q1}]; delay[{B}{unit}] q[{q1}];",
                f"delay[{lead2}{unit}] q[{q2}]; delay[{C}{unit}] q[{q2}];",
                f"x q[{q0}]; x q[{q1}]; x q[{q2}];"]
        params = {"q0": q0, "q1": q1, "q2": q2, "A": f"{A}{unit}"}
        meas = measure_all_block(meta)

    return _mk(17, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_18(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[18]
    tags = ["delay", "multi_qubit"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    d_all = rand_time(rng, 30, 180, unit)
    d_pre = rand_time(rng, 10, 90, unit)

    if v == 1:
        variant_name = "pre_delay_then_global_delay"
        desc = "Apply a pre-delay on one qubit, then delay all qubits together."
        core = [f"delay[{d_pre}] q[{q0}];", f"delay[{d_all}] q;", f"h q[{q0}];"]
        params = {"q": q0, "pre": d_pre, "all": d_all}
        meas = measure_all_block(meta)
    elif v == 2:
        variant_name = "global_delay_between_gates"
        desc = "Put a global delay between preparation and operation."
        core = [f"h q[{q0}];", f"delay[{d_all}] q;", f"x q[{q0}];"]
        params = {"q": q0, "all": d_all}
        meas = measure_all_block(meta)
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "global_delay_then_cx"
        desc = "Global delay then apply a 2-qubit gate."
        q0, q1 = pick_two_distinct_qubits(meta, rng)
        core = [f"delay[{d_pre}] q[{q1}];", f"delay[{d_all}] q;", f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "pre": d_pre, "all": d_all}
        meas = measure_all_block(meta)
    else:
        variant_name = "global_delay_with_barrier"
        desc = "Global delay followed by barrier and a rotation."
        core = [f"delay[{d_all}] q;", f"barrier q;", f"rz(0.785398) q[{q0}];"]
        params = {"all": d_all, "q": q0}
        meas = measure_all_block(meta)

    return _mk(18, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_19(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[19]
    tags = ["box", "nop", "sync"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0, q1 = pick_two_qubits(meta, rng)
    T = rng.randint(80, 240)
    Tdur = f"{T}{unit}"
    a = rng.randint(10, max(10, T // 2))
    b = max(1, T - a)

    if v == 1 and n_qubits(meta) >= 2:
        variant_name = "nop_sync_with_partial_delay"
        desc = "Use nop on one qubit to keep it synchronized with a delay on another qubit."
        core = [f"box[{Tdur}] {{", f"  delay[{a}{unit}] q[{q0}];", f"  nop q[{q1}];", f"  delay[{b}{unit}] q[{q0}];", f"}}", f"x q[{q1}];"]
        params = {"q0": q0, "q1": q1, "T": Tdur, "a": f"{a}{unit}"}
        meas = measure_all_block(meta)
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "nop_vs_delay_parallel"
        desc = "Timed box: nop on one qubit, full-duration delay on another."
        core = [f"box[{Tdur}] {{", f"  nop q[{q0}];", f"  delay[{Tdur}] q[{q1}];", f"}}", f"cz q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "T": Tdur}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "nop_only_box"
        desc = "Timed box with only nop, then apply a gate."
        q = pick_qubit(meta, rng)
        core = [f"box[{Tdur}] {{", f"  nop q[{q}];", f"}}", f"h q[{q}];"]
        params = {"q": q, "T": Tdur}
        meas = measure_subset_block(meta, [q])
    else:
        variant_name = "fallback_delay_only_box"
        desc = "Timed box with known delay only (nop not required)."
        core = [f"box[{Tdur}] {{", f"  delay[{Tdur}] q[{q0}];", f"}}", f"x q[{q0}];"]
        params = {"q": q0, "T": Tdur}
        meas = measure_all_block(meta)

    return _mk(19, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_20(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[20]
    tags = ["duration", "update", "delay"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    a = rng.randint(10, 80)
    b = rng.randint(10, 80)

    if v == 1:
        variant_name = "assign_then_reassign_duration"
        desc = "Assign a duration variable, delay, reassign it, delay again."
        core = [f"duration d = {a}{unit};", f"delay[d] q[{q0}];", f"d = {b}{unit};", f"delay[d] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "a": f"{a}{unit}", "b": f"{b}{unit}"}
    elif v == 2:
        variant_name = "duration_increment"
        desc = "Increment a duration variable and use it for a second delay."
        core = [f"duration d = {a}{unit};", f"delay[d] q[{q0}];", f"d = d + {b}{unit};", f"delay[d] q[{q0}];", f"h q[{q0}];"]
        params = {"q": q0, "a": f"{a}{unit}", "b": f"{b}{unit}"}
    elif v == 3:
        variant_name = "duration_scale"
        desc = "Scale a duration variable (2*d) before the second delay."
        core = [f"duration d = {a}{unit};", f"delay[d] q[{q0}];", f"d = 2*d;", f"delay[d] q[{q0}];", f"rz(0.785398) q[{q0}];"]
        params = {"q": q0, "a": f"{a}{unit}"}
    else:
        variant_name = "duration_noop_subtract_zero"
        desc = "Demonstrate duration reassignment with a no-op subtract of 0."
        core = [f"duration d = {a}{unit};", f"d = d - 0{unit};", f"delay[d] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "a": f"{a}{unit}"}

    meas = measure_subset_block(meta, [q0])
    return _mk(20, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_21(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[21]
    tags = ["delay", "structure"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0, q1 = pick_two_qubits(meta, rng)
    d = rand_time(rng, 20, 160, unit)

    if v == 1:
        variant_name = "delay_between_h_gates"
        desc = "Make idle explicit by inserting a delay between two H gates."
        core = [f"h q[{q0}];", f"delay[{d}] q[{q0}];", f"h q[{q0}];"]
        params = {"q": q0, "d": d}
        meas = measure_subset_block(meta, [q0])
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "delay_before_entangling"
        desc = "Insert a delay before a 2-qubit entangling gate."
        core = [f"h q[{q0}];", f"delay[{d}] q[{q0}];", f"x q[{q1}];", f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "d": d}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "global_delay_as_separator"
        desc = "Use a global delay as a separator between circuit phases."
        core = [f"delay[{d}] q;", f"rz(0.392699) q[{q0}];"]
        params = {"d_all": d, "q": q0}
        meas = measure_all_block(meta)
    else:
        variant_name = "repeated_delay_patterns"
        desc = "Repeat delay-gate-delay pattern on a single qubit."
        core = [f"x q[{q0}];", f"delay[{d}] q[{q0}];", f"z q[{q0}];", f"delay[{d}] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "d": d}
        meas = measure_subset_block(meta, [q0])

    return _mk(21, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_22(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[22]
    tags = ["delay", "zero", "ordering"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)

    if v == 1:
        variant_name = "delay_zero_between_ops"
        desc = "Use delay[0] as an explicit ordering point between two gates."
        core = [f"x q[{q0}];", f"delay[0{unit}] q[{q0}];", f"z q[{q0}];"]
        params = {"q": q0, "unit": unit}
        meas = measure_all_block(meta)
    elif v == 2:
        variant_name = "delay_zero_on_all_qubits"
        desc = "Use delay[0] on all qubits as a global ordering point."
        core = [f"h q[{q0}];", f"delay[0{unit}] q;", f"h q[{q0}];"]
        params = {"q": q0, "unit": unit, "scope": "all"}
        meas = measure_all_block(meta)
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "delay_zero_between_2q_gates"
        desc = "Insert delay[0] between two identical 2-qubit gates."
        q0, q1 = pick_two_distinct_qubits(meta, rng)
        core = [f"cx q[{q0}], q[{q1}];", f"delay[0{unit}] q[{q0}];", f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "unit": unit}
        meas = measure_all_block(meta)
    else:
        variant_name = "delay_zero_between_rotations"
        desc = "Use delay[0] between two rotations to force a boundary."
        core = [f"rz(0.785398) q[{q0}];", f"delay[0{unit}] q[{q0}];", f"rz(0.785398) q[{q0}];"]
        params = {"q": q0, "unit": unit}
        meas = measure_all_block(meta)

    return _mk(22, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_23(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[23]
    tags = ["box", "nested", "timed_box"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    outer = rng.randint(120, 320)
    inner = rng.randint(40, outer - 40)
    O = f"{outer}{unit}"
    I = f"{inner}{unit}"

    if v == 1:
        variant_name = "nested_timed_box_with_stretch"
        desc = "Nested timed boxes: inner fixed delay, outer uses stretch to fill."
        core = [f"box[{O}] {{",
                f"  box[{I}] {{ delay[{I}] q[{q0}]; }}",
                f"  stretch g;",
                f"  delay[g] q[{q0}];",
                f"}}",
                f"x q[{q0}];"]
        params = {"q": q0, "outer": O, "inner": I}
        meas = measure_subset_block(meta, [q0])
    elif v == 2 and n_qubits(meta) >= 2:
        variant_name = "nested_boxes_parallel_two_qubits"
        desc = "Nested timed boxes with two qubits delayed in parallel, then CZ."
        q1 = pick_qubit(meta, rng)
        core = [f"box[{O}] {{",
                f"  box[{I}] {{ delay[{I}] q[{q0}]; delay[{I}] q[{q1}]; }}",
                f"  stretch g;",
                f"  delay[g] q[{q0}]; delay[g] q[{q1}];",
                f"}}",
                f"cz q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "outer": O, "inner": I}
        meas = measure_all_block(meta)
    elif v == 3:
        variant_name = "nested_box_with_untimed_inner"
        desc = "Use an untimed inner box inside a timed outer box."
        core = [f"box[{O}] {{",
                f"  box {{ h q[{q0}]; }}",
                f"  delay[{I}] q[{q0}];",
                f"}}",
                f"h q[{q0}];"]
        params = {"q": q0, "outer": O, "inner": I}
        meas = measure_subset_block(meta, [q0])
    else:
        variant_name = "nested_box_with_exact_outer_delay"
        desc = "Timed outer box includes an exact outer-duration delay (redundant but valid)."
        core = [f"box[{O}] {{",
                f"  box[{I}] {{ delay[{I}] q[{q0}]; }}",
                f"  delay[{O}] q[{q0}];",
                f"}}",
                f"rz(0.392699) q[{q0}];"]
        params = {"q": q0, "outer": O, "inner": I}
        meas = measure_subset_block(meta, [q0])

    return _mk(23, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_24(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[24]
    tags = ["stretch", "system", "multiple_boxes"]

    unit = choose_unit(meta, rng, prefer_dt=False)
    q0 = pick_qubit(meta, rng)
    T1 = rng.randint(120, 240)
    T2 = rng.randint(120, 240)
    t1 = f"{T1}{unit}"
    t2 = f"{T2}{unit}"
    fixed = rand_time(rng, 10, 60, unit)

    if v == 1:
        variant_name = "two_equations_two_unknowns"
        desc = "Use two timed boxes to constrain stretch variables (a,b)."
        core = ["stretch a;", "stretch b;",
                f"box[{t1}] {{ delay[a] q[{q0}]; delay[b] q[{q0}]; }}",
                f"box[{t2}] {{ delay[2*a] q[{q0}]; delay[b] q[{q0}]; }}",
                f"x q[{q0}];"]
        params = {"q": q0, "t1": t1, "t2": t2, "fixed": None}
        meas = measure_subset_block(meta, [q0])
    elif v == 2:
        variant_name = "two_equations_with_fixed_offset"
        desc = "Two boxes constrain a,b with an additional fixed delay offset."
        core = ["stretch a;", "stretch b;",
                f"box[{t1}] {{ delay[{fixed}] q[{q0}]; delay[a] q[{q0}]; delay[b] q[{q0}]; }}",
                f"box[{t2}] {{ delay[{fixed}] q[{q0}]; delay[a] q[{q0}]; delay[2*b] q[{q0}]; }}",
                f"h q[{q0}];"]
        params = {"q": q0, "t1": t1, "t2": t2, "fixed": fixed}
        meas = measure_subset_block(meta, [q0])
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "two_qubits_shared_constraints"
        desc = "Constrain stretches across two qubits using paired timed boxes."
        q0, q1 = pick_two_distinct_qubits(meta, rng)
        core = ["stretch a;", "stretch b;",
                f"box[{t1}] {{ delay[a] q[{q0}]; delay[b] q[{q1}]; }}",
                f"box[{t2}] {{ delay[2*a] q[{q0}]; delay[b] q[{q1}]; }}",
                f"cx q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "t1": t1, "t2": t2}
        meas = measure_all_block(meta)
    else:
        variant_name = "three_stretches_mixed_constraints"
        desc = "Use three stretches with two boxes (underdetermined but constrained)."
        core = ["stretch a;", "stretch b;", "stretch c;",
                f"box[{t1}] {{ delay[a] q[{q0}]; delay[b] q[{q0}]; delay[c] q[{q0}]; }}",
                f"box[{t2}] {{ delay[2*a] q[{q0}]; delay[b] q[{q0}]; delay[c] q[{q0}]; }}",
                f"rz(0.785398) q[{q0}];"]
        params = {"q": q0, "t1": t1, "t2": t2}
        meas = measure_subset_block(meta, [q0])

    return _mk(24, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)

def theme_25(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[25]
    tags = ["durationof", "box", "compound"]

    q0 = pick_qubit(meta, rng)
    unit = choose_unit(meta, rng, prefer_dt=False)
    pad = rand_time(rng, 10, 60, unit)

    if v == 1:
        variant_name = "durationof_box_plus_pad"
        desc = "Delay by durationof(a box) plus a small pad, then H."
        core = [f"delay[durationof({{ box {{ x q[{q0}]; }} }}) + {pad}] q[{q0}];", f"h q[{q0}];"]
        params = {"q": q0, "pad": pad}
        meas = measure_all_block(meta)
    elif v == 2:
        variant_name = "durationof_timed_box_delay"
        desc = "Delay by durationof(timed box containing a delay), then X."
        core = [f"delay[durationof({{ box {{ delay[{pad}] q[{q0}]; }} }})] q[{q0}];", f"x q[{q0}];"]
        params = {"q": q0, "pad": pad}
        meas = measure_all_block(meta)
    elif v == 3 and n_qubits(meta) >= 2:
        variant_name = "durationof_box_two_qubits"
        desc = "Delay by durationof(a compound box with two qubits), then CZ."
        q1 = pick_qubit(meta, rng)
        core = [f"delay[durationof({{ box {{ delay[{pad}] q[{q0}]; delay[{pad}] q[{q1}]; }} }})] q[{q0}];",
                f"cz q[{q0}], q[{q1}];"]
        params = {"q0": q0, "q1": q1, "pad": pad}
        meas = measure_all_block(meta)
    else:
        variant_name = "durationof_box_with_barrier_plus_pad"
        desc = "Delay by durationof(box with barrier) plus pad, then rotate."
        core = [f"delay[durationof({{ box {{ x q[{q0}]; barrier q; }} }}) + {pad}] q[{q0}];", f"rz(0.392699) q[{q0}];"]
        params = {"q": q0, "pad": pad}
        meas = measure_all_block(meta)

    return _mk(25, v, theme_name=theme_name, variant_name=variant_name, description=desc,
               tags=tags, params=params, core=core, meas=meas)


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

# -------------------- Public API --------------------

def generate_core_task(meta: Dict[str, Any],
                       *,
                       theme_id: int,
                       variant_id: int,
                       seed: Optional[int] = None) -> CoreTaskInstance:
    if theme_id not in THEMES:
        raise KeyError(f"Unknown theme_id={theme_id}")
    if variant_id not in (1, 2, 3, 4):
        raise ValueError("variant_id must be 1..4")
    rng = random.Random(seed)
    return THEMES[theme_id](meta, rng, variant_id)

def generate_core_task_from_meta_path(meta_path: str,
                                      *,
                                      theme_id: int,
                                      variant_id: int,
                                      seed: Optional[int] = None) -> CoreTaskInstance:
    meta = load_meta(meta_path)
    return generate_core_task(meta, theme_id=theme_id, variant_id=variant_id, seed=seed)



# -------------------- Example main (no argparse) --------------------

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

def assemble_full_task(background_qasm: str, inst: "CoreTaskInstance") -> str:
    out = _replace_between_markers(background_qasm, CORE_START, CORE_END, inst.core_lines)

    if MEAS_START in out and MEAS_END in out:
        out = _replace_between_markers(out, MEAS_START, MEAS_END, inst.meas_lines)
    else:
        meas_block = "\n".join([MEAS_START] + inst.meas_lines + [MEAS_END]) + "\n"
        out = out.rstrip() + "\n\n" + meas_block

    return out


def main(task_num: int = 200, base_seed: int = 20260108) -> None:

    background_dir = "timing_background_qasm"
    out_dir = "timing_train"
    os.makedirs(out_dir, exist_ok=True)

    variants = [2, 3, 4]

    bg_paths = sorted(glob.glob(os.path.join(background_dir, "bg_*.qasm")))
    if not bg_paths:
        raise RuntimeError(f"No timing backgrounds found in {background_dir}")

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

        inst = generate_core_task_from_meta_path(
            meta_path,
            theme_id=theme_id,
            variant_id=variant_id,
            seed=inst_seed,
        )

        full_qasm = assemble_full_task(bg_text, inst)

        task_fname = f"timing_task_{t:05d}_th{theme_id:02d}_v{variant_id}.qasm"
        task_path = os.path.join(out_dir, task_fname)
        _write_text(task_path, full_qasm)

    print(f"Done. Wrote {task_num} timing train tasks into: {out_dir}")


if __name__ == "__main__":
    task_num = 1000 
    main(task_num=task_num)
