"""Kernlogik des Lithophan-Generators.

Ein Bild wird in eine Höhenkarte umgewandelt (dunkel = dick, hell = dünn),
2D-Skizzen (geschlossene Polygone in Bildpixelkoordinaten) begrenzen den
Festkörper, und das Ergebnis wird als wasserdichter Festkörper über
OpenCascade (CadQuery) als STEP- oder STL-Datei exportiert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import cadquery as cq
import numpy as np
from PIL import Image, ImageFilter

Point = Tuple[float, float]
Polygon = List[Point]

KEEP_INSIDE = "inside"
KEEP_OUTSIDE = "outside"


@dataclass
class LithophaneParams:
    """Alle einstellbaren Parameter der Lithophan-Berechnung."""

    width_mm: float = 100.0
    base_thickness_mm: float = 0.8
    relief_depth_mm: float = 2.2
    resolution_px: int = 150
    gamma: float = 1.0
    blur_px: float = 0.0
    invert: bool = False
    keep_mode: str = KEEP_INSIDE
    sketches: List[Polygon] = field(default_factory=list)


def load_heightmap(
    path: str,
    resolution_px: int,
    invert: bool = False,
    gamma: float = 1.0,
    blur_px: float = 0.0,
) -> np.ndarray:
    """Bild laden und in eine normalisierte Höhenkarte (0..1) umwandeln.

    Rückgabe: 2D-Array, Wert 0 = maximale Materialstärke (schwarz),
    Wert 1 = Grundplattendicke (weiß).
    """
    image = Image.open(path).convert("L")
    width, height = image.size
    scale = resolution_px / width
    new_size = (max(2, resolution_px), max(2, int(round(height * scale))))
    image = image.resize(new_size, Image.LANCZOS)
    if blur_px > 0:
        image = image.filter(ImageFilter.GaussianBlur(blur_px))
    pixels = np.asarray(image, dtype=np.float64) / 255.0
    if invert:
        pixels = 1.0 - pixels
    if gamma != 1.0 and gamma > 0:
        pixels = np.power(pixels, gamma)
    return pixels


def points_in_polygon(
    px: np.ndarray, py: np.ndarray, polygon: Sequence[Point]
) -> np.ndarray:
    """Even-Odd-Punkt-in-Polygon-Test, vektorisiert über px/py."""
    px = np.asarray(px, dtype=np.float64)
    py = np.asarray(py, dtype=np.float64)
    inside = np.zeros(np.broadcast(px, py).shape, dtype=bool)
    count = len(polygon)
    if count < 3:
        return inside
    for i in range(count):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % count]
        crosses = (y1 > py) != (y2 > py)
        if not crosses.any():
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            x_intersect = (x2 - x1) * (py - y1) / (y2 - y1) + x1
        inside ^= crosses & (px < x_intersect)
    return inside


def sketch_mask(
    heightmap: np.ndarray, sketches: Sequence[Polygon], keep_mode: str
) -> np.ndarray:
    """Maske für Zellmittelpunkte: True = Zelle behalten.

    Die Skizzen liegen in Bildpixelkoordinaten (x nach rechts, y nach unten,
    wie die Bildpixel). Mehrere Skizzen werden vereinigt.
    """
    height, width = heightmap.shape
    cx = (np.arange(width) + 0.5)[None, :]
    cy = (np.arange(height) + 0.5)[:, None]
    valid = [p for p in sketches if len(p) >= 3]
    if not valid:
        return np.ones((height, width), dtype=bool)
    inside_any = np.zeros((height, width), dtype=bool)
    for polygon in valid:
        inside_any |= points_in_polygon(cx, cy, polygon)
    if keep_mode == KEEP_OUTSIDE:
        return ~inside_any
    return inside_any


def build_lithophane(
    heightmap: np.ndarray,
    params: LithophaneParams,
    progress: Optional[Callable[[float, str], None]] = None,
) -> cq.Solid:
    """Aus einer Höhenkarte einen wasserdichten Festkörper aufbauen.

    Die Oberseite folgt der Höhenkarte (Zellflächen mit vier Eckhöhen),
    die Unterseite ist eben (z = 0). An Zellen, die durch die Skizzen
    entfernt wurden, entstehen seitliche Begrenzungswände.
    """
    if progress:
        progress(0.05, "Höhenkarte wird vorbereitet ...")

    height, width = heightmap.shape
    pixel_size = params.width_mm / width
    thickness = params.base_thickness_mm + (1.0 - heightmap) * params.relief_depth_mm
    keep = sketch_mask(heightmap, params.sketches, params.keep_mode)
    if not keep.any():
        raise ValueError(
            "Keine Zellen innerhalb der Skizzen. Bitte Skizze über das Motiv zeichnen "
            "oder den Behalten-Modus ändern."
        )

    node_z = np.pad(thickness, 1, mode="edge")

    xs = np.arange(width + 1) * pixel_size
    ys = np.arange(height + 1) * pixel_size

    faces: List[cq.Face] = []

    def quad(p1, p2, p3, p4) -> cq.Face:
        wire = cq.Wire.makePolygon(
            [cq.Vector(x, y, z) for x, y, z in (p1, p2, p3, p4, p1)]
        )
        return cq.Face.makeFromWires(wire)

    def tri(p1, p2, p3) -> cq.Face:
        wire = cq.Wire.makePolygon([cq.Vector(x, y, z) for x, y, z in (p1, p2, p3, p1)])
        return cq.Face.makeFromWires(wire)

    def emit_cell(i: int, j: int) -> None:
        x0, x1 = xs[i], xs[i + 1]
        y0, y1 = ys[j], ys[j + 1]
        z00 = node_z[j, i]
        z10 = node_z[j, i + 1]
        z11 = node_z[j + 1, i + 1]
        z01 = node_z[j + 1, i]
        if abs(z00 - z11) <= abs(z10 - z01):
            faces.append(tri((x0, y0, z00), (x1, y0, z10), (x1, y1, z11)))
            faces.append(tri((x0, y0, z00), (x1, y1, z11), (x0, y1, z01)))
        else:
            faces.append(tri((x0, y0, z00), (x1, y0, z10), (x0, y1, z01)))
            faces.append(tri((x1, y0, z10), (x1, y1, z11), (x0, y1, z01)))
        faces.append(quad((x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)))
        if j == 0 or not keep[j - 1, i]:
            faces.append(quad((x0, y0, 0.0), (x1, y0, 0.0), (x1, y0, z10), (x0, y0, z00)))
        if j == height - 1 or not keep[j + 1, i]:
            faces.append(quad((x1, y1, 0.0), (x0, y1, 0.0), (x0, y1, z01), (x1, y1, z11)))
        if i == 0 or not keep[j, i - 1]:
            faces.append(quad((x0, y1, 0.0), (x0, y0, 0.0), (x0, y0, z00), (x0, y1, z01)))
        if i == width - 1 or not keep[j, i + 1]:
            faces.append(quad((x1, y0, 0.0), (x1, y1, 0.0), (x1, y1, z11), (x1, y0, z10)))

    total = int(keep.sum())
    done = 0
    step = max(1, total // 50)
    for j in range(height):
        row = keep[j]
        for i in range(width):
            if row[i]:
                emit_cell(i, j)
                done += 1
                if progress and done % step == 0:
                    progress(
                        0.05 + 0.75 * done / total,
                        f"Zellen {done}/{total} ...",
                    )

    if progress:
        progress(0.85, f"{len(faces)} Flächen werden vernäht ...")

    shell = cq.Shell.makeShell(faces)
    solid = cq.Solid.makeSolid(shell)
    if not solid.isValid():
        solid = solid.fix()

    if progress:
        progress(0.95, "Festkörper geprüft.")
    return solid


def export_model(solid: cq.Solid, path: str, tolerance: float = 0.05) -> None:
    """Festkörper als STEP (oder STL anhand der Endung) exportieren."""
    lower = path.lower()
    if lower.endswith(".step") or lower.endswith(".stp"):
        cq.exporters.export(solid, path, opt={"write_pcurves": False})
    elif lower.endswith(".stl"):
        cq.exporters.export(solid, path, tolerance=tolerance, angularTolerance=0.2)
    else:
        raise ValueError("Nur .step/.stp oder .stl Endungen werden unterstützt.")


def generate(
    image_path: str,
    output_path: str,
    params: LithophaneParams,
    progress: Optional[Callable[[float, str], None]] = None,
) -> dict:
    """Gesamtpipeline: Bild laden, Lithophan bauen, exportieren."""
    heightmap = load_heightmap(
        image_path,
        resolution_px=params.resolution_px,
        invert=params.invert,
        gamma=params.gamma,
        blur_px=params.blur_px,
    )
    if progress:
        progress(0.02, "Bild geladen.")
    solid = build_lithophane(heightmap, params, progress=progress)
    if progress:
        progress(0.97, "Export läuft ...")
    export_model(solid, output_path)
    height, width = heightmap.shape
    pixel_size = params.width_mm / width
    info = {
        "output": output_path,
        "width_mm": params.width_mm,
        "height_mm": height * pixel_size,
        "cells": int(sketch_mask(heightmap, params.sketches, params.keep_mode).sum()),
        "volume_cm3": solid.Volume() / 1000.0,
    }
    if progress:
        progress(1.0, "Fertig.")
    return info
