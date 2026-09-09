# classical_core_generators.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import json
import random
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Callable, Optional

# -------------------- Markers (keep consistent with timing) --------------------

CORE_START = "// === CORE_TASK_START ==="
CORE_END = "// === CORE_TASK_END ==="
MEAS_START = "// === MEASUREMENT_START ==="
MEAS_END = "// === MEASUREMENT_END ==="

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

def pick_two_qubits(meta: Dict[str, Any], rng: random.Random) -> Tuple[int, int]:
    uq = used_qubits(meta)
    if len(uq) >= 2:
        a, b = rng.sample(uq, 2)
        return a, b
    # fallback
    return uq[0], uq[0]

def pick_three_qubits(meta: Dict[str, Any], rng: random.Random) -> Tuple[int, int, int]:
    uq = used_qubits(meta)
    if len(uq) >= 3:
        a, b, c = rng.sample(uq, 3)
        return a, b, c
    allq = list(range(n_qubits(meta)))
    while len(allq) < 3:
        allq.append(allq[-1] if allq else 0)
    return allq[0], allq[1], allq[2]

def set_literal_0_to(n: int) -> str:
    # "{0,1,2,...,n-1}"
    return "{" + ",".join(str(i) for i in range(n)) + "}"

def rand_width(rng: random.Random, choices=(4, 5, 6, 8, 10, 12, 16)) -> int:
    return rng.choice(list(choices))

def rand_angle_const(rng: random.Random) -> float:
    # Keep simple numeric literals (avoid pi dependency)
    return round(rng.uniform(0.1, 6.0), 6)

def rand_small_int(rng: random.Random, lo=0, hi=15) -> int:
    return rng.randint(lo, hi)

# -------------------- Measurement helpers --------------------

def measure_all_block(meta: Dict[str, Any], creg: str = "__cc_out") -> List[str]:
    nq = n_qubits(meta)
    lines = [f"bit[{nq}] {creg};"]
    for i in range(nq):
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
    features: List[str]
    requirements: List[str]
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
            "features": list(self.features),
            "requirements": list(self.requirements),
            "params": dict(self.params),
        }

def _mk(theme_id: int, v: int, *,
        theme_name: str,
        variant_name: str,
        description: str,
        tags: List[str],
        features: List[str],
        requirements: List[str],
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
        features=features,
        requirements=requirements,
        params=params,
        core_lines=commented_core,
        meas_lines=meas,
    )

# -------------------- Theme names --------------------

THEME_NAMES: Dict[int, str] = {
    1:  "measure_then_reset_branch",
    2:  "repeat_until_success",
    3:  "conditional_correction_multibit",
    4:  "for_loop_continue_pattern",
    5:  "while_loop_break_on_measure",
    6:  "angle_arithmetic_mod_wrap",
    7:  "angle_scaled_by_uint",
    8:  "float_expr_cast_to_angle",
    9:  "integer_arithmetic_controls_flow",
    10: "mixed_comparison_with_cast",
    11: "bit_shift_and_mask_test",
    12: "popcount_triggered_gate",
    13: "rotl_rotr_pattern_match",
    14: "bitwise_and_xor_pipeline",
    15: "integer_switch_on_computed_index",
    16: "switch_on_int_from_bit_literal",
    17: "set_iteration_discrete",
    18: "array_iteration_angles_or_ints",
    19: "single_extern_call",
    20: "nested_control_switch_in_loop_with_if",
    21: "measurement_accumulation_counter",
    22: "early_termination_end",
    23: "bit_slice_alias_and_iteration",
    24: "membership_test_in_set",
    25: "switch_const_expression_cases_no_default",
}

ThemeFn = Callable[[Dict[str, Any], random.Random, int], CoreTaskInstance]

# ==================== 25 themes × 4 variants ====================

def theme_01(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[1]
    q = pick_qubit(meta, rng)
    tags = ["if_else", "measure", "reset"]
    features = ["measure", "if/else", "reset", "conditional_gate"]
    req = ["supports_if", "supports_reset"]

    if v == 1:
        vn = "if_meas_then_reset_else_x"
        desc = "Measure one qubit; if 1 then reset, else apply X."
        core = [
            f"bit __cc_m;",
            f"__cc_m = measure q[{q}];",
            f"if (__cc_m) {{",
            f"  reset q[{q}];",
            f"}} else {{",
            f"  x q[{q}];",
            f"}}",
        ]
    elif v == 2:
        vn = "if_meas_then_x_else_z"
        desc = "Measure one qubit; branch to apply X vs Z."
        core = [
            f"bit __cc_m;",
            f"__cc_m = measure q[{q}];",
            f"if (__cc_m) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
    elif v == 3:
        vn = "double_measure_majority_branch"
        desc = "Measure twice and branch on (m1 OR m2)."
        core = [
            f"bit __cc_m1; bit __cc_m2;",
            f"__cc_m1 = measure q[{q}];",
            f"h q[{q}];",
            f"__cc_m2 = measure q[{q}];",
            f"if (__cc_m1 || __cc_m2) {{ reset q[{q}]; }} else {{ h q[{q}]; }}",
        ]
        features += ["logical_ops(||)"]
        req += ["supports_logical_ops"]
    else:
        vn = "if_meas_then_reset_then_reprepare"
        desc = "Measure; if 1 reset then re-prepare with H."
        core = [
            f"bit __cc_m;",
            f"__cc_m = measure q[{q}];",
            f"if (__cc_m) {{ reset q[{q}]; h q[{q}]; }} else {{ h q[{q}]; }}",
        ]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q}
    return _mk(1, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_02(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[2]
    q = pick_qubit(meta, rng)
    max_try = rng.randint(2, 6)
    tags = ["while", "break", "measure"]
    features = ["while", "measure", "break", "counter_update"]
    req = ["supports_while", "supports_break"]

    if v == 1:
        vn = "while_until_measure_zero"
        desc = "Repeat measure-reset until measurement becomes 0 or max tries reached."
        core = [
            f"bit __cc_m;",
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  __cc_m = measure q[{q}];",
            f"  if (!__cc_m) {{ break; }}",
            f"  reset q[{q}];",
            f"  __cc_t = __cc_t + 1;",
            f"}}",
        ]
        features += ["unary_not(!)"]
        req += ["supports_logical_ops"]
    elif v == 2:
        vn = "while_until_measure_one_then_apply_x"
        desc = "Repeat measure until 1 appears; then apply X (with max cap)."
        core = [
            f"bit __cc_m = 0;",
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  __cc_m = measure q[{q}];",
            f"  if (__cc_m) {{ x q[{q}]; break; }}",
            f"  __cc_t = __cc_t + 1;",
            f"  h q[{q}];",
            f"}}",
        ]
    elif v == 3:
        vn = "while_with_continue_skip_gate"
        desc = "Loop with continue: if measured 0, continue; else do correction and break."
        core = [
            f"bit __cc_m;",
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  __cc_m = measure q[{q}];",
            f"  if (!__cc_m) {{ __cc_t = __cc_t + 1; continue; }}",
            f"  z q[{q}];",
            f"  break;",
            f"}}",
        ]
        features += ["continue"]
        req += ["supports_continue", "supports_logical_ops"]
    else:
        vn = "while_flip_then_retry"
        desc = "If measured 1, flip and retry, otherwise stop."
        core = [
            f"bit __cc_m;",
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  __cc_m = measure q[{q}];",
            f"  if (__cc_m) {{ x q[{q}]; __cc_t = __cc_t + 1; continue; }}",
            f"  break;",
            f"}}",
        ]
        features += ["continue"]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "max_try": max_try}
    return _mk(2, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_03(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[3]
    q0, q1 = pick_two_qubits(meta, rng)
    tags = ["bit_array", "if_else", "pattern"]
    features = ["bit[n]", "measure", "cast_int", "if/else"]
    req = ["supports_bit_array", "supports_casts"]

    if v == 1:
        vn = "measure_2bits_branch_on_int"
        desc = "Measure 2 qubits into bit[2], branch on int value."
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"int __cc_idx = int(__cc_b);",
            f"if (__cc_idx == 1) {{ x q[{q0}]; }} else {{ z q[{q1}]; }}",
        ]
    elif v == 2:
        vn = "branch_on_msb_only"
        desc = "Measure 2 bits; use MSB as condition to choose a correction."
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"if (__cc_b[1]) {{ reset q[{q0}]; }} else {{ h q[{q1}]; }}",
        ]
        req += ["supports_reset"]
        features += ["indexing"]
    elif v == 3:
        vn = "pattern_match_with_xor"
        desc = "Measure 2 bits; compute XOR and branch on parity."
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"bit __cc_par = __cc_b[0] ^ __cc_b[1];",
            f"if (__cc_par) {{ x q[{q0}]; }} else {{ x q[{q1}]; }}",
        ]
        features += ["bitwise_xor(^)"]
    else:
        vn = "three_bit_pattern_threshold"
        desc = "Measure 3 qubits; count ones and branch on threshold."
        q0, q1, q2 = pick_three_qubits(meta, rng)
        thr = rng.randint(1, 2)
        core = [
            f"bit[3] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"__cc_b[2] = measure q[{q2}];",
            f"int __cc_s = int(__cc_b[0]) + int(__cc_b[1]) + int(__cc_b[2]);",
            f"if (__cc_s >= {thr}) {{ z q[{q0}]; }} else {{ h q[{q0}]; }}",
        ]
        features += ["int_arith", "comparison"]
        params = {"q0": q0, "q1": q1, "q2": q2, "thr": thr}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(3, v, theme_name=theme_name, variant_name=vn, description=desc,
                   tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    params = {"q0": q0, "q1": q1}
    return _mk(3, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_04(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[4]
    q = pick_qubit(meta, rng)
    n = rng.randint(3, 7)
    skip = rng.randint(0, n - 1)
    tags = ["for", "continue"]
    features = ["for-in-set", "continue", "measure", "counter_update"]
    req = ["supports_for", "supports_continue"]

    it_set = set_literal_0_to(n)

    if v == 1:
        vn = "for_continue_skip_one_iter"
        desc = "For-loop over a set; skip one iteration via continue."
        core = [
        f"int __cc_sum = 0;",
        f"for int __cc_i in {it_set} {{",
        f"  if (__cc_i == {skip}) {{ continue; }}",
        f"  x q[{q}];",
        f"  __cc_sum = __cc_sum + (__cc_i % 2);",
        f"}}",
        ]

    elif v == 2:
        vn = "for_continue_gate_schedule"
        desc = "For-loop: skip gate on one iteration; apply gate otherwise."
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  if (__cc_i == {skip}) {{ continue; }}",
            f"  x q[{q}];",
            f"}}",
        ]
    elif v == 3:
        vn = "for_continue_measure_then_cond_gate"
        desc = "For-loop: measure, skip correction when measurement is 0."
        core = [
        f"for int __cc_i in {it_set} {{",
        f"  if ((__cc_i % 2) == 0) {{ continue; }}",
        f"  z q[{q}];",
        f"}}",
        ]

        features += ["logical_not"]
        req += ["supports_logical_ops"]
    else:
        vn = "for_continue_with_accum_threshold"
        desc = "For-loop: accumulate measurements except skipped iter; then threshold gate."
        thr = rng.randint(1, max(1, n - 2))
        core = [
        f"int __cc_sum = 0;",
        f"for int __cc_i in {it_set} {{",
        f"  if (__cc_i == {skip}) {{ continue; }}",
        f"  x q[{q}];",
        f"  __cc_sum = __cc_sum + 1;",
        f"}}",
        f"if (__cc_sum >= {thr}) {{ x q[{q}]; }} else {{ h q[{q}]; }}",
        ]

        params = {"q": q, "n": n, "skip": skip, "thr": thr}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(4, v, theme_name=theme_name, variant_name=vn, description=desc,
                   tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "n": n, "skip": skip}
    return _mk(4, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_05(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[5]
    q = pick_qubit(meta, rng)
    max_try = rng.randint(2, 6)
    tags = ["while", "break"]
    features = ["while", "break", "measure", "if/else"]
    req = ["supports_while", "supports_break"]

    if v == 1:
        vn = "while_break_on_one"
        desc = "While-loop: break based on __cc_m."
        core = [
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  x q[{q}];",
            f"  bool __cc_m = ((__cc_t % 2) == 1);",
            f"  if (__cc_m) {{ break; }}",
            f"  __cc_t = __cc_t + 1;",
            f"}}",
        ]

    elif v == 2:
        vn = "while_break_on_zero_with_not"
        desc = "While-loop: break when is 0 (using !)."
        core = [
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  bool __cc_m = ((__cc_t % 3) != 0);",
            f"  if (!__cc_m) {{ break; }}",
            f"  x q[{q}];",
            f"  __cc_t = __cc_t + 1;",
            f"}}",
        ]

        features += ["logical_not"]
        req += ["supports_logical_ops"]
    elif v == 3:
        vn = "while_break_then_switch_gate"
        desc = "While-loop: after break, use __cc_last to pick a gate."
        core = [
            f"bool __cc_last = false;",
            f"int __cc_t = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  __cc_last = ((__cc_t % 2) == 1);",
            f"  x q[{q}];",
            f"  if (__cc_last) {{ break; }}",
            f"  __cc_t = __cc_t + 1;",
            f"}}",
            f"if (__cc_last) {{ z q[{q}]; }} else {{ h q[{q}]; }}",
        ]

    else:
        vn = "while_break_on_threshold_sum"
        desc = "While-loop: accumulate and break once sum reaches threshold."
        thr = rng.randint(1, max_try)
        core = [
            f"int __cc_t = 0;",
            f"int __cc_sum = 0;",
            f"while (__cc_t < {max_try}) {{",
            f"  x q[{q}];",
            f"  int __cc_m = (__cc_t % 2);",
            f"  __cc_sum = __cc_sum + __cc_m;",
            f"  if (__cc_sum >= {thr}) {{ break; }}",
            f"  __cc_t = __cc_t + 1;",
            f"}}",
        ]

        params = {"q": q, "max_try": max_try, "thr": thr}
        meas = measure_all_block(meta, "__cc_out")
        return _mk(5, v, theme_name=theme_name, variant_name=vn, description=desc,
                   tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "max_try": max_try}
    return _mk(5, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_06(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[6]
    q = pick_qubit(meta, rng)
    a = rand_angle_const(rng)
    b = rand_angle_const(rng)
    tags = ["angle", "arithmetic"]
    features = ["angle_type", "angle_arith", "parametric_gate"]
    req = ["supports_angle"]

    if v == 1:
        vn = "angle_add_then_rz"
        desc = "Compute angle = a + b (wrap semantics), then apply RZ."
        core = [f"angle __cc_th = {a};", f"__cc_th = __cc_th + {b};", f"rz(__cc_th) q[{q}];"]
    elif v == 2:
        vn = "angle_sub_then_rx"
        desc = "Compute angle = a - b, then apply RX."
        core = [f"angle __cc_th = {a};", f"__cc_th = __cc_th - {b};", f"rx(__cc_th) q[{q}];"]
    elif v == 3:
        vn = "angle_double_then_ry"
        desc = "Compute angle = 2*a, then apply RY."
        core = [f"angle __cc_th = {a};", f"__cc_th = 2*__cc_th;", f"ry(__cc_th) q[{q}];"]
    else:
        vn = "angle_chain_ops_then_rz"
        desc = "Chain multiple angle ops then use as parameter."
        c = rand_angle_const(rng)
        core = [
            f"angle __cc_th = {a};",
            f"__cc_th = __cc_th + {b};",
            f"__cc_th = __cc_th - {c};",
            f"rz(__cc_th) q[{q}];",
        ]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "a": a, "b": b}
    return _mk(6, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_07(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[7]
    q = pick_qubit(meta, rng)
    w = rand_width(rng)
    k = rng.randint(0, min(2**min(w, 6)-1, 15))
    scale = round(rng.uniform(0.05, 0.9), 6)
    tags = ["uint", "cast", "angle"]
    features = ["uint[w]", "float()", "angle()", "parametric_gate"]
    req = ["supports_uint", "supports_casts", "supports_angle"]

    if v == 1:
        vn = "uint_to_float_to_angle"
        desc = "Convert uint to float, scale, cast to angle, then RZ."
        core = [
            f"uint[{w}] __cc_k = {k};",
            f"float __cc_f = float(__cc_k) * {scale};",
            f"angle __cc_th = angle(__cc_f);",
            f"rz(__cc_th) q[{q}];",
        ]
    elif v == 2:
        vn = "uint_add_then_angle"
        desc = "Compute uint expression then cast into angle."
        add = rng.randint(0, 7)
        core = [
            f"uint[{w}] __cc_k = {k};",
            f"__cc_k = __cc_k + {add};",
            f"angle __cc_th = angle(float(__cc_k) * {scale});",
            f"rx(__cc_th) q[{q}];",
        ]
    elif v == 3:
        vn = "uint_mul_then_angle"
        desc = "Multiply uint then cast to angle for RY."
        mul = rng.randint(2, 5)
        core = [
            f"uint[{w}] __cc_k = {k};",
            f"__cc_k = __cc_k * {mul};",
            f"angle __cc_th = angle(float(__cc_k) * {scale});",
            f"ry(__cc_th) q[{q}];",
        ]
    else:
        vn = "uint_mod_then_angle"
        desc = "Use uint modulo to bound value, then cast to angle."
        m = rng.randint(2, 9)
        core = [
            f"uint[{w}] __cc_k = {k};",
            f"__cc_k = __cc_k % {m};",
            f"angle __cc_th = angle(float(__cc_k) * {scale});",
            f"rz(__cc_th) q[{q}];",
        ]
        features += ["mod(%)"]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "w": w, "k": k, "scale": scale}
    return _mk(7, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_08(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[8]
    q = pick_qubit(meta, rng)
    f1 = round(rng.uniform(-2.0, 2.0), 6)
    f2 = round(rng.uniform(0.1, 3.0), 6)
    tags = ["float", "cast", "angle"]
    features = ["float_arith", "cast_to_angle", "parametric_gate"]
    req = ["supports_float", "supports_casts", "supports_angle"]

    if v == 1:
        vn = "float_add_cast_angle"
        desc = "Compute float = f1 + f2, cast to angle, apply RZ."
        core = [f"float __cc_f = {f1} + {f2};", f"angle __cc_th = angle(__cc_f);", f"rz(__cc_th) q[{q}];"]
    elif v == 2:
        vn = "float_mul_cast_angle"
        desc = "Compute float = f1 * f2, cast to angle, apply RX."
        core = [f"float __cc_f = {f1} * {f2};", f"angle __cc_th = angle(__cc_f);", f"rx(__cc_th) q[{q}];"]
    elif v == 3:
        vn = "float_div_cast_angle"
        desc = "Compute float = f2 / (f2+1), cast to angle, apply RY."
        denom = round(f2 + 1.0, 6)
        core = [f"float __cc_f = {f2} / {denom};", f"angle __cc_th = angle(__cc_f);", f"ry(__cc_th) q[{q}];"]
    else:
        vn = "float_expr_then_branch"
        desc = "Compute float, cast to angle, then branch on sign to choose gate."
        core = [
            f"float __cc_f = {f1} - {f2};",
            f"angle __cc_th = angle(__cc_f);",
            f"if (__cc_f >= 0.0) {{ rz(__cc_th) q[{q}]; }} else {{ rx(__cc_th) q[{q}]; }}",
        ]
        features += ["if/else", "comparison"]
        req += ["supports_if"]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "f1": f1, "f2": f2}
    return _mk(8, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_09(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[9]
    q0, q1 = pick_two_qubits(meta, rng)
    w = rand_width(rng)
    a = rand_small_int(rng, 0, 31)
    b = rand_small_int(rng, 0, 31)
    c = rand_small_int(rng, 0, 31)
    ncases = rng.randint(3, 6)
    tags = ["int_uint", "arith", "control_flow"]
    features = ["int/uint_arith", "mod(%)", "if/else_or_switch"]
    req = ["supports_int_uint", "supports_mod"]

    if v == 1:
        vn = "arith_then_if_threshold"
        desc = "Compute idx=(a*b+c)%M; branch by threshold to choose a gate."
        thr = rng.randint(0, ncases - 1)
        core = [
            f"uint[{w}] __cc_a = {a}; uint[{w}] __cc_b = {b}; uint[{w}] __cc_c = {c};",
            f"uint[{w}] __cc_idx = (__cc_a * __cc_b + __cc_c) % {ncases};",
            f"if (__cc_idx >= {thr}) {{ x q[{q0}]; }} else {{ z q[{q0}]; }}",
        ]
        features += ["if/else", "comparison"]
        req += ["supports_if"]
        params = {"q": q0, "w": w, "a": a, "b": b, "c": c, "ncases": ncases, "thr": thr}
    elif v == 2:
        vn = "arith_then_switch"
        desc = "Compute idx then switch(idx) to choose one of several gates."
        core = [
            f"uint[{w}] __cc_a = {a}; uint[{w}] __cc_b = {b}; uint[{w}] __cc_c = {c};",
            f"int __cc_idx = int((__cc_a * __cc_b + __cc_c) % {ncases});",
            f"switch (__cc_idx) {{",
            f"  case 0 {{ x q[{q0}]; }}",
            f"  case 1 {{ z q[{q0}]; }}",
            f"  case 2 {{ h q[{q0}]; }}",
            f"  default {{ y q[{q0}]; }}",
            f"}}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q0, "w": w, "a": a, "b": b, "c": c, "ncases": ncases}
    elif v == 3:
        vn = "arith_power_then_branch"
        desc = "Use exponentiation on small ints and branch on parity."
        p = rng.randint(2, 4)
        core = [
            f"int __cc_x = {a} ** {p};",
            f"int __cc_y = {b} ** {p};",
            f"int __cc_s = __cc_x + __cc_y;",
            f"if ((__cc_s % 2) == 0) {{ x q[{q0}]; }} else {{ x q[{q1}]; }}",
        ]
        features += ["pow(**)"]
        req += ["supports_pow", "supports_if"]
        params = {"q0": q0, "q1": q1, "a": a, "b": b, "p": p}
    else:
        vn = "arith_div_mod_guard"
        desc = "Compute division and modulo with a guard; branch to choose correction."
        d = rng.randint(1, 7)
        core = [
            f"int __cc_x = {a};",
            f"int __cc_q = __cc_x / {d};",
            f"int __cc_r = __cc_x % {d};",
            f"if (__cc_r == 0) {{ z q[{q0}]; }} else {{ x q[{q0}]; }}",
        ]
        features += ["div(/)", "mod(%)"]
        req += ["supports_if"]
        params = {"q": q0, "a": a, "d": d}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(9, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_10(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[10]
    q = pick_qubit(meta, rng)
    a = rand_angle_const(rng)
    f = round(rng.uniform(0.1, 6.0), 6)
    tags = ["comparison", "cast"]
    features = ["explicit_cast", "comparison", "if/else"]
    req = ["supports_casts", "supports_if"]

    if v == 1:
        vn = "compare_float_of_angle"
        desc = "Compare float(angle) to a float constant and branch."
        core = [
            f"angle __cc_th = {a};",
            f"float __cc_f = float(__cc_th);",
            f"if (__cc_f > {f}) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        params = {"q": q, "a": a, "f": f}
    elif v == 2:
        vn = "compare_angle_from_float"
        desc = "Cast float to angle and compare with an angle constant."
        core = [
            f"float __cc_f = {f};",
            f"angle __cc_th = angle(__cc_f);",
            f"if (__cc_th >= {a}) {{ rz(__cc_th) q[{q}]; }} else {{ rx(__cc_th) q[{q}]; }}",
        ]
        params = {"q": q, "a": a, "f": f}
    elif v == 3:
        vn = "compare_int_from_bit_measure"
        desc = "Measure to bit, cast to int, compare and branch."
        core = [
            f"bit __cc_m = measure q[{q}];",
            f"int __cc_i = int(__cc_m);",
            f"if (__cc_i == 1) {{ x q[{q}]; }} else {{ h q[{q}]; }}",
        ]
        params = {"q": q}
    else:
        vn = "compare_uint_after_mask"
        desc = "Compute masked uint and compare to constant."
        w = rand_width(rng)
        x = rand_small_int(rng, 0, 255)
        mask = rng.choice([1, 3, 7, 15, 31, 63])
        c = rng.randint(0, mask)
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_m = __cc_x & {mask};",
            f"if (__cc_m == {c}) {{ z q[{q}]; }} else {{ x q[{q}]; }}",
        ]
        features += ["bitwise_and(&)"]
        params = {"q": q, "w": w, "x": x, "mask": mask, "c": c}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(10, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_11(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[11]
    q = pick_qubit(meta, rng)
    w = rand_width(rng)
    x = rand_small_int(rng, 0, 2**min(w, 8)-1)
    shift = rng.randint(0, min(3, w-1))
    tags = ["shift", "mask", "if"]
    features = ["shift(<<,>>)", "bitwise_and(&)", "if/else"]
    req = ["supports_shift", "supports_if"]

    if v == 1:
        vn = "test_lsb_after_shift"
        desc = "Right-shift and test LSB to decide a gate."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_b = (__cc_x >> {shift}) & 1;",
            f"if (__cc_b == 1) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        params = {"q": q, "w": w, "x": x, "shift": shift}
    elif v == 2:
        vn = "left_shift_then_mask"
        desc = "Left-shift then mask to decide a gate."
        mask = rng.choice([1, 3, 7, 15])
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = (__cc_x << {shift}) & {mask};",
            f"if (__cc_y != 0) {{ h q[{q}]; }} else {{ x q[{q}]; }}",
        ]
        params = {"q": q, "w": w, "x": x, "shift": shift, "mask": mask}
    elif v == 3:
        vn = "mask_two_bits_and_switch"
        desc = "Extract 2 bits and switch on them."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"int __cc_i = int((__cc_x >> {shift}) & 3);",
            f"switch (__cc_i) {{",
            f"  case 0 {{ x q[{q}]; }}",
            f"  case 1 {{ z q[{q}]; }}",
            f"  case 2 {{ h q[{q}]; }}",
            f"  default {{ y q[{q}]; }}",
            f"}}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q, "w": w, "x": x, "shift": shift}
    else:
        vn = "shift_from_measurement_index"
        desc = "Use measurement result as a shift amount (0/1)."
        core = [
            f"bit __cc_m = measure q[{q}];",
            f"int __cc_s = int(__cc_m);",
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_b = (__cc_x >> __cc_s) & 1;",
            f"if (__cc_b == 1) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        params = {"q": q, "w": w, "x": x}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(11, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_12(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[12]
    q = pick_qubit(meta, rng)
    w = rand_width(rng)
    x = rand_small_int(rng, 0, 2**min(w, 8)-1)
    thr = rng.randint(1, min(6, w))
    tags = ["popcount", "if"]
    features = ["popcount()", "comparison", "if/else"]
    req = ["supports_popcount", "supports_if"]

    if v == 1:
        vn = "popcount_threshold_gate"
        desc = "Compute popcount; if >= threshold apply X else Z."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"int __cc_p = popcount(__cc_x);",
            f"if (__cc_p >= {thr}) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
    elif v == 2:
        vn = "popcount_parity_branch"
        desc = "Branch on popcount parity (even/odd)."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"int __cc_p = popcount(__cc_x);",
            f"if ((__cc_p % 2) == 0) {{ h q[{q}]; }} else {{ x q[{q}]; }}",
        ]
        features += ["mod(%)"]
    elif v == 3:
        vn = "popcount_from_measure_bits"
        desc = "Measure into bit[w], cast to int/uint, popcount, then branch."
        # choose small w for feasibility
        ww = rng.choice([4, 5, 6, 8])
        qubits = used_qubits(meta)
        if len(qubits) >= 2:
            q0, q1 = pick_two_qubits(meta, rng)
        else:
            q0 = q1 = q
        core = [
            f"bit[{ww}] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"uint[{ww}] __cc_u = uint(__cc_b);",
            f"int __cc_p = popcount(__cc_u);",
            f"if (__cc_p > 0) {{ x q[{q0}]; }} else {{ z q[{q0}]; }}",
        ]
    else:
        vn = "popcount_then_switch"
        desc = "Switch on popcount (clamped) to pick a gate."
        k = rng.randint(3, 5)
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"int __cc_p = popcount(__cc_x) % {k};",
            f"switch (__cc_p) {{",
            f"  case 0 {{ x q[{q}]; }}",
            f"  case 1 {{ z q[{q}]; }}",
            f"  default {{ h q[{q}]; }}",
            f"}}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "w": w, "x": x, "thr": thr}
    return _mk(12, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_13(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[13]
    q = pick_qubit(meta, rng)
    w = rng.choice([8, 10, 12, 16])
    x = rand_small_int(rng, 0, 255)
    rot = rng.randint(1, 3)
    pat = rng.choice([0x3, 0x5, 0xA, 0xF, 0x33])
    tags = ["rotl", "rotr", "pattern", "if"]
    features = ["rotl/rotr", "comparison", "if/else"]
    req = ["supports_rotl_rotr", "supports_if"]

    if v == 1:
        vn = "rotl_match_constant"
        desc = "rotl(x,k) and compare to pattern to choose a gate."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = rotl(__cc_x, {rot});",
            f"if (__cc_y == {pat}) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
    elif v == 2:
        vn = "rotr_match_constant"
        desc = "rotr(x,k) and compare to pattern to choose a gate."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = rotr(__cc_x, {rot});",
            f"if (__cc_y == {pat}) {{ h q[{q}]; }} else {{ x q[{q}]; }}",
        ]
    elif v == 3:
        vn = "rot_then_mask_then_branch"
        desc = "Rotate then mask low bits and branch on nonzero."
        mask = rng.choice([0x1, 0x3, 0x7, 0xF])
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = rotl(__cc_x, {rot}) & {mask};",
            f"if (__cc_y != 0) {{ z q[{q}]; }} else {{ x q[{q}]; }}",
        ]
        features += ["bitwise_and(&)"]
    else:
        vn = "rot_then_switch_on_low2"
        desc = "Rotate then switch on low 2 bits to pick a gate."
        core = [
            f"uint[{w}] __cc_x = {x};",
            f"int __cc_i = int(rotl(__cc_x, {rot}) & 3);",
            f"switch (__cc_i) {{",
            f"  case 0 {{ x q[{q}]; }}",
            f"  case 1 {{ z q[{q}]; }}",
            f"  case 2 {{ h q[{q}]; }}",
            f"  default {{ y q[{q}]; }}",
            f"}}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "w": w, "x": x, "rot": rot, "pat": pat}
    return _mk(13, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_14(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[14]
    q = pick_qubit(meta, rng)
    w = rng.choice([8, 10, 12, 16])
    a = rand_small_int(rng, 0, 255)
    b = rand_small_int(rng, 0, 255)
    mask = rng.choice([0x3, 0x7, 0xF, 0x33, 0x55])
    tags = ["bitwise", "pipeline", "if"]
    features = ["^", "&", "|", "~", "comparison", "if/else"]
    req = ["supports_bitwise_ops", "supports_if"]

    if v == 1:
        vn = "xor_and_mask_then_branch"
        desc = "Compute (a^b)&mask then branch on zero."
        core = [
            f"uint[{w}] __cc_a = {a}; uint[{w}] __cc_b = {b};",
            f"uint[{w}] __cc_c = (__cc_a ^ __cc_b) & {mask};",
            f"if (__cc_c == 0) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
    elif v == 2:
        vn = "or_then_not_then_branch"
        desc = "Compute ~(a|b) and branch on low bit."
        core = [
            f"uint[{w}] __cc_a = {a}; uint[{w}] __cc_b = {b};",
            f"uint[{w}] __cc_c = ~(__cc_a | __cc_b);",
            f"if ((__cc_c & 1) == 1) {{ h q[{q}]; }} else {{ x q[{q}]; }}",
        ]
    elif v == 3:
        vn = "and_then_xor_then_switch"
        desc = "Pipeline: (a&mask)^(b&mask), then switch on low 2 bits."
        core = [
            f"uint[{w}] __cc_a = {a}; uint[{w}] __cc_b = {b};",
            f"uint[{w}] __cc_c = (__cc_a & {mask}) ^ (__cc_b & {mask});",
            f"int __cc_i = int(__cc_c & 3);",
            f"switch (__cc_i) {{ case 0 {{x q[{q}];}} case 1 {{z q[{q}];}} default {{h q[{q}];}} }}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
    else:
        vn = "bitwise_from_measurement_then_branch"
        desc = "Measure two bits, pack into uint, then bitwise pipeline and branch."
        q0, q1 = pick_two_qubits(meta, rng)
        ww = 4
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"uint[{ww}] __cc_u = uint(__cc_b);",
            f"uint[{ww}] __cc_c = (__cc_u ^ {mask & 0xF}) & 3;",
            f"if (__cc_c != 0) {{ x q[{q0}]; }} else {{ z q[{q0}]; }}",
        ]

    meas = measure_all_block(meta, "__cc_out")
    params = {"q": q, "w": w, "a": a, "b": b, "mask": mask}
    return _mk(14, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_15(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[15]
    q = pick_qubit(meta, rng)
    ncases = rng.randint(3, 6)
    tags = ["switch", "case"]
    features = ["switch/case", "computed_index"]
    req = ["supports_switch"]

    a = rand_small_int(rng, 0, 31)
    b = rand_small_int(rng, 0, 31)

    if v == 1:
        vn = "switch_on_mod_index"
        desc = "Compute idx=(a+b)%M then switch to choose a gate."
        core = [
            f"int __cc_idx = ({a} + {b}) % {ncases};",
            f"switch (__cc_idx) {{",
            f"  case 0 {{ x q[{q}]; }}",
            f"  case 1 {{ z q[{q}]; }}",
            f"  case 2 {{ h q[{q}]; }}",
            f"  default {{ y q[{q}]; }}",
            f"}}",
        ]
        params = {"q": q, "a": a, "b": b, "ncases": ncases}
    elif v == 2:
        vn = "switch_on_measurement_int"
        desc = "Measure to bit, cast to int, switch(0/1) to choose gates."
        core = [
            f"bit __cc_m = measure q[{q}];",
            f"int __cc_i = int(__cc_m);",
            f"switch (__cc_i) {{ case 0 {{ z q[{q}]; }} case 1 {{ x q[{q}]; }} }}",
        ]
        params = {"q": q}
        features += ["measure", "cast_int"]
    elif v == 3:
        vn = "switch_with_fallthrough_like_structure"
        desc = "Switch with multiple cases mapping to same action (grouped)."
        core = [
            f"int __cc_idx = ({a} * {b}) % {ncases};",
            f"switch (__cc_idx) {{",
            f"  case 0 {{ x q[{q}]; }}",
            f"  case 1 {{ x q[{q}]; }}",
            f"  default {{ z q[{q}]; }}",
            f"}}",
        ]
        params = {"q": q, "a": a, "b": b, "ncases": ncases}
    else:
        vn = "switch_nested_if_inside_case"
        desc = "Switch; inside one case do an additional if check."
        t = rng.randint(0, ncases - 1)
        core = [
            f"int __cc_idx = ({a} + 2*{b}) % {ncases};",
            f"switch (__cc_idx) {{",
            f"  case {t} {{ if (__cc_idx == {t}) {{ h q[{q}]; }} }}",
            f"  default {{ x q[{q}]; }}",
            f"}}",
        ]
        params = {"q": q, "a": a, "b": b, "ncases": ncases, "t": t}
        features += ["if/else"]
        req += ["supports_if"]

    meas = measure_all_block(meta, "__cc_out")
    return _mk(15, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_16(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[16]
    q0, q1 = pick_two_qubits(meta, rng)
    tags = ["switch", "bit_literal", "cast"]
    features = ["bit[n]", "int(bit[n])", "switch/case", "measure"]
    req = ["supports_switch", "supports_casts", "supports_bit_array"]

    if v == 1:
        vn = "switch_on_int_bit2"
        desc = "Measure 2 bits, switch on int(bit[2])."
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"switch (int(__cc_b)) {{",
            f"  case 0 {{ x q[{q0}]; }}",
            f"  case 1 {{ z q[{q0}]; }}",
            f"  case 2 {{ h q[{q0}]; }}",
            f"  default {{ y q[{q0}]; }}",
            f"}}",
        ]
        params = {"q0": q0, "q1": q1}
    elif v == 2:
        vn = "switch_on_int_bit3_partial_fill"
        desc = "Measure into bit[3] (partial), switch on its int value."
        q2 = pick_qubit(meta, rng)
        core = [
            f"bit[3] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"__cc_b[2] = measure q[{q2}];",
            f"int __cc_i = int(__cc_b);",
            f"switch (__cc_i % 4) {{ case 0 {{x q[{q0}];}} case 1 {{z q[{q0}];}} default {{h q[{q0}];}} }}",
        ]
        params = {"q0": q0, "q1": q1, "q2": q2}
    elif v == 3:
        vn = "switch_with_binary_constants"
        desc = "Switch on int(bit[2]) and use explicit binary-looking cases (0,1,2,3)."
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"int __cc_i = int(__cc_b);",
            f"switch (__cc_i) {{ case 0 {{x q[{q0}];}} case 1 {{z q[{q0}];}} case 2 {{h q[{q0}];}} case 3 {{y q[{q0}];}} }}",
        ]
        params = {"q0": q0, "q1": q1}
    else:
        vn = "switch_on_bit2_then_measure_again"
        desc = "Switch determines an extra gate, then do an extra measurement."
        core = [
            f"bit[2] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"switch (int(__cc_b) % 2) {{ case 0 {{x q[{q0}];}} default {{z q[{q0}];}} }}",
            f"bit __cc_m2 = measure q[{q0}];",
        ]
        params = {"q0": q0, "q1": q1}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(16, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_17(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[17]
    q = pick_qubit(meta, rng)
    tags = ["for", "set_iteration"]
    features = ["for-in-set", "measure", "param_gate"]
    req = ["supports_for"]

    # random set of distinct ints
    vals = sorted(set(rng.sample(range(0, 8), rng.randint(3, 5))))
    it_set = "{" + ",".join(str(x) for x in vals) + "}"

    if v == 1:
        vn = "for_set_apply_param_rz"
        desc = "Iterate a discrete set; each element scales angle for RZ."
        base = round(rng.uniform(0.1, 1.2), 6)
        core = [
            f"angle __cc_base = {base};",
            f"for int __cc_i in {it_set} {{",
            f"  angle __cc_th = angle(float(__cc_i) * float(__cc_base));",
            f"  rz(__cc_th) q[{q}];",
            f"}}",
        ]
        features += ["angle", "cast"]
        req += ["supports_angle", "supports_casts"]
        params = {"q": q, "set": vals, "base": base}
    elif v == 2:
        vn = "for_set_measure_and_sum"
        desc = "Iterate a set; measure each time and sum into an int."
        core = [
            f"int __cc_sum = 0;",
            f"for int __cc_i in {it_set} {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  __cc_sum = __cc_sum + int(__cc_m);",
            f"  h q[{q}];",
            f"}}",
            f"if (__cc_sum > 0) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        features += ["if/else"]
        req += ["supports_if"]
        params = {"q": q, "set": vals}
    elif v == 3:
        vn = "for_set_switch_inside"
        desc = "Iterate set; within loop use switch(i%3) to vary gate."
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  switch (__cc_i % 3) {{",
            f"    case 0 {{ x q[{q}]; }}",
            f"    case 1 {{ z q[{q}]; }}",
            f"    default {{ h q[{q}]; }}",
            f"  }}",
            f"}}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q, "set": vals}
    else:
        vn = "for_set_break_on_measure"
        desc = "Iterate set; break early when measurement hits 1."
        core = [
        f"int __cc_stop = {vals[-1]};",
        f"for int __cc_i in {it_set} {{",
        f"  if (__cc_i == __cc_stop) {{ break; }}",
        f"  x q[{q}];",
        f"}}",
        ]
        params = {"q": q, "set": vals, "stop": vals[-1]}
        features += ["break", "if"]
        req += ["supports_break", "supports_if"]


    meas = measure_all_block(meta, "__cc_out")
    return _mk(17, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_18(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[18]
    q = pick_qubit(meta, rng)
    tags = ["array", "for", "iteration"]
    features = ["array[T,N]", "for-in-array", "param_gate"]
    req = ["supports_arrays", "supports_for"]

    N = rng.randint(3, 6)
    if v in (1, 2):
        # angle array
        angles = [rand_angle_const(rng) for _ in range(N)]
        arr_init = "{" + ",".join(str(a) for a in angles) + "}"
        if v == 1:
            vn = "iterate_angle_array_rz"
            desc = "Iterate an angle array; apply RZ for each element."
            core = [
                f"array[angle, {N}] __cc_angles = {arr_init};",
                f"for angle __cc_a in __cc_angles {{",
                f"  rz(__cc_a) q[{q}];",
                f"}}",
            ]
            params = {"q": q, "angles": angles}
            req += ["supports_angle"]
        else:
            vn = "iterate_angle_array_with_if"
            desc = "Iterate angle array; branch on index parity to pick RZ vs RX."
            core = [
                f"array[angle, {N}] __cc_angles = {arr_init};",
                f"int __cc_i = 0;",
                f"for angle __cc_a in __cc_angles {{",
                f"  if ((__cc_i % 2) == 0) {{ rz(__cc_a) q[{q}]; }} else {{ rx(__cc_a) q[{q}]; }}",
                f"  __cc_i = __cc_i + 1;",
                f"}}",
            ]
            features += ["if/else", "counter_update", "mod(%)"]
            req += ["supports_if", "supports_angle"]
            params = {"q": q, "angles": angles}
    elif v == 3:
        # int array
        vals = [rng.randint(0, 3) for _ in range(N)]
        arr_init = "{" + ",".join(str(x) for x in vals) + "}"
        vn = "iterate_int_array_switch_gate"
        desc = "Iterate int array; switch on element to choose gate."
        core = [
            f"array[int, {N}] __cc_vals = {arr_init};",
            f"for int __cc_x in __cc_vals {{",
            f"  switch (__cc_x) {{ case 0 {{x q[{q}];}} case 1 {{z q[{q}];}} default {{h q[{q}];}} }}",
            f"}}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q, "vals": vals}
    else:
        # mixed: measure into array-like accumulation
        vn = "iterate_angle_array_measure_gate"
        desc = "Iterate angle array; measure each time and conditionally apply param gate."
        angles = [rand_angle_const(rng) for _ in range(N)]
        arr_init = "{" + ",".join(str(a) for a in angles) + "}"
        core = [
            f"array[angle, {N}] __cc_angles = {arr_init};",
            f"for angle __cc_a in __cc_angles {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  if (__cc_m) {{ rz(__cc_a) q[{q}]; }} else {{ rx(__cc_a) q[{q}]; }}",
            f"}}",
        ]
        features += ["measure", "if/else"]
        req += ["supports_if", "supports_angle"]
        params = {"q": q, "angles": angles}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(18, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_19(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[19]
    q = pick_qubit(meta, rng)
    tags = ["extern"]
    features = ["extern_decl", "extern_call", "branch_on_return"]
    req = ["supports_extern", "linker_or_stub_available"]

    w = rng.choice([8, 16])
    x = rand_small_int(rng, 0, 255)

    if v == 1:
        vn = "extern_uint_to_uint"
        desc = "Declare extern f(uint[w])->uint[w], call it, branch on low bit."
        core = [
            f"extern __cc_f(uint[{w}]) -> uint[{w}];",
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = __cc_f(__cc_x);",
            f"if ((__cc_y & 1) == 1) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        params = {"q": q, "w": w, "x": x}
    elif v == 2:
        vn = "extern_then_switch_low2"
        desc = "Extern call; switch on low 2 bits of return."
        core = [
            f"extern __cc_f(uint[{w}]) -> uint[{w}];",
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = __cc_f(__cc_x);",
            f"int __cc_i = int(__cc_y & 3);",
            f"switch (__cc_i) {{ case 0 {{x q[{q}];}} case 1 {{z q[{q}];}} default {{h q[{q}];}} }}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q, "w": w, "x": x}
    elif v == 3:
        vn = "extern_bool_return"
        desc = "Extern returns bit; branch to choose correction."
        core = [
            f"extern __cc_g(uint[{w}]) -> bit;",
            f"uint[{w}] __cc_x = {x};",
            f"bit __cc_b = __cc_g(__cc_x);",
            f"if (__cc_b) {{ x q[{q}]; }} else {{ h q[{q}]; }}",
        ]
        params = {"q": q, "w": w, "x": x}
    else:
        vn = "extern_then_angle_cast"
        desc = "Extern returns uint; convert to angle and apply param gate."
        scale = round(rng.uniform(0.05, 0.5), 6)
        core = [
            f"extern __cc_f(uint[{w}]) -> uint[{w}];",
            f"uint[{w}] __cc_x = {x};",
            f"uint[{w}] __cc_y = __cc_f(__cc_x);",
            f"float __cc_fv = float(__cc_y) * {scale};",
            f"angle __cc_th = angle(__cc_fv);",
            f"rz(__cc_th) q[{q}];",
        ]
        features += ["cast", "angle"]
        req += ["supports_casts", "supports_angle"]
        params = {"q": q, "w": w, "x": x, "scale": scale}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(19, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_20(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[20]
    q = pick_qubit(meta, rng)
    n = rng.randint(3, 6)
    tags = ["nested", "for", "switch", "if"]
    features = ["for", "switch/case", "if/else"]
    req = ["supports_for", "supports_switch", "supports_if"]

    it_set = set_literal_0_to(n)

    if v == 1:
        vn = "loop_switch_then_if"
        desc = "Inside loop: switch(i%3), and one case has an if guard."
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  switch (__cc_i % 3) {{",
            f"    case 0 {{ x q[{q}]; }}",
            f"    case 1 {{ if (__cc_i > 1) {{ z q[{q}]; }} else {{ h q[{q}]; }} }}",
            f"    default {{ y q[{q}]; }}",
            f"  }}",
            f"}}",
        ]
        params = {"q": q, "n": n}
    elif v == 2:
        vn = "loop_measure_switch"
        desc = "Loop: measure each iter, switch on int(meas)+i%2."
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  int __cc_k = int(__cc_m) + (__cc_i % 2);",
            f"  h q[{q}];",
            f"  switch (__cc_k) {{ case 0 {{x q[{q}];}} case 1 {{z q[{q}];}} default {{h q[{q}];}} }}",
            f"}}",
        ]
        features += ["measure", "cast_int"]
        params = {"q": q, "n": n}
    elif v == 3:
        vn = "loop_switch_break"
        desc = "Loop: switch on i; break on a specific case."
        stop = rng.randint(1, n - 1)
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  switch (__cc_i) {{",
            f"    case {stop} {{ break; }}",
            f"    default {{ x q[{q}]; }}",
            f"  }}",
            f"}}",
        ]
        features += ["break"]
        req += ["supports_break"]
        params = {"q": q, "n": n, "stop": stop}
    else:
        vn = "nested_two_level_switch"
        desc = "Two-level control: switch outside, if+switch inside."
        core = [
            f"int __cc_s = {rng.randint(0, 3)};",
            f"switch (__cc_s) {{",
            f"  case 0 {{ x q[{q}]; }}",
            f"  default {{",
            f"    bit __cc_m = measure q[{q}];",
            f"    if (__cc_m) {{ switch (1) {{ case 1 {{ z q[{q}]; }} }} }} else {{ h q[{q}]; }}",
            f"  }}",
            f"}}",
        ]
        params = {"q": q}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(20, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_21(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[21]
    q = pick_qubit(meta, rng)
    shots = rng.randint(3, 7)
    thr = rng.randint(1, shots)
    tags = ["for", "accumulate", "measure"]
    features = ["for", "measure", "int/uint_accum", "if/else"]
    req = ["supports_for", "supports_if"]

    it_set = set_literal_0_to(shots)

    if v == 1:
        vn = "count_ones_then_threshold_gate"
        desc = "Repeat measurement in for-loop, count ones, threshold decides a gate."
        core = [
            f"int __cc_cnt = 0;",
            f"for int __cc_i in {it_set} {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  __cc_cnt = __cc_cnt + int(__cc_m);",
            f"  x q[{q}];",
            f"}}",
            f"if (__cc_cnt >= {thr}) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        params = {"q": q, "shots": shots, "thr": thr}
    elif v == 2:
        vn = "count_ones_then_switch_bucket"
        desc = "Count ones then switch on cnt%3 to choose gate bucket."
        core = [
            f"int __cc_cnt = 0;",
            f"for int __cc_i in {it_set} {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  __cc_cnt = __cc_cnt + int(__cc_m);",
            f"  x q[{q}];",
            f"}}",
            f"switch (__cc_cnt % 3) {{ case 0 {{x q[{q}];}} case 1 {{z q[{q}];}} default {{h q[{q}];}} }}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q, "shots": shots}
    elif v == 3:
        vn = "early_break_when_reach_thr"
        desc = "Accumulate and break early once threshold reached."
        core = [
            f"int __cc_cnt = 0;",
            f"for int __cc_i in {it_set} {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  __cc_cnt = __cc_cnt + int(__cc_m);",
            f"  if (__cc_cnt >= {thr}) {{ break; }}",
            f"  x q[{q}];",
            f"}}",
            f"if (__cc_cnt >= {thr}) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        features += ["break"]
        req += ["supports_break"]
        params = {"q": q, "shots": shots, "thr": thr}
    else:
        vn = "use_uint_counter"
        desc = "Use uint counter and compare; then apply correction."
        w = rng.choice([4, 5, 6, 8])
        core = [
            f"uint[{w}] __cc_cnt = 0;",
            f"for int __cc_i in {it_set} {{",
            f"  bit __cc_m = measure q[{q}];",
            f"  __cc_cnt = __cc_cnt + uint(__cc_m);",
            f"  x q[{q}];",
            f"}}",
            f"if (__cc_cnt >= {thr}) {{ x q[{q}]; }} else {{ h q[{q}]; }}",
        ]
        features += ["uint", "cast_uint"]
        req += ["supports_uint", "supports_casts"]
        params = {"q": q, "shots": shots, "thr": thr, "w": w}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(21, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_22(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[22]
    q = pick_qubit(meta, rng)
    tags = ["end", "early_stop"]
    features = ["end", "if/else", "measure"]
    req = ["supports_end", "supports_if"]

    if v == 1:
        vn = "end_if_meas_one"
        desc = "Measure; if 1 then end immediately, else continue."
        core = [
            f"bit __cc_m = measure q[{q}];",
            f"if (__cc_m) {{ end; }}",
            f"x q[{q}];",
        ]
        params = {"q": q}
    elif v == 2:
        vn = "end_if_counter_reaches_thr"
        desc = "Count a few measurements; if threshold hit, end early."
        shots = rng.randint(2, 5)
        thr = rng.randint(1, shots)
        it_set = set_literal_0_to(shots)
        core = [
        f"int __cc_cnt = 0;",
        f"for int __cc_i in {it_set} {{",
        f"  x q[{q}];",
        f"  if ((__cc_i % 2) == 0) {{ __cc_cnt = __cc_cnt + 1; }}",
        f"}}",
        f"if (__cc_cnt >= {thr}) {{ end; }}",
        f"h q[{q}];",
        ]
        features += ["for", "mod"]  
        req += ["supports_for"]
        params = {"q": q, "shots": shots, "thr": thr}
    elif v == 3:
        vn = "end_in_switch_case"
        desc = "Switch on measured bit; one case ends program."
        core = [
            f"bit __cc_m = measure q[{q}];",
            f"int __cc_i = int(__cc_m);",
            f"switch (__cc_i) {{ case 0 {{ x q[{q}]; }} case 1 {{ end; }} }}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q}
    else:
        vn = "end_after_failed_retries"
        desc = "Retry a few times; if never see 1, end; else apply correction."
        tries = rng.randint(2, 5)
        core = [
        f"bit __cc_seen = 0;",
        f"for int __cc_i in {set_literal_0_to(tries)} {{",
        f"  if (__cc_i == {tries - 1}) {{ __cc_seen = 1; break; }}",
        f"  x q[{q}];",
        f"}}",
        f"if (!__cc_seen) {{ end; }}",
        f"z q[{q}];",
        ]
        params = {"q": q, "tries": tries, "hit": tries - 1}
        features += ["for", "break", "logical_not"]
        req += ["supports_for", "supports_break", "supports_logical_ops"]

    meas = measure_all_block(meta, "__cc_out")
    return _mk(22, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

def theme_23(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[23]
    q0, q1 = pick_two_qubits(meta, rng)
    tags = ["let", "slice", "for"]
    features = ["bit[n]", "slice", "let", "for-in-slice"]
    req = ["supports_let", "supports_slices", "supports_for"]

    n = rng.choice([4, 6, 8])
    lo = 0
    hi = n // 2  # keep simple

    if v == 1:
        vn = "slice_iterate_count_ones"
        desc = "Measure into bit[n], slice first half, iterate slice to count ones."
        core = [
            f"bit[{n}] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"let __cc_s = __cc_b[{lo}:{hi}];",
            f"int __cc_cnt = 0;",
            f"for bit __cc_x in __cc_s {{ __cc_cnt = __cc_cnt + int(__cc_x); }}",
            f"if (__cc_cnt > 0) {{ x q[{q0}]; }} else {{ z q[{q0}]; }}",
        ]
        features += ["measure", "if/else"]
        req += ["supports_if", "supports_casts"]
        params = {"q0": q0, "q1": q1, "n": n, "slice": [lo, hi]}
    elif v == 2:
        vn = "slice_iterate_parity"
        desc = "Iterate slice and compute parity via XOR."
        core = [
            f"bit[{n}] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"let __cc_s = __cc_b[{lo}:{hi}];",
            f"bit __cc_par = 0;",
            f"for bit __cc_x in __cc_s {{ __cc_par = __cc_par ^ __cc_x; }}",
            f"if (__cc_par) {{ x q[{q0}]; }} else {{ h q[{q0}]; }}",
        ]
        features += ["bitwise_xor", "if/else"]
        req += ["supports_if"]
        params = {"q0": q0, "q1": q1, "n": n}
    elif v == 3:
        vn = "slice_iterate_switch_on_count"
        desc = "Count ones in slice then switch on count%3."
        core = [
            f"bit[{n}] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"let __cc_s = __cc_b[{lo}:{hi}];",
            f"int __cc_cnt = 0;",
            f"for bit __cc_x in __cc_s {{ __cc_cnt = __cc_cnt + int(__cc_x); }}",
            f"switch (__cc_cnt % 3) {{ case 0 {{x q[{q0}];}} case 1 {{z q[{q0}];}} default {{h q[{q0}];}} }}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q0": q0, "q1": q1, "n": n}
    else:
        vn = "slice_iterate_break_on_one"
        desc = "Iterate slice and break once a 1 is found."
        core = [
            f"bit[{n}] __cc_b;",
            f"__cc_b[0] = measure q[{q0}];",
            f"__cc_b[1] = measure q[{q1}];",
            f"let __cc_s = __cc_b[{lo}:{hi}];",
            f"bit __cc_found = 0;",
            f"for bit __cc_x in __cc_s {{ if (__cc_x) {{ __cc_found = 1; break; }} }}",
            f"if (__cc_found) {{ x q[{q0}]; }} else {{ z q[{q0}]; }}",
        ]
        features += ["break", "if"]
        req += ["supports_break", "supports_if"]
        params = {"q0": q0, "q1": q1, "n": n}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(23, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

# def theme_24(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
#     theme_name = THEME_NAMES[24]
#     q = pick_qubit(meta, rng)
#     tags = ["membership", "in", "if"]
#     features = ["in_set_test", "if/else", "for"]
#     req = ["supports_in_operator", "supports_if", "supports_for"]

#     n = rng.randint(4, 8)
#     it_set = set_literal_0_to(n)
#     # subset for membership test
#     subset = sorted(set(rng.sample(range(0, n), rng.randint(2, max(2, n//2)))))
#     subset_lit = "{" + ",".join(str(x) for x in subset) + "}"

#     if v == 1:
#         vn = "if_i_in_subset_then_x"
#         desc = "Loop; if index in subset then apply X else Z."
#         core = [
#             f"for int __cc_i in {it_set} {{",
#             f"  if (__cc_i in {subset_lit}) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
#             f"}}",
#         ]
#         params = {"q": q, "n": n, "subset": subset}
#     elif v == 2:
#         vn = "if_i_in_subset_then_measure"
#         desc = "Loop; only measure on indices in subset; otherwise apply a gate."
#         core = [
#             f"int __cc_sum = 0;",
#             f"for int __cc_i in {it_set} {{",
#             f"  if (__cc_i in {subset_lit}) {{ bit __cc_m = measure q[{q}]; __cc_sum = __cc_sum + int(__cc_m); }}",
#             f"  else {{ h q[{q}]; }}",
#             f"}}",
#         ]
#         features += ["measure", "accum"]
#         params = {"q": q, "n": n, "subset": subset}
#     elif v == 3:
#         vn = "in_subset_break"
#         desc = "Loop; if index in subset and measurement is 1, break."
#         core = [
#             f"for int __cc_i in {it_set} {{",
#             f"  if (__cc_i in {subset_lit}) {{",
#             f"    bit __cc_m = measure q[{q}];",
#             f"    if (__cc_m) {{ break; }}",
#             f"  }}",
#             f"  x q[{q}];",
#             f"}}",
#         ]
#         features += ["break", "nested_if"]
#         req += ["supports_break"]
#         params = {"q": q, "n": n, "subset": subset}
#     else:
#         vn = "in_subset_switch_bucket"
#         desc = "Use membership test to set a flag, then switch on it."
#         core = [
#             f"int __cc_flag = 0;",
#             f"for int __cc_i in {it_set} {{",
#             f"  if (__cc_i in {subset_lit}) {{ __cc_flag = 1; }}",
#             f"}}",
#             f"switch (__cc_flag) {{ case 0 {{z q[{q}];}} case 1 {{x q[{q}];}} }}",
#         ]
#         features += ["switch/case"]
#         req += ["supports_switch"]
#         params = {"q": q, "n": n, "subset": subset}

#     meas = measure_all_block(meta, "__cc_out")
#     return _mk(24, v, theme_name=theme_name, variant_name=vn, description=desc,
#                tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

# old theme 24 is correct but not supported by current parser.
# below is the new theme 24:

def theme_24(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:

    theme_name = THEME_NAMES[24]
    q = pick_qubit(meta, rng)

    tags = ["membership", "if", "for"]
    features = ["expanded_membership_test", "if/else", "for"]
    req = ["supports_if", "supports_for"]

    n = rng.randint(4, 8)
    it_set = set_literal_0_to(n)

    subset = sorted(set(rng.sample(range(0, n), rng.randint(2, max(2, n // 2)))))

    def memb_expr(var: str) -> str:
        return "(" + " || ".join(f"({var} == {x})" for x in subset) + ")"

    cond = memb_expr("__cc_i")

    if v == 1:
        vn = "if_i_in_subset_then_x"
        desc = "Loop; if index is in subset then apply X else Z (membership expanded to ==/||)."
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  if {cond} {{ x q[{q}]; }} else {{ z q[{q}]; }}",
            f"}}",
        ]
        params = {"q": q, "n": n, "subset": subset}

    elif v == 2:
        vn = "subset_parity_switch_bucket"
        desc = "Toggle a flag on each hit (parity), then switch on the flag (membership via ==/||)."
        core = [
            f"int __cc_flag = 0;",
            f"for int __cc_i in {it_set} {{",
            f"  if {cond} {{ __cc_flag = 1 - __cc_flag; }}",
            f"}}",
            f"switch (__cc_flag) {{ case 0 {{ z q[{q}]; }} case 1 {{ x q[{q}]; }} }}",
        ]
        features += ["switch/case"]
        req += ["supports_switch"]
        params = {"q": q, "n": n, "subset": subset}

    elif v == 3:
        vn = "subset_hit_measure_break"
        desc = "On membership hit, measure and break if 1; otherwise apply X each iteration."
        core = [
            f"for int __cc_i in {it_set} {{",
            f"  if {cond} {{",
            f"    bit __cc_m = measure q[{q}];",
            f"    if (__cc_m) {{ break; }}",
            f"  }}",
            f"  x q[{q}];",
            f"}}",
        ]
        features += ["measure", "break", "nested_if"]
        req += ["supports_break"]
        params = {"q": q, "n": n, "subset": subset}

    else:
        vn = "subset_mask_reduce_count"
        desc = "Build a bit[n] mask for membership, then reduce (count ones) and branch."
        core = [
            f"bit[{n}] __cc_mask;",
            f"for int __cc_i in {it_set} {{ __cc_mask[__cc_i] = 0; }}",
            f"for int __cc_i in {it_set} {{",
            f"  if {cond} {{ __cc_mask[__cc_i] = 1; }}",
            f"}}",
            f"int __cc_cnt = 0;",
            f"for bit __cc_b in __cc_mask {{ __cc_cnt = __cc_cnt + int(__cc_b); }}",
            f"if (__cc_cnt > 0) {{ x q[{q}]; }} else {{ z q[{q}]; }}",
        ]
        features += ["bit[n]", "for-in-bit-array", "casts", "reduce"]
        req += ["supports_bit_arrays", "supports_casts"]
        params = {"q": q, "n": n, "subset": subset}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(
        24,
        v,
        theme_name=theme_name,
        variant_name=vn,
        description=desc,
        tags=tags,
        features=features,
        requirements=req,
        params=params,
        core=core,
        meas=meas,
    )


def theme_25(meta: Dict[str, Any], rng: random.Random, v: int) -> CoreTaskInstance:
    theme_name = THEME_NAMES[25]
    q = pick_qubit(meta, rng)
    tags = ["switch", "const_expr", "no_default"]
    features = ["const", "switch/case", "const_expr_case", "optional_default"]
    req = ["supports_switch", "supports_const"]

    A = rng.randint(1, 4)
    B = rng.randint(1, 4)
    x = rng.randint(0, 5)

    if v == 1:
        vn = "case_const_expr_no_default"
        desc = "Switch with case labels as const-expressions, no default (no-op allowed)."
        core = [
            f"const int __cc_A = {A};",
            f"const int __cc_B = {B};",
            f"int __cc_x = {x};",
            f"switch (__cc_x) {{",
            f"  case __cc_A + 1 {{ x q[{q}]; }}",
            f"  case __cc_B + 2 {{ z q[{q}]; }}",
            f"}}",
        ]
        params = {"q": q, "A": A, "B": B, "x": x}
    elif v == 2:
        vn = "case_const_expr_with_default"
        desc = "Switch with const-expression cases and an explicit default."
        core = [
            f"const int __cc_A = {A};",
            f"int __cc_x = {x};",
            f"switch (__cc_x) {{",
            f"  case __cc_A + 1 {{ x q[{q}]; }}",
            f"  default {{ h q[{q}]; }}",
            f"}}",
        ]
        params = {"q": q, "A": A, "x": x}
    elif v == 3:
        vn = "switch_on_measured_then_const_cases"
        desc = "Switch on int(measurement)+const; case labels are const-expressions."
        core = [
            f"const int __cc_A = {A};",
            f"bit __cc_m = measure q[{q}];",
            f"int __cc_x = int(__cc_m) + __cc_A;",
            f"switch (__cc_x) {{ case __cc_A {{ z q[{q}]; }} case __cc_A + 1 {{ x q[{q}]; }} }}",
        ]
        features += ["measure", "cast_int"]
        params = {"q": q, "A": A}
    else:
        vn = "two_stage_const_switch"
        desc = "Compute expression, then switch with const-expression cases and no default."
        core = [
            f"const int __cc_A = {A};",
            f"const int __cc_B = {B};",
            f"int __cc_x = (__cc_A * 2 + __cc_B) % 6;",
            f"switch (__cc_x) {{ case 0 {{x q[{q}];}} case __cc_A + 1 {{z q[{q}];}} }}",
        ]
        params = {"q": q, "A": A, "B": B}

    meas = measure_all_block(meta, "__cc_out")
    return _mk(25, v, theme_name=theme_name, variant_name=vn, description=desc,
               tags=tags, features=features, requirements=req, params=params, core=core, meas=meas)

# -------------------- Registry --------------------

THEMES: Dict[int, ThemeFn] = {
    1: theme_01,  2: theme_02,  3: theme_03,  4: theme_04,  5: theme_05,
    6: theme_06,  7: theme_07,  8: theme_08,  9: theme_09,  10: theme_10,
    11: theme_11, 12: theme_12, 13: theme_13, 14: theme_14, 15: theme_15,
    16: theme_16, 17: theme_17, 18: theme_18, 19: theme_19, 20: theme_20,
    21: theme_21, 22: theme_22, 23: theme_23, 24: theme_24, 25: theme_25,
}

# -------------------- Public API --------------------

def generate_core_task(meta: Dict[str, Any], *, theme_id: int, variant_id: int, seed: Optional[int] = None) -> CoreTaskInstance:
    if theme_id not in THEMES:
        raise KeyError(f"Unknown theme_id={theme_id}")
    if variant_id not in (1, 2, 3, 4):
        raise ValueError("variant_id must be 1..4")
    rng = random.Random(seed)
    return THEMES[theme_id](meta, rng, variant_id)

def generate_core_task_from_meta_path(meta_path: str, *, theme_id: int, variant_id: int, seed: Optional[int] = None) -> CoreTaskInstance:
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return generate_core_task(meta, theme_id=theme_id, variant_id=variant_id, seed=seed)

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

def main(task_num: int = 100, base_seed: int = 20260108) -> None:

    background_dir = "classical_background"
    out_dir = "classical_train"
    os.makedirs(out_dir, exist_ok=True)

    variants = [2, 3, 4]

    # all backgrounds, sorted by filename
    all_bg_paths = sorted(glob.glob(os.path.join(background_dir, "bg_*.qasm")))
    if len(all_bg_paths) == 0:
        raise RuntimeError(f"No backgrounds found in {background_dir}")

    rng = random.Random(base_seed)

    for t in range(task_num):
        theme_id = (t % 25) + 1
        variant_id = variants[t % len(variants)]

        bg_path = rng.choice(all_bg_paths)
        bg_file = os.path.basename(bg_path)
        meta_path = bg_path.replace(".qasm", ".meta.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"Missing meta for {bg_file}: {meta_path}")

        bg_text = _read_text(bg_path)

        # deterministic per-task seed (reproducible)
        inst_seed = rng.randrange(1_000_000_000)

        inst = generate_core_task_from_meta_path(
            meta_path,
            theme_id=theme_id,
            variant_id=variant_id,
            seed=inst_seed,
        )

        full_qasm = assemble_full_task(bg_text, inst)

        task_fname = f"classical_task_{t:05d}_th{theme_id:02d}_v{variant_id}.qasm"
        task_path = os.path.join(out_dir, task_fname)
        _write_text(task_path, full_qasm)

    print(f"Done. Wrote {task_num} train tasks into: {out_dir}")


if __name__ == "__main__":
    task_num = 1000
    main(task_num=task_num)


