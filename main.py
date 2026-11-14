"""Einstiegspunkt: GUI starten oder headless konvertieren.

Beispiele:
    python -m lithophane.gui                  (GUI)
    python main.py foto.png lithophan.step --width 120 --resolution 200
"""

from __future__ import annotations

import sys

from lithophane.core import LithophaneParams, generate


def run_cli(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Bild in ein Lithophan im STEP-Format umwandeln."
    )
    parser.add_argument("image", help="Eingabebild (PNG, JPG, ...)")
    parser.add_argument("output", help="Ausgabedatei (.step/.stp oder .stl)")
    parser.add_argument("--width", type=float, default=100.0, help="Breite in mm")
    parser.add_argument("--base", type=float, default=0.8, help="Grundplattendicke in mm")
    parser.add_argument("--depth", type=float, default=2.2, help="Relief-Tiefe in mm")
    parser.add_argument("--resolution", type=int, default=150, help="Pixel entlang der Breite")
    parser.add_argument("--gamma", type=float, default=1.0)
    parser.add_argument("--blur", type=float, default=0.0, help="Weichzeichnen in px")
    parser.add_argument("--invert", action="store_true", help="Hell = dick")
    args = parser.parse_args(argv)

    params = LithophaneParams(
        width_mm=args.width,
        base_thickness_mm=args.base,
        relief_depth_mm=args.depth,
        resolution_px=args.resolution,
        gamma=args.gamma,
        blur_px=args.blur,
        invert=args.invert,
    )

    def progress(fraction: float, message: str) -> None:
        sys.stdout.write(f"\r{int(fraction * 100):3d}%  {message}    ")
        sys.stdout.flush()

    info = generate(args.image, args.output, params, progress=progress)
    print(
        f"\nFertig: {info['output']} | {info['width_mm']:.1f} x "
        f"{info['height_mm']:.1f} mm | Volumen {info['volume_cm3']:.1f} cm³"
    )
    return 0


def main() -> int:
    if len(sys.argv) > 2:
        return run_cli(sys.argv[1:])
    from lithophane.gui import run_gui

    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
