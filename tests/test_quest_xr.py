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
        quest,
        "native_focus",
        lambda *args: {
            "browser_focused": True,
            "components": ["com.oculus.browser/.BrowserActivity"],
        },
    )
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


@pytest.mark.parametrize("serial", ["192.168.1.146:5555", "[::1]:5555"])
def test_wifi_transport_is_explicit(serial):
    assert quest.wifi_serial(serial) == serial


@pytest.mark.parametrize(
    "serial", ["USB-serial", "192.168.1.1", "192.168.1.1:0", "192.168.1.1:65536"]
)
def test_wifi_profile_rejects_usb_or_invalid_endpoints(serial):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        quest.wifi_serial(serial)


def test_cleanup_attempts_remaining_resources_after_restore_failure(tmp_path):
    calls = []

    def fail():
        calls.append("restore")
        raise RuntimeError("disconnected")

    report = quest.cleanup_resources(
        "192.168.1.146:5555",
        tmp_path,
        [
            ("keep-awake", fail),
            ("remove-owned-forward", lambda: calls.append("forward")),
            ("remove-owned-reverse", lambda: calls.append("reverse")),
            ("snapshot", lambda: calls.append("snapshot")),
        ],
    )
    assert calls == ["restore", "forward", "reverse", "snapshot"]
    assert not report["ok"]
    assert json.loads((tmp_path / "cleanup.json").read_text()) == report


def test_identity_refuses_changed_hardware_without_other_actions(monkeypatch):
    monkeypatch.setattr(
        quest,
        "adb",
        lambda serial, *args: (
            "Quest 2" if args[-1] == "ro.product.model" else "changed"
        ),
    )
    with pytest.raises(ValueError, match="identity changed"):
        quest.identity("192.168.1.146:5555", "expected")


def test_cleanup_recovers_a_created_target_after_foreground_handshake_failed(
    monkeypatch, tmp_path
):
    session = quest.QuestSite("192.168.1.146:5555", tmp_path)
    session.endpoint = "http://127.0.0.1:45541"
    session.url = "http://localhost:8892/live/looming/?check"
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                [
                    {"id": "owned", "url": session.url},
                    {"id": "other", "url": "http://localhost:8893/?check"},
                ]
            ).encode()

    monkeypatch.setattr(
        quest.urllib.request, "urlopen", lambda *args, **kwargs: Response()
    )
    monkeypatch.setattr(
        quest,
        "node_json",
        lambda *args, **kwargs: (calls.append(args) or {"success": True}, 0),
    )
    session.close_page()
    assert calls == [("observer_open.mjs", session.endpoint, session.url, "owned")]
    assert session.target is None


def test_proximity_restore_checks_identity_and_readback(monkeypatch):
    calls = []
    monkeypatch.setattr(
        quest, "identity", lambda serial, expected: calls.append((serial, expected))
    )
    monkeypatch.setattr(quest, "adb", lambda *args: calls.append(args) or "")
    monkeypatch.setattr(
        quest,
        "proximity_state",
        lambda serial: {"state": "DISABLED", "locks": [0, 0, 0]},
    )
    assert (
        quest.restore_proximity("192.168.1.146:5555", "hardware")["state"] == "DISABLED"
    )
    assert calls[0] == ("192.168.1.146:5555", "hardware")
    assert calls[1][-1] == "com.oculus.vrpowermanager.automation_disable"


def test_unknown_proximity_format_is_rejected(monkeypatch):
    monkeypatch.setattr(quest, "adb", lambda *args: "unknown firmware")
    with pytest.raises(RuntimeError, match="unrecognized"):
        quest.proximity_state("192.168.1.146:5555")


def test_readback_readiness_cannot_authorize_xr_receipts(monkeypatch, tmp_path):
    from types import SimpleNamespace

    session = quest.QuestSite("192.168.1.146:5555", tmp_path)
    session.endpoint, session.target, session.url = "endpoint", "owned", "url"
    session.server = SimpleNamespace(ready_document_id="previous")
    monkeypatch.setattr(
        quest, "snapshot", lambda *a, **k: {"power": "mWakefulness=Awake"}
    )
    calls = []
    monkeypatch.setattr(
        quest,
        "native_focus",
        lambda *args: {
            "components": ["com.oculus.browser/.BrowserActivity"],
            "browser_focused": True,
        },
    )

    def ready(*args, **kwargs):
        calls.append(kwargs)
        return {
            "eligible": True,
            "state": {"after": {"document_id": "current"}},
            "reasons": [],
        }

    monkeypatch.setattr(quest, "browser_preflight", ready)
    assert session.wait_ready(readback_only=True)["eligible"]
    assert all(call["readback_only"] for call in calls)
    assert session.server.ready_document_id is None
    assert session.wait_ready()["eligible"]
    assert session.server.ready_document_id == "current"


def test_native_guardian_focus_cannot_be_confused_with_a_resumed_browser(monkeypatch):
    for raw, expected in [
        (
            "mCurrentFocus=null\nmCurrentFocus=Window{abc u0 com.oculus.guardian/.GuardianDialogActivity}",
            False,
        ),
        (
            "mCurrentFocus=Window{abc u0 com.oculus.browser/com.oculus.browser.BrowserActivity}",
            True,
        ),
        (
            "mCurrentFocus=Window{abc u0 com.oculus.browser/.BrowserActivity}\nmCurrentFocus=Window{def u0 com.oculus.guardian/.Dialog}",
            False,
        ),
        ("unknown firmware", False),
    ]:
        monkeypatch.setattr(quest, "adb", lambda *args, text=raw: text)
        assert quest.native_focus("192.168.1.146:5555")["browser_focused"] is expected


def test_bounded_xr_final_receipt_recomputes_all_raw_frame_certificates():
    import copy

    identity = {
        "representation": "skeleton-bounded",
        "selected": 1128,
        "represented": 1128,
    }
    doc = {
        "status": "ended",
        "frames": 2,
        "content": {"identity": identity, "checked_frames": 2, "incomplete_frames": 0},
        "bounded": {
            "fields": [
                "maximum_error_px",
                "submitted_indices",
                "source_indices",
                "fallback_pages",
                "coarse_pages",
                "invalid",
            ],
            "checked_frames": 2,
            "uncertified_frames": 0,
        },
        "raw_bounded_frames": [[0.4, 20, 100, 0, 1, 0], [0, 100, 100, 1, 0, 0]],
    }
    result = quest.bounded_xr_certificate(doc, identity)
    assert result["status"] == "pass" and result["fallback_frames"] == 1
    for damage in (
        "over-limit",
        "nan",
        "boolean",
        "missing",
        "identity",
        "error",
        "summary",
    ):
        bad = copy.deepcopy(doc)
        if damage == "over-limit":
            bad["raw_bounded_frames"][0][0] = 0.5001
        elif damage == "nan":
            bad["raw_bounded_frames"][0][0] = float("nan")
        elif damage == "boolean":
            bad["raw_bounded_frames"][0][1] = True
        elif damage == "missing":
            bad["raw_bounded_frames"].pop()
        elif damage == "identity":
            bad["content"]["identity"]["selected"] = 2
        elif damage == "error":
            bad["raw_bounded_frames"][0][5] = 1
        else:
            bad["bounded"]["checked_frames"] = 3
        assert quest.bounded_xr_certificate(bad, identity)["status"] == "fail"
    doc["status"] = "running"
    assert quest.bounded_xr_certificate(doc, identity)["status"] == "pending"


def test_native_focus_exclusion_is_durable_before_document_admission(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    session = quest.QuestSite("192.168.1.146:5555", tmp_path)
    session.endpoint, session.target, session.url = "endpoint", "owned", "url"
    session.server = SimpleNamespace(ready_document_id=None)
    monkeypatch.setattr(
        quest, "snapshot", lambda *a, **k: {"power": "mWakefulness=Awake"}
    )
    monkeypatch.setattr(
        quest,
        "native_focus",
        lambda *a: {
            "browser_focused": False,
            "components": ["com.oculus.guardian/.Dialog"],
        },
    )
    monkeypatch.setattr(
        quest,
        "browser_preflight",
        lambda *a, **k: {
            "eligible": True,
            "reasons": [],
            "state": {"after": {"document_id": "current"}},
        },
    )
    evidence = tmp_path / "preflight.jsonl"
    check = session.wait_ready(timeout=0, evidence=evidence)
    saved = json.loads(evidence.read_text())
    assert not check["eligible"] and not saved["browser"]["eligible"]
    assert "native-browser-not-focused" in saved["browser"]["reasons"]
    assert session.server.ready_document_id is None
