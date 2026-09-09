import numpy as np
import openqasm3
import openqasm3.ast as ast
from collections import Counter
import math
from pulse_simulator import PulseSimulator, Pulse
try:
    from pulse_simulator import Waveform
except Exception:
    Waveform = None
import traceback
import re

from qiskit.quantum_info import Statevector, Operator
from qiskit.circuit.library import (
    IGate, XGate, YGate, ZGate, HGate, SGate, SdgGate, TGate, TdgGate, SXGate,
    RXGate, RYGate, RZGate, PhaseGate, UGate, U2Gate, U3Gate,
    CXGate, CZGate, CCXGate, SwapGate, CSwapGate,
    CHGate, CYGate, CRXGate, CRYGate, CRZGate, CPhaseGate, RZZGate
)

from qiskit.circuit import Reset


# =================
# this one single file contains too many classes and functions to support most OpenQASM features, 
# but for simplicity we put all the simulator-related code here. it can be refactored later if needed.
# =================


class EndProgram(Exception):
    pass

def mock_calculate_syndrome(measurements_int):
    #mimic the behavior of a simple error syndrome calculator: if any measurement is 1, return 1 (indicating an error), otherwise return 0 (no error).
    if measurements_int > 0:
        return 1
    return 0

# --- VQE-like demo extern state (to avoid infinite while loop) ---
__extern_vqe_state = {
    "iter": 0,
    "prev_energy": None,
    "max_iter": 20,   
    "tol": 1e-3,     
    "lr": 0.2,        
    "shots": 1000,
}

def compute_energy(count_z: int, count_x: int) -> float:

    shots = max(1, int(__extern_vqe_state.get("shots", 1000)))
    ez = float(count_z) / shots  
    ex = float(count_x) / shots  
    return -0.5 * (ez + ex)

def check_convergence(energy: float) -> bool:

    st = __extern_vqe_state
    st["iter"] = int(st.get("iter", 0)) + 1

    prev = st.get("prev_energy", None)
    st["prev_energy"] = float(energy)
    if st["iter"] >= int(st.get("max_iter", 20)):
        return True
    if prev is not None:
        try:
            if abs(float(energy) - float(prev)) < float(st.get("tol", 1e-3)):
                return True
        except Exception:
            pass
    return False

def get_next_params(theta: float, energy: float) -> float:
    lr = float(__extern_vqe_state.get("lr", 0.2))
    new_theta = float(theta) - lr * float(energy)
    import math
    twopi = 2.0 * math.pi
    new_theta = new_theta % twopi
    return new_theta

external_funcs = {
    "calculate_syndrome": mock_calculate_syndrome,
    "compute_energy": compute_energy,
    "check_convergence": check_convergence,
    "get_next_params": get_next_params,
}

# quantum backend based on Qiskit Statevector simulator
class QuantumState:
    def __init__(self, num_qubits):
        self.num_qubits = num_qubits
        # |0...0>
        self._sv = Statevector.from_label('0' * num_qubits)

    @property
    def state(self):
        return np.asarray(self._sv.data)

    def apply_gate(self, name, qubits, params=None):
        if params is None:
            params = []
        f_params = [float(p) for p in params]
        
        gate_obj = None
        name = name.lower()

        if name == 'id': gate_obj = IGate()
        elif name == 'x': gate_obj = XGate()
        elif name == 'y': gate_obj = YGate()
        elif name == 'z': gate_obj = ZGate()
        elif name == 'h': gate_obj = HGate()
        elif name == 's': gate_obj = SGate()
        elif name == 'sdg': gate_obj = SdgGate()
        elif name == 't': gate_obj = TGate()
        elif name == 'tdg': gate_obj = TdgGate()
        elif name == 'sx': gate_obj = SXGate()
        
        elif name == 'rx': gate_obj = RXGate(*f_params)
        elif name == 'ry': gate_obj = RYGate(*f_params)
        elif name == 'rz': gate_obj = RZGate(*f_params)
        elif name in ['p', 'phase', 'u1']: gate_obj = PhaseGate(*f_params)
        elif name == 'u2': gate_obj = U2Gate(*f_params)
        elif name in ['u', 'u3']: gate_obj = U3Gate(*f_params)
        
        elif name in ['cx', 'cnot']: gate_obj = CXGate()
        elif name == 'cz': gate_obj = CZGate()
        elif name == 'ccx': gate_obj = CCXGate()
        elif name == 'swap': gate_obj = SwapGate()
        elif name == 'cswap': gate_obj = CSwapGate()
        
        elif name == 'ch': gate_obj = CHGate()
        elif name == 'cy': gate_obj = CYGate()
        elif name in ['cp', 'cphase']: gate_obj = CPhaseGate(*f_params)
        elif name == 'crx': gate_obj = CRXGate(*f_params)
        elif name == 'cry': gate_obj = CRYGate(*f_params)
        elif name == 'crz': gate_obj = CRZGate(*f_params)
        elif name == 'cu': 
            from qiskit.circuit.library import CUGate
            gate_obj = CUGate(*f_params)
        elif name == 'rzz': gate_obj = RZZGate(*f_params)
        
        elif name == 'rotary':
            gate_obj = RXGate(f_params[0])

        if gate_obj is None:
            raise NotImplementedError(f"Gate {name} not supported in Qiskit backend adapter.")
        self._sv = self._sv.evolve(gate_obj, qargs=qubits)

    def apply_unitary(self, matrix, qubits):
        op = Operator(matrix)
        
        expected_dim = 2 ** len(qubits)
        if matrix.shape != (expected_dim, expected_dim):
            raise ValueError(f"Matrix shape {matrix.shape} does not match {len(qubits)} qubits")

        self._sv = self._sv.evolve(op, qargs=qubits)
        current_norm = np.linalg.norm(self._sv.data)
        if abs(current_norm - 1.0) > 1e-13:
            self._sv = self._sv / current_norm

    def measure(self, qubit_idx):
        norm = np.linalg.norm(self._sv.data)
        if abs(norm - 1.0) > 1e-13:
             self._sv = self._sv / norm
        outcome, new_sv = self._sv.measure([qubit_idx])
        self._sv = new_sv
        return int(outcome)

    def reset(self, qubit_idx):
        outcome = self.measure(qubit_idx)
        if outcome == 1:
            self.apply_gate('x', [qubit_idx])
        return outcome

#OpenQASM 3 Interpreter
class QASM3Interpreter:
    def __init__(self, program_ast, externals=None,system_model=None):

        self.program = program_ast
        self.classical_memory = {} 
        self.qubit_map = {} 
        self.num_qubits = 0
        self.q_backend = None
        self.output_buffer = {} 
        self.gate_definitions = {}
        self.constants=set()
        self.classical_bit_width = {} 
        self.measurements=[]

        self.external_functions = externals if externals else {}
        self.calibrations = {}
        self.system_model = system_model if system_model else {'freqs': [], 'dt': 1e-9}

        dt = float(self.system_model.get("dt", 1e-9))

        self.system_model.setdefault("default_gate_duration_s", 40 * dt)

        self.system_model["gate_durations_s"] = {

            "rz": 0.0,
            "z": 0.0,
            "s": 0.0,       
            "sdg": 0.0,     
            "t": 0.0,      
            "tdg": 0.0,
            "p": 0.0,       
            "phase": 0.0,
            "barrier": 0.0, 

            "x": 40 * dt,
            "y": 40 * dt,
            "sx": 40 * dt, 
            "h": 40 * dt,   
            "u1": 0.0,     
            "u2": 40 * dt,  
            "u3": 80 * dt,  

            "cx": 300 * dt,
            "cnot": 300 * dt,
            "cz": 300 * dt,
            "ecr": 300 * dt,
            
            "swap": 900 * dt, 
            "cswap": 900 * dt, 

            "id": 40 * dt,
            "measure": 1000 * dt, 
            "reset": 1200 * dt, 
        }


        # Classical control latency (not necessary, e.g., FPGA/controller feedforward). Set to 0.0 to disable.
        self.system_model.setdefault("classical_latency_s", 0.0)

        try:
            self.system_model["gate_durations_s"].setdefault(
                "nop", float(self.system_model.get("default_gate_duration_s", 0.0) or 0.0)
            )
        except Exception:
            pass


        self.timeline = []
        self._timeline_scope_stack = [] 
        self._timeline_next_scope_id = 1

        self._timing_clock = {}
        self._timing_stretch = 1.0

    def _timeline_reset(self):
        self.timeline = []
        self._timeline_scope_stack = []
        self._timeline_next_scope_id = 1
    def _measurement_reset(self):
        self.measurements = []
    
    def _record_measure(self, *, t0, t1, qubits, outcomes, value=None, form=None, target=None, detail=None):
        rec = {
            "t0": float(t0),
            "t1": float(t1),
            "qubits": [int(q) for q in (qubits or [])],
            "outcomes": [int(b) for b in (outcomes or [])],
            "value": int(value) if value is not None else None,
            "form": str(form) if form is not None else None,   
            "target": target,                                  
            "detail": detail or {},
        }
        self.measurements.append(rec)
        return rec

    def _timeline_current_scope_id(self):
        return self._timeline_scope_stack[-1]["id"] if self._timeline_scope_stack else None

    def _timeline_push_scope(self, kind, meta=None, t0=None):
        sid = int(self._timeline_next_scope_id)
        self._timeline_next_scope_id += 1
        self._timeline_scope_stack.append({
            "id": sid,
            "kind": str(kind),
            "meta": meta or {},
            "t0": float(t0) if t0 is not None else None,
        })
        return sid

    def _timeline_pop_scope(self, t1=None):
        if not self._timeline_scope_stack:
            return None
        scope = self._timeline_scope_stack.pop()
        if t1 is not None:
            scope["t1"] = float(t1)
        return scope

    def _timeline_add_event(self, *, t0, t1, kind, resources=None, detail=None, scope_id=None):
        ev = {
            "t0": float(t0),
            "t1": float(t1),
            "kind": str(kind),
            "resources": list(resources or []),
            "detail": detail or {},
            "scope": scope_id if scope_id is not None else self._timeline_current_scope_id(),
        }
        self.timeline.append(ev)
        return ev

    def _timing_reset_clocks(self):
        self._timing_clock = {i: 0.0 for i in range(int(self.num_qubits or 0))}
        self._timing_stretch = 1.0

    def _timing_ready_time(self, qubits):
        qs = [int(q) for q in (qubits or [])]
        if not qs:
            return 0.0
        return max(float(self._timing_clock.get(q, 0.0)) for q in qs)

    def _timing_barrier(self, qubits):
        qs = [int(q) for q in (qubits or [])]
        if not qs:
            return 0.0
        t = self._timing_ready_time(qs)

        # Record explicit idle/wait events for qubits that are fast-forwarded to the barrier time.
        for q in qs:
            try:
                t_prev = float(self._timing_clock.get(q, 0.0))
            except Exception:
                t_prev = 0.0
            if t_prev < t:
                try:
                    self._timeline_add_event(
                        t0=t_prev,
                        t1=t,
                        kind="idle",
                        resources=[f"q{q}"],
                        detail={"reason": "barrier_wait"},
                    )
                except Exception:
                    pass
            self._timing_clock[q] = t
        return t

    def _timing_delay(self, qubits, duration_s):
        qs = [int(q) for q in (qubits or [])]
        for q in qs:
            self._timing_clock[q] = float(self._timing_clock.get(q, 0.0)) + float(duration_s)

    def _apply_classical_latency(self, *, reason: str = "classical", qubits=None):
        try:
            latency = float(self.system_model.get("classical_latency_s", 0.0) or 0.0)
        except Exception:
            latency = 0.0
        if latency <= 0.0:
            return 0.0

        if qubits is None:
            qs = list(self._timing_clock.keys())
        else:
            try:
                qs = [int(q) for q in qubits]
            except Exception:
                qs = []

        if not qs:
            return 0.0

        try:
            t0 = max(float(self._timing_clock.get(q, 0.0)) for q in qs)
        except Exception:
            t0 = 0.0
        t1 = float(t0) + float(latency)

        for q in qs:
            try:
                self._timing_clock[int(q)] = max(float(self._timing_clock.get(int(q), 0.0)), t1)
            except Exception:
                pass
        try:
            self._timeline_add_event(
                t0=t0,
                t1=t1,
                kind="classical_latency",
                resources=["global"],
                detail={"reason": str(reason), "latency_s": float(latency), "qubits": list(qs)},
            )
        except Exception:
            pass

        return float(latency)


    def _extract_block_statements(self, node):
        body = getattr(node, 'body', None)
        if body is None:
            body = getattr(node, 'block', None)
        if body is None and hasattr(node, 'statements'):
            body = getattr(node, 'statements', None)

        if body is None:
            return []
        if isinstance(body, list):
            return body
        if hasattr(body, 'statements'):
            try:
                return list(body.statements or [])
            except Exception:
                return []
        if hasattr(body, 'body'):
            try:
                return list(body.body or [])
            except Exception:
                return []
        return [body]

    def _infer_qubits_in_timing_block(self, stmts, all_qubits):
        touched = set()

        def _handle_frame_ident(name):
            if name in self.classical_memory:
                f_obj = self.classical_memory.get(name)
                if isinstance(f_obj, dict) and 'qubit' in f_obj:
                    touched.add(int(f_obj['qubit']))
                    return
            m = re.search(r'\d+', str(name))
            if m:
                touched.add(int(m.group()))

        def _walk_stmt(s):
            if s is None:
                return
            cn = s.__class__.__name__

            # nested blocks
            if 'Box' in cn or 'Align' in cn or 'Stretch' in cn:
                for ch in self._extract_block_statements(s):
                    _walk_stmt(ch)
                return

            # function calls: play/shift_phase
            if isinstance(s, ast.ExpressionStatement) and isinstance(getattr(s, 'expression', None), ast.FunctionCall):
                fc = s.expression
                fn = getattr(fc.name, 'name', None)
                if fn in ('play', 'shift_phase'):
                    if fc.arguments and isinstance(fc.arguments[0], ast.Identifier):
                        _handle_frame_ident(fc.arguments[0].name)
                return

            # delay
            if isinstance(s, ast.DelayInstruction) or ('Delay' in cn):
                qs = getattr(s, 'qubits', None) or getattr(s, 'targets', None) or []
                if not qs:
                    return
                for q in qs:
                    if isinstance(q, ast.Identifier) and q.name.startswith('$'):
                        touched.add(int(q.name[1:]))
                    elif isinstance(q, ast.IndexedIdentifier):
                        # qreg index; map if possible
                        try:
                            qname = q.name.name
                            raw = q.indices[0]
                            idx_node = raw[0] if isinstance(raw, list) else raw
                            idx = int(self.visit(idx_node))
                            if qname in self.qubit_map:
                                touched.add(int(self.qubit_map[qname][idx]))
                        except Exception:
                            pass
                return

            # barrier
            if 'Barrier' in cn:
                targets = getattr(s, 'frames', None) or getattr(s, 'qubits', None) or getattr(s, 'operands', None) or []
                for nm in targets or []:
                    if isinstance(nm, ast.Identifier):
                        _handle_frame_ident(nm.name)
                return

            # quantum gate
            if 'QuantumGate' in cn:
                qrefs = getattr(s, 'qubits', None) or getattr(s, 'operands', None) or []
                for q in qrefs or []:
                    if isinstance(q, ast.Identifier) and q.name.startswith('$'):
                        touched.add(int(q.name[1:]))

        for st in stmts or []:
            _walk_stmt(st)

        if not touched:
            return list(all_qubits)
        return sorted(touched)
    def _get_declared_bit_width(self, qasm_type):

        if qasm_type is None:
            return None

        try:
            if isinstance(qasm_type, ast.BitType) and getattr(qasm_type, "size", None) is None:
                return 1
        except Exception:
            pass

        for attr in ("size", "width", "bits", "length"):
            if hasattr(qasm_type, attr):
                v = getattr(qasm_type, attr)
                if v is None:
                    continue
                # IntegerLiteral-like node
                if hasattr(v, "value"):
                    v = v.value
                try:
                    return int(v)
                except Exception:
                    pass

        return None

    def visit_EndStatement(self, node):
        raise EndProgram()

    def visit_CalibrationDefinition(self, node):
        gate_name = node.name.name
        if isinstance(node.body, str):
            try:
                _q_args = []
                for _q in getattr(node, 'qubits', []) or []:
                    if isinstance(_q, ast.Identifier):
                        _q_args.append(_q.name)
                    elif hasattr(_q, 'name') and isinstance(_q.name, ast.Identifier):
                        _q_args.append(_q.name.name)
                    elif hasattr(_q, 'name') and isinstance(_q.name, str):
                        _q_args.append(_q.name)
                    else:
                        _q_args.append(str(_q))
                _q_arg_str = ", ".join(_q_args)

                _wrapped = (
                    "OPENQASM 3.0;\n"
                    'defcalgrammar "openpulse";\n'
                    f"defcal {gate_name} {_q_arg_str} {{\n"
                    + node.body +
                    "\n}\n"
                )
                _parsed = openqasm3.parse(_wrapped)
                _found = None
                for _st in getattr(_parsed, 'statements', []) or []:
                    if isinstance(_st, ast.CalibrationDefinition):
                        _found = _st
                        break
                if _found is not None and hasattr(_found, 'body'):
                    node.body = _found.body
                else:
                    raise RuntimeError("wrapped defcal parse succeeded but no CalibrationDefinition found")
            except Exception as e:
                print(f"Warning: Failed to parse defcal body for {gate_name}: {e}")

        target_qubits = []
        for q in node.qubits:
             if isinstance(q, ast.Identifier):
                 name = q.name
                 if name.startswith('$'):
                     target_qubits.append(int(name[1:]))
                 elif name in self.qubit_map:
                      target_qubits.extend(self.qubit_map[name])

        key = (gate_name, tuple(target_qubits))
        self.calibrations[key] = node
    def visit_CalibrationStatement(self, node):
        cal_body_str = node.body if isinstance(node.body, str) else ""
        port_matches = re.findall(r'extern\s+port\s+(\w+);', cal_body_str)
        for port_name in port_matches:
            self.classical_memory[port_name] = port_name 
        
        sanitized_body = cal_body_str
        sanitized_body = re.sub(r'extern\s+port\s+\w+;', '', sanitized_body)
        sanitized_body = re.sub(r'extern\s+[\w\s\(\)\[\],]+\s*->\s*\w+;', '', sanitized_body)
        sanitized_body = re.sub(r'extern\s+[\w\s\(\)\[\],]+;', '', sanitized_body)
        arb_pat = re.compile(r'\bwaveform\s+(\w+)\s*=\s*\[(.*?)\]\s*;', re.S)

        def _parse_openpulse_complex_list(s: str):
            import math
            out = []
            parts = [p.strip() for p in s.replace("\n", " ").split(",") if p.strip()]
            for p in parts:
                expr = re.sub(r'\bim\b', '*1j', p)
                env = {"sqrt": math.sqrt, "pi": math.pi}
                try:
                    val = complex(eval(expr, {"__builtins__": {}}, env))
                except Exception:
                    val = 0.0 + 0.0j
                out.append(val)
            return out

        for m in arb_pat.finditer(cal_body_str):
            w_name = m.group(1)
            samples_src = m.group(2)
            self.classical_memory[w_name] = _parse_openpulse_complex_list(samples_src)

        sanitized_body = arb_pat.sub(lambda m: f"int {m.group(1)} = 0;", sanitized_body)
        sanitized_body = re.sub(r'\bframe\b', 'int', sanitized_body)
        sanitized_body = re.sub(r'\bwaveform\b', 'int', sanitized_body)
        

        statements = []
        try:
            parsed_program = openqasm3.parse(sanitized_body)
            statements = parsed_program.statements
        except Exception as e:
            # traceback.print_exc()
            print(f"Error parsing sanitized cal block: {e}")
            return

        def _has_schedule_ops(st):
            if st is None:
                return False

            if isinstance(st, ast.DelayInstruction):
                return True

            if isinstance(st, ast.ExpressionStatement) and isinstance(getattr(st, 'expression', None), ast.FunctionCall):
                fn = getattr(st.expression.name, 'name', None)
                if fn in ('play', 'shift_phase', 'set_phase', 'set_frequency', 'shift_frequency'):
                    return True

            if isinstance(st, ast.ForInLoop):
                for s2 in (st.block or []):
                    if _has_schedule_ops(s2):
                        return True
            cn = st.__class__.__name__
            if ('Box' in cn) or ('Align' in cn) or ('Stretch' in cn):
                for s2 in self._extract_block_statements(st):
                    if _has_schedule_ops(s2):
                        return True

            return False

        is_schedule = any(_has_schedule_ops(stmt) for stmt in statements)

        if is_schedule:
            all_qubits = list(range(self.num_qubits))

            t0 = 0.0
            scope_id = None
            try:
                t0 = float(self._timing_ready_time(all_qubits))
                scope_id = self._timeline_push_scope('calibration_schedule', meta={'qubits': list(all_qubits)}, t0=t0)
            except Exception:
                t0 = 0.0
                scope_id = None

            U_pulse = self._execute_pulse_schedule(statements, all_qubits, timeline_offset=t0, record_timeline=True, timeline_scope_id=scope_id)
            self.q_backend.apply_unitary(U_pulse, all_qubits)

            try:
                dur = float(getattr(self, '_last_pulse_schedule_duration', 0.0) or 0.0)
            except Exception:
                dur = 0.0
            t1 = float(t0) + float(dur)
            try:
                for q in all_qubits:
                    self._timing_clock[int(q)] = max(float(self._timing_clock.get(int(q), 0.0)), t1)
                self._timeline_add_event(t0=t0, t1=t1, kind='calibration_schedule', resources=[f'q{q}' for q in all_qubits], detail={'duration_s': dur}, scope_id=scope_id)
                if scope_id is not None:
                    self._timeline_pop_scope(t1=t1)
            except Exception:
                pass
        else:
            for stmt in statements:
                self.visit(stmt)
    
    def _execute_pulse_schedule(self, node_or_list, qubits, *, timeline_offset=0.0, record_timeline=False, timeline_scope_id=None):

        if not self.system_model.get('freqs'):
             self.system_model['freqs'] = [5e9] * self.num_qubits
        max_rabi_hz = self.system_model.get('max_rabi_hz', 500e6) 

        sim = PulseSimulator(
            N=len(self.system_model['freqs']),
            qubit_freqs_hz=self.system_model['freqs'],
            J_hz=self.system_model.get('coupling', None),
            amp_unit="Hz" 
        )
        pulse_records = []   
        gate_events = []     

        def _resolve_placeholder_qubit(_id_str, _actual_qubits):
            if isinstance(_id_str, str) and _id_str.startswith('$'):
                try:
                    _k = int(_id_str[1:])
                    if 0 <= _k < len(_actual_qubits):
                        return int(_actual_qubits[_k])
                except Exception:
                    pass
            try:
                return int(re.findall(r'\d+', str(_id_str))[0])
            except Exception:
                return None

        def _extract_ident_names(_items):
            out = []
            for _it in _items or []:
                if isinstance(_it, ast.Identifier):
                    out.append(_it.name)
                elif hasattr(_it, 'name') and isinstance(_it.name, ast.Identifier):
                    out.append(_it.name.name)
                elif hasattr(_it, 'name') and isinstance(_it.name, str):
                    out.append(_it.name)
                else:
                    out.append(str(_it))
            return out


        clock = {i: 0.0 for i in range(len(self.system_model['freqs']))}
        frame_phases = {} 

        statements = []
        if isinstance(node_or_list, list):
            statements = node_or_list
        elif hasattr(node_or_list, 'body'):
            statements = node_or_list.body
        else:
            statements = [node_or_list]

        try:
            timeline_offset = float(timeline_offset or 0.0)
        except Exception:
            timeline_offset = 0.0

        def _tl(_t0, _t1, _kind, _resources=None, _detail=None):
            if not record_timeline:
                return
            try:
                self._timeline_add_event(
                    t0=float(timeline_offset + float(_t0)),
                    t1=float(timeline_offset + float(_t1)),
                    kind=_kind,
                    resources=list(_resources or []),
                    detail=_detail or {},
                    scope_id=timeline_scope_id,
                )
            except Exception:
                pass

        def _frame_to_qubit(_frame_name):
            if _frame_name in self.classical_memory:
                f_obj = self.classical_memory[_frame_name]
                if isinstance(f_obj, dict) and 'qubit' in f_obj:
                    try:
                        return int(f_obj['qubit'])
                    except Exception:
                        pass
            m = re.search(r'\d+', str(_frame_name))
            if m:
                try:
                    return int(m.group())
                except Exception:
                    pass
            return 0

        def _extract_block_body(_node):
            return self._extract_block_statements(_node)

        def _alignment_mode(_node):
            mode = None
            for attr in ('alignment', 'mode', 'kind', 'position', 'type'):
                if hasattr(_node, attr):
                    v = getattr(_node, attr)
                    try:
                        if hasattr(v, 'name'):
                            v = v.name
                        mode = str(v).lower()
                    except Exception:
                        mode = None
                    break
            return mode or 'left'

        def _stretch_factor(_node):
            for attr in ('factor', 'stretch', 'scale', 'amount'):
                if hasattr(_node, attr):
                    try:
                        return float(self.visit(getattr(_node, attr)))
                    except Exception:
                        try:
                            return float(getattr(_node, attr))
                        except Exception:
                            pass
            return 1.0

        def _process_statements(_stmts, _stretch=1.0):
            for stmt in (_stmts or []):
                cn = stmt.__class__.__name__

                if 'Box' in cn:
                    t0_box = max(clock.values()) if clock else 0.0
                    _tl(t0_box, t0_box, 'box_start', _resources=[f'q{q}' for q in qubits], _detail={'node': cn})
                    _process_statements(_extract_block_body(stmt), _stretch=_stretch)
                    t1_box = max(clock.values()) if clock else 0.0
                    _tl(t0_box, t1_box, 'box', _resources=[f'q{q}' for q in qubits], _detail={'node': cn})
                    continue

                if 'Align' in cn or 'Alignment' in cn:
                    mode = _alignment_mode(stmt)
                    q_targets = list(qubits) if qubits is not None else list(clock.keys())
                    t_enter = max((clock.get(q, 0.0) for q in q_targets), default=0.0)
                    if ('right' not in mode) and ('end' not in mode):
                        t_sync = max((clock.get(q, 0.0) for q in q_targets), default=0.0)
                        for q in q_targets:
                            clock[q] = t_sync
                        _tl(t_sync, t_sync, 'barrier', _resources=[f'q{q}' for q in q_targets], _detail={'reason': 'alignment_start', 'mode': mode, 'node': cn})
                    _process_statements(_extract_block_body(stmt), _stretch=_stretch)
                    if ('right' in mode) or ('end' in mode) or ('center' in mode):
                        t_sync2 = max((clock.get(q, 0.0) for q in q_targets), default=0.0)
                        for q in q_targets:
                            clock[q] = t_sync2
                        _tl(t_sync2, t_sync2, 'barrier', _resources=[f'q{q}' for q in q_targets], _detail={'reason': 'alignment_end', 'mode': mode, 'node': cn})
                    t_exit = max((clock.get(q, 0.0) for q in q_targets), default=0.0)
                    _tl(t_enter, t_exit, 'alignment', _resources=[f'q{q}' for q in q_targets], _detail={'mode': mode, 'node': cn})
                    continue

                if 'Stretch' in cn:
                    factor = _stretch_factor(stmt)
                    if factor is None or factor <= 0:
                        factor = 1.0
                    t0_s = max(clock.values()) if clock else 0.0
                    _process_statements(_extract_block_body(stmt), _stretch=float(_stretch) * float(factor))
                    t1_s = max(clock.values()) if clock else 0.0
                    _tl(t0_s, t1_s, 'stretch', _resources=[f'q{q}' for q in qubits], _detail={'factor': float(factor), 'node': cn})
                    continue
                if isinstance(stmt, ast.ForInLoop):
                    loop_var_name = stmt.identifier.name

                    iterator = []

                    if isinstance(stmt.set_declaration, ast.RangeDefinition):
                        start = self.visit(stmt.set_declaration.start) if stmt.set_declaration.start else 0
                        end = self.visit(stmt.set_declaration.end)
                        step = self.visit(stmt.set_declaration.step) if stmt.set_declaration.step else 1

                        is_float_loop = isinstance(start, float) or isinstance(end, float) or isinstance(step, float)
                        if is_float_loop:
                            iterator = []
                            current = start
                            epsilon = 1e-14 if isinstance(step, float) else 0
                            if step > 0:
                                while current <= end + epsilon:
                                    iterator.append(current)
                                    current += step
                            elif step < 0:
                                while current >= end - epsilon:
                                    iterator.append(current)
                                    current += step
                        else:
                            iterator = range(int(start), int(end) + 1, int(step))

                    elif isinstance(stmt.set_declaration, ast.DiscreteSet):
                        iterator = [self.visit(v) for v in stmt.set_declaration.values]

                    elif isinstance(stmt.set_declaration, ast.Identifier):
                        arr_name = stmt.set_declaration.name
                        iterator = self.classical_memory.get(arr_name, [])
                        if not isinstance(iterator, (list, tuple, range, np.ndarray)):
                            iterator = [iterator]
                    else:
                        raise NotImplementedError(f"Loop set type {type(stmt.set_declaration)} not implemented in pulse schedule")

                    for val in iterator:
                        self.classical_memory[loop_var_name] = val
                        _process_statements(stmt.block, _stretch=_stretch)

                    continue


                if isinstance(stmt, ast.ClassicalDeclaration):
                    self.visit(stmt)
                    continue

                if isinstance(stmt, ast.ExpressionStatement) and isinstance(stmt.expression, ast.FunctionCall):
                    func_call = stmt.expression
                    func_name = func_call.name.name

                    if func_name == 'play':
                        frame_arg = func_call.arguments[0]
                        waveform_arg = func_call.arguments[1]

                        q_idx = 0
                        frame_name = "default"
                        if isinstance(frame_arg, ast.Identifier):
                            frame_name = frame_arg.name
                            if frame_name in self.classical_memory:
                                f_obj = self.classical_memory[frame_name]
                                if isinstance(f_obj, dict) and 'qubit' in f_obj:
                                    q_idx = f_obj['qubit']
                            elif 'd' in frame_name:
                                import re
                                m = re.search(r'\d+', frame_name)
                                if m:
                                    q_idx = int(m.group())

                        wf_data = None
                        if isinstance(waveform_arg, ast.Identifier):
                            w_name = waveform_arg.name
                            if w_name in self.classical_memory:
                                wf_data = self.classical_memory[w_name]
                        else:
                            wf_data = self.visit(waveform_arg)

                        current_frame_phase = frame_phases.get(frame_name, 0.0)

                        if Waveform is not None and hasattr(sim, 'add_waveform_pulse'):
                            try:
                                wf_obj, wf_freq_shift = self._convert_openpulse_waveform(wf_data, max_rabi_hz=max_rabi_hz)
                            except Exception:
                                wf_obj, wf_freq_shift = None, 0.0
                            if wf_obj is not None:
                                t_start = clock[q_idx]
                                dur = float(getattr(wf_obj, 'duration', 0.0))
                                t_stop = t_start + float(dur) * float(_stretch)
                                carrier = self.system_model['freqs'][q_idx] + float(wf_freq_shift)
                                sim.add_waveform_pulse(
                                    qubit=q_idx,
                                    waveform=wf_obj,
                                    t_start=t_start,
                                    carrier_hz=carrier,
                                    phase_rad=current_frame_phase
                                )
                                if hasattr(sim, '_pulses') and sim._pulses:
                                    pulse_records.append(sim._pulses[-1])
                                clock[q_idx] = t_stop
                                _tl(t_start, t_stop, 'play', _resources=[f'q{q_idx}', f'frame:{frame_name}'], _detail={'waveform': 'Waveform', 'carrier_hz': float(carrier)})
                                continue

                        freq_shift = 0.0
                        target_data = wf_data
                        if isinstance(wf_data, dict) and wf_data.get('name') == 'mix':
                            ops = wf_data['operands']
                            for op in ops:
                                if isinstance(op, dict):
                                    if op.get('name') == 'gaussian':
                                        target_data = op
                                    elif op.get('name') == 'sine':
                                        freq_shift = float(op['args'][2])
                        if isinstance(wf_data, dict) and wf_data.get('name') == 'scale':
                            base = wf_data['waveform']
                            s = float(wf_data['scale'])
                            if isinstance(base, dict) and base.get('name') == 'gaussian':
                                target_data = dict(base)
                                target_data['args'] = list(base['args'])
                                target_data['args'][0] = float(target_data['args'][0]) * s
                            else:
                                target_data = base

                        if isinstance(target_data, dict) and target_data.get('name') == 'gaussian':
                            args = target_data['args']
                            amp = float(args[0])
                            duration = float(args[1]) * float(_stretch)
                            sigma = float(args[2]) * float(_stretch)

                            if abs(amp) <= 1.0 and max_rabi_hz > 0:
                                amp *= max_rabi_hz

                            t_start = clock[q_idx]
                            t_stop = t_start + duration
                            t0 = t_start + duration / 2.0
                            carrier = self.system_model['freqs'][q_idx] + freq_shift

                            sim.add_gaussian_pulse(
                                qubit=q_idx,
                                amp=amp,
                                t0=t0,
                                sigma=sigma,
                                t_start=t_start,
                                t_stop=t_stop,
                                carrier_hz=carrier,
                                phase_rad=current_frame_phase
                            )
                            if hasattr(sim, '_pulses') and sim._pulses:
                                pulse_records.append(sim._pulses[-1])
                            clock[q_idx] = t_stop
                            _tl(t_start, t_stop, 'play', _resources=[f'q{q_idx}', f'frame:{frame_name}'], _detail={'waveform': 'gaussian', 'carrier_hz': float(carrier), 'amp': float(amp)})
                    elif func_name == 'shift_phase':
                        frame_arg = func_call.arguments[0]
                        angle = self.visit(func_call.arguments[1])
                        f_name = frame_arg.name if isinstance(frame_arg, ast.Identifier) else "default"
                        frame_phases[f_name] = frame_phases.get(f_name, 0.0) + angle
                        qph = _frame_to_qubit(f_name)
                        t_now = float(clock.get(qph, 0.0))
                        _tl(t_now, t_now, 'shift_phase', _resources=[f'q{qph}', f'frame:{f_name}'], _detail={'angle_rad': float(angle)})
                    elif func_name == 'set_phase':
                        frame_arg = func_call.arguments[0]
                        angle = self.visit(func_call.arguments[1])

                        f_name = frame_arg.name if isinstance(frame_arg, ast.Identifier) else "default"
                        frame_phases[f_name] = float(angle)  

                        
                        if isinstance(frame_arg, ast.Identifier) and frame_arg.name in self.classical_memory:
                            f_obj = self.classical_memory[frame_arg.name]
                            if isinstance(f_obj, dict):
                                f_obj['phase'] = float(angle)
                                self.classical_memory[frame_arg.name] = f_obj

                        qph = _frame_to_qubit(f_name)
                        t_now = float(clock.get(qph, 0.0))
                        _tl(t_now, t_now, 'set_phase', _resources=[f'q{qph}', f'frame:{f_name}'],
                            _detail={'phase_rad': float(angle)})
                        continue

                    continue

                if 'Barrier' in cn:
                    targets = (
                        getattr(stmt, 'frames', None)
                        or getattr(stmt, 'qubits', None)
                        or getattr(stmt, 'operands', None)
                        or []
                    )
                    names = _extract_ident_names(targets)
                    q_targets = []
                    import re
                    for nm in names:
                        if nm in self.classical_memory:
                            f_obj = self.classical_memory[nm]
                            if isinstance(f_obj, dict) and 'qubit' in f_obj:
                                q_targets.append(int(f_obj['qubit']))
                        else:
                            m = re.search(r'\d+', str(nm))
                            if m:
                                q_targets.append(int(m.group()))
                    if q_targets:
                        t_sync = max(clock.get(q, 0.0) for q in q_targets)
                        for q in q_targets:
                            clock[q] = t_sync
                        _tl(t_sync, t_sync, 'barrier', _resources=[f'q{q}' for q in q_targets], _detail={'node': cn})
                    continue

                if 'QuantumGate' in cn or isinstance(stmt, getattr(ast, 'QuantumGate', tuple())):
                    gname = None
                    if hasattr(stmt, 'name') and isinstance(stmt.name, ast.Identifier):
                        gname = stmt.name.name
                    elif hasattr(stmt, 'name') and hasattr(stmt.name, 'name'):
                        gname = stmt.name.name
                    else:
                        gname = str(getattr(stmt, 'name', ''))

                    gparams = []
                    for a in (getattr(stmt, 'arguments', None) or []):
                        try:
                            gparams.append(self.visit(a))
                        except Exception:
                            gparams.append(a)

                    qrefs = (
                        getattr(stmt, 'qubits', None)
                        or getattr(stmt, 'operands', None)
                        or []
                    )
                    qnames = _extract_ident_names(qrefs)
                    q_actual = []
                    for nm in qnames:
                        q_idx = _resolve_placeholder_qubit(nm, qubits)
                        if q_idx is not None:
                            q_actual.append(int(q_idx))

                    if len(q_actual) == 1:
                        q0 = q_actual[0]
                        t_gate = float(clock.get(q0, 0.0))
                        U2 = _gate_matrix_2x2(gname, gparams)
                        Ufull = _expand_single_qubit(U2, q0, len(self.system_model['freqs']))
                        gate_events.append({'t': t_gate, 'U': Ufull})
                        _tl(t_gate, t_gate, 'instant_gate', _resources=[f'q{q0}'], _detail={'gate': str(gname), 'params': gparams})
                    else:
                        pass
                    continue

                if isinstance(stmt, ast.DelayInstruction):
                    duration = float(self.visit(stmt.duration)) * float(_stretch)
                    target_qubits_indices = qubits
                    for q in target_qubits_indices:
                        t0_d = float(clock[q])
                        clock[q] += duration
                        t1_d = float(clock[q])
                        _tl(t0_d, t1_d, 'delay', _resources=[f'q{q}'], _detail={'duration_s': float(duration)})
                    continue

        _process_statements(statements, _stretch=1.0)


        try:
            total_time_clock = float(max(clock.values()) if clock else 0.0)
        except Exception:
            total_time_clock = 0.0
        try:
            total_time_gate = float(max([float(ev.get('t', 0.0)) for ev in gate_events], default=0.0))
        except Exception:
            total_time_gate = 0.0

        total_time = float(max(total_time_clock, total_time_gate))
        self._last_pulse_schedule_duration = float(total_time)


        if total_time == 0.0 and (not gate_events):
            return np.eye(2**len(self.system_model['freqs']))

        if not gate_events:
            return sim.unitary(T=total_time)


        dim = 2 ** len(self.system_model['freqs'])
        U_total = np.eye(dim, dtype=complex)


        times = [0.0, float(total_time)] + [float(ev['t']) for ev in gate_events]

        times = sorted(set([t for t in times if t is not None and t >= 0.0]))


        gates_by_t = {}
        for ev in gate_events:
            t = float(ev['t'])
            gates_by_t.setdefault(t, []).append(ev['U'])

  
        all_pulses = pulse_records
        if (not all_pulses) and hasattr(sim, '_pulses'):
            try:
                all_pulses = list(sim._pulses)
            except Exception:
                all_pulses = pulse_records

        # Apply gates that happen at t=0.0 
        try:
            if 0.0 in gates_by_t:
                for Ug in gates_by_t[0.0]:
                    U_total = Ug @ U_total
        except Exception:
            pass


        for i in range(len(times) - 1):
            t0 = float(times[i])
            t1 = float(times[i + 1])
            seg_T = t1 - t0
            try:
                if (t0 in gates_by_t) and (t0 != 0.0):
                    for Ug in gates_by_t[t0]:
                        U_total = Ug @ U_total
            except Exception:
                pass
            if seg_T > 0:
                seg = PulseSimulator(
                    N=len(self.system_model['freqs']),
                    qubit_freqs_hz=self.system_model['freqs'],
                    J_hz=self.system_model.get('coupling', None),
                    amp_unit="Hz"
                )

                for p in all_pulses:
                    try:
                        p_ts = float(getattr(p, 't_start', 0.0))
                        p_te = float(getattr(p, 't_stop', 0.0))
                    except Exception:
                        continue
                    if p_te <= t0 or p_ts >= t1:
                        continue
                    ts = max(p_ts, t0)
                    te = min(p_te, t1)
                    if te <= ts:
                        continue

                    def _env_seg(t, _p=p, _offset=t0):
                        return complex(_p.envelope(t + _offset))

                    seg._pulses.append(
                        Pulse(
                            qubit=int(getattr(p, 'qubit')),
                            carrier_hz=float(getattr(p, 'carrier_hz')),
                            phase_rad=float(getattr(p, 'phase_rad')),
                            envelope=_env_seg,
                            t_start=float(ts - t0),
                            t_stop=float(te - t0),
                        )
                    )

                U_seg = seg.unitary(T=seg_T)
                U_total = U_seg @ U_total

            if t1 in gates_by_t:
                for Ug in gates_by_t[t1]:
                    U_total = Ug @ U_total

        return U_total

    def _convert_openpulse_waveform(self, wf_data, max_rabi_hz=0.0):

        if Waveform is None:
            return None, 0.0
        dt = self.system_model.get('dt', 1e-9)

        def _to_complex(x):
            try:
                return complex(x)
            except Exception:
                return complex(float(x))

        def _auto_scale_amp(amp):
            a = _to_complex(amp)
            if max_rabi_hz and abs(a) <= 1.0 + 1e-12:
                a = a * float(max_rabi_hz)
            return a


        if isinstance(wf_data, Waveform):
            return wf_data, 0.0


        if isinstance(wf_data, (list, tuple, np.ndarray)):
            samples = [_to_complex(v) for v in list(wf_data)]
            if len(samples) == 0:
                return Waveform.constant(0.0, 0.0), 0.0

            if max_rabi_hz:
                max_abs = max(abs(s) for s in samples)
                if max_abs <= 1.0 + 1e-12:
                    samples = [s * float(max_rabi_hz) for s in samples]

            duration = float(len(samples)) * float(dt)
            return Waveform.from_samples(samples=samples, duration=duration), 0.0


        if isinstance(wf_data, dict):
            name = wf_data.get('name')


            if name == 'gaussian':
                args = wf_data.get('args', [])
                amp = _auto_scale_amp(args[0])
                duration = float(args[1])
                sigma = float(args[2])
                return Waveform.gaussian(amp=amp, duration=duration, sigma=sigma), 0.0

            if name == 'sech':
                args = wf_data.get('args', [])
                amp = _auto_scale_amp(args[0])
                duration = float(args[1])
                sigma = float(args[2])
                return Waveform.sech(amp=amp, duration=duration, sigma=sigma), 0.0

            if name == 'gaussian_square':
                args = wf_data.get('args', [])
                amp = _auto_scale_amp(args[0])
                duration = float(args[1])
                square_width = float(args[2])
                sigma = float(args[3])
                return Waveform.gaussian_square(amp=amp, duration=duration, square_width=square_width, sigma=sigma), 0.0

            if name == 'drag':
                args = wf_data.get('args', [])
                amp = _auto_scale_amp(args[0])
                duration = float(args[1])
                sigma = float(args[2])
                beta = float(args[3])*dt

                return Waveform.drag(amp=amp, duration=duration, sigma=sigma, beta=beta), 0.0

            if name == 'constant':
                args = wf_data.get('args', [])
                amp = _auto_scale_amp(args[0])
                duration = float(args[1])
                return Waveform.constant(amp=amp, duration=duration), 0.0

            if name == 'sine':
                args = wf_data.get('args', [])
                amp = _auto_scale_amp(args[0])
                duration = float(args[1])
                freq = float(args[2])
                phase = float(args[3]) if len(args) > 3 else 0.0
                return Waveform.sine(amp=amp, duration=duration, frequency_hz=freq, phase_rad=phase), 0.0

            if name == 'scale':
                base = wf_data.get('waveform')
                s = float(wf_data.get('scale', 1.0))
                w0, f0 = self._convert_openpulse_waveform(base, max_rabi_hz=max_rabi_hz)
                if w0 is None:
                    return None, 0.0
                return w0.scale(s), float(f0)

            if name == 'phase_shift':
                base = wf_data.get('waveform')
                ang = float(wf_data.get('phase', 0.0))
                w0, f0 = self._convert_openpulse_waveform(base, max_rabi_hz=max_rabi_hz)
                if w0 is None:
                    return None, 0.0
                return w0.phase_shift(ang), float(f0)

            if name == 'sum':
                ops = wf_data.get('operands', [])
                if len(ops) < 2:
                    return None, 0.0
                w, f = self._convert_openpulse_waveform(ops[0], max_rabi_hz=max_rabi_hz)
                if w is None:
                    return None, 0.0
                for op in ops[1:]:
                    w2, f2 = self._convert_openpulse_waveform(op, max_rabi_hz=max_rabi_hz)
                    if w2 is None:
                        return None, 0.0
                    w = w.sum(w2)
                    f += float(f2)
                return w, float(f)

            if name == 'mix':
                ops = wf_data.get('operands', [])
                if len(ops) == 2:
                    a, b = ops[0], ops[1]
                    sine_op = None
                    base_op = None
                    if isinstance(a, dict) and a.get('name') == 'sine':
                        sine_op = a
                        base_op = b
                    elif isinstance(b, dict) and b.get('name') == 'sine':
                        sine_op = b
                        base_op = a
                    if sine_op is not None:
                        s_args = sine_op.get('args', [])
                        if isinstance(s_args, list) and len(s_args) >= 3:
                            try:
                                freq_shift = float(s_args[2])
                            except Exception:
                                freq_shift = 0.0
                            base_w, base_f = self._convert_openpulse_waveform(base_op, max_rabi_hz=max_rabi_hz)
                            if base_w is not None:
                                return base_w, float(base_f) + float(freq_shift)

                if len(ops) < 2:
                    return None, 0.0
                w, f = self._convert_openpulse_waveform(ops[0], max_rabi_hz=max_rabi_hz)
                if w is None:
                    return None, 0.0
                for op in ops[1:]:
                    w2, f2 = self._convert_openpulse_waveform(op, max_rabi_hz=max_rabi_hz)
                    if w2 is None:
                        return None, 0.0
                    w = w.mix(w2)
                    f += float(f2)
                return w, float(f)

        return None, 0.0

    def visit_ExternDeclaration(self, node):
        func_name = node.name.name

        if func_name not in self.external_functions:
            print(f"Warning: 'extern {func_name}' declared in QASM but not provided in Python backend.")
            self.external_functions[func_name] = lambda x, *args: int(x)  # or 0
        return
    def get_quantum_state(self):
        if self.q_backend:
            return self.q_backend.state
        return None

    def run_shot(self):
        self.output_buffer = {}
        self._scan_qubits()
        self.q_backend = QuantumState(self.num_qubits)
        self.classical_memory = {}

        self._timeline_reset()
        self._measurement_reset()

        self._timing_reset_clocks()
        
        for statement in self.program.statements:
            try:
                self.visit(statement)
            except EndProgram:
                break
        try:
            self.output_buffer["__timeline__"] = list(self.timeline)
            
        except Exception:
            self.output_buffer["__timeline__"] = self.timeline
        try:
            self.output_buffer["__measurements__"] = list(self.measurements)
        except Exception:
            self.output_buffer["__measurements__"] = self.measurements
            
        return self.output_buffer

    def _scan_qubits(self):
        self.num_qubits = 0
        self.qubit_map = {}

        _size_env = {}

        def _eval_size_expr(expr):
            if expr is None:
                raise ValueError("size expr is None")

            if hasattr(expr, "value"):
                return int(expr.value)

            if isinstance(expr, ast.Identifier):
                if expr.name in _size_env:
                    return int(_size_env[expr.name])
                raise KeyError(f"Unknown size identifier: {expr.name}")

            if isinstance(expr, ast.BinaryExpression):
                a = _eval_size_expr(expr.lhs)
                b = _eval_size_expr(expr.rhs)
                op = getattr(expr.op, "name", str(expr.op))
                if op == "+":  return a + b
                if op == "-":  return a - b
                if op == "*":  return a * b
                if op == "/":  return int(a / b)
                if op == "%":  return a % b
                if op == "**": return a ** b
                if op == "<<": return a << b
                if op == ">>": return a >> b
                raise ValueError(f"Unsupported size op: {op}")

            if isinstance(expr, ast.UnaryExpression):
                v = _eval_size_expr(expr.expression)
                op = getattr(expr.op, "name", str(expr.op))
                if op == "+": return +v
                if op == "-": return -v
                if op == "~": return ~v
                raise ValueError(f"Unsupported unary op: {op}")

            inner = getattr(expr, "expression", None) or getattr(expr, "operand", None)
            if inner is not None:
                return _eval_size_expr(inner)

            return int(str(expr))

        for stmt in self.program.statements:
            if isinstance(stmt, (ast.ConstantDeclaration, ast.ClassicalDeclaration)):
                try:
                    ident = getattr(stmt, "identifier", None) or getattr(stmt, "name", None)
                    if isinstance(ident, ast.Identifier):
                        nm = ident.name
                    elif hasattr(ident, "name"):
                        nm = ident.name
                    else:
                        nm = str(ident)

                    init = (
                        getattr(stmt, "init_expression", None)
                        or getattr(stmt, "value", None)
                        or getattr(stmt, "expression", None)
                    )
                    if init is not None:
                        _size_env[nm] = _eval_size_expr(init)
                except Exception:
                    pass

            if isinstance(stmt, ast.QubitDeclaration):
                name = stmt.qubit.name
                size = 1
                if stmt.size is not None:
                    try:
                        size = _eval_size_expr(stmt.size)
                    except Exception:
                        size = 1  # fallback (keeps simulator running)

                self.qubit_map[name] = list(range(self.num_qubits, self.num_qubits + int(size)))
                self.num_qubits += int(size)
        
        if self.system_model and 'freqs' in self.system_model:
            hw_qubits_count = len(self.system_model['freqs'])

            if hw_qubits_count > self.num_qubits:
                self.num_qubits = hw_qubits_count
        if self.system_model is None:
            self.system_model = {}

        if 'freqs' not in self.system_model or self.system_model['freqs'] is None:
            self.system_model['freqs'] = []

        if len(self.system_model['freqs']) < self.num_qubits:
            fill = 5e9
            if len(self.system_model['freqs']) > 0:
                fill = self.system_model['freqs'][-1]
            self.system_model['freqs'].extend([fill] * (self.num_qubits - len(self.system_model['freqs'])))

        max_idx = -1
        for stmt in self.program.statements:
            if isinstance(stmt, (ast.CalibrationStatement, ast.CalibrationDefinition)):
                body = getattr(stmt, "body", None)
                if not isinstance(body, str):
                    continue

                for nm in re.findall(r'extern\s+port\s+(\w+)\s*;', body):
                    m = re.search(r'\d+', nm)
                    if m:
                        max_idx = max(max_idx, int(m.group()))

                for nm in re.findall(r'newframe\s*\(\s*([A-Za-z_]\w*)', body):
                    m = re.search(r'\d+', nm)
                    if m:
                        max_idx = max(max_idx, int(m.group()))

                for k in re.findall(r'\$(\d+)', body):
                    max_idx = max(max_idx, int(k))

        if max_idx >= 0 and (max_idx + 1) > self.num_qubits:
            self.num_qubits = max_idx + 1
        if max_idx >= 0 and (max_idx + 1) > self.num_qubits:
            self.num_qubits = max_idx + 1

        if self.system_model is None:
            self.system_model = {}
        if 'freqs' not in self.system_model or self.system_model['freqs'] is None:
            self.system_model['freqs'] = []

        if len(self.system_model['freqs']) < self.num_qubits:
            fill = 5e9
            if len(self.system_model['freqs']) > 0:
                fill = self.system_model['freqs'][-1]
            self.system_model['freqs'].extend([fill] * (self.num_qubits - len(self.system_model['freqs'])))



    def visit(self, node):
        method_name = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        cn = node.__class__.__name__
        if 'Box' in cn:
            t0 = self._timing_ready_time(list(self._timing_clock.keys()))
            sid = self._timeline_push_scope('box', meta={'node': cn}, t0=t0)
            for st in self._extract_block_statements(node):
                self.visit(st)
            t1 = self._timing_ready_time(list(self._timing_clock.keys()))
            self._timeline_add_event(t0=t0, t1=t1, kind='box', resources=[], detail={'node': cn}, scope_id=sid)
            self._timeline_pop_scope(t1=t1)
            return

        if 'Align' in cn or 'Alignment' in cn:
            mode = None
            for attr in ('alignment', 'mode', 'kind', 'position', 'type'):
                if hasattr(node, attr):
                    v = getattr(node, attr)
                    try:
                        if hasattr(v, 'name'):
                            v = v.name
                        mode = str(v).lower()
                    except Exception:
                        mode = None
                    break
            if mode is None:
                mode = 'left'

            qs = list(self._timing_clock.keys())
            t0 = self._timing_ready_time(qs)
            sid = self._timeline_push_scope('alignment', meta={'mode': mode, 'node': cn}, t0=t0)
            if 'right' not in mode and 'end' not in mode:
                self._timing_barrier(qs)
                self._timeline_add_event(t0=t0, t1=t0, kind='barrier', resources=[f'q{q}' for q in qs], detail={'reason': 'alignment_start', 'mode': mode}, scope_id=sid)
            for st in self._extract_block_statements(node):
                self.visit(st)
            if 'right' in mode or 'end' in mode or 'center' in mode:
                t_sync = self._timing_barrier(qs)
                self._timeline_add_event(t0=t_sync, t1=t_sync, kind='barrier', resources=[f'q{q}' for q in qs], detail={'reason': 'alignment_end', 'mode': mode}, scope_id=sid)
            t1 = self._timing_ready_time(qs)
            self._timeline_add_event(t0=t0, t1=t1, kind='alignment', resources=[f'q{q}' for q in qs], detail={'mode': mode}, scope_id=sid)
            self._timeline_pop_scope(t1=t1)
            return


        if 'Stretch' in cn:

            factor = 1.0
            for attr in ('factor', 'stretch', 'scale', 'amount'):
                if hasattr(node, attr):
                    try:
                        factor = float(self.visit(getattr(node, attr)))
                    except Exception:
                        try:
                            factor = float(getattr(node, attr))
                        except Exception:
                            factor = 1.0
                    break
            if factor <= 0:
                factor = 1.0

            t0 = self._timing_ready_time(list(self._timing_clock.keys()))
            sid = self._timeline_push_scope('stretch', meta={'node': cn, 'factor': factor}, t0=t0)

            prev = float(getattr(self, '_timing_stretch', 1.0))
            self._timing_stretch = prev * float(factor)
            try:
                for st in self._extract_block_statements(node):
                    self.visit(st)
            finally:
                self._timing_stretch = prev

            t1 = self._timing_ready_time(list(self._timing_clock.keys()))
            self._timeline_add_event(t0=t0, t1=t1, kind='stretch', resources=[], detail={'node': cn, 'factor': factor}, scope_id=sid)
            self._timeline_pop_scope(t1=t1)
            return

        if 'Barrier' in cn:
            qs = list(self._timing_clock.keys())
            t = self._timing_barrier(qs)
            self._timeline_add_event(t0=t, t1=t, kind='barrier', resources=[f'q{q}' for q in qs], detail={'node': cn})
            return

        raise NotImplementedError(f"Node type {type(node).__name__} not supported yet.")
    
    def visit_IntegerLiteral(self, node): return node.value
    def visit_FloatLiteral(self, node): return node.value
    def visit_BooleanLiteral(self, node): return node.value
    def visit_BitstringLiteral(self, node): return node.value
    def visit_ExpressionStatement(self, node):
        return self.visit(node.expression)

    def visit_AliasStatement(self, node):

        ident = getattr(node, "identifier", None) or getattr(node, "name", None) or getattr(node, "target", None)
        if hasattr(ident, "name"):
            alias_name = ident.name
        else:
            alias_name = str(ident)

        # RHS expression
        rhs = getattr(node, "value", None) or getattr(node, "expression", None) or getattr(node, "rhs", None)
        if rhs is None:
            raise ValueError("AliasStatement missing RHS expression")

        val = self.visit(rhs)
        if not isinstance(val, (list, tuple, range, np.ndarray)):
            val = [val]

        self.classical_memory[alias_name] = val
        return val

    def visit_QuantumGateDefinition(self, node):
        self.gate_definitions[node.name.name] = node
    
    def visit_Identifier(self, node):
        if node.name in self.classical_memory:
            return self.classical_memory[node.name]
        if node.name == 'pi': return np.pi
        if node.name == 'tau': return 2 * np.pi
        if node.name == 'euler': return np.e
        raise ValueError(f"Undefined variable: {node.name}")
    def visit_ImaginaryLiteral(self, node):
        return 1j * node.value


    def visit_BinaryExpression(self, node):
            lhs = self.visit(node.lhs)
            rhs = self.visit(node.rhs)
            op = node.op.name 
            
            if op == '+': return lhs + rhs
            if op == '-': return lhs - rhs
            if op == '*': return lhs * rhs
            if op == '/': return lhs / rhs
            if op == '%': return lhs % rhs
            if op == '**': return lhs ** rhs
            
            if op == '>': return lhs > rhs
            if op == '<': return lhs < rhs
            if op == '>=': return lhs >= rhs
            if op == '<=': return lhs <= rhs
            if op == '==': return lhs == rhs
            if op == '!=': return lhs != rhs
            
            if op == '&&': return bool(lhs) and bool(rhs)
            if op == '||': return bool(lhs) or bool(rhs)
            
            if op == '&': return int(lhs) & int(rhs)
            if op == '|': return int(lhs) | int(rhs)
            if op == '^': return int(lhs) ^ int(rhs)
            if op == '<<': return int(lhs) << int(rhs)
            if op == '>>': return int(lhs) >> int(rhs)
            
            raise ValueError(f"Unknown binary operator: {op}")

    def visit_UnaryExpression(self, node):
            val = self.visit(node.expression)
            op = node.op.name
            
            if op == '-': return -val
            if op == '!': return not val      
            if op == '~': return ~int(val)    
            
            raise ValueError(f"Unknown unary operator: {op}")

    def visit_IndexExpression(self, node):
        collection = self.visit(node.collection)
        idx_node = node.index[0]
        if isinstance(idx_node, ast.RangeDefinition):
            start = self.visit(idx_node.start) if idx_node.start is not None else 0
            end = self.visit(idx_node.end)
            step = self.visit(idx_node.step) if idx_node.step is not None else 1
            indices = list(range(int(start), int(end) + 1, int(step)))

            if isinstance(collection, int):
                return [ (collection >> i) & 1 for i in indices ]
            if isinstance(collection, list):
                return [ collection[i] for i in indices ]
            raise ValueError("Slicing not supported for this collection type")

        if isinstance(collection, int):
            idx = self.visit(idx_node)
            return (collection >> idx) & 1

        if isinstance(collection, list):
            idx = self.visit(idx_node)
            return collection[idx]

        raise ValueError("Indexing not supported for this type")

    def visit_QubitDeclaration(self, node):
        pass 

    def visit_CalibrationGrammarDeclaration(self, node):
        
        pass
    
    def visit_DurationLiteral(self, node):
        val = node.value
        unit = node.unit.name
        
        if unit == "dt":
            return val * self.system_model.get('dt', 1e-9)
        elif unit == "ns":
            return val * 1e-9
        elif unit == "us":
            return val * 1e-6
        elif unit == "ms":
            return val * 1e-3
        elif unit == "s":
            return val
        return val
    def visit_DurationOf(self, node):
        try:
            dt_s = float(self.system_model.get('dt', 1e-9))
        except Exception:
            dt_s = 1e-9

        try:
            return float(self.system_model.get('durationof_default_s', dt_s))
        except Exception:
            return dt_s

    def visit_DelayInstruction(self, node):

        try:
            duration_s = float(self.visit(getattr(node, 'duration', None)))
        except Exception:
            duration_s = 0.0

        try:
            duration_s *= float(getattr(self, '_timing_stretch', 1.0))
        except Exception:
            pass

        targets = (getattr(node, 'qubits', None) or getattr(node, 'targets', None) or getattr(node, 'operands', None) or [])
        if targets is None:
            targets = []
        if not isinstance(targets, (list, tuple)):
            targets = [targets]

        flat_qubits = []
        for q in targets:
            if q is None:
                continue
            if isinstance(q, ast.Identifier):
                q_name = q.name
                if q_name.startswith('$'):
                    flat_qubits.append(int(q_name[1:]))
                elif q_name in self.qubit_map:
                    flat_qubits.extend(self.qubit_map[q_name])
            elif isinstance(q, ast.IndexedIdentifier):
                try:
                    qname = q.name.name
                    raw_idx_list = q.indices[0]
                    idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
                    idx_val = self.visit(idx_node)
                    if qname in self.qubit_map:
                        flat_qubits.append(int(self.qubit_map[qname][idx_val]))
                except Exception:
                    pass

        if not flat_qubits:
            flat_qubits = list(self._timing_clock.keys())

        t0 = self._timing_ready_time(flat_qubits)
        self._timing_delay(flat_qubits, duration_s)
        t1 = self._timing_ready_time(flat_qubits)
        self._timeline_add_event(
            t0=t0,
            t1=t1,
            kind='delay',
            resources=[f'q{q}' for q in flat_qubits],
            detail={'duration_s': duration_s, 'node': node.__class__.__name__},
        )
        return

    def visit_FrameType(self, node): pass
    def visit_PortType(self, node): pass
    def visit_WaveformType(self, node): pass
    # def visit_ExternDeclaration(self, node):
    #     pass

    def visit_ConstantDeclaration(self, node):

        ident = getattr(node, 'identifier', None) or getattr(node, 'name', None)
        if isinstance(ident, ast.Identifier):
            name = ident.name
        elif hasattr(ident, 'name'):
            name = ident.name
        else:
            name = str(ident)

        init_expr = (
            getattr(node, 'init_expression', None)
            or getattr(node, 'value', None)
            or getattr(node, 'expression', None)
        )
        if init_expr is None:
            value = 0
        else:
            value = self.visit(init_expr)

        decl_type = getattr(node, 'type', None) or getattr(node, 'constant_type', None)
        try:
            if decl_type is not None and isinstance(decl_type, ast.BitType):
                value = int(value)
        except Exception:
            pass

        self.classical_memory[name] = value
        w = self._get_declared_bit_width(decl_type)
        if w is not None:
            self.classical_bit_width[name] = w

        self.constants.add(name)
        return value


    def visit_ClassicalDeclaration(self, node):
        name = node.identifier.name
        value = 0
        if node.init_expression:
            value = self.visit(node.init_expression)

        if isinstance(node.type, ast.BitType):
            self.classical_memory[name] = int(value)
        else:
            self.classical_memory[name] = value

        w = self._get_declared_bit_width(getattr(node, "type", None))
        if w is not None:
            self.classical_bit_width[name] = w


    def visit_ClassicalAssignment(self, node):
            value = self.visit(node.rvalue)
        
            if isinstance(node.lvalue, ast.IndexedIdentifier):
                target_name = node.lvalue.name.name

                raw_idx_list = node.lvalue.indices[0]
                idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
                idx = self.visit(idx_node)
                
                current_val = self.classical_memory.get(target_name, 0)
                if value:
                    final_val = current_val | (1 << idx)
                else:
                    final_val = current_val & ~(1 << idx)
                self.classical_memory[target_name] = final_val
                return

            target_name = node.lvalue.name
            op = node.op.name 
            current_val = self.classical_memory.get(target_name, 0)
            
            if op == '=': final_val = value
            elif op == '+=': final_val = current_val + value
            elif op == '-=': final_val = current_val - value
            elif op == '*=': final_val = current_val * value
            elif op == '/=': final_val = current_val / value
            elif op == '%=': final_val = current_val % value
            else: raise ValueError(f"Assignment op {op} not implemented")

            self.classical_memory[target_name] = final_val

    def visit_QuantumGate(self, node):
        gate_name = node.name.name
        params = [self.visit(arg) for arg in node.arguments]
        
        flat_qubits = []
        for qubit_node in node.qubits:
             if isinstance(qubit_node, ast.IndexedIdentifier):
                q_name = qubit_node.name.name
                raw_idx_list = qubit_node.indices[0]
                idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
                idx_val = self.visit(idx_node)
                flat_qubits.append(self.qubit_map[q_name][idx_val])
             elif isinstance(qubit_node, ast.Identifier):
                q_name = qubit_node.name

                if q_name.startswith('$'):
                    flat_qubits.append(int(q_name[1:]))
                elif q_name in self.qubit_map:
                    flat_qubits.extend(self.qubit_map[q_name])
                else:
                    raise ValueError(f"Undefined qubit: {q_name}")


        if str(gate_name).lower() == "nop":

            try:
                dur = float(self.system_model.get("gate_durations_s", {}).get(
                    "nop",
                    self.system_model.get("default_gate_duration_s", 0.0)
                ) or 0.0)
            except Exception:
                dur = 0.0

            try:
                t0 = float(self._timing_ready_time(flat_qubits))
            except Exception:
                t0 = 0.0
            t1 = float(t0) + float(max(dur, 0.0))

            try:
                for q in flat_qubits:
                    self._timing_clock[int(q)] = max(float(self._timing_clock.get(int(q), 0.0)), t1)
            except Exception:
                pass

            try:
                self._timeline_add_event(
                    t0=t0,
                    t1=t1,
                    kind="nop",
                    resources=[f"q{q}" for q in flat_qubits],
                    detail={"duration_s": float(max(dur, 0.0))},
                )
            except Exception:
                pass
            return

        if gate_name in self.gate_definitions:
            definition = self.gate_definitions[gate_name]

            previous_scope = self.qubit_map.copy()


            if len(definition.qubits) != len(flat_qubits):
                raise ValueError(f"Gate {gate_name} expects {len(definition.qubits)} qubits, got {len(flat_qubits)}")

            for i, formal_arg in enumerate(definition.qubits):
                formal_name = formal_arg.name
                self.qubit_map[formal_name] = [flat_qubits[i]]

            t_gate0 = 0.0
            scope_id = None
            try:
                t_gate0 = float(self._timing_ready_time(flat_qubits))
                scope_id = self._timeline_push_scope(
                    "logical_gate",
                    meta={"name": str(gate_name), "qubits": list(flat_qubits)},
                    t0=t_gate0,
                )
            except Exception:
                t_gate0 = 0.0
                scope_id = None

            for stmt in definition.body:
                self.visit(stmt)

            try:
                t_gate1 = float(self._timing_ready_time(flat_qubits))
            except Exception:
                t_gate1 = float(t_gate0)

            try:
                self._timeline_pop_scope(t1=t_gate1)
            except Exception:
                pass

            try:
                self._timeline_add_event(
                    t0=t_gate0,
                    t1=t_gate1,
                    kind="gate_macro",
                    resources=[f"q{q}" for q in flat_qubits],
                    detail={"name": str(gate_name)},
                    scope_id=scope_id,
                )
            except Exception:
                pass

            self.qubit_map = previous_scope
            return

        cal_key = (gate_name, tuple(flat_qubits))
        if cal_key in self.calibrations:

            cal_node = self.calibrations[cal_key]
            t_gate0 = 0.0
            scope_id = None
            try:
                t_gate0 = float(self._timing_ready_time(flat_qubits))
                scope_id = self._timeline_push_scope('calibrated_gate', meta={'gate': gate_name, 'qubits': list(flat_qubits)}, t0=t_gate0)
            except Exception:
                t_gate0 = 0.0
                scope_id = None

            U_pulse = self._execute_pulse_schedule(cal_node, flat_qubits, timeline_offset=t_gate0, record_timeline=True, timeline_scope_id=scope_id)

            try:
                dur = float(getattr(self, '_last_pulse_schedule_duration', 0.0) or 0.0)
            except Exception:
                dur = 0.0
            t_gate1 = float(t_gate0) + float(dur)
            try:
                for q in flat_qubits:
                    self._timing_clock[int(q)] = max(float(self._timing_clock.get(int(q), 0.0)), t_gate1)
                self._timeline_add_event(t0=t_gate0, t1=t_gate1, kind='calibrated_gate', resources=[f'q{q}' for q in flat_qubits], detail={'gate': gate_name, 'duration_s': dur}, scope_id=scope_id)
                if scope_id is not None:
                    self._timeline_pop_scope(t1=t_gate1)
            except Exception:
                pass
            
            all_qubits = list(range(self.num_qubits))
            self.q_backend.apply_unitary(U_pulse, all_qubits)
            return

        if gate_name in self.gate_definitions:
            definition = self.gate_definitions[gate_name]
            previous_scope = self.qubit_map.copy()
            
            if len(definition.qubits) != len(flat_qubits):
                raise ValueError(f"Gate {gate_name} expects {len(definition.qubits)} qubits, got {len(flat_qubits)}")
            
            for i, formal_arg in enumerate(definition.qubits):
                formal_name = formal_arg.name
                self.qubit_map[formal_name] = [flat_qubits[i]]
            
            for stmt in definition.body:
                self.visit(stmt)
            
            self.qubit_map = previous_scope
            return
        try:
            t0 = float(self._timing_ready_time(flat_qubits))

            gate_durs = self.system_model.get("gate_durations_s", {}) or {}
            dur = float(gate_durs.get(gate_name, self.system_model.get("default_gate_duration_s", 0.0)))
            dur *= float(getattr(self, "_timing_stretch", 1.0) or 1.0)

            t1 = t0 + dur
            for q in flat_qubits:
                q = int(q)
                self._timing_clock[q] = max(float(self._timing_clock.get(q, 0.0)), t1)

            self._timeline_add_event(
                t0=t0,
                t1=t1,
                kind='gate',
                resources=[f'q{q}' for q in flat_qubits],
                detail={'gate': gate_name, 'params': params, 'duration_s': dur},
            )
        except Exception:
            pass


        self.q_backend.apply_gate(gate_name, flat_qubits, params)
    def visit_QuantumMeasurementStatement(self, node):
        q_expr = node.measure.qubit
        q_idx = 0
        
        if isinstance(q_expr, ast.IndexedIdentifier):
            q_name = q_expr.name.name
            raw_idx_list = q_expr.indices[0]
            idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
            idx_val = self.visit(idx_node)
            q_idx = self.qubit_map[q_name][idx_val]
            
        else:
            q_name = q_expr.name     
            if q_name.startswith('$'):
                q_idx = int(q_name[1:])
            elif q_name in self.qubit_map:
                q_idx = self.qubit_map[q_name][0]
            else:
                raise ValueError(f"Undefined qubit: {q_name}")
            
        meas_dur = self.system_model.get("gate_durations_s", {}).get("measure", 1000e-9)
        t_start = float(self._timing_ready_time([q_idx]))
        t_end = t_start + meas_dur
        self._timeline_add_event(t0=t_start, t1=t_end, kind='measure', resources=[f'q{q_idx}'], detail={'qubit': int(q_idx)})
        self._timing_clock[q_idx]= t_end
        outcome = self.q_backend.measure(q_idx)
        target = node.target
        if target:

            if isinstance(target, ast.IndexedIdentifier):
                name = target.name.name
                
                raw_idx_list = target.indices[0]
                idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
                idx = self.visit(idx_node)

                curr = self.classical_memory.get(name, 0)
                if outcome == 1:
                    self.classical_memory[name] = curr | (1 << idx)
                else:
                    self.classical_memory[name] = curr & ~(1 << idx)
                target_meta = {"name": str(name), "index": int(idx)}
            else:
                self.classical_memory[target.name] = outcome
                target_meta = {"name": str(target.name)}
        
            t_name = target.name.name if isinstance(target, ast.IndexedIdentifier) else target.name
            self.output_buffer[t_name] = self.classical_memory.get(t_name, outcome)
        self._record_measure(
            t0=t_start,
            t1=t_end,
            qubits=[q_idx],
            outcomes=[outcome],
            value=outcome,
            form="stmt",
            target=target_meta,
            detail={"node": "QuantumMeasurementStatement"},)
    def visit_QuantumReset(self, node):
        targets = (getattr(node, "qubits", None)
           or getattr(node, "qubit", None)
           or getattr(node, "targets", None))
        
        if targets is None:
            one = getattr(node, "qubit", None)
            targets = [one] if one is not None else []

        if not isinstance(targets, (list, tuple)):
            targets = [targets]

        flat_qubits = []

        for q in targets:
            if q is None:
                continue

            if isinstance(q, ast.IndexedIdentifier):
                q_name = q.name.name
                raw_idx_list = q.indices[0]
                idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
                idx_val = self.visit(idx_node)
                flat_qubits.append(self.qubit_map[q_name][idx_val])

            elif isinstance(q, ast.Identifier):
                q_name = q.name
                if q_name.startswith('$'):
                    flat_qubits.append(int(q_name[1:]))
                elif q_name in self.qubit_map:
                    flat_qubits.extend(self.qubit_map[q_name])
                else:
                    raise ValueError(f"Undefined qubit: {q_name}")

            else:
                raise NotImplementedError(f"Unsupported reset target node: {type(q).__name__}")

        for q_idx in flat_qubits:
            reset_dur = self.system_model.get("gate_durations_s", {}).get("reset", 1200e-9)
            t_start = float(self._timing_ready_time([q_idx]))
            t_end = t_start + reset_dur
            self._timeline_add_event(t0=t_start, t1=t_end, kind='reset', 
                                    resources=[f'q{q_idx}'], detail={'qubit': int(q_idx)})

            self._timing_clock[q_idx] = t_end

            self.q_backend.reset(q_idx)

    def visit_QuantumMeasurement(self, node):
        q_expr = node.qubit
        target_indices = []
        if isinstance(q_expr, ast.Identifier):
            q_name = q_expr.name
            if q_name in self.qubit_map:
                target_indices = self.qubit_map[q_name]
            else:
                raise ValueError(f"Undefined qubit: {q_name}")

        elif isinstance(q_expr, ast.IndexedIdentifier):

            q_name = q_expr.name.name
            if q_name not in self.qubit_map:
                raise ValueError(f"Undefined qubit: {q_name}")
            

            raw_idx_list = q_expr.indices[0]
            idx_node = raw_idx_list[0] if isinstance(raw_idx_list, list) else raw_idx_list
            idx_val = self.visit(idx_node)
            
            target_indices = [self.qubit_map[q_name][idx_val]]

        meas_dur = self.system_model.get("gate_durations_s", {}).get("measure", 1000e-9)

        t_start = self._timing_ready_time(target_indices) 
        t_end = t_start + meas_dur

        for q_idx in target_indices:
            self._timeline_add_event(
                t0=t_start, 
                t1=t_end, 
                kind='measure', 
                resources=[f'q{q_idx}'], 
                detail={'type': 'expression_measure'}
            )
            self._timing_clock[q_idx] = t_end

        measurement_value = 0
        outcomes = []
        for i, q_idx in enumerate(target_indices):
            outcome = self.q_backend.measure(q_idx)
            outcomes.append(outcome)
            measurement_value |= (outcome << i)
        self._record_measure(
            t0=t_start,
            t1=t_end,
            qubits=target_indices,
            outcomes=outcomes,
            value=measurement_value,
            form="expr",
            target=None,
            detail={"node": "QuantumMeasurement", "bit_order": "lsb_is_first"},
        )


        return measurement_value
    def visit_BranchingStatement(self, node):
        self._apply_classical_latency(reason="branch_decision")
        condition = self.visit(node.condition)
        if condition:
            for stmt in node.if_block:
                self.visit(stmt)
        else:
            if node.else_block:
                for stmt in node.else_block:
                    self.visit(stmt)
    def visit_ArrayLiteral(self, node):
        return [self.visit(v) for v in node.values]

    def visit_WhileLoop(self, node):
        max_iter = 1000
        iter_count = 0
        while self.visit(node.while_condition):
            if iter_count > max_iter:
                raise RuntimeError("While loop exceeded max iterations (safety break)")
            
            for stmt in node.block:
                try:
                    self.visit(stmt)
                except StopIteration: # Break
                    return
                except ContinueException: # Continue
                    break 
            iter_count += 1
    def visit_SwitchStatement(self, node):
        target_value = self.visit(node.target)
        executed_any = False
        for case_item in node.cases:
            case_values = []
            case_body_node = None 
            is_default = False

            if isinstance(case_item, tuple):
                raw_values = case_item[0]
                case_body_node = case_item[1]
                
                if raw_values is None or (isinstance(raw_values, list) and len(raw_values) == 0):
                    is_default = True
                else:
                    case_values = raw_values
                    
            else:
                if hasattr(case_item, 'values') and case_item.values:
                    case_values = case_item.values
                elif 'Default' in type(case_item).__name__ or not hasattr(case_item, 'values'):
                    is_default = True
                
                if hasattr(case_item, 'body'):
                    case_body_node = case_item.body
                else:
                    print(f"Warning: Unknown case item structure: {type(case_item)}")
                    continue

            statements_to_execute = []
            
            if hasattr(case_body_node, 'statements'):
                statements_to_execute = case_body_node.statements
            elif isinstance(case_body_node, list):
                statements_to_execute = case_body_node
            else:
                statements_to_execute = [case_body_node]
            if is_default:
                if not executed_any:
                    for stmt in statements_to_execute:
                        self.visit(stmt)
                    executed_any = True
                continue

            match_found = False
            if not isinstance(case_values, list):
                case_values = [case_values]
                
            for val_node in case_values:
                val = self.visit(val_node)
                if val == target_value:
                    match_found = True
                    break
            
            if match_found:
                for stmt in statements_to_execute:
                    self.visit(stmt)
                executed_any = True
                break
    def visit_Cast(self, node):


        val = self.visit(node.argument) 
        
        target_type = node.type
        
        if isinstance(target_type, (ast.IntType, ast.UintType)):
            return int(val)
            
        elif isinstance(target_type, (ast.FloatType, ast.AngleType)):
            return float(val)
            
        elif isinstance(target_type, ast.BoolType):
            return bool(val)
            
        elif isinstance(target_type, ast.BitType):
            return int(val)
        
        elif isinstance(target_type, ast.ComplexType):
            return complex(val)

        return val
    def visit_Include(self, node):
        filename = node.filename
        if filename == "stdgates.inc":
            return
        else:
            print(f"Warning: Ignoring include file '{filename}' in simulation.")
    
    def visit_ForInLoop(self, node):
        loop_var_name = node.identifier.name
        iterator = []
        
        if isinstance(node.set_declaration, ast.RangeDefinition):
            start = self.visit(node.set_declaration.start) if node.set_declaration.start else 0
            end = self.visit(node.set_declaration.end)
            step = self.visit(node.set_declaration.step) if node.set_declaration.step else 1
            is_float_loop = isinstance(start, float) or isinstance(end, float) or isinstance(step, float)
            
            if is_float_loop:
                iterator = []
                current = start
                epsilon = 1e-14 if isinstance(step, float) else 0
                
                if step > 0:
                    while current <= end + epsilon:
                        iterator.append(current)
                        current += step
                elif step < 0:
                    while current >= end - epsilon:
                        iterator.append(current)
                        current += step
            else:
                iterator = range(start, end + 1, step)
            
        elif isinstance(node.set_declaration, ast.DiscreteSet):
            iterator = [self.visit(v) for v in node.set_declaration.values]
            
        elif isinstance(node.set_declaration, ast.Identifier):
            arr_name = node.set_declaration.name
            if arr_name in self.classical_memory:
                iterator = self.classical_memory[arr_name]
                if not isinstance(iterator, (list, tuple, range, np.ndarray)):
                     iterator = [iterator]
            else:
                 raise ValueError(f"Undefined variable in loop: {arr_name}")
        else:
            raise NotImplementedError(f"Loop set type {type(node.set_declaration)} not implemented")

        for val in iterator:
            self.classical_memory[loop_var_name] = val
            for stmt in node.block:
                try:
                    self.visit(stmt)
                except StopIteration: # Break
                    return
                except ContinueException: # Continue
                    break
    def visit_FunctionCall(self, node):
        func_name = node.name.name
        args = [self.visit(arg) for arg in node.arguments]
        if func_name == 'newframe':
            port_arg = node.arguments[0]
            q_idx = 0
            if isinstance(port_arg, ast.Identifier):
                port_name = port_arg.name
                import re
                match = re.search(r'\d+', port_name)
                if match:
                    q_idx = int(match.group())
            
            return {'qubit': q_idx, 'freq': args[1], 'phase': args[2]}
        if func_name in ("rotl", "rotr", "rol", "ror"):
            val = args[0]
            shift = int(args[1])
            width = None
            arg0 = node.arguments[0]
            if isinstance(arg0, ast.Identifier):
                width = self.classical_bit_width.get(arg0.name)

            if isinstance(val, str):
                s = val.replace("_", "")
                try:
                    ival = int(s, 0)      # handles 0b..., 0x..., etc.
                except Exception:
                    ival = int(s, 2) if set(s) <= {"0", "1"} else int(s)
                val = ival
                if width is None:
                    if s.lower().startswith("0b"):
                        width = max(1, len(s) - 2)
                    else:
                        width = max(1, int(val).bit_length())
            else:
                val = int(val)
                if width is None:
                    width = max(1, val.bit_length())

            if width <= 0:
                return int(val)

            mask = (1 << width) - 1
            val &= mask
            shift %= width  # handles negative too in python

            if func_name in ("rotl", "rol"):
                return ((val << shift) | (val >> (width - shift))) & mask
            else:
                return ((val >> shift) | (val << (width - shift))) & mask

        if func_name == 'popcount':
            val = args[0]
            if isinstance(val, int):
                return bin(val).count('1')
            else:
                raise ValueError(f"popcount expects an integer, got {type(val)}")
        if func_name == 'set_frequency':
            frame_obj = args[0]
            new_freq = float(args[1])

            if isinstance(frame_obj, dict) and 'qubit' in frame_obj:
                q_idx = int(frame_obj['qubit'])
                frame_obj['freq'] = new_freq

                if 'freqs' not in self.system_model or not self.system_model['freqs']:
                    self.system_model['freqs'] = [5e9] * self.num_qubits
                if 0 <= q_idx < len(self.system_model['freqs']):
                    self.system_model['freqs'][q_idx] = new_freq

                frame_arg = node.arguments[0]
                if isinstance(frame_arg, ast.Identifier):
                    self.classical_memory[frame_arg.name] = frame_obj

            return None
        if func_name == 'set_phase':
            # set_phase(frame, phase)
            frame_obj = args[0]
            new_phase = float(args[1])

            if isinstance(frame_obj, dict) and 'qubit' in frame_obj:
                frame_obj['phase'] = new_phase
                frame_arg = node.arguments[0]
                if isinstance(frame_arg, ast.Identifier):
                    self.classical_memory[frame_arg.name] = frame_obj

            return None

        if func_name == "capture":
            frame_obj = args[0]
            filt = args[1] if len(args) > 1 else None  
            q_idx = None
            if isinstance(frame_obj, dict) and "qubit" in frame_obj:
                q_idx = int(frame_obj["qubit"])
            bias = float(self.system_model.get("readout_bias", 0.0)) 
            p1 = 0.5 + 0.5 * max(-1.0, min(1.0, bias))
            bit_out = 1 if np.random.rand() < p1 else 0

            return int(bit_out)

        if func_name in ("capture_v1", "capture_v2", "capture_v3"):
            frame_obj = args[0]
            duration_s = float(args[1])
            dt = float(self.system_model.get("dt", 1e-9))

            n_samples = 0
            if dt > 0:
                n_samples = int(round(duration_s / dt))
                n_samples = max(n_samples, 0)

            noise = float(self.system_model.get("readout_noise", 0.0))
            if noise > 0:
                samples = noise * (np.random.randn(n_samples) + 1j * np.random.randn(n_samples))
            else:
                samples = np.zeros(n_samples, dtype=complex)

            q_idx = None
            if isinstance(frame_obj, dict) and "qubit" in frame_obj:
                q_idx = int(frame_obj["qubit"])

            return {
                "name": "capture",
                "frame": frame_obj,
                "qubit": q_idx,
                "dt": dt,
                "duration_s": duration_s,
                "samples": samples,
            }

        if func_name == "sin": return np.sin(args[0])
        if func_name == "cos": return np.cos(args[0])
        if func_name == "sqrt": return np.sqrt(args[0])
        if func_name in self.external_functions:
            return self.external_functions[func_name](*args)
        if func_name in ['gaussian', 'sech', 'gaussian_square', 'drag', 'constant', 'sine']:
             return {'name': func_name, 'args': args}
        if func_name == 'mix':
            return {'name': 'mix', 'operands': args} 
        if func_name == 'scale':
            a0 = args[0] if len(args) > 0 else 0.0
            a1 = args[1] if len(args) > 1 else 1.0
            is_waveform_like = (
                isinstance(a0, dict) or
                isinstance(a0, (list, tuple, np.ndarray)) or
                (Waveform is not None and isinstance(a0, Waveform))
            )
            if is_waveform_like:
                return {'name': 'scale', 'waveform': a0, 'scale': a1}
            try:
                return complex(a0) * complex(a1)
            except Exception:
                return float(a0) * float(a1)


        if func_name == "add":
            if len(args) == 0:
                return 0
            out = args[0]
            for x in args[1:]:
                if isinstance(out, (int, float, complex, np.number)) and isinstance(x, (int, float, complex, np.number)):
                    out = out + x
                else:
                    if isinstance(out, dict) and out.get("name") == "sum":
                        out = {"name": "sum", "operands": list(out.get("operands", [])) + [x]}
                    else:
                        out = {"name": "sum", "operands": [out, x]}
            return out

        if func_name == 'sum':
            return {'name': 'sum', 'operands': args}
        if func_name == 'phase_shift':
            return {'name': 'phase_shift', 'waveform': args[0], 'phase': args[1]}
        if func_name == "get_frequency":
            frame_obj = args[0]
            frame_arg = node.arguments[0]
            if isinstance(frame_arg, ast.Identifier):
                frame_obj = self.classical_memory.get(frame_arg.name, frame_obj)
            if isinstance(frame_obj, dict):
                return float(frame_obj.get("freq", 0.0))
            return float(getattr(frame_obj, "freq", 0.0))

        if func_name == "get_phase":
            frame_obj = args[0]
            frame_arg = node.arguments[0]
            if isinstance(frame_arg, ast.Identifier):
                frame_obj = self.classical_memory.get(frame_arg.name, frame_obj)
            if isinstance(frame_obj, dict):
                return float(frame_obj.get("phase", 0.0))
            return float(getattr(frame_obj, "phase", 0.0))

        if func_name in self.external_functions:
            pyfunc = self.external_functions[func_name]
            try:
                return pyfunc(*args)
            except TypeError:
                return pyfunc(self, *args)


        raise NotImplementedError(f"Function '{func_name}' is not implemented.")

    def visit_BreakStatement(self, node):
        raise StopIteration()
        
    def visit_ContinueStatement(self, node):
        raise ContinueException()

class ContinueException(Exception): pass

# main runner 
def _pick_time_unit(max_t_s: float):
    try:
        max_t_s = float(max_t_s)
    except Exception:
        max_t_s = 0.0
    if max_t_s < 1e-9:
        return (1e12, "ps")
    if max_t_s < 1e-6:
        return (1e9, "ns")
    if max_t_s < 1e-3:
        return (1e6, "us")
    if max_t_s < 1.0:
        return (1e3, "ms")
    return (1.0, "s")


def _compact_kv(detail: dict, *, max_items: int = 6, max_len: int = 120) -> str:
    if not isinstance(detail, dict) or not detail:
        return ""

    items = []
    for k in sorted(detail.keys(), key=lambda x: str(x)):
        try:
            v = detail[k]
            if isinstance(v, float):
                v_s = f"{v:.6g}"
            else:
                v_s = str(v)
            items.append(f"{k}={v_s}")
        except Exception:
            continue

    if len(items) > max_items:
        items = items[:max_items] + ["…"]
    s = ", ".join(items)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def format_timeline(timeline_events, *, show_header: bool = True, show_details: bool = True) -> str:

    events = list(timeline_events or [])
    if not events:
        return "<empty timeline>"

    def _key(ev):
        try:
            return (float(ev.get("t0", 0.0)), float(ev.get("t1", 0.0)), str(ev.get("kind", "")))
        except Exception:
            return (0.0, 0.0, "")

    events.sort(key=_key)

    max_t = 0.0
    for ev in events:
        try:
            max_t = max(max_t, float(ev.get("t1", 0.0)))
        except Exception:
            pass

    scale, unit = _pick_time_unit(max_t)

    w_t = 10
    w_d = 10
    w_kind = 20
    w_res = 22

    lines = []
    if show_header:
        total = max_t * scale
        lines.append(f"Timeline ({unit}), total={total:.6g}{unit}, events={len(events)}")
        lines.append("-" * (w_t * 2 + w_d + w_kind + w_res + 16))

    header = (
        f"{'t0':>{w_t}}  {'t1':>{w_t}}  {'dur':>{w_d}}  "
        f"{'kind':<{w_kind}}  {'resources':<{w_res}}"
    )
    if show_details:
        header += "  detail"
    lines.append(header)
    lines.append(
        f"{'-'*w_t}  {'-'*w_t}  {'-'*w_d}  {'-'*w_kind}  {'-'*w_res}" + ("  " + "-" * 40 if show_details else "")
    )

    for ev in events:
        try:
            t0 = float(ev.get("t0", 0.0)) * scale
            t1 = float(ev.get("t1", 0.0)) * scale
            dur = (float(ev.get("t1", 0.0)) - float(ev.get("t0", 0.0))) * scale
        except Exception:
            t0, t1, dur = 0.0, 0.0, 0.0

        kind = str(ev.get("kind", ""))
        scope = ev.get("scope", None)
        if scope is not None:
            kind = f"{kind}#{scope}"

        resources = ev.get("resources", [])
        if isinstance(resources, (list, tuple)):
            res_s = ",".join(str(r) for r in resources)
        else:
            res_s = str(resources)
        if len(res_s) > w_res:
            res_s = res_s[: w_res - 1] + "…"

        row = f"{t0:>{w_t}.6g}  {t1:>{w_t}.6g}  {dur:>{w_d}.6g}  {kind:<{w_kind}}  {res_s:<{w_res}}"
        if show_details:
            detail = ev.get("detail", {})
            row += "  " + _compact_kv(detail)
        lines.append(row)

    return "\n".join(lines)


def simulate_timeline(qasm_str, shots: int = 1, *, show_details: bool = True) -> str:

    program = openqasm3.parse(qasm_str)

    sys_model = {
        'freqs': [5.0e9],
        'dt': 1e-9  # 1ns
    }
    interpreter = QASM3Interpreter(program, externals=external_funcs, system_model=sys_model)

    shots = max(1, int(shots))
    blocks = []
    for s in range(shots):
        out = interpreter.run_shot()
        tl = out.get("__timeline__", [])
        if shots > 1:
            blocks.append(f"=== Shot {s+1}/{shots} ===")
        blocks.append(format_timeline(tl, show_header=True, show_details=show_details))
        if shots > 1 and s != shots - 1:
            blocks.append("")

    return "\n".join(blocks)

def format_statevector(state, num_qubits, tolerance=1e-10):

    if state is None:
        return "No state available"
    
    terms = []
    for i, amplitude in enumerate(state):
        if abs(amplitude) > tolerance:
            basis_state = format(i, f'0{num_qubits}b')
            real = amplitude.real
            imag = amplitude.imag
            if abs(imag) < tolerance:
                coeff = f"{real:.4f}"
            elif abs(real) < tolerance:
                coeff = f"{imag:.4f}j"
            else:
                sign = "+" if imag >= 0 else "-"
                coeff = f"({real:.4f}{sign}{abs(imag):.4f}j)"
                
            terms.append(f"{coeff}|{basis_state}>")
            
    return " + ".join(terms)
 
def simulate_statevector(qasm_str):
    sys_model = {
    'freqs': [5.0e9], 
    'dt': 1e-9 # 1ns
    }
    program = openqasm3.parse(qasm_str)
    interpreter = QASM3Interpreter(program,externals=external_funcs,system_model=sys_model)
    print("Running statevector simulation (1 shot)...")
    out = interpreter.run_shot()
    state = interpreter.get_quantum_state()
    num_qubits = interpreter.num_qubits
    
    return state, num_qubits
def freeze(x):
    if isinstance(x, dict):
        return tuple(sorted((k, freeze(v)) for k, v in x.items()))
    if isinstance(x, (list, tuple)):
        return tuple(freeze(v) for v in x)
    return x
def fmt_val(v):
    if isinstance(v, bool):
        return format(int(v), "b")
    if isinstance(v, int):
        return format(v, "b")
    if isinstance(v, tuple):
        return "(" + ", ".join(fmt_val(x) for x in v) + ")"
    if isinstance(v, list):
        return "[" + ", ".join(fmt_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{kk}:{fmt_val(vv)}" for kk, vv in sorted(v.items())) + "}"
    return str(v)
import openqasm3

def extract_exist(qasm_str: str) -> dict:
    program = openqasm3.parse(qasm_str)
    exist: dict[str, bool] = {}

    def mark(key):
        if key:
            exist[str(key)] = True

    def get_name(obj):
        if obj is None:
            return None

        nm = getattr(obj, "name", None)
        if isinstance(nm, str):
            return nm

        nm2 = getattr(nm, "name", None)
        if isinstance(nm2, str):
            return nm2

        try:
            return str(obj)
        except Exception:
            return None

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
        mark(tname)
        if tname == "FunctionCall":
            fname = None
            name_obj = getattr(node, "name", None)

            if name_obj is not None:
                fname = getattr(name_obj, "name", None)
                if not isinstance(fname, str):
                    fname = get_name(name_obj)
            if isinstance(fname, str):
                mark(f"func:{fname}")
        if tname == "QuantumGate":
            gname = None
            name_obj = getattr(node, "name", None)
            if name_obj is not None:
                gname = getattr(name_obj, "name", None)
                if not isinstance(gname, str):
                    gname = get_name(name_obj)
            if isinstance(gname, str):
                mark(f"gate:{gname}")

        if tname == "Identifier":
            nm = getattr(node, "name", None)
            if isinstance(nm, str) and nm.startswith("$"):
                mark("uses_physical_qubit")

        d = getattr(node, "__dict__", None)
        if isinstance(d, dict):
            for v in d.values():
                walk(v)

    walk(getattr(program, "statements", None))
    return exist

def simulate_qasm_distribution(qasm_str, shots=1000):
    program = openqasm3.parse(qasm_str)
    
    sys_model = {
    'freqs': [5.0e9], 
    'dt': 1e-9 # 1ns
    }
    program = openqasm3.parse(qasm_str)
    interpreter = QASM3Interpreter(program,externals=external_funcs,system_model=sys_model)

    results = []
    print(f"Running simulation with {shots} shots...")
    
    for _ in range(shots):
        out = interpreter.run_shot()
        out.pop("__timeline__", None)
        out.pop("__measurements__", None)
        #out={"__cc_out": out.get("__cc_out", 0)}
        res_key=freeze(out)
        results.append(res_key)   
    counts = Counter(results)
    formatted_dist = {}
    for res_tuple, count in counts.items():
        key_str = ", ".join([f"{k}={fmt_val(v)}" for k, v in res_tuple])
        formatted_dist[key_str] = count / shots
        
    return formatted_dist



if __name__ == "__main__":
# a test case 

    tobetested='''OPENQASM 3;
include "stdgates.inc";

// Pulse background 000002
qubit[5] q;

defcalgrammar "openpulse";

const float drive_freq_0 = 6.190303e9;
const float meas_freq_0  = 6.479896e9;
const float drive_freq_1 = 6.160229e9;
const float meas_freq_1  = 6.031293e9;
const float drive_freq_2 = 6.412279e9;
const float meas_freq_2  = 6.677964e9;
const float drive_freq_3 = 5.282711e9;
const float meas_freq_3  = 6.795719e9;
const float drive_freq_4 = 4.672408e9;
const float meas_freq_4  = 6.864890e9;

cal {
  // --- declare ports ---
  extern port d0;
  extern port m0;
  extern port a0;
  extern port d1;
  extern port m1;
  extern port a1;
  extern port d2;
  extern port m2;
  extern port a2;
  extern port d3;
  extern port m3;
  extern port a3;
  extern port d4;
  extern port m4;
  extern port a4;

  // --- extern waveform templates (common) ---
  extern gaussian(complex[float[32]] amp, duration d, duration sigma) -> waveform;
  extern drag(complex[float[32]] amp, duration d, duration sigma, float[32] beta) -> waveform;
  extern constant(complex[float[32]] amp, duration d) -> waveform;
  extern sine(complex[float[32]] amp, duration d, float[64] frequency, angle phase) -> waveform;
  extern gaussian_square(complex[float[32]] amp, duration d, duration square_width, duration sigma) -> waveform;

  // --- extern capture/discriminate hooks (for measure-style tasks) ---
  extern capture(frame capture_frame, waveform filter) -> bit;
  extern capture_v1(frame capture_frame, duration d) -> waveform;
  extern discriminate(complex[float[64]] iq) -> bit;

  // --- create frames ---
  frame q0_drive = newframe(d0, drive_freq_0, 0.0);
  frame q0_meas  = newframe(m0,  meas_freq_0,  0.0);
  frame q0_acq   = newframe(a0,   meas_freq_0,  0.0);
  frame q1_drive = newframe(d1, drive_freq_1, 0.0);
  frame q1_meas  = newframe(m1,  meas_freq_1,  0.0);
  frame q1_acq   = newframe(a1,   meas_freq_1,  0.0);
  frame q2_drive = newframe(d2, drive_freq_2, 0.0);
  frame q2_meas  = newframe(m2,  meas_freq_2,  0.0);
  frame q2_acq   = newframe(a2,   meas_freq_2,  0.0);
  frame q3_drive = newframe(d3, drive_freq_3, 0.0);
  frame q3_meas  = newframe(m3,  meas_freq_3,  0.0);
  frame q3_acq   = newframe(a3,   meas_freq_3,  0.0);
  frame q4_drive = newframe(d4, drive_freq_4, 0.0);
  frame q4_meas  = newframe(m4,  meas_freq_4,  0.0);
  frame q4_acq   = newframe(a4,   meas_freq_4,  0.0);

  // --- background pulse actions (phase/freq/time context) ---
  waveform _bg_wf = gaussian(0.8, 50dt, 27dt);
  shift_phase(q1_drive, 0.556885);
  set_frequency(q1_drive, (get_frequency(q1_drive) + -12538389.0));
  delay[66dt] q1_drive;
  play(q1_drive, _bg_wf);
  shift_phase(q2_drive, 0.504095);
  set_frequency(q2_drive, (get_frequency(q2_drive) + 5704355.0));
  delay[26dt] q2_drive;
  play(q2_drive, _bg_wf);
  shift_phase(q3_drive, -0.340456);
  set_frequency(q3_drive, (get_frequency(q3_drive) + -16343780.0));
  delay[22dt] q3_drive;
  play(q3_drive, _bg_wf);
  shift_phase(q4_drive, -0.440536);
  set_frequency(q4_drive, (get_frequency(q4_drive) + -11819093.0));
  delay[26dt] q4_drive;
  play(q4_drive, _bg_wf);
  barrier q1_drive, q2_drive, q3_drive, q4_drive;
}

// --- gate-level background circuit ---
h q[4];
h q[4];
x q[2];
rx(0.356813) q[2];
rx(0.782476) q[0];
rz(-0.521408) q[3];

// === CORE_TASK_START ===
// virtual_z_shift_phase | shift_phase_then_play: Implement a virtual-Z by shifting the phase of the drive frame before a play.
cal {
  waveform w = gaussian(0.5+0.0im, 123dt, 51dt);
  shift_phase(q3_drive, -0.208738);
  play(q3_drive, w);
}
// === CORE_TASK_END ===

// === MEASUREMENT_START ===
bit[5] c;
c[3] = measure q[3];
// === MEASUREMENT_END ===
    '''
    try:
        distribution = simulate_qasm_distribution(tobetested, shots=1000)
        for outcome, prob in distribution.items():
            print(f"State [{outcome}]: {prob:.2%}")
    except Exception as e:
        print(f"Error simulating: {e}")
        traceback.print_exc()