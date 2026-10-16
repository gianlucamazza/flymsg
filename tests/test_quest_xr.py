"""Collector boundaries: one selected headset, same-origin evidence, durable records."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quest_xr", ROOT / "scripts/quest_xr.py")
quest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quest)


def test_power_state_is_retained_separately_from_page_visibility(monkeypatch):
    monkeypatch.setattr(
        quest,
        "adb",
        lambda serial, *args: (
            "mWakefulness=Asleep" if args == ("shell", "dumpsys", "power") else "sample"
        ),
    )
    snapshot = quest.snapshot("explicit-headset")
    assert snapshot["power"] == "mWakefulness=Asleep"
    assert snapshot["browser_memory"] == "sample"


def test_collector_refuses_foreign_device_before_mutations(monkeypatch, tmp_path):
    calls = []

    def adb(serial, *args):
        calls.append((serial, args))
        return "Philips TV"

    monkeypatch.setattr(quest, "adb", adb)
    monkeypatch.setattr(
        "sys.argv",
        ["quest_xr.py", "--serial", "explicit", "--out", str(tmp_path / "out")],
    )
    with pytest.raises(SystemExit):
        quest.main()
    assert calls == [("explicit", ("shell", "getprop", "ro.product.model"))]
    assert not (tmp_path / "out").exists()


def test_paged_mixed_representation_is_rejected_before_contacting_device(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "quest_xr.py",
            "--serial",
            "explicit",
            "--uploads",
            "--representation",
            "mixed",
        ],
    )
    monkeypatch.setattr(
        quest,
        "adb",
        lambda *_args: pytest.fail("Invalid configuration contacted a device"),
    )
    with pytest.raises(SystemExit):
        quest.main()


def test_collector_retains_real_json_and_rejects_foreign_origin(tmp_path):
    evidence = tmp_path / "sessions.jsonl"
    handler = partial(quest.EvidenceHandler, directory=str(tmp_path), evidence=evidence)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        server.evidence_lock = threading.Lock()
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/__xr_evidence"
        report = {
            "schema": "flymsg.xr-bench/v1",
            "status": "ended",
            "raw_intervals_ms": [14, 2000],
        }

        def post(doc, origin):
            request = urllib.request.Request(
                url,
                data=json.dumps(doc).encode(),
                headers={"Origin": origin, "Content-Type": "application/json"},
            )
            return urllib.request.urlopen(request, timeout=5)

        try:
            with pytest.raises(urllib.error.HTTPError) as exc:
                post(report, "https://foreign.example")
            assert exc.value.code == 403
            assert not evidence.exists()
            with post(report, f"http://localhost:{server.server_port}") as response:
                assert response.status == 204
            with pytest.raises(urllib.error.HTTPError) as exc:
                post({"schema": "wrong"}, f"http://localhost:{server.server_port}")
            assert exc.value.code == 400
            assert json.loads(evidence.read_text())["report"] == report
        finally:
            server.shutdown()
            thread.join()


def test_preflight_rejects_sleeping_headset_before_browser_contact(monkeypatch):
    monkeypatch.setattr(
        quest, "snapshot", lambda serial: {"power": "mWakefulness=Asleep"}
    )
    monkeypatch.setattr(
        quest, "adb", lambda *a: pytest.fail("Sleeping headset reached browser")
    )
    check = quest.preflight("Quest", "http://localhost:8892/live/looming/?check")
    assert not check["eligible"]
    assert check["reasons"] == ["headset-not-awake"]


def test_preflight_removes_only_owned_forward_after_bad_target(monkeypatch):
    calls = []
    monkeypatch.setattr(
        quest, "snapshot", lambda serial: {"power": "mWakefulness=Awake"}
    )

    def adb(serial, *args):
        calls.append(args)
        if args[:2] == ("shell", "cat"):
            return "socket @chrome_devtools_remote"
        if args[:2] == ("forward", "tcp:0"):
            return "39261"
        return ""

    class Response:
        def __enter__(self):
            import io

            return io.StringIO('[{"url":"http://localhost:old/","id":"other"}]')

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(quest, "adb", adb)
    monkeypatch.setattr(quest.urllib.request, "urlopen", lambda *a, **kw: Response())
    check = quest.preflight("Quest", "http://localhost:8892/live/looming/?check")
    assert not check["eligible"]
    assert "expected page URL" in check["reasons"][0]
    assert calls[-1] == ("forward", "--remove", "tcp:39261")
