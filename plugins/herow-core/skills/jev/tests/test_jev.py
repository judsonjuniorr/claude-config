"""jev.py: redaction, key order, dry-run, and the consumer-facing output contract (REG-1)."""

import json
import subprocess
import sys
from pathlib import Path

import jev
import pytest

SCRIPT = Path(jev.__file__)
ITEM = {
    "items": [{"id": "t1", "state": "hello"}],
    "questions": {
        "q": {"type": "choice", "instructions": "x", "criteria": {"a": None}}
    },
}


def run_cli(args, stdin="", env=None):
    import os

    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def spec_file(tmp_path, spec=ITEM):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(spec))
    return str(p)


def call_main(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["jev.py", *argv])
    code = 0
    try:
        jev.main()
    except SystemExit as e:
        code = e.code
    return code, capsys.readouterr()


# redaction and uncertainty


def test_redact_br_scrubs_documents_and_long_digits():
    out = jev.redact_br(
        {"a": "CPF 123.456.789-09 conta: 12345-6 ref 123456789012", "b": ["ok"]}
    )
    assert (
        "123.456.789" not in out["a"]
        and "12345-6" not in out["a"]
        and "123456789012" not in out["a"]
    )
    assert out["b"] == ["ok"]


def test_uncertain_thresholds():
    answers = {
        "c": {"type": "choice", "confidence": 0.6},
        "d": {"type": "choice", "confidence": 0.9},
        "n": {"type": "noul", "noul": 0.5},
        "m": {"type": "noul", "noul": 0.95},
        "x": {"type": "score", "confidence": None},
    }
    assert jev.uncertain(answers, 0.7, [0.3, 0.7]) == ["c", "n", "x"]


# dry run


def test_dry_run_needs_no_key_and_has_body_shape(tmp_path):
    res = run_cli([spec_file(tmp_path), "--dry-run", "--redact-br"])
    assert res.returncode == 0
    body = json.loads(res.stdout)["dry_run"][0]
    assert (
        set(body) == {"model", "state", "questions"}
        and body["model"] == jev.DEFAULT_MODEL
    )


# read_key


def test_read_key_keychain_wins_over_env(security_stub, monkeypatch):
    stub = security_stub(rc=0, out="KEYCHAIN-KEY\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert jev.read_key() == "KEYCHAIN-KEY"
    assert "-w" in Path(f"{stub}.args").read_text().split()


def test_read_key_env_when_keychain_missing_entry(security_stub, monkeypatch):
    security_stub(rc=44)
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert jev.read_key() == "env-key"


def test_read_key_timeout_falls_through_to_env(security_stub, monkeypatch):
    security_stub(rc=0, out="late", sleep=5)
    monkeypatch.setenv("JEV_KEY_TIMEOUT", "0.5")
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert jev.read_key() == "env-key"


def test_read_key_timeout_exception_is_caught(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("security", 5)

    monkeypatch.setattr(jev.subprocess, "run", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert jev.read_key() == "env-key"


def test_read_key_missing_binary_falls_through(monkeypatch, tmp_path):
    monkeypatch.setenv("JEV_SECURITY_BIN", str(tmp_path / "nope"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert jev.read_key() == "env-key"


def test_read_key_no_source_is_one_line_with_fix_no_traceback(tmp_path):
    res = run_cli(
        [spec_file(tmp_path)],
        env={"JEV_SECURITY_BIN": "/nonexistent", "OPENROUTER_API_KEY": ""},
    )
    assert res.returncode == 1
    lines = res.stderr.strip().splitlines()
    assert len(lines) == 1 and "Traceback" not in res.stderr
    assert lines[0].startswith("jev unavailable: ")
    assert "OPENROUTER_API_KEY" in lines[0] and "openrouter-api-key" in lines[0]
    assert res.stdout == ""


# output contract (REG-1)


def stub_http(monkeypatch, status=200, body=None):
    body = (
        body
        if body is not None
        else {
            "id": "gen-1",
            "model": "typesafe/jev-1.13",
            "answers": {
                "q": {
                    "type": "choice",
                    "choice": "a",
                    "confidence": 0.9,
                    "probabilities": {"a": 0.9},
                }
            },
            "usage": {"cost": 0.0001, "input_tokens": 120},
        }
    )
    monkeypatch.setattr(jev, "http", lambda *a, **k: (status, json.dumps(body)))


def test_output_schema_and_exit_zero(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    stub_http(monkeypatch)
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    out = json.loads(cap.out)
    assert code == 0
    assert set(out) == {"results", "errors", "totals"} and out["errors"] == []
    assert set(out["results"][0]) == {
        "id",
        "answers",
        "uncertain",
        "ms",
        "cost",
        "cost_source",
        "model",
        "generation_id",
        "usage",
    }
    assert set(out["totals"]) == {"n", "failed", "ms", "wall_ms", "cost", "cost_note"}
    assert out["results"][0]["uncertain"] == [] and out["totals"]["n"] == 1
    assert out["totals"]["cost"] == pytest.approx(0.0001)


def test_output_schema_failure_exits_one(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    stub_http(monkeypatch, status=500, body="bad")
    monkeypatch.setattr(jev, "http", lambda *a, **k: (500, "bad"))
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    out = json.loads(cap.out)
    assert code == 1 and out["results"] == []
    assert set(out["errors"][0]) == {"item_id", "status", "body", "request"}
    assert out["errors"][0]["status"] == 500
    assert "Authorization" not in json.dumps(out["errors"][0]["request"])


# http plumbing


class FakeResp:
    status = 200

    def __init__(self, body=b"{}"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


def test_http_success_http_error_and_timeout(monkeypatch):
    import io
    import urllib.error

    monkeypatch.setattr(
        jev.urllib.request, "urlopen", lambda req, timeout: FakeResp(b'{"ok": 1}')
    )
    assert jev.http("POST", "http://x", "k", {"a": 1}) == (200, '{"ok": 1}')

    def http_error(req, timeout):
        raise urllib.error.HTTPError(
            "http://x", 402, "pay", {}, io.BytesIO(b"no credits")
        )

    monkeypatch.setattr(jev.urllib.request, "urlopen", http_error)
    assert jev.http("GET", "http://x", "k") == (402, "no credits")

    def timeout(req, timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr(jev.urllib.request, "urlopen", timeout)
    status, text = jev.http("GET", "http://x", "k")
    assert status is None and "TimeoutError" in text


def test_cost_falls_back_to_generation_lookup(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(jev.time, "sleep", lambda s: None)
    body = {"id": "gen-9", "model": "m", "answers": {}, "usage": {}}

    def fake_http(method, url, key, body_=None, timeout=60):
        if method == "POST":
            return 200, json.dumps(body)
        return 200, json.dumps({"data": {"total_cost": 0.5}})

    monkeypatch.setattr(jev, "http", fake_http)
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    out = json.loads(cap.out)
    assert (
        code == 0
        and out["results"][0]["cost_source"] == "generation"
        and out["totals"]["cost"] == 0.5
    )


def test_cost_missing_is_reported_not_estimated(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(jev.time, "sleep", lambda s: None)

    def fake_http(method, url, key, body_=None, timeout=60):
        return (200, json.dumps({"answers": {}})) if method == "POST" else (404, "")

    monkeypatch.setattr(jev, "http", fake_http)
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    out = json.loads(cap.out)
    assert out["totals"]["cost"] is None and out["totals"]["cost_note"]


def test_worker_exception_is_an_error_row(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    def boom(*a, **k):
        raise RuntimeError("kaput")

    monkeypatch.setattr(jev, "http", boom)
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    out = json.loads(cap.out)
    assert code == 1 and out["errors"][0]["status"] == "exception"


# key hygiene: a malformed key is rejected, and never echoed anywhere

LEAKY = "sk-or-SECRET\nX"


def test_key_with_newline_is_rejected_without_echo(tmp_path):
    res = run_cli(
        [spec_file(tmp_path)],
        env={"JEV_SECURITY_BIN": "/nonexistent", "OPENROUTER_API_KEY": LEAKY},
    )
    assert res.returncode == 1
    assert "SECRET" not in res.stdout + res.stderr
    assert res.stderr.startswith(
        "jev unavailable: the OpenRouter key from OPENROUTER_API_KEY contains whitespace"
    )
    assert "Fix:" in res.stderr


def test_keychain_key_with_control_chars_is_rejected(security_stub):
    security_stub(rc=0, out="sk-or-SECRET X")
    with pytest.raises(SystemExit) as exc:
        jev.read_key()
    assert "SECRET" not in str(exc.value) and "Keychain" in str(exc.value)


def test_key_is_scrubbed_from_exception_and_error_bodies(monkeypatch, capsys, tmp_path):
    key = "sk-or-SECRETKEY"
    monkeypatch.setattr(jev, "read_key", lambda: key)

    def leaky(*a, **k):
        raise ValueError(f"Invalid header value b'Bearer {key}'")

    monkeypatch.setattr(jev, "http", leaky)
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    assert code == 1 and key not in cap.out + cap.err and "[redacted]" in cap.out
    monkeypatch.setattr(jev, "http", lambda *a, **k: (401, f"bad token {key}"))
    code, cap = call_main(monkeypatch, capsys, [spec_file(tmp_path)])
    assert code == 1 and key not in cap.out + cap.err
