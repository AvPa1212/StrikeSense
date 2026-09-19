"""Kick detection (streaming) and feature extraction (per kick window).

Ball frame convention, set by how you place the ball before a kick:
    +X points at the target, +Y to the kicker's left, +Z up.
    Topspin is +gy, and sidespin +gz curls the ball to the left.

What each sensor tier can measure:
    Tier 1 (MPU-6050, +-16 g): contact time, spin, hang time, apex height, strike point.
                                Contact acceleration saturates, so speed and angle are None.
    Tier 2 (high-g accelerometer): everything above plus launch speed, angle and azimuth.
                                Hard kicks can still clip a +-200 g part. A +-400 g part is safer.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from config import ACCEL_RANGE_G, FORCE_GAINS_LIST, G, GYRO_RANGE_DPS, SAMPLE_RATE_HZ
from protocol import Sample

CONTACT_G = 3.0        # |a| above this counts as foot contact
TRIGGER_G = 6.0        # start recording when |a| exceeds this
TRIGGER_F = 350        # ...or when any force channel exceeds this many ADC counts
PRE_ROLL_S = 0.15
MAX_RECORD_S = 5.0
SETTLE_S = 0.5
MIN_FLIGHT_S = 0.04

# Unit vectors from the ball center to the four force sensors (tetrahedral layout).
_S3 = 3 ** 0.5
SENSOR_DIRS = np.array([
    [1, 1, 1],
    [1, -1, -1],
    [-1, 1, -1],
    [-1, -1, 1],
], dtype=float) / _S3


_DESIGN = np.hstack([SENSOR_DIRS, np.ones((4, 1))])
FORCE_GAINS = np.array(FORCE_GAINS_LIST, float)


def _cross_time(t0, t1, y0, y1, thr):
    if y1 == y0:
        return t1
    return t0 + (thr - y0) / (y1 - y0) * (t1 - t0)


def extract_features(t, a, g, f, accel_range: float | None = None) -> dict | None:
    """t: (n,) seconds, a: (n,3) g, g: (n,3) dps, f: (n,4) ADC counts. None if not a kick."""
    accel_range = ACCEL_RANGE_G if accel_range is None else accel_range
    t = np.asarray(t, float)
    a = np.asarray(a, float)
    g = np.asarray(g, float)
    f = np.asarray(f, float)
    n = len(t)
    if n < 30:
        return None

    amag = np.linalg.norm(a, axis=1)
    above = amag > CONTACT_G
    if not above.any():
        return None
    i0 = int(np.argmax(above))
    j = i0
    while j + 1 < n and (above[j + 1] or (j + 2 < n and above[j + 2])):
        j += 1
    while not above[j]:
        j -= 1
    i1 = j

    # Contact time with linear interpolation of the threshold crossings.
    t_start = _cross_time(t[i0 - 1], t[i0], amag[i0 - 1], amag[i0], CONTACT_G) if i0 > 0 else t[i0]
    t_end = _cross_time(t[i1], t[i1 + 1], amag[i1], amag[i1 + 1], CONTACT_G) if i1 + 1 < n else t[i1]
    contact_ms = (t_end - t_start) * 1000.0
    if not (1.0 <= contact_ms <= 60.0):
        return None

    peak_g = float(amag[i0:i1 + 1].max())
    clipped = bool(np.abs(a[i0:i1 + 1]).max() >= 0.97 * accel_range)

    # Strike point from the four force channels.
    lo = max(0, i0 - 5)
    hi = min(n, i1 + 12)
    base = np.median(f[:max(3, i0 - 5)], axis=0) if i0 > 3 else np.zeros(4)
    peaks = np.clip(f[lo:hi].max(axis=0) - base, 0, None)
    force_peak = float(peaks.max() / 1023.0)
    if peaks.sum() > 20:
        # Contact direction from the log-amplitude gradient across the four sensors.
        # Solves log(peak_i) = k * (dir_i . c) + b exactly (four sensors, four unknowns).
        L = np.log(peaks / FORCE_GAINS + 5.0)
        sol = np.linalg.solve(_DESIGN, L)
        c = sol[:3]
        nc = np.linalg.norm(c)
        contact_lat = float(c[1] / nc) if nc > 0 else 0.0
        contact_vert = float(c[2] / nc) if nc > 0 else 0.0
    else:
        contact_lat = contact_vert = None  # force sensors not connected or not triggered
    zone_offset = None if contact_lat is None else float(np.hypot(contact_lat, contact_vert))

    # Spin in the window just after contact.
    m = (t >= t_end + 0.02) & (t <= t_end + 0.15)
    gm = g[m].mean(axis=0) if m.any() else np.zeros(3)
    spin_sat = bool(np.abs(g[m]).max() >= 0.97 * GYRO_RANGE_DPS) if m.any() else False

    # Flight (free fall reads ~0 g) gives hang time and apex without needing the impact peak.
    k = np.ones(3) / 3
    sm = np.convolve(amag, k, mode="same")
    low = sm < 0.5
    k0 = min(n - 1, i1 + max(1, int(0.01 * SAMPLE_RATE_HZ)))
    start = None
    end = None
    for i in range(k0, n):
        if low[i]:
            if start is None:
                start = i
        elif start is not None:
            if t[i] - t[start] >= MIN_FLIGHT_S:
                end = i
                break
            start = None
    if end is None and start is not None and t[-1] - t[start] >= MIN_FLIGHT_S:
        end = n - 1
    hang_s = float(t[end] - t[start]) if (start is not None and end is not None) else 0.0
    apex_m = G * hang_s ** 2 / 8.0
    v_up = G * hang_s / 2.0

    # Launch vector from the impulse. Only trustworthy when the sensor did not saturate.
    speed = angle = azimuth = None
    if not clipped:
        s0, s1 = max(0, i0 - 1), min(n - 1, i1 + 1)
        rest = a[:max(1, i0 - 3)].mean(axis=0)
        seg = a[s0:s1 + 1] - rest
        tt = t[s0:s1 + 1]
        imp = ((seg[1:] + seg[:-1]) / 2 * np.diff(tt)[:, None]).sum(axis=0) * G
        speed = float(np.linalg.norm(imp))
        angle = float(np.degrees(np.arctan2(imp[2], np.hypot(imp[0], imp[1]))))
        azimuth = float(np.degrees(np.arctan2(imp[1], imp[0])))

    r = lambda x, d=2: None if x is None else round(float(x), d)
    t_flight = [round(float(t[start] - t[0]), 3), round(float(t[end] - t[0]), 3)] if hang_s > 0 else None
    return {
        "t_contact": [round(float(t_start - t[0]), 4), round(float(t_end - t[0]), 4)],
        "t_flight": t_flight,
        "contact_ms": r(contact_ms),
        "peak_g": r(peak_g, 1),
        "accel_clipped": clipped,
        "spin_dps": r(np.linalg.norm(gm), 0),
        "roll_dps": r(gm[0], 0),
        "topspin_dps": r(gm[1], 0),
        "sidespin_dps": r(gm[2], 0),
        "spin_saturated": spin_sat,
        "hang_ms": r(hang_s * 1000, 0),
        "apex_m": r(apex_m),
        "v_up": r(v_up),
        "contact_lat": r(contact_lat, 3),
        "contact_vert": r(contact_vert, 3),
        "zone_offset": r(zone_offset, 3),
        "force_peak": r(force_peak, 3),
        "speed_ms": r(speed),
        "launch_angle_deg": r(angle, 1),
        "azimuth_deg": r(azimuth, 1),
    }


class KickDetector:
    """Feed samples one at a time. push() returns a finished kick window or None."""

    def __init__(self, fs: int = SAMPLE_RATE_HZ) -> None:
        self.fs = fs
        self.pre: deque[Sample] = deque(maxlen=int(PRE_ROLL_S * fs))
        self.rec: list[Sample] | None = None
        self.calm = 0
        self.recording = False

    def push(self, s: Sample) -> dict | None:
        amag = float(np.linalg.norm(s.a))
        if self.rec is None:
            if amag > TRIGGER_G or max(s.f) > TRIGGER_F:
                self.rec = list(self.pre) + [s]
                self.pre.clear()
                self.calm = 0
                self.recording = True
            else:
                self.pre.append(s)
            return None

        self.rec.append(s)
        if abs(amag - 1.0) < 0.3:
            self.calm += 1
        else:
            self.calm = 0
        elapsed = self.rec[-1].t - self.rec[0].t
        if (self.calm >= SETTLE_S * self.fs and elapsed > 0.4) or elapsed > MAX_RECORD_S:
            return self._finish()
        return None

    def _finish(self) -> dict:
        rec = self.rec or []
        self.rec = None
        self.recording = False
        self.calm = 0
        t0 = rec[0].t
        return {
            "t": np.array([s.t - t0 for s in rec]),
            "a": np.array([s.a for s in rec]),
            "g": np.array([s.g for s in rec]),
            "f": np.array([s.f for s in rec], float),
            "t_abs": t0,
        }
