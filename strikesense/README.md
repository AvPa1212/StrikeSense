# StrikeSense

A sensor ball that measures how you strike a soccer ball, then coaches you. Built for VTHacks 14, Code for the Cup.

The stack runs end to end with no hardware (simulator), and switches to a real Arduino Uno with one environment variable.

## Run it

Server (Python 3.10+):

```bash
cd server
pip install -r requirements.txt
uvicorn app:app --port 8000
```

First start trains the small neural network (about 10 seconds). Then open http://localhost:8000. The built dashboard in `web/dist` is served by the same process.

Dashboard development (hot reload on http://localhost:5173, proxies to the server):

```bash
cd web
npm install
npm run dev
```

Tests: `cd server && pip install pytest && pytest -q` (8 tests: protocol, feature accuracy, detector, classifier, scoring, missing sensors, full API).

Real hardware: see `hardware/WIRING.md`, then `SOURCE=serial SERIAL_PORT=COM5 uvicorn app:app --port 8000`.

## What it does

1. The Uno streams 500 packets per second (IMU plus four force channels) over USB.
2. A detector spots a kick, and feature extraction turns the window into: contact time, spin (top, side, total), hang time, apex height, strike point on the ball, and launch speed and angle when the sensor can measure them.
3. A small neural network (scikit-learn MLP) classifies the technique: drive, curl, chip, pass, knuckle.
4. The kick is scored against a benchmark for the technique you are practising. Stats are weighted by importance (ranking on the dashboard).
5. Coaching text comes from Gemini when a key is set, otherwise a rule-based coach. ElevenLabs speaks it when a key is set, otherwise the browser speaks it.
6. Pages: Pitch (scoreboard, strike map, live trace, benchmark gauges, session, ranking, World Cup context) and Sensors (raw data for every individual sensor, sample table, CSV export).

## Honest status

| Piece | State |
|---|---|
| Packet protocol, parser, firmware logic | Tested against each other on a desktop. Firmware not run on a physical Uno |
| Simulator, features, detector, API, dashboard | Tested, and visually checked in a browser |
| Neural network | Trains on simulator kicks, so its 90%+ accuracy describes the simulator only. Label real kicks in the dashboard and press Retrain to learn from your own data |
| Benchmarks | Generated from simulator settings that are plausible physics, not measurements of pros. Replace them with your own recorded reference kicks |
| Launch speed and angle | Need a high-g accelerometer. The MPU-6050 clips. Dashboard shows these as locked, not guessed |
| Tiger Data (Postgres) backend | Written, untested against a live database |
| Gemini and ElevenLabs | Written, untested without your keys. Check the Gemini model name in your account |
| FIFA data | Not used. FIFA ratings are player attributes, not kinematics. StatsBomb World Cup 2022 shot outcomes are shown as context (`server/statsbomb_context.py`) |

## 36-hour plan

Hours 0 to 4: server and dashboard running in simulator mode, everyone can see the demo. Ask the hardware desk for an MPU-6050 (and an ESP32 if you want wireless).
Hours 4 to 12: wire the Uno, bring up in CSV mode, then packet mode. Get real kick windows on the Sensors page.
Hours 12 to 20: record 10 to 20 labeled kicks per technique, press Retrain, replace the simulated benchmarks with your best kicks.
Hours 20 to 28: sponsor integrations (below), polish the coach.
Hours 28 to 34: rehearse the demo, record a backup video, write the Devpost.
Last 2 hours: freeze. No new features.

## Three-minute demo

1. Show the ball rig and say the problem: coaching feedback needs a lab, this needs a ball.
2. Kick. Strike map lights up where the foot met the ball, spin arrow shows the curl, score ring settles.
3. Coach speaks the fix. Kick again, score improves.
4. Sensors page: every raw sensor, live. Judges see it is real data.
5. Label a kick, retrain, show the model changing.
6. Close with the roadmap: passing, dribbling, top-player style matching, floor mat.

Keep the simulator one click away as a fallback if the hardware misbehaves on stage.

## Prize fits (from the MLH prize page for VTHacks 14 when I checked)

- Best Use of Gemini API: `GEMINI_API_KEY` turns on written coaching.
- Best Use of ElevenLabs: `ELEVENLABS_API_KEY` turns on the spoken coach.
- Best Use of Tiger Data: `DATABASE_URL` streams every raw sample into a Postgres hypertable with a 100 ms continuous aggregate (needs a Tiger Data instance and `pip install "psycopg[binary]"`).

Prize lists and rules change. Read the current VTHacks and MLH rules, including anything about work started before the event.

## Layout

```
hardware/firmware/strikesense_uno/   Uno sketch (500 Hz, 250000 baud, 27-byte packets)
hardware/WIRING.md                   pinout, resistors, sensor placement, limits
server/                              FastAPI, detector, features, network, coach, storage
server/tests/                        pytest suite
web/                                 React + Tailwind + Lucide dashboard (Vite)
```

## Environment variables

See `.env.example`.

## Data credit

Shot context uses StatsBomb Open Data. Keep the credit and follow their license if you publish.
