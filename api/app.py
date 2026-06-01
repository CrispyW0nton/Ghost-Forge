"""Compatibility entry point for the Electron launcher.

The Flask adapter now lives in `ghostforge_app`. Keeping this file lets the
existing `python api/app.py` startup path continue to work while domain logic
is owned by `ghostforge_core`.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ghostforge_app.app import app  # noqa: E402


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
