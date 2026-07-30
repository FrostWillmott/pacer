from __future__ import annotations

import sys
from pathlib import Path

# notify.py is a host script run directly (`python notifier/notify.py`), not an
# installed package — it imports its sibling `_env` module assuming its own
# directory is on sys.path (true when launchd/a shell runs it as a script).
# Put notifier/ on sys.path here so `import notify` resolves the same way in
# tests, before any test module in this package tries the import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "notifier"))
