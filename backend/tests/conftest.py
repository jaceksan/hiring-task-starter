import sys
from pathlib import Path


# Ensure `backend/` is on sys.path so tests can import local modules
# like `layers.*`, `geo.*`, and `main`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
