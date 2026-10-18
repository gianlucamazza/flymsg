"""`dead_time` is one object: song re-exports the stimulus primitive."""

import ast
from pathlib import Path

import numpy as np

from flymsg import gf_looming, song, stimulus


def _same(k, gap, expected):
    got = song.dead_time(k, gap)
    other = stimulus.dead_time(np.array(k, copy=True), gap)
    assert np.array_equal(got, other)
    assert got.dtype == other.dtype == np.dtype(np.int8)
    assert got.shape == other.shape == np.shape(k)
    assert np.array_equal(got, expected)


def test_song_dead_time_is_the_stimulus_primitive():
    assert song.dead_time is stimulus.dead_time


def test_dead_time_on_deterministic_inputs():
    # Several kicks in one bin collapse to one. A gap of 2 steps drops the rest.
    k = np.array(
        [
            [1, 0, 2],
            [1, 1, 0],
            [1, 0, 1],
            [0, 1, 0],
            [3, 0, 0],
        ],
        dtype=np.int64,
    )
    _same(
        k,
        2,
        np.array(
            [
                [1, 0, 1],
                [0, 1, 0],
                [1, 0, 1],
                [0, 1, 0],
                [1, 0, 0],
            ],
            dtype=np.int8,
        ),
    )
    # Dead time 0 keeps every occupied step, still one kick per step.
    _same(
        k,
        0,
        np.array(
            [
                [1, 0, 1],
                [1, 1, 0],
                [1, 0, 1],
                [0, 1, 0],
                [1, 0, 0],
            ],
            dtype=np.int8,
        ),
    )
    # Consecutive kicks: a gap of one step keeps neighbours; a gap of three keeps
    # the first and the kick three steps later.
    run = np.ones((5, 1), dtype=np.int32)
    _same(run, 1, np.ones((5, 1), dtype=np.int8))
    _same(run, 3, np.array([[1], [0], [0], [1], [0]], dtype=np.int8))
    quiet = np.zeros((6, 2), dtype=np.int16)
    _same(quiet, 0, np.zeros((6, 2), dtype=np.int8))
    _same(quiet, 4, np.zeros((6, 2), dtype=np.int8))


def test_dead_time_empty_inputs_keep_shape_and_dtype():
    for shape in ((0, 3), (4, 0), (0, 0)):
        k = np.zeros(shape, dtype=np.int64)
        for gap in (0, 5):
            got = song.dead_time(k, gap)
            other = stimulus.dead_time(k, gap)
            assert np.array_equal(got, other)
            assert got.dtype == other.dtype == np.dtype(np.int8)
            assert got.shape == other.shape == shape
            assert got.sum() == 0


def test_gf_looming_does_not_import_song():
    tree = ast.parse(Path(gf_looming.__file__).read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                found.add(module)
            for alias in node.names:
                found.add(alias.name)
                if module:
                    found.add(f"{module}.{alias.name}")
    assert "song" not in found and "flymsg.song" not in found
    assert "stimulus" in found or "flymsg.stimulus" in found
