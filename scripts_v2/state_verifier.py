from __future__ import annotations
import copy
import io
from contextlib import redirect_stdout, redirect_stderr
from functools import lru_cache
import numpy as np
import openqasm3
import openqasm3.ast as ast
from . import QASM_simulator as sim
STATE_TRACE_TOL = 0.05
MAX_BRANCHES = 256
MAX_QUBITS = 10

def _before_terminal_readout(qasm):
    program = openqasm3.parse(qasm)
    statements = list(program.statements)
    removed_measurement = False
    while statements:
        node = statements[-1]
        if isinstance(node, ast.QuantumMeasurementStatement):
            removed_measurement = True
            statements.pop()
        elif removed_measurement and isinstance(node, ast.ClassicalDeclaration) and (node.init_expression is None):
            statements.pop()
        else:
            break
    program.statements = statements
    return program

@lru_cache(maxsize=128)
def output_density(qasm: str):
    program = _before_terminal_readout(qasm)
    pending = [((), 1.0)]
    density = None
    completed = 0
    external_state = copy.deepcopy(sim.__extern_vqe_state)
    try:
        while pending:
            if completed + len(pending) > MAX_BRANCHES:
                raise sim.SimulationLimitError('State verification branch limit exceeded')
            path, weight = pending.pop()
            interpreter = sim.QASM3Interpreter(program, externals=dict(sim.external_funcs), system_model={'freqs': [5000000000.0], 'dt': 1e-09})
            interpreter._scan_qubits()
            if interpreter.num_qubits > MAX_QUBITS:
                raise sim.SimulationLimitError('State verification qubit limit exceeded')
            interpreter.measurement_path = path
            sim.__extern_vqe_state.clear()
            sim.__extern_vqe_state.update(copy.deepcopy(external_state))
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                try:
                    interpreter.run_shot()
                except sim.MeasurementBranch as branch:
                    for outcome, probability in enumerate(branch.probabilities):
                        if probability > 1e-14:
                            pending.append((path + (outcome,), weight * probability))
                    continue
            state = interpreter.get_quantum_state()
            contribution = weight * np.outer(state, state.conj())
            density = contribution if density is None else density + contribution
            completed += 1
    finally:
        sim.__extern_vqe_state.clear()
        sim.__extern_vqe_state.update(external_state)
    if density is None or not np.isclose(np.trace(density), 1.0, atol=1e-08):
        raise ValueError('Incomplete output-state ensemble')
    density.setflags(write=False)
    return density

def compare_output_states(golden_qasm: str, candidate_qasm: str):
    golden = output_density(golden_qasm)
    candidate = output_density(candidate_qasm)
    if golden.shape != candidate.shape:
        return (False, 1.0)
    delta = golden - candidate
    distance = float(np.abs(np.linalg.eigvalsh((delta + delta.conj().T) / 2)).sum() / 2)
    return (distance <= STATE_TRACE_TOL, distance)
