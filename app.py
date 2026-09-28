import sys
from pathlib import Path

CORE_SRC = Path(__file__).resolve().parent / "core" / "src"

if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from flood_prediction.server import app

__all__ = ["app"]
