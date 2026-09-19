"""Technique classification (small neural network), benchmarks and scoring.

The network learns from labeled kicks. At first launch it trains on simulator kicks so the
demo works out of the box. Label real kicks in the dashboard and retrain to replace the
simulated knowledge with your own data (see retrain()).
"""
from __future__ import annotations

import math
import os
import warnings
from pathlib import Path

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import MODEL_PATH as MODEL_PATH_STR
from features import extract_features
from simulator import PRIORS, synth_kick

warnings.filterwarnings("ignore", category=ConvergenceWarning)

TECHNIQUES = list(PRIORS)
LABELS = {
    "drive": "Driven shot",
    "curl": "Curled shot",
    "chip": "Chip",
    "pass": "Inside-foot pass",
    "knuckle": "Knuckleball",
}
NN_FEATURES = ["contact_ms", "topspin_dps", "sidespin_dps", "spin_dps", "hang_ms",
               "contact_lat", "contact_vert", "force_peak"]

# key: (label, unit, weight, needs_high_g_sensor)
# Weights are the ranking of which statistics matter most for a good strike. They are
# reasoned from the physics (strike point sets spin and direction, speed and angle set the
# trajectory) and should be validated against real coaching data.
SCORE_METRICS = {
    "contact_lat":      ("Strike point, side",  "",     0.12, False),
    "contact_vert":     ("Strike point, height", "",    0.13, False),
    "topspin_dps":      ("Topspin",             "deg/s", 0.10, False),
    "sidespin_dps":     ("Sidespin",            "deg/s", 0.10, False),
    "speed_ms":         ("Launch speed",        "m/s",  0.20, True),
    "launch_angle_deg": ("Launch angle",        "deg",  0.10, True),
    "contact_ms":       ("Contact time",        "ms",   0.10, False),
    "hang_ms":          ("Hang time",           "ms",   0.15, False),
}

IMPORTANCE = [
    ("Launch speed", 0.20, "Sets how quickly the ball arrives. Needs a high-g accelerometer."),
    ("Hang time", 0.15, "Reveals trajectory shape from the free-fall window, no impact peak needed."),
    ("Strike point", 0.25, "Where the foot meets the ball decides spin and direction."),
    ("Spin", 0.20, "Topspin and sidespin bend the flight and control the bounce."),
    ("Contact time", 0.10, "A crisp strike and a cushioned pass feel different in the data."),
    ("Launch angle", 0.10, "Loft matters for chips and crosses. Needs a high-g accelerometer."),
]

MODEL_PATH = Path(MODEL_PATH_STR)
ELITE_SPREAD = 0.5   # benchmarks come from tight, elite-quality simulated kicks
BENCH_SIGMA = 2.0    # a kick 2 elite standard deviations away scores about 61


def _vec(feat: dict) -> list[float]:
    return [float(feat.get(k) or 0.0) for k in NN_FEATURES]


def _make_features(technique: str, rng, spread: float, clip: bool, accel_range=None):
    k = synth_kick(technique, rng, spread=spread, clip=clip)
    return extract_features(k["t"], k["a"], k["g"], k["f"], accel_range=accel_range)


def build_training_set(n_per_class: int = 220, seed: int = 7):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for tech in TECHNIQUES:
        for i in range(n_per_class):
            spread = rng.uniform(0.5, 1.8)
            f = _make_features(tech, rng, spread, clip=True)
            if f:
                X.append(_vec(f))
                y.append(tech)
    return np.array(X), np.array(y)


def build_benchmarks(n: int = 300, seed: int = 11) -> dict:
    """Mean and std of every scored metric for each technique, from elite-quality kicks.
    Uses unclipped sensor data so speed and angle benchmarks exist even on a tier 1 sensor."""
    rng = np.random.default_rng(seed)
    out = {}
    for tech in TECHNIQUES:
        rows = [f for f in (_make_features(tech, rng, ELITE_SPREAD, clip=False, accel_range=1e9)
                            for _ in range(n)) if f]
        out[tech] = {}
        for key in SCORE_METRICS:
            vals = np.array([r[key] for r in rows if r.get(key) is not None], float)
            if len(vals) > 10:
                out[tech][key] = {"mu": float(vals.mean()),
                                  "sd": float(max(vals.std() * BENCH_SIGMA, _SD_FLOOR[key]))}
    return out


_SD_FLOOR = {"contact_lat": 0.08, "contact_vert": 0.08, "topspin_dps": 60, "sidespin_dps": 60,
             "speed_ms": 1.5, "launch_angle_deg": 2.0, "contact_ms": 0.8, "hang_ms": 60}


class TechniqueModel:
    def __init__(self) -> None:
        self.pipe = None
        self.bench: dict = {}
        self.n_real = 0

    def load_or_train(self) -> None:
        import joblib
        if MODEL_PATH.exists():
            try:
                d = joblib.load(MODEL_PATH)
                self.pipe, self.bench, self.n_real = d["pipe"], d["bench"], d.get("n_real", 0)
                return
            except Exception:
                pass
        self.train()

    def train(self, extra_X=None, extra_y=None, extra_weight: int = 5) -> dict:
        import joblib
        X, y = build_training_set()
        if extra_X is not None and len(extra_X):
            X = np.vstack([X] + [np.array(extra_X)] * extra_weight)
            y = np.concatenate([y] + [np.array(extra_y)] * extra_weight)
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(X))
        cut = int(len(X) * 0.85)
        tr, te = idx[:cut], idx[cut:]
        pipe = make_pipeline(StandardScaler(),
                             MLPClassifier(hidden_layer_sizes=(24, 16), max_iter=800,
                                           random_state=0, early_stopping=False))
        pipe.fit(X[tr], y[tr])
        acc = float(pipe.score(X[te], y[te]))
        pipe.fit(X, y)
        self.pipe = pipe
        self.n_real = 0 if extra_X is None else len(extra_X)
        if not self.bench:
            self.bench = build_benchmarks()
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipe": pipe, "bench": self.bench, "n_real": self.n_real}, MODEL_PATH)
        return {"holdout_accuracy": round(acc, 3), "samples": int(len(X)), "real_kicks": self.n_real}

    def classify(self, feat: dict) -> dict:
        proba = self.pipe.predict_proba([_vec(feat)])[0]
        classes = list(self.pipe.classes_)
        probs = {c: float(p) for c, p in zip(classes, proba)}
        best = max(probs, key=probs.get)
        return {"technique": best, "confidence": probs[best], "probs": probs}

    def score(self, feat: dict, technique: str) -> dict:
        bench = self.bench.get(technique, {})
        rows, num, den = [], 0.0, 0.0
        for key, (label, unit, w, needs_hg) in SCORE_METRICS.items():
            x = feat.get(key)
            b = bench.get(key)
            row = {"key": key, "label": label, "unit": unit, "weight": w, "value": x,
                   "target": b["mu"] if b else None, "band": b["sd"] if b else None,
                   "available": x is not None and b is not None, "score": None, "z": None,
                   "reason": None}
            if x is None and needs_hg:
                row["reason"] = "Needs a high-g accelerometer (contact peak saturated)"
            elif x is None or b is None:
                row["reason"] = "Not measured"
            else:
                z = (x - b["mu"]) / b["sd"]
                s = 100.0 * math.exp(-0.5 * z * z)
                row["z"], row["score"] = round(z, 2), round(s, 1)
                num += w * s
                den += w
            rows.append(row)
        return {"technique": technique, "overall": round(num / den, 1) if den else 0.0,
                "metrics": rows, "coverage": round(den, 2)}


def retrain_from_labeled(model: TechniqueModel, labeled: list[tuple[dict, str]]) -> dict:
    X = [_vec(f) for f, _ in labeled]
    y = [t for _, t in labeled]
    return model.train(extra_X=X, extra_y=y)
