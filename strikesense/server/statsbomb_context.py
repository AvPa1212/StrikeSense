"""Builds data/statsbomb_context.json from StatsBomb Open Data (FIFA World Cup 2022).

    python statsbomb_context.py            # all 64 matches, a few minutes
    python statsbomb_context.py --limit 12 # quick run

Penalties and shootouts are excluded. StatsBomb events describe shots (technique tag, body part, xG, outcome). They do not contain
kinematics such as spin or contact time, so this file gives outcome CONTEXT for the
dashboard, not training data for the sensor model. Attribution: StatsBomb Open Data,
https://github.com/statsbomb/open-data (please keep the credit and follow their license).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from config import CONTEXT_PATH

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
COMPETITION, SEASON = 43, 106  # FIFA World Cup 2022


def shots_for(match_id: int) -> list[dict]:
    r = httpx.get(f"{BASE}/events/{match_id}.json", timeout=90)
    r.raise_for_status()
    # Skip penalty shootouts (period 5) and penalties: they say nothing about striking technique.
    return [e["shot"] for e in r.json()
            if e.get("type", {}).get("name") == "Shot" and e.get("period") != 5
            and e["shot"]["type"]["name"] != "Penalty"]


def bucket(rows: list[dict], key) -> list[dict]:
    agg = defaultdict(lambda: {"shots": 0, "goals": 0, "xg": 0.0})
    for s in rows:
        k = key(s)
        a = agg[k]
        a["shots"] += 1
        a["goals"] += s["outcome"]["name"] == "Goal"
        a["xg"] += s.get("statsbomb_xg") or 0.0
    out = []
    for k, a in sorted(agg.items(), key=lambda kv: -kv[1]["shots"]):
        out.append({"name": k, "shots": a["shots"], "goals": a["goals"],
                    "goal_rate": round(a["goals"] / a["shots"], 3),
                    "avg_xg": round(a["xg"] / a["shots"], 3)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(CONTEXT_PATH))
    args = ap.parse_args()

    matches = httpx.get(f"{BASE}/matches/{COMPETITION}/{SEASON}.json", timeout=60).json()
    ids = [m["match_id"] for m in matches]
    if args.limit:
        ids = ids[:args.limit]
    print(f"Fetching {len(ids)} matches...")
    with ThreadPoolExecutor(8) as ex:
        shots = [s for lst in ex.map(shots_for, ids) for s in lst]

    out = {
        "source": "StatsBomb Open Data",
        "competition": "FIFA World Cup 2022",
        "matches": len(ids),
        "shots": len(shots),
        "goals": sum(s["outcome"]["name"] == "Goal" for s in shots),
        "by_technique": bucket(shots, lambda s: s["technique"]["name"]),
        "by_body_part": bucket(shots, lambda s: s["body_part"]["name"]),
        "by_play_type": bucket(shots, lambda s: s["type"]["name"]),
        "by_first_time": bucket(shots, lambda s: "First time" if s.get("first_time") else "Controlled"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}: {out['shots']} shots, {out['goals']} goals")


if __name__ == "__main__":
    main()
