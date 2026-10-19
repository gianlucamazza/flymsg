"""Profiling must never select another device or treat denied counters as zero."""

import pytest

from flymsg import quest_profile as profile


def test_refuses_other_device(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(profile, "read", lambda *args: calls.append(args) or "TV")
    monkeypatch.setattr(
        "sys.argv",
        ["quest_profile.py", "--serial", "chosen", "--out", str(tmp_path / "out")],
    )
    with pytest.raises(SystemExit):
        profile.main()
    assert calls == [("chosen", "shell", "getprop", "ro.product.model")]
    assert not (tmp_path / "out").exists()


def test_retains_browser_children_and_unavailable_counters(monkeypatch):
    def read(serial, *args):
        assert serial == "chosen"
        if args[:2] == ("shell", "ps"):
            return "PID NAME\n11 com.oculus.browser\n12 com.oculus.browser:sandboxed_process0\n13 unrelated\n"
        return {"unavailable": "denied"}

    monkeypatch.setattr(profile, "read", read)
    result = profile.sample("chosen")
    assert set(result["browser_processes"]) == {"11", "12"}
    assert result["gpu_busy_raw"] == {"unavailable": "denied"}
    assert result["browser_processes"]["12"]["status"] == {"unavailable": "denied"}
