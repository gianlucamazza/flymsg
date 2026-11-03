"""Pillow 13 against the packages that pull it in (#310).

flygym 2.1.0 declares `pillow<13`, so `[tool.uv] override-dependencies` forces 13.x.
These tests run the Pillow-touching code paths of flygym, imageio, mediapy and
matplotlib, so a resolver that falls back to Pillow 12 or an API break in 13 fails here.
"""

from importlib import metadata

import imageio.v3 as iio
import matplotlib
import mediapy
import numpy as np
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flygym.utils.video import write_video_from_frames


def _frames(n=3, h=21, w=35):
    rng = np.random.default_rng(0)
    return [rng.integers(0, 256, (h, w, 3), dtype=np.uint8) for _ in range(n)]


def test_pillow_is_13_or_later():
    assert int(metadata.version("pillow").split(".")[0]) >= 13
    assert Image.__version__ == metadata.version("pillow")


def test_flygym_video_writer_resizes_with_pillow(tmp_path):
    # 35x21 is not a multiple of 16: flygym resizes every frame through PIL (BICUBIC)
    path = tmp_path / "out" / "clip.gif"
    write_video_from_frames(path, _frames())
    back = iio.imread(path)
    assert back.shape[0] == 3
    assert back.shape[1:3] == (32, 48)


def test_imageio_png_and_gif_roundtrip(tmp_path):
    frame = _frames(1)[0]
    iio.imwrite(tmp_path / "f.png", frame)
    assert np.array_equal(iio.imread(tmp_path / "f.png"), frame)
    iio.imwrite(tmp_path / "f.gif", np.stack(_frames()))
    assert iio.imread(tmp_path / "f.gif").shape[0] == 3


def test_mediapy_image_roundtrip(tmp_path):
    frame = _frames(1)[0]
    mediapy.write_image(tmp_path / "m.png", frame)
    assert np.array_equal(mediapy.read_image(tmp_path / "m.png"), frame)


def test_matplotlib_png_through_pillow(tmp_path):
    fig, ax = plt.subplots(figsize=(1, 1), dpi=20)
    ax.plot([0, 1])
    fig.savefig(tmp_path / "p.png")
    plt.close(fig)
    with Image.open(tmp_path / "p.png") as im:
        assert im.size == (20, 20)
