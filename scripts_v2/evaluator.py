from __future__ import annotations
import hashlib
import json
import os
import re
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar
START_RE = re.compile('^\\s*//\\s*===\\s*CORE_TASK_START\\s*===.*$', re.IGNORECASE | re.MULTILINE)
END_RE = re.compile('^\\s*//\\s*===\\s*CORE_TASK_END\\s*===.*$', re.IGNORECASE | re.MULTILINE)
_T = TypeVar('_T')
SEED_DIST = 12345
SEED_TIMELINE = 67890
GOLDEN_CACHE_VERSION = 2
DEFAULT_GOLDEN_CACHE_DIR = Path(__file__).resolve().parents[1] / '.eval_cache_completion_v2'

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
    state_ok: bool | None = None
    state_distance: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _import_judge():
    from . import judge
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

def _golden_cache_dir() -> Path:
    configured = os.environ.get('QASM_EVAL_V2_GOLDEN_CACHE_DIR', '').strip()
    return Path(configured) if configured else DEFAULT_GOLDEN_CACHE_DIR

def _golden_reference(judge, golden_code: str, task_type: str):
    metadata = {'version': GOLDEN_CACHE_VERSION, 'verifier_version': judge.VERIFIER_VERSION, 'implementation_sha256': hashlib.sha256(b''.join(((Path(__file__).parent / name).read_bytes() for name in ('QASM_simulator.py', 'pulse_simulator.py', 'judge.py', 'state_verifier.py')))).hexdigest(), 'golden_sha256': hashlib.sha256(golden_code.encode('utf-8')).hexdigest(), 'task_type': task_type, 'shots_dist_golden': judge.SHOTS_DIST_GOLDEN, 'seed_dist': SEED_DIST, 'seed_timeline': SEED_TIMELINE}
    cache_key = hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    cache_enabled = os.environ.get('QASM_EVAL_DISABLE_CACHE', '') != '1'
    cache_path = _golden_cache_dir() / f'{cache_key}.json'
    if cache_enabled:
        try:
            payload = json.loads(cache_path.read_text(encoding='utf-8'))
            if payload.get('metadata') == metadata:
                events = [judge.TimelineEvent(**event) for event in payload['events']]
                return (payload['exist'], payload['dist'], events)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
    golden_program = judge.parse_qasm_safely(golden_code)
    golden_exist = judge.extract_exist_from_program(golden_program)
    golden_dist = _with_numpy_seed(SEED_DIST, lambda: judge.simulate_distribution_safely(golden_code, shots=judge.SHOTS_DIST_GOLDEN))
    golden_events = _with_numpy_seed(SEED_TIMELINE, lambda: judge.simulate_timeline_events_safely(golden_code))
    if cache_enabled:
        payload = {'metadata': metadata, 'exist': golden_exist, 'dist': golden_dist, 'events': [asdict(event) for event in golden_events]}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            temporary.replace(cache_path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return (golden_exist, golden_dist, golden_events)

def clean_returned_code(text: str) -> str:
    text = (text or '').strip()
    if text.startswith('```'):
        text = re.sub('^```[a-zA-Z0-9_-]*\\s*', '', text)
        text = re.sub('\\s*```$', '', text)
    lines: list[str] = []
    for line in text.splitlines():
        if START_RE.match(line) or END_RE.match(line):
            continue
        lines.append(line.rstrip())
    return '\n'.join(lines).strip('\n\r')

def _detect_newline(text: str) -> str:
    if '\r\n' in text:
        return '\r\n'
    return '\n'

def extract_core_block(qasm: str) -> str:
    start = START_RE.search(qasm)
    if not start:
        raise ValueError('CORE_TASK_START not found')
    end = END_RE.search(qasm, pos=start.end())
    if not end:
        raise ValueError('CORE_TASK_END not found')
    return qasm[start.end():end.start()].strip('\n\r')

def replace_core_block(qasm: str, core_snippet: str) -> str:
    start = START_RE.search(qasm)
    if not start:
        raise ValueError('CORE_TASK_START not found')
    end = END_RE.search(qasm, pos=start.end())
    if not end:
        raise ValueError('CORE_TASK_END not found')
    newline = _detect_newline(qasm)
    core_snippet = core_snippet.strip('\n\r')
    middle = newline + core_snippet + newline if core_snippet else newline
    return qasm[:start.end()] + middle + qasm[end.start():]

def returned_code_to_qasm(golden_code: str, returned_code: str) -> tuple[str, str]:
    if re.search('^\\s*OPENQASM\\s+3\\s*;', returned_code or '', flags=re.IGNORECASE | re.MULTILINE):
        candidate_qasm = returned_code.strip() + '\n'
        try:
            cleaned = clean_returned_code(extract_core_block(candidate_qasm))
        except ValueError:
            cleaned = clean_returned_code(returned_code)
        return (candidate_qasm, cleaned)
    cleaned = clean_returned_code(returned_code)
    return (replace_core_block(golden_code, cleaned), cleaned)

def infer_domain(golden_code: str, default: str='complex') -> str:
    lowered = golden_code.lower()
    if 'delay[' in lowered or 'durationof' in lowered:
        return 'timing'
    if 'defcal' in lowered or 'cal {' in lowered or 'play(' in lowered:
        return 'pulse'
    if any((token in lowered for token in ('while', 'if (', 'for ', 'switch', 'extern '))):
        return 'complex'
    return default

def prime_golden_cache(golden_code: str, domain: str | None=None) -> None:
    judge = _import_judge()
    task_type = domain or infer_domain(golden_code)
    _golden_reference(judge, golden_code, task_type)

def evaluate_qasm_completion(golden_code: str, returned_code: str, domain: str | None=None, require_distribution: bool | None=None, require_timeline: bool | None=None) -> EvaluationResult:
    try:
        candidate_qasm, cleaned = returned_code_to_qasm(golden_code, returned_code)
    except Exception as exc:
        return EvaluationResult(ok=False, syntax_ok=None, element_ok=None, dist_ok=None, timeline_ok=None, detail=f'preprocess failed: {exc}', cleaned_returned_code=clean_returned_code(returned_code))
    task_type = domain or infer_domain(golden_code)
    try:
        judge = _import_judge()
    except Exception as exc:
        return EvaluationResult(ok=False, syntax_ok=None, element_ok=None, dist_ok=None, timeline_ok=None, detail=f'semantic judge unavailable: {exc}', candidate_qasm=candidate_qasm, cleaned_returned_code=cleaned)
    syntax_ok = None
    try:
        golden_exist, golden_dist, golden_events = _golden_reference(judge, golden_code, task_type)
        try:
            candidate_program = judge.parse_qasm_safely(candidate_qasm)
        except Exception as exc:
            return EvaluationResult(ok=False, syntax_ok=False, element_ok=False, dist_ok=None, timeline_ok=None, detail=f'syntax parse failed: {exc}', candidate_qasm=candidate_qasm, cleaned_returned_code=cleaned)
        syntax_ok = True
        candidate_exist = judge.extract_exist_from_program(candidate_program)
        missing = [k for k, v in golden_exist.items() if v and (not candidate_exist.get(k, False))]
        if missing:
            return EvaluationResult(ok=False, syntax_ok=True, element_ok=False, dist_ok=None, timeline_ok=None, detail=f'exist missing: {missing[:20]}' + (' ...' if len(missing) > 20 else ''), candidate_qasm=candidate_qasm, cleaned_returned_code=cleaned)
        if re.search('(?m)^\\s*while\\s*\\(\\s*true\\s*\\)', cleaned) and (not re.search('(?m)^\\s*break\\s*;', cleaned)):
            return EvaluationResult(ok=False, syntax_ok=True, element_ok=True, dist_ok=False, timeline_ok=False, detail='nonterminating while(true) loop without break', candidate_qasm=candidate_qasm, cleaned_returned_code=cleaned)
        candidate_dist = _with_numpy_seed(SEED_DIST, lambda: judge.simulate_distribution_safely(candidate_qasm, shots=judge.SHOTS_DIST_CAND))
        dist_err = judge.tvd(golden_dist, candidate_dist)
        dist_ok = dist_err <= judge.dist_tol_for_task(task_type)
        candidate_events = _with_numpy_seed(SEED_TIMELINE, lambda: judge.simulate_timeline_events_safely(candidate_qasm))
        timeline_dist = judge.timeline_distance_normalized(golden_events, candidate_events)
        timeline_ok = judge.timeline_ok_for_task(task_type, golden_events, candidate_events)
        from .state_verifier import compare_output_states
        state_ok, state_distance = compare_output_states(golden_code, candidate_qasm)
        ok = judge.decide_ok(task_type, True, True, dist_ok, timeline_ok) and state_ok
        if require_distribution is not None or require_timeline is not None:
            required: list[bool] = [state_ok]
            if require_distribution is not False:
                required.append(bool(dist_ok))
            if require_timeline is True or (require_timeline is None and task_type in ('timing', 'complex')):
                required.append(bool(timeline_ok))
            ok = all(required)
    except Exception as exc:
        return EvaluationResult(ok=False, syntax_ok=syntax_ok, element_ok=None, dist_ok=None, timeline_ok=None, detail=f'semantic judge failed: {exc}', candidate_qasm=candidate_qasm, cleaned_returned_code=cleaned)
    return EvaluationResult(ok=bool(ok), syntax_ok=True, element_ok=True, dist_ok=dist_ok, timeline_ok=timeline_ok, tvd=dist_err, timeline_dist=timeline_dist, detail=None, candidate_qasm=candidate_qasm, cleaned_returned_code=cleaned, state_ok=state_ok, state_distance=state_distance)

def check(golden_code: str, returned_code: str, domain: str | None=None) -> bool:
    return evaluate_qasm_completion(golden_code, returned_code, domain=domain).ok

def check_timeline_and_distribution(golden_code: str, returned_code: str, domain: str | None=None) -> bool:
    return evaluate_qasm_completion(golden_code, returned_code, domain=domain or 'complex', require_distribution=True, require_timeline=True).ok
