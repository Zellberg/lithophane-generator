"""Einfache Tests ohne Testframework: python tests/test_core.py"""

import math
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lithophane.core import (  # noqa: E402
    LithophaneParams,
    generate,
    load_heightmap,
    points_in_polygon,
    sketch_mask,
)


def make_test_image(path: str) -> None:
    x = np.linspace(0, 1, 200)
    xx, yy = np.meshgrid(x, x)
    r = np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
    arr = (255 * np.clip(1 - r * 1.6, 0, 1)).astype(np.uint8)
    Image.fromarray(arr).save(path)


def test_points_in_polygon() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    px = np.array([5.0, 15.0, 5.0])
    py = np.array([5.0, 5.0, -1.0])
    result = points_in_polygon(px, py, square)
    assert result.tolist() == [True, False, False], result


def test_mask_without_sketches() -> None:
    heightmap = np.zeros((10, 10))
    assert sketch_mask(heightmap, [], "inside").all()


def test_sketch_limits_model() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        image = os.path.join(tmp, "motiv.png")
        make_test_image(image)
        heightmap = load_heightmap(image, resolution_px=100)
        assert heightmap.shape == (100, 100)

        circle = [
            (50 + 30 * math.cos(2 * math.pi * k / 48),
             50 + 30 * math.sin(2 * math.pi * k / 48))
            for k in range(48)
        ]
        inside = sketch_mask(heightmap, [circle], "inside")
        outside = sketch_mask(heightmap, [circle], "outside")
        expected = 2828
        assert inside.sum() == expected, inside.sum()
        assert outside.sum() == 10000 - expected

        params = LithophaneParams(width_mm=60, resolution_px=100, sketches=[circle])
        step_path = os.path.join(tmp, "lithophan.step")
        info = generate(image, step_path, params)
        assert os.path.exists(step_path)
        assert 59 < info["height_mm"] < 61

        stl_path = os.path.join(tmp, "lithophan.stl")
        generate(image, stl_path, params)
        assert os.path.exists(stl_path)

    print("Alle Tests bestanden.")


if __name__ == "__main__":
    test_points_in_polygon()
    test_mask_without_sketches()
    test_sketch_limits_model()
