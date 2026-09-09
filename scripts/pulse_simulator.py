"""
Lab-frame pulse simulator with flexible waveforms based on QuTiP

1) This simulator models a single-qubit XY drive per pulse in the lab frame:
       H_p(t) = (|Ω(t)|/2) [ cos(ω_d t + φ + arg Ω(t)) X + sin(ω_d t + φ + arg Ω(t)) Y ]
   where Ω(t) is the (possibly complex) envelope, ω_d=2π f_d is the carrier angular frequency,
   and φ is the frame phase offset.
   - If Ω(t) is real, arg Ω(t) is 0 (or π if negative).
   - If Ω(t) is complex (I + iQ), its argument adds a time-dependent phase offset.

2) Units
   - times: seconds
   - qubit frequencies & carrier frequencies: Hz
   - phases: radians
   - amplitudes: either "Hz" (default, meaning |Ω|/2π) or "rad/s" (meaning |Ω|)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple, Union
import numpy as np
from scipy.linalg import expm


# Basic operators

I2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)


def kron_n(ops: Sequence[np.ndarray]) -> np.ndarray:
    out = np.array([[1]], dtype=complex)
    for op in ops:
        out = np.kron(out, op)
    return out


def op_on(N: int, i: int, op: np.ndarray) -> np.ndarray:
    ops = [I2] * N
    ops[i] = op
    return kron_n(ops)


def two_body(N: int, i: int, j: int, op_i: np.ndarray, op_j: np.ndarray) -> np.ndarray:
    ops = [I2] * N
    ops[i] = op_i
    ops[j] = op_j
    return kron_n(ops)


def window(t: float, t_start: float, t_stop: float) -> float:
    return 1.0 if (t_start <= t <= t_stop) else 0.0


def _sech(x: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    return 1.0 / np.cosh(x)



# Waveforms (OpenPulse-ish)

ComplexLike = Union[complex, float, np.complex128, np.float64]
EnvelopeFn = Callable[[float], ComplexLike]


@dataclass(frozen=True)
class Waveform:
    duration: float
    _sample: EnvelopeFn

    def __post_init__(self) -> None:
        if self.duration <= 0:
            raise ValueError("Waveform.duration must be > 0")

    def sample(self, t: float) -> complex:
        tt = float(np.clip(t, 0.0, self.duration))
        v = self._sample(tt)
        return complex(v)

    @staticmethod
    def constant(amp: ComplexLike, duration: float) -> "Waveform":
        a = complex(amp)

        def s(_: float) -> complex:
            return a

        return Waveform(duration=float(duration), _sample=s)

    @staticmethod
    def gaussian(amp: ComplexLike, duration: float, sigma: float) -> "Waveform":
        a = complex(amp)
        d = float(duration)
        sig = float(sigma)
        if sig <= 0:
            raise ValueError("sigma must be > 0")

        t0 = 0.5 * d

        def s(t: float) -> complex:
            return a * np.exp(-0.5 * ((t - t0) / sig) ** 2)

        return Waveform(duration=d, _sample=s)

    @staticmethod
    def sech(amp: ComplexLike, duration: float, sigma: float) -> "Waveform":
        a = complex(amp)
        d = float(duration)
        sig = float(sigma)
        if sig <= 0:
            raise ValueError("sigma must be > 0")

        t0 = 0.5 * d

        def s(t: float) -> complex:
            return a * _sech((t - t0) / sig)

        return Waveform(duration=d, _sample=s)

    @staticmethod
    def sine(amp: ComplexLike, duration: float, frequency_hz: float, phase_rad: float = 0.0) -> "Waveform":
        a = complex(amp)
        d = float(duration)
        f = float(frequency_hz)
        ph = float(phase_rad)

        def s(t: float) -> complex:
            return a * np.sin(2.0 * np.pi * f * t + ph)

        return Waveform(duration=d, _sample=s)

    @staticmethod
    def gaussian_square(amp: ComplexLike, duration: float, square_width: float, sigma: float) -> "Waveform":
        a = complex(amp)
        d = float(duration)
        w = float(square_width)
        sig = float(sigma)
        if sig <= 0:
            raise ValueError("sigma must be > 0")
        if w < 0:
            raise ValueError("square_width must be >= 0")
        if w > d:
            raise ValueError("square_width must be <= duration")
        edge = 0.5 * (d - w)
        if edge == 0.0:
            return Waveform.constant(a, d)

        c_rise = edge
        c_fall = edge + w

        def s(t: float) -> complex:
            if t < edge:
                return a * np.exp(-0.5 * ((t - c_rise) / sig) ** 2)
            if t <= edge + w:
                return a
            return a * np.exp(-0.5 * ((t - c_fall) / sig) ** 2)

        return Waveform(duration=d, _sample=s)

    @staticmethod
    def drag(amp: ComplexLike, duration: float, sigma: float, beta: float) -> "Waveform":
        a = complex(amp)
        d = float(duration)
        sig = float(sigma)
        b = float(beta)
        if sig <= 0:
            raise ValueError("sigma must be > 0")

        t0 = 0.5 * d

        def s(t: float) -> complex:
            g = np.exp(-0.5 * ((t - t0) / sig) ** 2)
            dg = -((t - t0) / (sig ** 2)) * g
            return a * (g + 1j * b * dg)

        return Waveform(duration=d, _sample=s)

    @staticmethod
    def from_samples(
        samples: Sequence[ComplexLike],
        duration: float,
        interpolation: str = "zoh",
    ) -> "Waveform":
        if len(samples) < 1:
            raise ValueError("samples must be non-empty")
        d = float(duration)
        if d <= 0:
            raise ValueError("duration must be > 0")

        y = np.asarray(samples, dtype=complex)
        n = int(y.shape[0])
        dt = d / n

        if interpolation not in ("zoh", "linear"):
            raise ValueError('interpolation must be "zoh" or "linear"')

        if interpolation == "zoh":

            def s(t: float) -> complex:
                k = int(np.floor(t / dt))
                if k >= n:
                    k = n - 1
                return y[k]

        else:  # linear
            tk = (np.arange(n) + 0.5) * dt

            def s(t: float) -> complex:
                if t <= tk[0]:
                    return y[0]
                if t >= tk[-1]:
                    return y[-1]
                j = int(np.searchsorted(tk, t, side="right"))
                t1, t2 = tk[j - 1], tk[j]
                y1, y2 = y[j - 1], y[j]
                w = (t - t1) / (t2 - t1)
                return (1 - w) * y1 + w * y2

        return Waveform(duration=d, _sample=s)


    def _assert_same_duration(self, other: "Waveform", tol: float = 1e-18) -> None:
        if abs(self.duration - other.duration) > tol:
            raise ValueError(f"Waveform durations differ ({self.duration} vs {other.duration}).")

    def mix(self, other: "Waveform") -> "Waveform":
        self._assert_same_duration(other)

        def s(t: float) -> complex:
            return self.sample(t) * other.sample(t)

        return Waveform(duration=self.duration, _sample=s)

    def sum(self, other: "Waveform") -> "Waveform":
        self._assert_same_duration(other)

        def s(t: float) -> complex:
            return self.sample(t) + other.sample(t)

        return Waveform(duration=self.duration, _sample=s)

    def phase_shift(self, angle_rad: float) -> "Waveform":
        ang = float(angle_rad)
        ph = np.exp(1j * ang)

        def s(t: float) -> complex:
            return self.sample(t) * ph

        return Waveform(duration=self.duration, _sample=s)

    def scale(self, factor: float) -> "Waveform":
        fac = float(factor)

        def s(t: float) -> complex:
            return self.sample(t) * fac

        return Waveform(duration=self.duration, _sample=s)


# Pulses

@dataclass(frozen=True)
class Pulse:
    qubit: int
    carrier_hz: float
    phase_rad: float
    envelope: Callable[[float], complex] 
    t_start: float
    t_stop: float


class PulseSimulatorNumpy:
    def __init__(
        self,
        N: int,
        qubit_freqs_hz: Sequence[float],
        J_hz: Optional[np.ndarray] = None,
        coupling_type: str = "ZZ",
        amp_unit: str = "Hz",
    ):
        if len(qubit_freqs_hz) != N:
            raise ValueError("len(qubit_freqs_hz) must equal N")
        if amp_unit not in ("Hz", "rad/s"):
            raise ValueError('amp_unit must be "Hz" or "rad/s"')
        if coupling_type not in ("ZZ", "XXYY"):
            raise ValueError("coupling_type must be 'ZZ' or 'XXYY'")

        self.N = int(N)
        self.qubit_freqs_hz = np.array(qubit_freqs_hz, dtype=float)
        self.J_hz = None if J_hz is None else np.array(J_hz, dtype=float)
        self.coupling_type = coupling_type
        self.amp_unit = amp_unit

        self._pulses: List[Pulse] = []

        # Precompute single-qubit ops on full Hilbert space
        self._Xi = [op_on(self.N, i, X) for i in range(self.N)]
        self._Yi = [op_on(self.N, i, Y) for i in range(self.N)]
        self._Zi = [op_on(self.N, i, Z) for i in range(self.N)]

        self._H0 = self._build_drift()


    def add_waveform_pulse(
        self,
        qubit: int,
        waveform: Waveform,
        t_start: float = 0.0,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:
        q = int(qubit)
        ts = float(t_start)
        te = ts + float(waveform.duration)

        def env(t: float, ts=ts, te=te, wf=waveform) -> complex:
            if t < ts or t > te:
                return 0.0 + 0.0j
            return wf.sample(t - ts)

        self._pulses.append(
            Pulse(
                qubit=q,
                carrier_hz=float(carrier_hz),
                phase_rad=float(phase_rad),
                envelope=env,
                t_start=ts,
                t_stop=te,
            )
        )

    def add_constant_pulse(
        self,
        qubit: int,
        amp: ComplexLike,
        duration: float,
        t_start: float = 0.0,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:
        self.add_waveform_pulse(
            qubit=qubit,
            waveform=Waveform.constant(amp=amp, duration=duration),
            t_start=t_start,
            carrier_hz=carrier_hz,
            phase_rad=phase_rad,
        )

    def add_gaussian_pulse(
        self,
        qubit: int,
        amp: ComplexLike,
        t0: float,
        sigma: float,
        t_start: float,
        t_stop: float,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:

        if t_stop <= t_start:
            raise ValueError("t_stop must be > t_start")
        d = float(t_stop - t_start)
        sig = float(sigma)
        a = complex(amp)
        center_rel = float(t0 - t_start)

        def s(t: float) -> complex:
            return a * np.exp(-0.5 * ((t - center_rel) / sig) ** 2)

        wf = Waveform(duration=d, _sample=s)
        self.add_waveform_pulse(
            qubit=qubit,
            waveform=wf,
            t_start=t_start,
            carrier_hz=carrier_hz,
            phase_rad=phase_rad,
        )

    def add_custom_pulse(
        self,
        qubit: int,
        envelope: Callable[[float], ComplexLike],
        t_start: float,
        t_stop: float,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:

        if t_stop <= t_start:
            raise ValueError("t_stop must be > t_start")

        ts = float(t_start)
        te = float(t_stop)

        def env(t: float, envelope=envelope, ts=ts, te=te) -> complex:
            if t < ts or t > te:
                return 0.0 + 0.0j
            return complex(envelope(t))

        self._pulses.append(
            Pulse(
                qubit=int(qubit),
                carrier_hz=float(carrier_hz),
                phase_rad=float(phase_rad),
                envelope=env,
                t_start=ts,
                t_stop=te,
            )
        )

    def _amp_to_omega(self, a_abs: float) -> float:
        return (2.0 * np.pi * float(a_abs)) if self.amp_unit == "Hz" else float(a_abs)

    def _build_drift(self) -> np.ndarray:

        H0 = np.zeros((2 ** self.N, 2 ** self.N), dtype=complex)
        for i, f0 in enumerate(self.qubit_freqs_hz):
            w0 = 2.0 * np.pi * float(f0)
            H0 = H0 + 0.5 * w0 * self._Zi[i]

        # Couplings
        if self.J_hz is not None:
            for i in range(self.N):
                for j in range(i + 1, self.N):
                    Jij_hz = float(self.J_hz[i, j])
                    if Jij_hz == 0.0:
                        continue
                    Jij = 2.0 * np.pi * Jij_hz
                    if self.coupling_type == "ZZ":
                        H0 = H0 + 0.5 * Jij * two_body(self.N, i, j, Z, Z)
                    else:  # XXYY
                        H0 = H0 + 0.5 * Jij * (
                            two_body(self.N, i, j, X, X) + two_body(self.N, i, j, Y, Y)
                        )

        return H0

    def H(self, t: float) -> np.ndarray:
        Ht = self._H0.copy()

        for p in self._pulses:
            if not (p.t_start <= t <= p.t_stop):
                continue
            i = p.qubit
            wd = 2.0 * np.pi * p.carrier_hz

            env_val = complex(p.envelope(t))
            a_abs = abs(env_val)
            if a_abs == 0.0:
                continue

            Omega_t = self._amp_to_omega(a_abs)
            extra = float(np.angle(env_val))
            theta = wd * t + p.phase_rad + extra
            Ht = Ht + 0.5 * Omega_t * (np.cos(theta) * self._Xi[i] + np.sin(theta) * self._Yi[i])

        return Ht

    def unitary(self, T: float, n_steps: int = 20000) -> np.ndarray:

        if T <= 0:
            raise ValueError("T must be > 0")
        if n_steps < 1:
            raise ValueError("n_steps must be >= 1")

        dim = 2 ** self.N
        U = np.eye(dim, dtype=complex)
        dt = float(T) / float(n_steps)

        for k in range(n_steps):
            t_mid = (k + 0.5) * dt
            Hmid = self.H(t_mid)
            U = expm(-1j * Hmid * dt) @ U

        return U

    @staticmethod
    def equal_up_to_global_phase(U: np.ndarray, V: np.ndarray, atol: float = 1e-7) -> Tuple[bool, complex]:
        inner = np.trace(V.conj().T @ U)
        phase = inner / (abs(inner) + 1e-30)
        ok = np.allclose(U, phase * V, atol=atol, rtol=0)
        return ok, phase


from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple
import numpy as np

try:
    import qutip as qt
except Exception as e:
    qt = None

from collections import OrderedDict
import hashlib
import threading

_QT_CACHE_LOCK = threading.RLock()
_QT_COEFF_CACHE: "OrderedDict[tuple, tuple[np.ndarray, np.ndarray]]" = OrderedDict()
_QT_UNITARY_CACHE: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_QT_MAX_COEFF = 256      
_QT_MAX_UNITARY = 64     

# this part is not necessary, it's just to speed up repeated simulations of the same pulse shapes on the same system

def _lru_get(cache: "OrderedDict", key):
    try:
        val = cache.pop(key)
    except KeyError:
        return None
    cache[key] = val
    return val

def _lru_put(cache: "OrderedDict", key, val, max_items: int):
    if key in cache:
        cache.pop(key, None)
    cache[key] = val
    while len(cache) > max_items:
        cache.popitem(last=False)

def _hash_bytes(*chunks: bytes, digest_size: int = 16) -> str:
    h = hashlib.blake2b(digest_size=digest_size)
    for c in chunks:
        h.update(c)
    return h.hexdigest()

def _hash_system_signature(N: int, qubit_freqs_hz: np.ndarray, J_hz: Optional[np.ndarray], coupling_type: str, amp_unit: str) -> str:
    parts = [str(int(N)).encode(), coupling_type.encode(), amp_unit.encode(), np.asarray(qubit_freqs_hz, dtype=float).tobytes()]
    if J_hz is None:
        parts.append(b"J=None")
    else:
        parts.append(np.asarray(J_hz, dtype=float).tobytes())
    return _hash_bytes(*parts)

def _hash_pulse_signature(p, fp_points: int = 64) -> str:
    meta = np.array([p.qubit, p.carrier_hz, p.phase_rad, p.t_start, p.t_stop], dtype=np.float64).tobytes()
    if fp_points < 4:
        fp_points = 4
    ts = np.linspace(float(p.t_start), float(p.t_stop), int(fp_points), dtype=np.float64)
    vals = np.fromiter((complex(p.envelope(float(t))) for t in ts), dtype=np.complex128, count=ts.size)
    vals_q = np.round(vals.real, 12) + 1j * np.round(vals.imag, 12)
    return _hash_bytes(meta, vals_q.astype(np.complex128).tobytes())


def _qt_op_on(N: int, i: int, op: "qt.Qobj") -> "qt.Qobj":
    ops = [qt.qeye(2) for _ in range(N)]
    ops[i] = op
    return qt.tensor(ops)


def _qt_two_body(N: int, i: int, j: int, op_i: "qt.Qobj", op_j: "qt.Qobj") -> "qt.Qobj":
    ops = [qt.qeye(2) for _ in range(N)]
    ops[i] = op_i
    ops[j] = op_j
    return qt.tensor(ops)


@dataclass(frozen=True)
class _PulseQt:
    qubit: int
    carrier_hz: float
    phase_rad: float
    envelope: Callable[[float], complex]   # abs-time envelope a(t) in user's amp_unit
    t_start: float
    t_stop: float


class PulseSimulator:   # this one is based on QuTiP

    def __init__(
        self,
        N: int,
        qubit_freqs_hz: Sequence[float],
        J_hz: Optional[np.ndarray] = None,
        coupling_type: str = "ZZ",
        amp_unit: str = "Hz",
    ):
        if qt is None:
            raise ImportError("QuTiP is not installed. pip install qutip")
        if len(qubit_freqs_hz) != N:
            raise ValueError("len(qubit_freqs_hz) must equal N")
        if amp_unit not in ("Hz", "rad/s"):
            raise ValueError('amp_unit must be "Hz" or "rad/s"')
        if coupling_type not in ("ZZ", "XXYY"):
            raise ValueError("coupling_type must be 'ZZ' or 'XXYY'")

        self.N = int(N)
        self.qubit_freqs_hz = np.asarray(qubit_freqs_hz, dtype=float)
        self.J_hz = None if J_hz is None else np.asarray(J_hz, dtype=float)
        self.coupling_type = coupling_type
        self.amp_unit = amp_unit

        self._sx = qt.sigmax()
        self._sy = qt.sigmay()
        self._sz = qt.sigmaz()
        self._sp = qt.sigmap()
        self._sm = qt.sigmam()

        self._Sp = [_qt_op_on(self.N, i, self._sp) for i in range(self.N)]
        self._Sm = [_qt_op_on(self.N, i, self._sm) for i in range(self.N)]
        self._Sz = [_qt_op_on(self.N, i, self._sz) for i in range(self.N)]

        self._pulses: List[_PulseQt] = []
        self._H0 = self._build_drift()

        self._system_sig = _hash_system_signature(self.N, self.qubit_freqs_hz, self.J_hz, self.coupling_type, self.amp_unit)
        self._pulse_sig_cache = {}  # id(pulse) -> signature string
        self._pulse_fp_points = 64
    def _build_drift(self) -> "qt.Qobj":
        H0 = 0 * _qt_op_on(self.N, 0, self._sz) 
        for i, f0 in enumerate(self.qubit_freqs_hz):
            w0 = 2.0 * np.pi * float(f0)
            H0 = H0 + 0.5 * w0 * self._Sz[i]

        if self.J_hz is not None:
            for i in range(self.N):
                for j in range(i + 1, self.N):
                    Jij_hz = float(self.J_hz[i, j])
                    if Jij_hz == 0.0:
                        continue
                    Jij = 2.0 * np.pi * Jij_hz
                    if self.coupling_type == "ZZ":
                        H0 = H0 + 0.5 * Jij * _qt_two_body(self.N, i, j, self._sz, self._sz)
                    else:
                        H0 = H0 + 0.5 * Jij * (
                            _qt_two_body(self.N, i, j, self._sx, self._sx) +
                            _qt_two_body(self.N, i, j, self._sy, self._sy)
                        )
        return H0

    def add_constant_pulse(
        self,
        qubit: int,
        amp: ComplexLike,
        duration: float,
        t_start: float = 0.0,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:
        self.add_waveform_pulse(
            qubit=qubit,
            waveform=Waveform.constant(amp=amp, duration=duration),
            t_start=t_start,
            carrier_hz=carrier_hz,
            phase_rad=phase_rad,
        )

    def add_gaussian_pulse(
        self,
        qubit: int,
        amp: ComplexLike,
        t0: float,
        sigma: float,
        t_start: float,
        t_stop: float,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:

        if t_stop <= t_start:
            raise ValueError("t_stop must be > t_start")
        d = float(t_stop - t_start)
        sig = float(sigma)
        a = complex(amp)
        center_rel = float(t0 - t_start)

        def s(t: float) -> complex:
            return a * np.exp(-0.5 * ((t - center_rel) / sig) ** 2)

        wf = Waveform(duration=d, _sample=s)
        self.add_waveform_pulse(
            qubit=qubit,
            waveform=wf,
            t_start=t_start,
            carrier_hz=carrier_hz,
            phase_rad=phase_rad,
        )

    def add_custom_pulse(
        self,
        qubit: int,
        envelope: Callable[[float], complex],
        t_start: float,
        t_stop: float,
        carrier_hz: float = 0.0,
        phase_rad: float = 0.0,
    ) -> None:
        if t_stop <= t_start:
            raise ValueError("t_stop must be > t_start")
        self._pulses.append(
            _PulseQt(
                qubit=int(qubit),
                carrier_hz=float(carrier_hz),
                phase_rad=float(phase_rad),
                envelope=lambda t, env=envelope: complex(env(t)),
                t_start=float(t_start),
                t_stop=float(t_stop),
            )
        )

    def add_waveform_pulse(self, qubit: int, waveform, t_start: float = 0.0, carrier_hz: float = 0.0, phase_rad: float = 0.0) -> None:
        ts = float(t_start)
        te = ts + float(waveform.duration)

        def env_abs_time(t: float, ts=ts, te=te, wf=waveform) -> complex:
            if t < ts or t > te:
                return 0.0 + 0.0j
            return complex(wf.sample(t - ts))

        self._pulses.append(
            _PulseQt(
                qubit=int(qubit),
                carrier_hz=float(carrier_hz),
                phase_rad=float(phase_rad),
                envelope=env_abs_time,
                t_start=ts,
                t_stop=te,
            )
        )

    def _k_scale(self) -> float:
        return np.pi if self.amp_unit == "Hz" else 0.5


    def _pulse_sig(self, p: "_PulseQt") -> str:
        pid = id(p)
        sig = self._pulse_sig_cache.get(pid)
        if sig is None:
            sig = _hash_pulse_signature(p, fp_points=self._pulse_fp_points)
            self._pulse_sig_cache[pid] = sig
        return sig

    def _schedule_sig(self) -> str:
        hs = hashlib.blake2b(digest_size=16)
        hs.update(self._system_sig.encode())
        hs.update(str(len(self._pulses)).encode())
        for p in self._pulses:
            hs.update(self._pulse_sig(p).encode())
        return hs.hexdigest()

    def unitary(self, T: float, n_steps: int = 20000) -> np.ndarray:
        if T <= 0:
            raise ValueError("T must be > 0")
        if n_steps < 1:
            raise ValueError("n_steps must be >= 1")

        T = float(T)
        # print('T:', T)

        sched_sig = self._schedule_sig()
        unitary_key = ("qutip", self._system_sig, sched_sig, T, n_steps)
        with _QT_CACHE_LOCK:
            hit = _lru_get(_QT_UNITARY_CACHE, unitary_key)
        if hit is not None:
            #print("QT cache hit")
            return hit

        tlist = np.linspace(0.0, T, n_steps + 1, dtype=np.float64)
        t_hash = _hash_bytes(tlist.tobytes())

        k = self._k_scale()
        H_terms = [self._H0]

        use_arrays = True
        array_terms = []

        for p in self._pulses:
            i = p.qubit
            wd = 2.0 * np.pi * p.carrier_hz
            ph = p.phase_rad

            pulse_sig = self._pulse_sig(p)
            coeff_key = ("coeff", pulse_sig, t_hash, float(k))
            with _QT_CACHE_LOCK:
                coeff_pair = _lru_get(_QT_COEFF_CACHE, coeff_key)

            if coeff_pair is None:

                c_minus = np.zeros(tlist.shape[0], dtype=np.complex128)
                c_plus  = np.zeros(tlist.shape[0], dtype=np.complex128)

                mask = (tlist >= p.t_start) & (tlist <= p.t_stop)
                if np.any(mask):
                    ts = tlist[mask]
                    a = np.fromiter((complex(p.envelope(float(t))) for t in ts), dtype=np.complex128, count=ts.size)
                    c_minus[mask] = k * np.exp(1j * (wd * ts + ph)) * a
                    c_plus[mask]  = k * np.exp(-1j * (wd * ts + ph)) * np.conjugate(a)

                coeff_pair = (c_minus, c_plus)
                with _QT_CACHE_LOCK:
                    _lru_put(_QT_COEFF_CACHE, coeff_key, coeff_pair, _QT_MAX_COEFF)

            c_minus, c_plus = coeff_pair
            array_terms.append([self._Sm[i], c_minus])
            array_terms.append([self._Sp[i], c_plus])


        try:
            H_terms_full = H_terms + array_terms
            H = qt.QobjEvo(H_terms_full, tlist=tlist)
        except Exception:
            use_arrays = False

        if not use_arrays:

            H_terms = [self._H0]
            for p in self._pulses:
                i = p.qubit
                wd = 2.0 * np.pi * p.carrier_hz
                ph = p.phase_rad

                def c_minus(t, args=None, p=p, wd=wd, ph=ph, k=k):
                    if t < p.t_start or t > p.t_stop:
                        return 0.0j
                    a = complex(p.envelope(t))
                    return k * np.exp(1j * (wd * t + ph)) * a

                def c_plus(t, args=None, p=p, wd=wd, ph=ph, k=k):
                    if t < p.t_start or t > p.t_stop:
                        return 0.0j
                    a = complex(p.envelope(t))
                    return k * np.exp(-1j * (wd * t + ph)) * np.conjugate(a)

                H_terms.append([self._Sm[i], c_minus])
                H_terms.append([self._Sp[i], c_plus])

            H = qt.QobjEvo(H_terms, tlist=tlist)
        
        max_internal = max(10000, int(50 * n_steps))

        U = qt.propagator(H, tlist[-1], [], args=None, options=qt.Options(nsteps=max_internal))
        U_np = np.array(U.full(), dtype=complex)

        with _QT_CACHE_LOCK:
            _lru_put(_QT_UNITARY_CACHE, unitary_key, U_np, _QT_MAX_UNITARY)
        return U_np

    @staticmethod
    def equal_up_to_global_phase(U: np.ndarray, V: np.ndarray, atol: float = 1e-7) -> Tuple[bool, complex]:
        inner = np.trace(V.conj().T @ U)
        phase = inner / (abs(inner) + 1e-30)
        ok = np.allclose(U, phase * V, atol=atol, rtol=0)
        return ok, phase

    @staticmethod
    def clear_global_cache() -> None:

        with _QT_CACHE_LOCK:
            _QT_COEFF_CACHE.clear()
            _QT_UNITARY_CACHE.clear()


if __name__ == "__main__":
# a test of simple pulse
    T = 20e-9
    sim= PulseSimulator(N=1, qubit_freqs_hz=[0.0], amp_unit="Hz")
    amp_hz = 1.0 / (2.0 * T)
    sim.add_constant_pulse(
        qubit=0,
        amp=amp_hz,
        duration=T,
        t_start=0.0,
        carrier_hz=0.0,
        phase_rad=0.0,
    )

    U = sim.unitary(T, n_steps=20000)

    expected = np.array([[0.0, -1.0j],
                         [-1.0j, 0.0]], dtype=complex)

    ok, phase = PulseSimulator.equal_up_to_global_phase(U, expected, atol=5e-6)

    print("U(T)=\n", U)
    print("Expected=\n", expected)
    print("Global phase factor found =", phase)
    print("Close up to global phase?", ok)
