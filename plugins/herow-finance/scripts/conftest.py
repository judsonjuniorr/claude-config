"""Hermetic env for the whole herow-finance pytest suite.

Runs at collection time, before any test module (or the modules it imports,
e.g. organizze scripts that call auto_migrate() at import time) is loaded, so
the real ~/finance is never touched: auto_migrate() short-circuits as soon as
any of HEROW_HOME/ORGANIZZE_HOME/CONTABILIZEI_HOME is set. Uses setdefault so
a test module that sets its own hermetic dir (existing pattern: direct
`os.environ[...] = tempfile.mkdtemp(...)`) still wins for that module.
"""

from __future__ import annotations

import os
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="herow-finance-test-home-")
os.environ.setdefault("HEROW_HOME", _TMP_HOME)
os.environ.setdefault("ORGANIZZE_HOME", os.path.join(_TMP_HOME, "finance", "organizze"))
os.environ.setdefault(
    "CONTABILIZEI_HOME", os.path.join(_TMP_HOME, "finance", "contabilizei")
)
