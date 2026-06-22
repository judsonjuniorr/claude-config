"""Shared hermetic test harness for the doctor scripts.

Each test gets a fresh temp HOME via DOCTOR_HOME, so nothing touches real config.
Paths in _doctor.py are functions that read DOCTOR_HOME on every call, so no module
reload is needed between cases.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

# Make the doctor scripts importable (tests/ -> doctor/).
_DOCTOR_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_DOCTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_DOCTOR_DIR))


class DoctorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="doctor-test-"))
        (self.home / ".claude").mkdir(parents=True)
        self._prev = os.environ.get("DOCTOR_HOME")
        os.environ["DOCTOR_HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("DOCTOR_HOME", None)
        else:
            os.environ["DOCTOR_HOME"] = self._prev
        shutil.rmtree(self.home, ignore_errors=True)

    # --- fixtures ----------------------------------------------------------
    @property
    def claude_home(self) -> pathlib.Path:
        return self.home / ".claude"

    def write_json(self, path: pathlib.Path, obj) -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2))
        return path

    def write_text(self, path: pathlib.Path, text: str) -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    # --- capture helpers ---------------------------------------------------
    def run_check(self, fn) -> dict:
        """Call a check_* fn, capture its single JSON line, return it parsed."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, f"expected one JSON line, got: {lines!r}")
        return json.loads(lines[0])

    def call(self, fn):
        """Call any fn, capture stdout, return (return_value, stdout_text)."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rv = fn()
        return rv, buf.getvalue()
