from __future__ import annotations
import os
import re
import io
import json
import time
import math
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from collections import Counter, defaultdict
from contextlib import redirect_stdout, redirect_stderr
import openqasm3
import QASM_simulator as sim


SHOTS_DIST_GOLDEN = 1000 # or recommend 8000 
SHOTS_DIST_CAND = 1000 ## or recommend 8000 

TOL_DIST_DEFAULT = 0.05
TOL_DIST_TIMING = 0.1

TOL_TIME_ABS = 1e-6
TOL_TOTAL_TIME_ABS = 1e-6

K_MAX_DEFAULT = 5

CACHE_DIR = "./.eval_cache_golden_v8"
REPORT_DIR = "./eval_reports"

SAVE_REPORT = True
REPORT_FILENAME_PREFIX = "eval_report"

TO_TEST="THE DIRECTORY THAT STORES LLM RESPONSES" # the folder in which you put all the llm generated OpenQASM scripts


#=============== where to find the files ===============

TASK_SPECS = {
    "classical": {
        "golden_dir": "./classical_test",
        "resp_dir": f"./{TO_TEST}/response_classical",
        "prefix": "classical_task_",
    },
    "complex": {
        "golden_dir": "./complex_test",
        "resp_dir": f"./{TO_TEST}/response_complex",
        "prefix": "complex_task_",
    },
    "pulse": {
        "golden_dir": "./pulse_test",
        "resp_dir": f"./{TO_TEST}/response_pulse",
        "prefix": "pulse_task_",
    },
    "timing": {
        "golden_dir": "./timing_test",
        "resp_dir": f"./{TO_TEST}/response_timing",
        "prefix": "timing_task_",
    },
}


# ============== useful structures ==============

@dataclass(frozen=True)
class TimelineEvent:
    t0: float
    t1: float
    dur: float
    kind: str
    resources: str

@dataclass
class CandidateResult:
    ok: bool
    syntax_ok: bool
    element_ok: bool
    dist_ok: Optional[bool] = None
    timeline_ok: Optional[bool] = None

    tvd: Optional[float] = None
    timeline_dist: Optional[float] = None

    detail: Optional[str] = None


# ============== funtions to find files ==============

def ensure_dir_exists(p: str) -> None:
    if not os.path.isdir(p):
        raise FileNotFoundError(f"Directory not found: {p}")

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def list_qasm_files(d: str) -> List[str]:
    return sorted([fn for fn in os.listdir(d) if fn.endswith(".qasm")])

def parse_task_id(prefix: str, filename: str) -> Optional[str]:
    m = re.fullmatch(rf"{re.escape(prefix)}(\d+)\.qasm", filename)
    if not m:
        return None
    return m.group(1).zfill(2)

def parse_candidate(prefix: str, filename: str) -> Optional[Tuple[str, int]]:
    m = re.fullmatch(rf"{re.escape(prefix)}(\d+)__k(\d+)\.qasm", filename)
    if not m:
        return None
    task_id = m.group(1).zfill(2)
    k = int(m.group(2))
    return task_id, k

def index_tasks(spec: dict) -> Tuple[Dict[str, str], Dict[str, Dict[int, str]], int]:
    gdir = spec["golden_dir"]
    rdir = spec["resp_dir"]
    prefix = spec["prefix"]

    ensure_dir_exists(gdir)
    ensure_dir_exists(rdir)

    golden = {}
    for fn in list_qasm_files(gdir):
        tid = parse_task_id(prefix, fn)
        if tid is None:
            continue
        golden[tid] = os.path.join(gdir, fn)

    cand = defaultdict(dict)
    k_max_found = 0
    for fn in list_qasm_files(rdir):
        parsed = parse_candidate(prefix, fn)
        if parsed is None:
            continue
        tid, k = parsed
        cand[tid][k] = os.path.join(rdir, fn)
        k_max_found = max(k_max_found, k)

    k_max = max(K_MAX_DEFAULT, k_max_found)
    return golden, cand, k_max


# ============== check syntax first=============

def parse_qasm_safely(qasm: str):
    return openqasm3.parse(qasm)

from typing import Dict


# ============== check existence of critical syntax components =============
def extract_exist_from_program(program) -> Dict[str, bool]:
    exist: Dict[str, bool] = {}

    def mark(k: str) -> None:
        if k:
            exist[k] = True

    def walk(node):
        if node is None:
            return
        if isinstance(node, (str, int, float, bool)):
            return

        if isinstance(node, (list, tuple)):
            for x in node:
                walk(x)
            return

        tname = type(node).__name__

        if tname == "BranchingStatement":
            mark("BranchingStatement")
            else_block = getattr(node, "else_block", None)
            if else_block:
                mark("has_else")

        elif tname == "WhileLoop":
            mark("WhileLoop")

        elif tname == "SwitchStatement":
            mark("SwitchStatement")

        elif tname == "FunctionCall":
            mark("FunctionCall")
            name_obj = getattr(node, "name", None)
            fname = getattr(name_obj, "name", None) if name_obj is not None else None
            if isinstance(fname, str) and fname:
                mark(f"func:{fname}")

        d = getattr(node, "__dict__", None)
        if isinstance(d, dict):
            for v in d.values():
                walk(v)

    walk(getattr(program, "statements", None))
    return exist

def extract_exist(qasm: str) -> Dict[str, bool]:
    program = parse_qasm_safely(qasm)
    return extract_exist_from_program(program)


# ============== distribution ==============

def normalize_dist(d: Dict[str, float]) -> Dict[str, float]:
    s = float(sum(d.values())) if d else 0.0
    if s <= 0.0:
        return {}
    return {k: float(v) / s for k, v in d.items()}

def tvd(dist_a: Dict[str, float], dist_b: Dict[str, float]) -> float:
    keys = set(dist_a.keys()) | set(dist_b.keys())
    l1 = 0.0
    for k in keys:
        l1 += abs(dist_a.get(k, 0.0) - dist_b.get(k, 0.0))
    return 0.5 * l1


def _align_outcome_counts(
    counts_a: Dict[str, int], counts_b: Dict[str, int]
) -> Tuple[List[str], List[int], List[int]]:
    """Align raw shot histograms without projecting or merging joint outcomes."""
    from collections.abc import Mapping
    from numbers import Integral

    histograms = []
    for name, counts in (("counts_a", counts_a), ("counts_b", counts_b)):
        if not isinstance(counts, Mapping):
            raise TypeError(f"{name} must map complete outcome labels to counts")
        validated = {}
        for outcome, count in counts.items():
            if not isinstance(outcome, str):
                raise TypeError(f"{name}: outcome labels must be strings")
            if isinstance(count, bool) or not isinstance(count, Integral) or count < 0:
                raise ValueError(f"{name}: counts must be nonnegative integers")
            if count:
                validated[outcome] = int(count)
        if not validated:
            raise ValueError(f"{name} must contain at least one observed shot")
        histograms.append(validated)
    # The likelihood calculation converts counts to float64, and the random
    # table sampler uses fixed-width integers. Reject totals that lose precision.
    if sum(sum(counts.values()) for counts in histograms) > 2**53 - 1:
        raise ValueError("Combined shot count exceeds the exact float64 integer range")
    outcomes = sorted(set(histograms[0]) | set(histograms[1]))
    return (
        outcomes,
        [histograms[0].get(outcome, 0) for outcome in outcomes],
        [histograms[1].get(outcome, 0) for outcome in outcomes],
    )


def multinomial_homogeneity_test(
    counts_a: Dict[str, int],
    counts_b: Dict[str, int],
    *,
    n_resamples: int = 9999,
    seed: Optional[int] = 0,
    alpha: float = 0.05,
) -> dict:
    """Conditional Monte Carlo G-test of two joint outcome distributions.

    Inputs are raw counts from two independent, fixed-size i.i.d. shot samples,
    not normalized probabilities. Each key identifies the complete measured
    outcome (for example, the simulator's joint classical-register label).
    Keeping joint labels preserves correlations between measured bits.

    The statistic is 2 * sum(O * log(O / E)) for the 2-by-K count table.
    Null tables retain both sample sizes and pooled outcome counts, using
    scipy.stats.random_table (Patefield sampling). Rare outcomes are retained;
    no large-expected-count chi-square approximation or pseudocounts are used.
    The Monte Carlo p-value is (exceedances + 1) / (n_resamples + 1), including
    ties. Non-rejection is not evidence that the distributions are equivalent.

    A local RNG makes repeated calls with the same seed reproducible without
    changing the simulator's random state.
    """
    from numbers import Integral
    import numpy as np
    from scipy.special import xlogy
    from scipy.stats import random_table

    if isinstance(n_resamples, bool) or not isinstance(n_resamples, Integral) or n_resamples < 1:
        raise ValueError("n_resamples must be a positive integer")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0):
        raise ValueError("seed must be a nonnegative integer or None")
    if isinstance(alpha, bool) or not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between zero and one")
    n_resamples = int(n_resamples)
    seed = None if seed is None else int(seed)
    outcomes, a, b = _align_outcome_counts(counts_a, counts_b)
    n_a, n_b = sum(a), sum(b)
    observed = np.asarray([a, b], dtype=np.int64)
    row_totals = observed.sum(axis=1)
    column_totals = observed.sum(axis=0)
    expected = np.outer(row_totals.astype(float), column_totals.astype(float)) / (n_a + n_b)
    statistic = max(0.0, float(2.0 * xlogy(observed, observed / expected).sum()))
    empirical_tvd = min(1.0, 0.5 * math.fsum(abs(x / n_a - y / n_b) for x, y in zip(a, b)))

    completed = 0
    exceedances = 0
    if len(outcomes) == 1:
        pvalue = 1.0  # The conditional table is constant; this is not equivalence.
    else:
        rng = np.random.default_rng(seed)
        batch_size = min(256, max(1, 1_000_000 // (2 * len(outcomes))))
        tie_tolerance = 64 * np.finfo(float).eps * max(1.0, statistic)
        while completed < n_resamples:
            batch = min(batch_size, n_resamples - completed)
            tables = random_table.rvs(
                row_totals, column_totals, size=batch,
                method="patefield", random_state=rng,
            )
            statistics = 2.0 * xlogy(tables, tables / expected).sum(axis=(1, 2))
            exceedances += int(np.count_nonzero(statistics >= statistic - tie_tolerance))
            completed += batch
        pvalue = (exceedances + 1) / (completed + 1)
    return {
        "statistic": statistic,
        "pvalue": pvalue,
        "reject_equal_distribution": bool(pvalue < alpha),
        "alpha": float(alpha),
        "empirical_tvd": empirical_tvd,
        "shots_a": n_a,
        "shots_b": n_b,
        "observed_outcomes": len(outcomes),
        "n_resamples": completed,
        "seed": seed,
    }


def _multinomial_tvd_radius(shots: int, support_size: int, failure_probability: float) -> float:
    """Invert the finite-alphabet L1 concentration bound in TVD units."""
    if support_size == 1:
        return 0.0
    # log(2**K - 2), without constructing an exponentially large integer.
    try:
        log_factor = support_size * math.log(2.0)
    except OverflowError:
        return 1.0
    log_factor += math.log1p(-2.0 * math.exp(-log_factor))
    return min(1.0, math.sqrt((log_factor - math.log(failure_probability)) / (2.0 * shots)))


def multinomial_tvd_interval(
    counts_a: Dict[str, int],
    counts_b: Dict[str, int],
    *,
    support_size: int,
    confidence_level: float = 0.95,
) -> dict:
    """Finite-sample confidence interval for TVD over the full outcome alphabet.

    Both histograms must be raw counts of complete joint outcomes from i.i.d.
    shots. support_size is a pre-specified upper bound on the union of all
    possible outcomes of both programs, including outcomes never observed.
    It must not be inferred from the observed support. For exactly m measured
    bits it is 2**m; a simulator label containing other registers may have a
    larger alphabet. This parameter is an assumption supplied by the caller.

    For alphabet size K > 1, use
        Pr(TVD(p_hat, p) >= r) <= (2**K - 2) * exp(-2 * n * r**2).
    This follows from a union bound over outcome subsets and one-sided
    Hoeffding bounds (also the L1 bound of Weissman et al., HPL-2003-97R1).
    Allocate half the failure probability to each sample and apply the
    triangle inequality to their two radii. No binary variance approximation,
    normal approximation, support truncation or smoothing is used.

    Coverage is at least confidence_level for a fixed comparison under the
    stated sampling/support assumptions. The bound is conservative; large
    alphabets or small samples can yield [0, 1]. Repeated/adaptive comparisons
    require a separate error-budget policy.
    """
    from numbers import Integral

    if isinstance(support_size, bool) or not isinstance(support_size, Integral) or support_size < 1:
        raise ValueError("support_size must be a positive integer")
    if (isinstance(confidence_level, bool) or not math.isfinite(confidence_level)
            or not 0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be strictly between zero and one")
    support_size = int(support_size)
    outcomes, a, b = _align_outcome_counts(counts_a, counts_b)
    if support_size < len(outcomes):
        raise ValueError("support_size is smaller than the observed union of outcomes")
    n_a, n_b = sum(a), sum(b)
    distance = min(1.0, 0.5 * math.fsum(abs(x / n_a - y / n_b) for x, y in zip(a, b)))
    failure_probability = (1.0 - confidence_level) / 2.0
    radius_a = _multinomial_tvd_radius(n_a, support_size, failure_probability)
    radius_b = _multinomial_tvd_radius(n_b, support_size, failure_probability)
    return {
        "empirical_tvd": distance,
        "lower": max(0.0, distance - radius_a - radius_b),
        "upper": min(1.0, distance + radius_a + radius_b),
        "confidence_level": float(confidence_level),
        "radius_a": radius_a,
        "radius_b": radius_b,
        "shots_a": n_a,
        "shots_b": n_b,
        "support_size": support_size,
        "observed_outcomes": len(outcomes),
    }


def multinomial_equivalence_test(
    counts_a: Dict[str, int],
    counts_b: Dict[str, int],
    *,
    support_size: int,
    tolerance: float,
    confidence_level: float = 0.95,
) -> dict:
    """Compare a multinomial TVD interval with a pre-specified tolerance.

    Return 'equivalent' only if the entire interval is within tolerance,
    'different' if its lower endpoint exceeds tolerance, or 'inconclusive'
    otherwise. Equivalence means TVD <= tolerance, not exact equality or
    equality of quantum states beyond the measured output distribution.
    Tolerance and support_size must be fixed independently of these samples.
    """
    if isinstance(tolerance, bool) or not math.isfinite(tolerance) or not 0.0 <= tolerance <= 1.0:
        raise ValueError("tolerance must be between zero and one")
    interval = multinomial_tvd_interval(
        counts_a, counts_b, support_size=support_size,
        confidence_level=confidence_level,
    )
    if interval["upper"] <= tolerance:
        decision = "equivalent"
    elif interval["lower"] > tolerance:
        decision = "different"
    else:
        decision = "inconclusive"
    return {**interval, "tolerance": float(tolerance), "decision": decision}


def simulate_distribution_safely(qasm: str, shots: int) -> Dict[str, float]:
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        d = sim.simulate_qasm_distribution(qasm, shots=shots)
    return normalize_dist(d)


# ============== timeline ==============

def simulate_timeline_text_safely(qasm: str) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        return sim.simulate_timeline(qasm, shots=1, show_details=True)

def _is_timeline_row(line: str) -> bool:
    return bool(re.match(r"^\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?\s+", line))

def _strip_scope(kind: str) -> str:
    return kind.split("#", 1)[0].strip()

def parse_timeline_events(timeline_text: str) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []
    for line in timeline_text.splitlines():
        if not _is_timeline_row(line):
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue
        try:
            t0 = float(parts[0])
            t1 = float(parts[1])
            dur = float(parts[2])
        except Exception:
            continue
        kind = _strip_scope(parts[3])
        resources = parts[4].strip()
        events.append(TimelineEvent(t0=t0, t1=t1, dur=dur, kind=kind, resources=resources))
    return events

def timeline_total_time(events: List[TimelineEvent]) -> float:
    if not events:
        return 0.0
    return max(ev.t1 for ev in events)

def timeline_signature(events: List[TimelineEvent]) -> Tuple[Counter, float]:
    c = Counter((ev.kind, ev.resources) for ev in events)
    total = timeline_total_time(events)
    return c, total

def timeline_strict_match(a: List[TimelineEvent], b: List[TimelineEvent], tol_time_abs: float) -> bool:
    if len(a) != len(b):
        return False
    for ea, eb in zip(a, b):
        if ea.kind != eb.kind:
            return False
        if ea.resources != eb.resources:
            return False
        if abs(ea.t0 - eb.t0) > tol_time_abs:
            return False
        if abs(ea.t1 - eb.t1) > tol_time_abs:
            return False
    return True

def timeline_coarse_match(a: List[TimelineEvent], b: List[TimelineEvent], tol_total_abs: float) -> bool:
    ca, ta = timeline_signature(a)
    cb, tb = timeline_signature(b)
    if ca != cb:
        return False
    if abs(ta - tb) > tol_total_abs:
        return False
    return True


# ============== timeline distance (for analysis only)=============
def timeline_distance_normalized(g: List[TimelineEvent], c: List[TimelineEvent]) -> float:
    tg = timeline_total_time(g)
    scale = max(tg, 1e-12)

    if len(g) == len(c):
        alignable = True
        for eg, ec in zip(g, c):
            if eg.kind != ec.kind or eg.resources != ec.resources:
                alignable = False
                break
        if alignable and len(g) > 0:
            acc = 0.0
            for eg, ec in zip(g, c):
                acc += abs(eg.t0 - ec.t0) + abs(eg.t1 - ec.t1)
            return (acc / (2.0 * len(g))) / scale

    tc = timeline_total_time(c)
    len_pen = abs(len(g) - len(c)) / max(len(g), 1)
    time_pen = abs(tg - tc) / scale
    return 1.0 + len_pen + time_pen


# ============== golden criterion cache ==============

def sha256_text(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8"))
    return h.hexdigest()

def golden_cache_path(task_type: str, tid: str) -> str:
    return os.path.join(CACHE_DIR, f"golden_{task_type}_task_{tid}.json")

def load_golden_cache(task_type: str, tid: str, qasm_sha: str, shots: int) -> Optional[dict]:
    path = golden_cache_path(task_type, tid)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return None

    if obj.get("qasm_sha256") != qasm_sha:
        return None
    if obj.get("shots_dist") != shots:
        return None
    if "dist" not in obj or "timeline_events" not in obj:
        return None
    return obj

def save_golden_cache(task_type: str, tid: str, qasm_sha: str, shots: int,
                      dist: Dict[str, float], events: List[TimelineEvent]) -> None:
    path = golden_cache_path(task_type, tid)
    obj = {
        "task_type": task_type,
        "task_id": tid,
        "qasm_sha256": qasm_sha,
        "shots_dist": shots,
        "dist": dist,
        "timeline_events": [
            {"t0": e.t0, "t1": e.t1, "dur": e.dur, "kind": e.kind, "resources": e.resources}
            for e in events
        ],
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def decode_events(obj: dict) -> List[TimelineEvent]:
    out = []
    for e in obj.get("timeline_events", []):
        out.append(TimelineEvent(
            t0=float(e["t0"]),
            t1=float(e["t1"]),
            dur=float(e["dur"]),
            kind=str(e["kind"]),
            resources=str(e["resources"]),
        ))
    return out


# ============== score =============

def dist_tol_for_task(task_type: str) -> float:
    if task_type == "timing":
        return TOL_DIST_TIMING
    return TOL_DIST_DEFAULT

def timeline_ok_for_task(task_type: str, golden_events: List[TimelineEvent], cand_events: List[TimelineEvent]) -> bool:
    if task_type in ("timing", "complex"):
        return timeline_strict_match(golden_events, cand_events, tol_time_abs=TOL_TIME_ABS)
    return timeline_coarse_match(golden_events, cand_events, tol_total_abs=TOL_TOTAL_TIME_ABS)

def decide_ok(task_type: str, syntax_ok: bool, element_ok: bool,
              dist_ok: Optional[bool], timeline_ok: Optional[bool]) -> bool:
    if not syntax_ok or not element_ok:
        return False
    if task_type == "timing":
        return bool(timeline_ok)
    if task_type in ("classical", "pulse"):
        return bool(dist_ok)
    if task_type == "complex":
        return bool(dist_ok and timeline_ok)
    return False

def eval_candidate(
    task_type: str,
    cand_qasm: str,
    golden_exist: Dict[str, bool],
    golden_dist: Dict[str, float],
    golden_events: List[TimelineEvent],
) -> CandidateResult:
    
    # syntax

    try:
        program = parse_qasm_safely(cand_qasm)
    except Exception as e:
        return CandidateResult(
            ok=False,
            syntax_ok=False,
            element_ok=False,
            dist_ok=None,
            timeline_ok=None,
            detail=f"syntax parse failed: {e}",
        )

    try:
        cand_exist = extract_exist_from_program(program)
    except Exception as e:

        return CandidateResult(
            ok=False,
            syntax_ok=False,
            element_ok=False,
            dist_ok=None,
            timeline_ok=None,
            detail=f"exist extraction failed: {e}",
        )

    # critical elements / structure
    missing = [k for k, v in golden_exist.items() if v and not cand_exist.get(k, False)]
    element_ok = (len(missing) == 0)
    if not element_ok:
        return CandidateResult(
            ok=False,
            syntax_ok=True,
            element_ok=False,
            dist_ok=None,
            timeline_ok=None,
            detail=f"exist missing: {missing[:20]}" + (" ..." if len(missing) > 20 else ""),
        )

    # distribution
    dist_err = None
    dist_ok = None
    try:
        cand_dist = simulate_distribution_safely(cand_qasm, shots=SHOTS_DIST_CAND)
        dist_err = tvd(golden_dist, cand_dist)
        dist_ok = (dist_err <= dist_tol_for_task(task_type))
    except Exception as e:
        dist_err = None
        dist_ok = False

    # timeline
    tl_dist = None
    tl_ok = None
    try:
        cand_tl_text = simulate_timeline_text_safely(cand_qasm)
        cand_events = parse_timeline_events(cand_tl_text)
        tl_dist = timeline_distance_normalized(golden_events, cand_events)
        tl_ok = timeline_ok_for_task(task_type, golden_events, cand_events)
    except Exception as e:
        tl_dist = None
        tl_ok = False

    ok = decide_ok(task_type, True, True, dist_ok, tl_ok)
    return CandidateResult(
        ok=ok,
        syntax_ok=True,
        element_ok=True,
        dist_ok=dist_ok,
        timeline_ok=tl_ok,
        tvd=dist_err,
        timeline_dist=tl_dist,
        detail=None,
    )


# ============== pass@k calculation ==============

def compute_pass_at_k(per_task_ok_by_k: Dict[str, Dict[int, bool]], k_max: int) -> Dict[int, float]:
    task_ids = sorted(per_task_ok_by_k.keys())
    if not task_ids:
        return {k: 0.0 for k in range(1, k_max + 1)}
    out = {}
    for K in range(1, k_max + 1):
        passed = 0
        for tid in task_ids:
            ok_map = per_task_ok_by_k.get(tid, {})
            hit = any(ok for kk, ok in ok_map.items() if kk <= K)
            if hit:
                passed += 1
        out[K] = passed / len(task_ids)
    return out

def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0

def pvariance(xs: List[float]) -> float:
    if xs is None or len(xs) < 2:
        return 0.0
    m = mean(xs)
    return mean([(x - m) ** 2 for x in xs])


def main() -> None:
    ensure_dir(CACHE_DIR)
    ensure_dir(REPORT_DIR)

    report = {}


    overall_per_task_ok_by_k: Dict[str, Dict[int, bool]] = defaultdict(dict)
    overall_k_max = 0

    overall_candidates_total = 0

    overall_syntax_err = 0
    overall_element_checked = 0
    overall_element_err = 0
    overall_simulated = 0
    overall_dist_err = 0
    overall_tvd_vals: List[float] = []
    overall_timeline_err = 0
    overall_tl_vals: List[float] = []

    overall_num_tasks = 0

    for task_type, spec in TASK_SPECS.items():
        golden_idx, cand_idx, k_max = index_tasks(spec)
        task_ids = sorted(golden_idx.keys())
        overall_num_tasks += len(task_ids)
        overall_k_max = max(overall_k_max, k_max)

        per_task_ok_by_k: Dict[str, Dict[int, bool]] = defaultdict(dict)

        cand_total = 0
        syntax_err = 0

        element_checked = 0  
        element_err = 0

        simulated = 0 
        dist_err = 0
        tvd_vals: List[float] = []

        timeline_err = 0
        tl_vals: List[float] = []

        golden_cache = {}
        for tid in task_ids:
            print(f"[info] preparing golden cache for {task_type} task {tid}...")
            gpath = golden_idx[tid]
            gqasm = read_text(gpath)
            gsha = sha256_text(gqasm)
            try:
                gprog = parse_qasm_safely(gqasm)
                gexist = extract_exist_from_program(gprog)
            except Exception as e:
                raise RuntimeError(f"Golden parse failed for {task_type}:{tid} ({gpath}): {e}") from e

            cached = load_golden_cache(task_type, tid, qasm_sha=gsha, shots=SHOTS_DIST_GOLDEN)
            if cached is not None:
                gdist = normalize_dist(cached["dist"])
                gevents = decode_events(cached)
            else:
                try:
                    gdist = simulate_distribution_safely(gqasm, shots=SHOTS_DIST_GOLDEN)
                    gtl_text = simulate_timeline_text_safely(gqasm)
                    gevents = parse_timeline_events(gtl_text)
                except Exception as e:
                    raise RuntimeError(f"Golden simulation failed for {task_type}:{tid} ({gpath}): {e}") from e
                save_golden_cache(task_type, tid, qasm_sha=gsha, shots=SHOTS_DIST_GOLDEN, dist=gdist, events=gevents)

            golden_cache[tid] = (gexist, gdist, gevents)

        for tid in task_ids:
            gexist, gdist, gevents = golden_cache[tid]
            cands = cand_idx.get(tid, {})

            overall_tid = f"{task_type}:{tid}"

            for k in range(0, k_max + 1):
                print(f"[info] evaluating {task_type} task {tid} candidate k={k}...")
                if k not in cands:
                    continue

                cand_total += 1
                overall_candidates_total += 1

                cpath = cands[k]
                cqasm = read_text(cpath)

                res = eval_candidate(task_type, cqasm, gexist, gdist, gevents)

                per_task_ok_by_k[tid][k] = bool(res.ok)
                overall_per_task_ok_by_k[overall_tid][k] = bool(res.ok)

                if not res.syntax_ok:
                    syntax_err += 1
                    overall_syntax_err += 1
                    continue

                element_checked += 1
                overall_element_checked += 1
                if not res.element_ok:
                    element_err += 1
                    overall_element_err += 1
                    continue

                simulated += 1
                overall_simulated += 1

                if res.dist_ok is False:
                    dist_err += 1
                    overall_dist_err += 1
                if res.tvd is not None:
                    tvd_vals.append(float(res.tvd))
                    overall_tvd_vals.append(float(res.tvd))

                if res.timeline_ok is False:
                    timeline_err += 1
                    overall_timeline_err += 1
                if res.timeline_dist is not None:
                    tl_vals.append(float(res.timeline_dist))
                    overall_tl_vals.append(float(res.timeline_dist))

        pass_at_k = compute_pass_at_k(per_task_ok_by_k, k_max=k_max)
        syntax_err_rate = (syntax_err / cand_total) if cand_total else 0.0
        element_err_rate = (element_err / element_checked) if element_checked else 0.0
        dist_err_rate = (dist_err / simulated) if simulated else 0.0
        timeline_err_rate = (timeline_err / simulated) if simulated else 0.0

        report[task_type] = {
            "num_tasks": len(task_ids),
            "num_candidates": cand_total,

            "pass_at_k": {str(k): pass_at_k[k] for k in sorted(pass_at_k.keys())},

            "error_rates": {
                "syntax": syntax_err_rate,
                "element": element_err_rate,
                "distribution": dist_err_rate,
                "timeline": timeline_err_rate,
            },
            "error_counts": {
                "syntax": syntax_err,
                "element": element_err,
                "distribution": dist_err,
                "timeline": timeline_err,
            },
            "denominators": {
                "total_candidates": cand_total,
                "syntax_ok": element_checked,
                "syntax_and_element_ok": simulated,
            },

            "variance": {
                "distribution": pvariance(tvd_vals),
                "timeline": pvariance(tl_vals),
            },

            "means": {
                "tvd": mean(tvd_vals),
                "timeline_dist": mean(tl_vals),
            },
        }

    overall_pass_at_k = compute_pass_at_k(overall_per_task_ok_by_k, k_max=overall_k_max)

    overall_syntax_err_rate = (overall_syntax_err / overall_candidates_total) if overall_candidates_total else 0.0
    overall_element_err_rate = (overall_element_err / overall_element_checked) if overall_element_checked else 0.0
    overall_dist_err_rate = (overall_dist_err / overall_simulated) if overall_simulated else 0.0
    overall_timeline_err_rate = (overall_timeline_err / overall_simulated) if overall_simulated else 0.0

    report["overall"] = {
        "overall_num_tasks": overall_num_tasks,
        "overall_num_candidates": overall_candidates_total,

        "pass_at_k": {str(k): overall_pass_at_k[k] for k in sorted(overall_pass_at_k.keys())},

        "error_rates": {
            "syntax": overall_syntax_err_rate,
            "element": overall_element_err_rate,
            "distribution": overall_dist_err_rate,
            "timeline": overall_timeline_err_rate,
        },
        "error_counts": {
            "syntax": overall_syntax_err,
            "element": overall_element_err,
            "distribution": overall_dist_err,
            "timeline": overall_timeline_err,
        },
        "denominators": {
            "total_candidates": overall_candidates_total,
            "syntax_ok": overall_element_checked,
            "syntax_and_element_ok": overall_simulated,
        },
        "variance": {
            "distribution": pvariance(overall_tvd_vals),
            "timeline": pvariance(overall_tl_vals),
        },
        "means": {
            "tvd": mean(overall_tvd_vals),
            "timeline_dist": mean(overall_tl_vals),
        },
    }

    # save the report


    if SAVE_REPORT:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(REPORT_DIR, f"{REPORT_FILENAME_PREFIX}_{ts}_{TO_TEST}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        report["_saved_report_path"] = out_path

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
