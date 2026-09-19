import time

import numpy as np
import pytest

from features import KickDetector, extract_features
from protocol import PacketParser, encode
from simulator import PRIORS, SimSource, arrays_to_samples, synth_kick


def test_packet_roundtrip_and_resync():
    pkts = b"".join(encode(i * 2000, (i, -i, 2048), (10, -20, 30), (1, 2, 3, 4)) for i in range(50))
    noisy = b"\x00\xaa\x12" + pkts[:100] + b"\xff\xff" + pkts[100:]
    p = PacketParser()
    out = []
    for i in range(0, len(noisy), 7):          # awkward chunking on purpose
        out += p.feed(noisy[i:i + 7])
    assert len(out) >= 48                      # a couple may be lost around the corruption
    assert out[10].a_raw[2] == 2048
    assert out[10].f == (1, 2, 3, 4)


def test_features_match_truth():
    rng = np.random.default_rng(5)
    for tech in PRIORS:
        for _ in range(10):
            k = synth_kick(tech, rng)
            f = extract_features(k["t"], k["a"], k["g"], k["f"])
            tr = k["truth"]
            assert f is not None
            assert abs(f["hang_ms"] - tr["hang_ms"]) < 30 + 0.03 * tr["hang_ms"]
            if abs(tr["sidespin_dps"]) < 1800:
                assert abs(f["sidespin_dps"] - tr["sidespin_dps"]) < 40
            assert f["accel_clipped"] is True and f["speed_ms"] is None


def test_unclipped_gives_launch_vector():
    rng = np.random.default_rng(9)
    errs = []
    for _ in range(30):
        k = synth_kick("drive", rng, clip=False)
        f = extract_features(k["t"], k["a"], k["g"], k["f"], accel_range=1e9)
        errs.append(abs(f["speed_ms"] - k["truth"]["speed_ms"]) / k["truth"]["speed_ms"])
    assert np.median(errs) < 0.08


def test_detector_finds_kick_in_stream():
    rng = np.random.default_rng(2)
    src = SimSource(auto=False, seed=1)
    det = KickDetector()
    quiet = 0
    for _ in range(400):
        s = arrays_to_samples({"t": [0.0], "a": np.array([[0, 0, 1.0]]),
                               "g": np.zeros((1, 3)), "f": np.zeros((1, 4))})[0]
        assert det.push(s) is None
        quiet += 1
    k = synth_kick("curl", rng, rest_s=0.3)
    win = None
    for i, s in enumerate(arrays_to_samples(k, t_offset=1.0)):
        win = det.push(s) or win
    assert win is not None
    f = extract_features(win["t"], win["a"], win["g"], win["f"])
    assert f and f["sidespin_dps"] > 800


def test_classifier_accuracy():
    from technique import TECHNIQUES, TechniqueModel, _make_features
    m = TechniqueModel()
    info = m.train()
    assert info["holdout_accuracy"] > 0.85
    rng = np.random.default_rng(123)
    ok = tot = 0
    for tech in TECHNIQUES:
        for _ in range(40):
            f = _make_features(tech, rng, 1.0, True)
            ok += m.classify(f)["technique"] == tech
            tot += 1
    assert ok / tot > 0.85


def test_score_orders_quality():
    from technique import TechniqueModel, _make_features
    m = TechniqueModel()
    m.load_or_train()
    rng = np.random.default_rng(4)
    pro = np.mean([m.score(_make_features("curl", rng, 0.5, True), "curl")["overall"] for _ in range(60)])
    am = np.mean([m.score(_make_features("curl", rng, 1.8, True), "curl")["overall"] for _ in range(60)])
    assert pro > am + 15


def test_api_end_to_end():
    from fastapi.testclient import TestClient
    import app as appmod
    with TestClient(appmod.app) as c:
        assert c.get("/api/status").json()["source"] == "simulator"
        assert c.post("/api/sim/kick?technique=chip&level=pro").json()["queued"] == "chip"
        kicks = []
        for _ in range(60):
            time.sleep(0.25)
            kicks = c.get("/api/kicks").json()
            if kicks:
                break
        assert kicks, "no kick detected"
        k = kicks[-1]
        assert k["predicted"] == "chip"
        full = c.get(f"/api/kicks/{k['id']}").json()
        assert len(full["window"]["t"]) > 500
        coach = c.get(f"/api/kicks/{k['id']}/coach").json()
        assert coach["source"] == "rules" and "\u2014" not in coach["text"]
        assert c.get(f"/api/kicks/{k['id']}/voice").status_code == 501
        assert c.post(f"/api/kicks/{k['id']}/label", json={"technique": "chip"}).json()["ok"]
        assert c.post("/api/model/retrain").json()["real_kicks"] == 1
        assert c.post("/api/target", json={"technique": "drive"}).json()["target"] == "drive"
        assert c.get("/api/techniques").json()["importance"]


def test_missing_force_sensors_are_not_scored():
    from technique import TechniqueModel
    rng = np.random.default_rng(6)
    k = synth_kick("drive", rng)
    k["f"][:] = 0
    f = extract_features(k["t"], k["a"], k["g"], k["f"])
    assert f["contact_lat"] is None and f["contact_vert"] is None
    m = TechniqueModel()
    m.load_or_train()
    sc = m.score(f, "drive")
    rows = {r["key"]: r for r in sc["metrics"]}
    assert not rows["contact_lat"]["available"] and rows["hang_ms"]["available"]
