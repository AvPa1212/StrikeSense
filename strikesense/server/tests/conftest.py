import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = tempfile.mkdtemp()
os.environ.setdefault("SQLITE_PATH", os.path.join(_tmp, "test.db"))
os.environ.setdefault("MODEL_PATH", os.path.join(_tmp, "model.joblib"))
os.environ.setdefault("SOURCE", "sim")
os.environ.setdefault("SIM_AUTO", "0")
