"""Physics-based kick simulator. Lets the whole stack run with no hardware.

A kick is modeled as a half-sine force pulse along the launch direction, followed by free
flight (accelerometer reads about 0 g), a landing spike, and a settle. Spin builds during
contact and stays constant in flight. Force sensors ring with the pulse and weight by how
close each one sits to the contact point. Contact height and side offset drive topspin and
sidespin (torque = r x F), so the strike point carries real information.

The PRIORS below are simulator settings chosen to be physically plausible. They are NOT
measurements of real players. Replace them by recording and labeling your own kicks.
"""
from __future__ import annotations

import time
from collections import deque

import numpy as np

from config import (ACCEL_LSB_PER_G, ACCEL_RANGE_G, G, GYRO_LSB_PER_DPS, GYRO_RANGE_DPS,
                    SAMPLE_RATE_HZ)
from features import SENSOR_DIRS
from protocol import Sample

# (mean, std) for each quantity. Speed m/s, angle deg, contact ms, spin deg/s.
PRIORS = {
    "drive":   dict(speed=(27, 3),  angle=(10, 4), contact=(9, 1),    top=(250, 150),  side=(0, 250)),
    "curl":    dict(speed=(22, 3),  angle=(14, 4), contact=(11, 1.5), top=(100, 150),  side=(1400, 300)),
    "chip":    dict(speed=(14, 2),  angle=(45, 6), contact=(13, 1.5), top=(-900, 250), side=(0, 200)),
    "pass":    dict(speed=(11, 2),  angle=(4, 2),  contact=(15, 2),   top=(100, 100),  side=(0, 120)),
    "knuckle": dict(speed=(24, 3),  angle=(9, 3),  contact=(8, 1),    top=(0, 60),     side=(0, 60)),
}
K_SIDE = 3500.0  # deg/s of sidespin per unit of side offset
K_TOP = 1800.0   # deg/s of topspin per unit of contact height


def _unit(rng):
    v = rng.normal(size=3)
    return v / np.linalg.norm(v)


def synth_kick(technique: str, rng: np.random.Generator, spread: float = 1.0,
               fs: int = SAMPLE_RATE_HZ, clip: bool = True, rest_s: float = 0.35,
               tail_s: float = 1.0) -> dict:
    """Return arrays t, a (g), g (dps), f (ADC) plus the ground truth used to make them."""
    p = PRIORS[technique]
    draw = lambda k: rng.normal(p[k][0], p[k][1] * spread)
    v = max(4.0, draw("speed"))
    theta = max(1.0, draw("angle"))
    tc = max(5.0, draw("contact")) / 1000.0
    top, side = draw("top"), draw("side")
    roll = rng.normal(0, 100 * spread)
    phi = rng.normal(0, 4 * spread)
    lat = float(np.clip(-side / K_SIDE + rng.normal(0, 0.04 * spread), -0.9, 0.9))
    vert = float(np.clip(top / K_TOP + rng.normal(0, 0.05 * spread), -0.9, 0.9))

    hang = 2 * v * np.sin(np.radians(theta)) / G
    t0 = rest_s + rng.uniform(0, 1 / fs)
    t_end = t0 + tc
    t_land = t_end + hang
    n = int((t_land + tail_s) * fs)
    t = np.arange(n) / fs

    rest = np.array([0.0, 0.0, 1.0])
    a = np.zeros((n, 3))
    a[t < t0] = rest
    contact = (t >= t0) & (t < t_end)
    u = (t[contact] - t0) / tc
    th, ph = np.radians(theta), np.radians(phi)
    direction = np.array([np.cos(th) * np.cos(ph), np.cos(th) * np.sin(ph), np.sin(th)])
    a_pk = np.pi * v / (2 * tc) / G
    a[contact] = rest + np.outer(a_pk * np.sin(np.pi * u), direction)
    # flight stays at 0 g
    post = t >= t_land
    spike = post & (t < t_land + 0.006)
    a[spike] = _unit(rng) * rng.uniform(8, 20)
    a[post & ~spike] = _unit(rng)
    a += rng.normal(0, 0.04, a.shape)

    S = np.array([roll, top, side])
    s = np.zeros(n)
    s[contact] = u * u * (3 - 2 * u)
    s[(t >= t_end) & (t < t_land)] = 1.0
    s[post] = np.exp(-(t[post] - t_land) / 0.5)
    g = np.outer(s, S) + rng.normal(0, 0.5, (n, 3))

    c = np.array([-1.0, lat, vert])
    c /= np.linalg.norm(c)
    w = np.exp(3.0 * (SENSOR_DIRS @ c))
    amps = min(1023.0, 32.0 * v) * w / w.max()
    f = np.abs(rng.normal(0, 2.0, (n, 4)))
    on = t >= t0
    f[on] += np.outer(np.exp(-(t[on] - t0) / 0.006), amps)

    if clip:
        a = np.clip(a, -ACCEL_RANGE_G, ACCEL_RANGE_G)
        g = np.clip(g, -GYRO_RANGE_DPS, GYRO_RANGE_DPS)
    f = np.clip(f, 0, 1023)

    return {
        "t": t, "a": a, "g": g, "f": f,
        "truth": {"technique": technique, "speed_ms": v, "launch_angle_deg": theta,
                  "contact_ms": tc * 1000, "topspin_dps": top, "sidespin_dps": side,
                  "hang_ms": hang * 1000, "contact_lat": lat, "contact_vert": vert},
    }


def arrays_to_samples(k: dict, t_offset: float = 0.0) -> list[Sample]:
    """Quantize like the real ADC path so the pipeline sees what the Uno would send."""
    a_raw = np.clip(np.round(k["a"] * ACCEL_LSB_PER_G), -32768, 32767).astype(int)
    g_raw = np.clip(np.round(k["g"] * GYRO_LSB_PER_DPS), -32768, 32767).astype(int)
    f = np.round(k["f"]).astype(int)
    out = []
    for i in range(len(k["t"])):
        ar, gr = tuple(int(x) for x in a_raw[i]), tuple(int(x) for x in g_raw[i])
        out.append(Sample(
            t=t_offset + float(k["t"][i]),
            a=tuple(x / ACCEL_LSB_PER_G for x in ar),
            g=tuple(x / GYRO_LSB_PER_DPS for x in gr),
            f=tuple(int(x) for x in f[i]),
            a_raw=ar, g_raw=gr,
        ))
    return out


class SimSource:
    """Real-time sample source. drain() returns whatever samples are due since the last call."""

    def __init__(self, auto: bool = True, seed: int | None = None, fs: int = SAMPLE_RATE_HZ):
        self.rng = np.random.default_rng(seed)
        self.fs = fs
        self.auto = auto
        self.queue: deque[Sample] = deque()
        self._k = 0
        self._last = time.monotonic()
        self._next_auto = self._last + 5.0
        self.last_truth: dict | None = None
        self.name = "simulator"

    def trigger(self, technique: str | None = None, spread: float = 1.0) -> dict:
        technique = technique or str(self.rng.choice(list(PRIORS)))
        k = synth_kick(technique, self.rng, spread=spread, rest_s=0.25, tail_s=0.9)
        # samples get their real timestamps as they are emitted
        self.queue.extend(arrays_to_samples(k))
        self.last_truth = k["truth"]
        return k["truth"]

    def drain(self) -> list[Sample]:
        now = time.monotonic()
        due = int((now - self._last) * self.fs)
        if due <= 0:
            return []
        self._last += due / self.fs
        if self.auto and not self.queue and now >= self._next_auto:
            self.trigger(spread=float(self.rng.uniform(0.6, 1.6)))
            self._next_auto = now + float(self.rng.uniform(9, 14))
        out = []
        for _ in range(min(due, self.fs)):
            if self.queue:
                s = self.queue.popleft()
            else:
                ar = tuple(int(x) for x in np.round(
                    (np.array([0, 0, 1.0]) + self.rng.normal(0, 0.02, 3)) * ACCEL_LSB_PER_G))
                gr = tuple(int(x) for x in np.round(self.rng.normal(0, 0.4, 3) * GYRO_LSB_PER_DPS))
                s = Sample(t=0.0, a=tuple(x / ACCEL_LSB_PER_G for x in ar),
                           g=tuple(x / GYRO_LSB_PER_DPS for x in gr),
                           f=tuple(int(x) for x in np.abs(self.rng.normal(0, 2, 4))),
                           a_raw=ar, g_raw=gr)
            s.t = self._k / self.fs
            self._k += 1
            out.append(s)
        return out

    def close(self) -> None:
        pass
