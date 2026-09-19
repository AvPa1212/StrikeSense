"""Central configuration. Everything is overridable with environment variables."""
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

SAMPLE_RATE_HZ = 500

# Sensor ranges. Defaults match an MPU-6050 (GY-521) set to +-16 g and +-2000 dps.
# Swap in a high-g part (for example H3LIS331DL at +-400 g) by changing ACCEL_RANGE_G
# and ACCEL_LSB_PER_G. The pipeline then unlocks launch speed and launch angle.
ACCEL_RANGE_G = float(os.getenv("ACCEL_RANGE_G", "16"))
ACCEL_LSB_PER_G = float(os.getenv("ACCEL_LSB_PER_G", "2048"))
GYRO_RANGE_DPS = float(os.getenv("GYRO_RANGE_DPS", "2000"))
GYRO_LSB_PER_DPS = float(os.getenv("GYRO_LSB_PER_DPS", "16.4"))

# Simulator only: pretend a high-g accelerometer is fitted so launch speed and angle appear.
if os.getenv("SIM_HIGHG", "0") == "1":
    ACCEL_RANGE_G = 1000.0
    ACCEL_LSB_PER_G = 30.0

# Per-sensor gain correction for the four force channels (piezo discs vary a lot).
FORCE_GAINS_LIST = [float(x) for x in os.getenv("FORCE_GAINS", "1,1,1,1").split(",")]

# Where samples come from: "sim" (no hardware) or "serial" (the Uno).
SOURCE = os.getenv("SOURCE", "sim")
SERIAL_PORT = os.getenv("SERIAL_PORT", "")  # empty = auto-detect
BAUD = int(os.getenv("BAUD", "250000"))

# Storage. Empty DATABASE_URL uses local SQLite. A postgres:// URL (Tiger Data) uses Postgres.
DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_PATH = os.getenv("SQLITE_PATH", str(DATA_DIR / "strikesense.db"))
MODEL_PATH = os.getenv("MODEL_PATH", str(DATA_DIR / "model.joblib"))
CONTEXT_PATH = DATA_DIR / "statsbomb_context.json"

# Optional coaching services. Both degrade gracefully when unset.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")

# Ball physical constants used by the simulator and estimators.
BALL_MASS_KG = 0.43
G = 9.81
