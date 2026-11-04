"""Explicit, ordered DX12 streaming runtime; never falls back to host execution.

The worker must have been qualified separately for the caller's source/shader.
Creating a runtime uploads a graph but does not launch or replace the worker app.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

import numpy as np

from flymsg import native
from flymsg.console import STOPPED, Device, PortalError
from flymsg.runtime import CpuRuntime


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ConsoleRuntime:
    def __init__(
        self,
        template: CpuRuntime,
        device: Device,
        out: Path,
        *,
        window_steps: int,
        source_commit: str,
        timeout_s: float = 120,
    ):
        if len(source_commit) != 40 or any(
            c not in "0123456789abcdef" for c in source_commit
        ):
            raise ValueError("exact qualified worker source commit required")
        if not np.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("positive finite timeout required")
        self._template, self._device = template, device
        self._source, self._timeout = source_commit, timeout_s
        self._window, self._step, self._seq = window_steps, 0, 0
        self._failed = self._closed = False
        self._job = "stream-" + uuid.uuid4().hex
        self._folder = Path(out) / self._job
        self._folder.mkdir(parents=True, exist_ok=False)
        self._fixture = self._folder / "fixture.bin"
        meta = native.export_fixture(template, self._fixture, window_steps=window_steps)
        self._identity = _sha(self._fixture.read_bytes())
        self._receipt = self._identity
        self._trace = np.zeros((template._steps, template._trace.size), np.uint8)
        self._rel = "inbox\\" + self._job
        job = {
            "schema": "flymsg.neural_job/v1",
            "job_id": self._job,
            "semantics": meta["semantics"],
            "backend": "dx12",
            "fixture_sha256": self._identity,
            "shader_sha256": device.shader_sha,
            "expected_adapter": device.adapter,
            "expected_source_commit": source_commit,
            "stream": "flymsg.neural_stream/v1",
        }
        path = self._folder / "job.json"
        path.write_text(json.dumps(job, sort_keys=True))
        device.portal.mkdir(device.package, self._rel)
        device.portal.put(device.package, self._rel, self._fixture)
        device.portal.put(device.package, self._rel, path)

    @property
    def step(self):
        return self._step

    @property
    def tick_us(self):
        return self._template.tick_us

    @property
    def n_inputs(self):
        return self._template.n_inputs

    @property
    def input_encoding(self):
        return self._template.input_encoding

    def _guard(self):
        if self._failed or self._closed:
            raise RuntimeError("console stream unavailable; explicit recovery required")

    def schedule_inputs(self, values):
        self._guard()
        # Reuse input validation/storage only. This template never advances neurons.
        self._template._step = self._step
        self._template.schedule_inputs(values)

    def _command(self, operation, payload=None, *, target=None):
        self._guard()
        self._seq += 1
        stem = f"command_{self._seq}"
        cmd = {
            "schema": "flymsg.stream_command/v1",
            "job_id": self._job,
            "sequence": self._seq,
            "expected_step": self.step,
            "operation": operation,
            "previous_receipt_sha256": self._receipt,
        }
        if target is not None:
            cmd["target"] = target
        p, package = self._device.portal, self._device.package
        try:
            if payload is not None:
                data = self._folder / (stem + ".bin")
                data.write_bytes(payload)
                cmd["payload_sha256"] = _sha(payload)
                p.put(package, self._rel, data)
            path = self._folder / (stem + ".json")
            raw = json.dumps(cmd, sort_keys=True).encode()
            path.write_bytes(raw)
            p.put(package, self._rel, path)
            ack_path = self._folder / f"receipt_{self._seq}.json"
            deadline = time.monotonic() + self._timeout
            while True:
                try:
                    p.get(package, self._rel, ack_path.name, ack_path)
                    ack_raw = ack_path.read_bytes()
                    ack = json.loads(ack_raw)
                    break
                except PortalError as exc:
                    if exc.http_status != 404:
                        raise
                except json.JSONDecodeError:
                    pass
                status = self._device.status(self._rel, self._folder / "status.json")
                if status and status.get("source_commit") != self._source:
                    raise RuntimeError("unqualified worker source")
                if status.get("state") in STOPPED:
                    raise RuntimeError("console stream stopped: " + status["state"])
                if time.monotonic() >= deadline:
                    raise TimeoutError("console stream receipt timeout; do not replay")
                time.sleep(0.02)
            expected_step = self.step if target is None else target
            if (
                ack.get("schema") != "flymsg.stream_receipt/v1"
                or ack.get("job_id") != self._job
                or ack.get("sequence") != self._seq
                or ack.get("source_commit") != self._source
                or ack.get("command_sha256") != _sha(raw)
                or ack.get("step") != expected_step
            ):
                raise RuntimeError("console receipt identity/order mismatch")
            result = None
            if operation != "finish":
                result = self._folder / f"result_{self._seq}.bin"
                p.get(package, self._rel, result.name, result)
                if _sha(result.read_bytes()) != ack.get("result_sha256"):
                    raise RuntimeError("console result integrity mismatch")
            self._receipt = _sha(ack_raw)
            return result
        except Exception:
            self._failed = True
            raise

    def advance_to(self, step):
        self._guard()
        if type(step) is not int or not self.step <= step <= self._template._steps:
            raise ValueError("invalid advance boundary")
        while self.step < step:
            stop = min(step, self.step + self._window)
            values = self._template._kicks[self.step : stop].astype(
                np.float32 if self.input_encoding == "kick_equivalent" else np.int64
            )
            result = self._command(
                "advance",
                native.input_block(
                    values, step=self.step, input_encoding=self.input_encoding
                ),
                target=stop,
            )
            words = np.frombuffer(result.read_bytes(), dtype="<u4")
            width = self._trace.shape[1]
            if (
                words.size != 4 + (stop - self.step) * width
                or list(words[:4]) != [0x31544D46, self.step, stop, width]
                or np.any(words[4:] > 1)
            ):
                self._failed = True
                raise RuntimeError("invalid console trace")
            self._trace[self.step : stop] = words[4:].reshape(stop - self.step, width)
            self._step = stop

    def traced_spikes(self, start, stop):
        if not 0 <= start <= stop <= self.step:
            raise ValueError("invalid trace boundary")
        return self._trace[start:stop].copy()

    def snapshot(self):
        return native.read_output(self._command("snapshot"), self._fixture)

    def _checkpoint_identity(self):
        return {
            "schema": "flymsg.console_checkpoint/v1",
            "fixture_sha256": self._identity,
            "source_commit": self._source,
            "package": self._device.package,
            "shader_sha256": self._device.shader_sha,
            "adapter": self._device.adapter,
            "input_encoding": self.input_encoding,
        }

    def checkpoint(self, path):
        remote = self._command("checkpoint").read_bytes()
        inputs = self._template._kicks.copy()
        meta = self._checkpoint_identity() | {
            "step": self.step,
            "input_end": self._template._stim_steps,
            "remote_sha256": _sha(remote),
            "inputs_sha256": _sha(inputs.tobytes()),
            "traces_sha256": _sha(self._trace.tobytes()),
        }
        path = Path(path)
        temp = path.with_name(path.name + ".tmp")
        with temp.open("wb") as f:
            np.savez(
                f,
                metadata=np.array(json.dumps(meta, sort_keys=True)),
                remote=np.frombuffer(remote, np.uint8),
                inputs=inputs,
                traces=self._trace,
            )
        temp.replace(path)

    def restore(self, path):
        self._guard()
        if self.step or self._seq:
            raise ValueError("restore requires fresh console stream")
        with np.load(path, allow_pickle=False) as saved:
            meta = json.loads(str(saved["metadata"]))
            remote, inputs, traces = [
                saved[k].copy() for k in ("remote", "inputs", "traces")
            ]
        if (
            any(meta.get(k) != v for k, v in self._checkpoint_identity().items())
            or inputs.dtype != self._template._kicks.dtype
            or inputs.shape != self._template._kicks.shape
            or traces.dtype != self._trace.dtype
            or traces.shape != self._trace.shape
            or type(meta.get("step")) is not int
            or type(meta.get("input_end")) is not int
            or not 0 <= meta["step"] <= self._template._steps
            or not 0 <= meta["input_end"] <= self._template._steps
            or remote.dtype != np.uint8
            or remote.ndim != 1
            or _sha(remote.tobytes()) != meta["remote_sha256"]
            or _sha(inputs.tobytes()) != meta["inputs_sha256"]
            or _sha(traces.tobytes()) != meta["traces_sha256"]
        ):
            raise ValueError("console checkpoint identity/integrity mismatch")
        result = self._command("restore", remote.tobytes(), target=meta["step"])
        actual = native.read_output(result, self._fixture)
        if actual["step"] != meta["step"] or not np.array_equal(
            actual["traced"], traces
        ):
            self._failed = True
            raise ValueError("console checkpoint trace mismatch")
        self._template._kicks[:] = inputs
        self._template._stim_steps = meta["input_end"]
        self._trace[:] = traces
        self._step = meta["step"]

    def close(self):
        if self._closed:
            return
        try:
            if self._failed:
                path = self._folder / "cancel.json"
                path.write_text(
                    json.dumps(
                        {"schema": "flymsg.worker_cancel/v1", "job_id": self._job}
                    )
                )
                self._device.portal.put(self._device.package, self._rel, path)
            else:
                self._command("finish")
        finally:
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
