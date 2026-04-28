
from __future__ import annotations

import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Callable, TypeVar

#==============================================================================
# IMPORTANT：
# either set enough shots (recommend 8000) or set a fixed random seed. 
# the random nature of quantum simulation means that with too few shots, even a correct program may fail the check.
#==============================================================================

START_RE = re.compile(r"^\s*//\s*===\s*CORE_TASK_START\s*===.*$", re.IGNORECASE | re.MULTILINE)
END_RE = re.compile(r"^\s*//\s*===\s*CORE_TASK_END\s*===.*$", re.IGNORECASE | re.MULTILINE)
_T = TypeVar("_T")

SEED_DIST = 12345
SEED_TIMELINE = 67890

@dataclass
class EvaluationResult:
    ok: bool
    syntax_ok: bool | None
    element_ok: bool | None
    dist_ok: bool | None
    timeline_ok: bool | None
    tvd: float | None = None
    timeline_dist: float | None = None
    detail: str | None = None
    candidate_qasm: str | None = None
    cleaned_returned_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def _import_judge():
    _ensure_scripts_dir_on_path()
    try:
        from scripts import judge
    except Exception:
        import judge
    return judge


def _with_numpy_seed(seed: int, func: Callable[[], _T]) -> _T:
    try:
        import numpy as np
    except Exception:
        return func()

    state = np.random.get_state()
    try:
        np.random.seed(seed)
        return func()
    finally:
        np.random.set_state(state)


def clean_returned_code(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    lines: list[str] = []
    for line in text.splitlines():
        if START_RE.match(line) or END_RE.match(line):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip("\n\r")


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def extract_core_block(qasm: str) -> str:
    start = START_RE.search(qasm)
    if not start:
        raise ValueError("CORE_TASK_START not found")
    end = END_RE.search(qasm, pos=start.end())
    if not end:
        raise ValueError("CORE_TASK_END not found")
    return qasm[start.end():end.start()].strip("\n\r")


def replace_core_block(qasm: str, core_snippet: str) -> str:
    start = START_RE.search(qasm)
    if not start:
        raise ValueError("CORE_TASK_START not found")
    end = END_RE.search(qasm, pos=start.end())
    if not end:
        raise ValueError("CORE_TASK_END not found")

    newline = _detect_newline(qasm)
    core_snippet = core_snippet.strip("\n\r")
    middle = newline + core_snippet + newline if core_snippet else newline
    return qasm[:start.end()] + middle + qasm[end.start():]


def returned_code_to_qasm(golden_code: str, returned_code: str) -> tuple[str, str]:
    if re.search(r"^\s*OPENQASM\s+3\s*;", returned_code or "", flags=re.IGNORECASE | re.MULTILINE):
        candidate_qasm = returned_code.strip() + "\n"
        try:
            cleaned = clean_returned_code(extract_core_block(candidate_qasm))
        except ValueError:
            cleaned = clean_returned_code(returned_code)
        return candidate_qasm, cleaned

    cleaned = clean_returned_code(returned_code)
    return replace_core_block(golden_code, cleaned), cleaned


def infer_domain(golden_code: str, default: str = "complex") -> str:
    lowered = golden_code.lower()
    if "delay[" in lowered or "durationof" in lowered:
        return "timing"
    if "defcal" in lowered or "cal {" in lowered or "play(" in lowered:
        return "pulse"
    if any(token in lowered for token in ("while", "if (", "for ", "switch", "extern ")):
        return "complex"
    return default


def evaluate_qasm_completion(
    golden_code: str,
    returned_code: str,
    domain: str | None = None,
    require_distribution: bool | None = None,
    require_timeline: bool | None = None,
) -> EvaluationResult:
    """Evaluate one QASM answer against a golden program.

    Args:
        golden_code: The canonical full QASM program. If `returned_code` is a
            snippet, `golden_code` must contain the CORE_TASK markers.
        returned_code: Either a full OpenQASM program or only the completed core
            snippet returned by a model.
        domain: One of `timing`, `classical`, `pulse`, or `complex`. When
            omitted, a conservative best-effort inference is used.
        require_distribution: Override the final `ok` decision to require a
            correct distribution result.
        require_timeline: Override the final `ok` decision to require a correct
            timeline result.

    Returns:
        EvaluationResult. `ok` follows the same domain-specific policy as
        `scripts/judge.py`: timing checks timeline, classical/pulse check
        distribution, and complex checks both.
    """
    try:
        candidate_qasm, cleaned = returned_code_to_qasm(golden_code, returned_code)
    except Exception as exc:
        return EvaluationResult(
            ok=False,
            syntax_ok=None,
            element_ok=None,
            dist_ok=None,
            timeline_ok=None,
            detail=f"preprocess failed: {exc}",
            cleaned_returned_code=clean_returned_code(returned_code),
        )

    task_type = domain or infer_domain(golden_code)

    try:
        judge = _import_judge()
    except Exception as exc:
        return EvaluationResult(
            ok=False,
            syntax_ok=None,
            element_ok=None,
            dist_ok=None,
            timeline_ok=None,
            detail=f"semantic judge unavailable: {exc}",
            candidate_qasm=candidate_qasm,
            cleaned_returned_code=cleaned,
        )

    try:
        golden_program = judge.parse_qasm_safely(golden_code)
        golden_exist = judge.extract_exist_from_program(golden_program)
        golden_dist = _with_numpy_seed(
            SEED_DIST,
            lambda: judge.simulate_distribution_safely(golden_code, shots=judge.SHOTS_DIST_GOLDEN),
        )
        golden_timeline_text = _with_numpy_seed(
            SEED_TIMELINE,
            lambda: judge.simulate_timeline_text_safely(golden_code),
        )
        golden_events = judge.parse_timeline_events(golden_timeline_text)

        try:
            candidate_program = judge.parse_qasm_safely(candidate_qasm)
        except Exception as exc:
            return EvaluationResult(
                ok=False,
                syntax_ok=False,
                element_ok=False,
                dist_ok=None,
                timeline_ok=None,
                detail=f"syntax parse failed: {exc}",
                candidate_qasm=candidate_qasm,
                cleaned_returned_code=cleaned,
            )

        candidate_exist = judge.extract_exist_from_program(candidate_program)
        missing = [k for k, v in golden_exist.items() if v and not candidate_exist.get(k, False)]
        if missing:
            return EvaluationResult(
                ok=False,
                syntax_ok=True,
                element_ok=False,
                dist_ok=None,
                timeline_ok=None,
                detail=f"exist missing: {missing[:20]}" + (" ..." if len(missing) > 20 else ""),
                candidate_qasm=candidate_qasm,
                cleaned_returned_code=cleaned,
            )

        candidate_dist = _with_numpy_seed(
            SEED_DIST,
            lambda: judge.simulate_distribution_safely(candidate_qasm, shots=judge.SHOTS_DIST_CAND),
        )
        dist_err = judge.tvd(golden_dist, candidate_dist)
        dist_ok = dist_err <= judge.dist_tol_for_task(task_type)

        candidate_timeline_text = _with_numpy_seed(
            SEED_TIMELINE,
            lambda: judge.simulate_timeline_text_safely(candidate_qasm),
        )
        candidate_events = judge.parse_timeline_events(candidate_timeline_text)
        timeline_dist = judge.timeline_distance_normalized(golden_events, candidate_events)
        timeline_ok = judge.timeline_ok_for_task(task_type, golden_events, candidate_events)

        ok = judge.decide_ok(task_type, True, True, dist_ok, timeline_ok)
        if require_distribution is not None or require_timeline is not None:
            required: list[bool] = [True, True]
            if require_distribution:
                required.append(bool(dist_ok))
            if require_timeline:
                required.append(bool(timeline_ok))
            ok = all(required)
    except Exception as exc:
        return EvaluationResult(
            ok=False,
            syntax_ok=None,
            element_ok=None,
            dist_ok=None,
            timeline_ok=None,
            detail=f"semantic judge failed: {exc}",
            candidate_qasm=candidate_qasm,
            cleaned_returned_code=cleaned,
        )

    return EvaluationResult(
        ok=bool(ok),
        syntax_ok=True,
        element_ok=True,
        dist_ok=dist_ok,
        timeline_ok=timeline_ok,
        tvd=dist_err,
        timeline_dist=timeline_dist,
        detail=None,
        candidate_qasm=candidate_qasm,
        cleaned_returned_code=cleaned,
    )


def check(golden_code: str, returned_code: str, domain: str | None = None) -> bool:
    return evaluate_qasm_completion(golden_code, returned_code, domain=domain).ok


def check_timeline_and_distribution(
    golden_code: str,
    returned_code: str,
    domain: str | None = None,
) -> bool:
    return evaluate_qasm_completion(
        golden_code,
        returned_code,
        domain=domain or "complex",
        require_distribution=True,
        require_timeline=True,
    ).ok
