"""Tkinter-Bedienoberfläche des Lithophan-Generators.

Links: Bildvorschau mit Zeichenfläche für 2D-Skizzen (geschlossene Polygone),
die das Lithophan begrenzen. Rechts: Parameter und Export-Steuerung.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

import numpy as np
from PIL import Image, ImageTk

from .core import (
    KEEP_INSIDE,
    KEEP_OUTSIDE,
    LithophaneParams,
    Polygon,
    generate,
    load_heightmap,
    sketch_mask,
)

CANVAS_MAX = 620


def display_size(width: int, height: int, max_size: int = CANVAS_MAX) -> tuple:
    """Anzeigegröße, die ein Bild vollständig in ein Quadrat der Kantenlänge
    max_size einpasst; Rückgabe (breite, höhe) in Canvas-Pixeln."""
    scale = min(max_size / width, max_size / height)
    return (max(1, int(width * scale)), max(1, int(height * scale)))


class LithophaneApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Lithophan-Generator (STEP)")
        self.minsize(1000, 700)

        self.image: Optional[Image.Image] = None
        self.image_path: Optional[str] = None
        self.display_scale = 1.0
        self.sketches: List[Polygon] = []
        self.current_polygon: Polygon = []
        self.heightmap: Optional[np.ndarray] = None
        self.preview_photo: Optional[ImageTk.PhotoImage] = None

        self.progress_queue: queue.Queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None

        self._build_ui()
        self.after(100, self._poll_progress)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        canvas_frame = ttk.LabelFrame(main, text="Motiv und 2D-Skizzen", padding=4)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_frame, width=CANVAS_MAX, height=CANVAS_MAX, bg="#202020"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Button-3>", self._on_canvas_undo)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_close)

        self.canvas_hint = ttk.Label(
            canvas_frame,
            text=(
                "Skizze zeichnen: Linksklick setzt Punkte, Doppelklick (oder Button) "
                "schließt das Polygon. Rechtsklick löscht den letzten Punkt."
            ),
            wraplength=620,
        )
        self.canvas_hint.pack(fill=tk.X, pady=(4, 0))

        controls = ttk.Frame(main)
        controls.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

        file_frame = ttk.LabelFrame(controls, text="Bild", padding=6)
        file_frame.pack(fill=tk.X)
        ttk.Button(file_frame, text="Bild laden ...", command=self.load_image).pack(
            fill=tk.X
        )
        self.file_label = ttk.Label(file_frame, text="Kein Bild geladen", wraplength=240)
        self.file_label.pack(fill=tk.X, pady=(4, 0))

        param_frame = ttk.LabelFrame(controls, text="Lithophan-Parameter", padding=6)
        param_frame.pack(fill=tk.X, pady=(8, 0))

        self.vars = {
            "width_mm": tk.DoubleVar(value=100.0),
            "base_thickness_mm": tk.DoubleVar(value=0.8),
            "relief_depth_mm": tk.DoubleVar(value=2.2),
            "resolution_px": tk.IntVar(value=150),
            "gamma": tk.DoubleVar(value=1.0),
            "blur_px": tk.DoubleVar(value=0.0),
            "invert": tk.BooleanVar(value=False),
        }
        rows = [
            ("Breite (mm)", "width_mm", (10.0, 400.0, 0.5)),
            ("Grundplatte (mm)", "base_thickness_mm", (0.2, 10.0, 0.05)),
            ("Relief-Tiefe (mm)", "relief_depth_mm", (0.2, 10.0, 0.05)),
            ("Auflösung (Pixel)", "resolution_px", (40, 400, 10)),
            ("Gamma", "gamma", (0.2, 4.0, 0.05)),
            ("Weichzeichnen (px)", "blur_px", (0.0, 10.0, 0.5)),
        ]
        for label, key, rng in rows:
            row = ttk.Frame(param_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
            ttk.Spinbox(
                row, from_=rng[0], to=rng[1], increment=rng[2],
                textvariable=self.vars[key], width=8,
            ).pack(side=tk.RIGHT)

        ttk.Checkbutton(
            param_frame, text="Bild invertieren (dunkel = dünn)",
            variable=self.vars["invert"],
        ).pack(anchor=tk.W, pady=(6, 0))

        sketch_frame = ttk.LabelFrame(controls, text="2D-Skizzen (Begrenzung)", padding=6)
        sketch_frame.pack(fill=tk.X, pady=(8, 0))
        self.keep_mode = tk.StringVar(value=KEEP_INSIDE)
        ttk.Radiobutton(
            sketch_frame, text="Innerhalb der Skizze behalten",
            value=KEEP_INSIDE, variable=self.keep_mode,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            sketch_frame, text="Außerhalb der Skizze behalten",
            value=KEEP_OUTSIDE, variable=self.keep_mode,
        ).pack(anchor=tk.W)

        buttons = ttk.Frame(sketch_frame)
        buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(buttons, text="Polygon schließen",
                   command=self.close_polygon).pack(fill=tk.X, pady=1)
        ttk.Button(buttons, text="Letzten Punkt löschen",
                   command=self.undo_point).pack(fill=tk.X, pady=1)
        ttk.Button(buttons, text="Alle Skizzen löschen",
                   command=self.clear_sketches).pack(fill=tk.X, pady=1)

        preview_frame = ttk.LabelFrame(controls, text="Vorschau", padding=6)
        preview_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(preview_frame, text="Vorschau aktualisieren",
                   command=self.update_preview).pack(fill=tk.X)
        self.preview_info = ttk.Label(preview_frame, text="", wraplength=240)
        self.preview_info.pack(fill=tk.X, pady=(4, 0))

        export_frame = ttk.LabelFrame(controls, text="Export", padding=6)
        export_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(export_frame, text="STEP exportieren ...",
                   command=lambda: self.export(".step")).pack(fill=tk.X, pady=1)
        ttk.Button(export_frame, text="STL exportieren ...",
                   command=lambda: self.export(".stl")).pack(fill=tk.X, pady=1)

        self.progress = ttk.Progressbar(controls, maximum=100)
        self.progress.pack(fill=tk.X, pady=(12, 2))
        self.status = ttk.Label(controls, text="Bereit.", wraplength=240)
        self.status.pack(fill=tk.X)

    # ------------------------------------------------------------- Bild/Laden

    def load_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Bild auswählen",
            filetypes=[
                ("Bilddateien", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.image = Image.open(path).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Fehler", f"Bild konnte nicht geladen werden:\n{exc}")
            return
        self.image_path = path
        self.file_label.config(text=path)
        self._fit_canvas_to_image()
        self.update_preview()

    def _fit_canvas_to_image(self) -> None:
        if self.image is None:
            return
        width, height = self.image.size
        disp_w, disp_h = display_size(width, height)
        self.display_scale = disp_w / width
        self.canvas.config(width=disp_w, height=disp_h)

    # ------------------------------------------------------------- Skizzen

    def _to_image_coords(self, event) -> tuple:
        return (event.x / self.display_scale, event.y / self.display_scale)

    def _on_canvas_click(self, event) -> None:
        if self.image is None:
            return
        self.current_polygon.append(self._to_image_coords(event))
        self.redraw()

    def _on_canvas_undo(self, event) -> None:
        self.undo_point()

    def _on_canvas_close(self, event) -> None:
        self.close_polygon()

    def close_polygon(self) -> None:
        if len(self.current_polygon) >= 3:
            self.sketches.append(self.current_polygon)
        self.current_polygon = []
        self.redraw()

    def undo_point(self) -> None:
        if self.current_polygon:
            self.current_polygon.pop()
        elif self.sketches:
            self.sketches.pop()
        self.redraw()

    def clear_sketches(self) -> None:
        self.sketches = []
        self.current_polygon = []
        self.redraw()

    # ------------------------------------------------------------ Vorschau

    def _collect_params(self) -> LithophaneParams:
        params = LithophaneParams()
        params.width_mm = float(self.vars["width_mm"].get())
        params.base_thickness_mm = float(self.vars["base_thickness_mm"].get())
        params.relief_depth_mm = float(self.vars["relief_depth_mm"].get())
        params.resolution_px = int(self.vars["resolution_px"].get())
        params.gamma = float(self.vars["gamma"].get())
        params.blur_px = float(self.vars["blur_px"].get())
        params.invert = bool(self.vars["invert"].get())
        params.keep_mode = self.keep_mode.get()
        params.sketches = [list(p) for p in self.sketches]
        return params

    def update_preview(self) -> None:
        if self.image is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Bild laden.")
            return
        try:
            params = self._collect_params()
            heightmap = load_heightmap(
                self.image_path,
                resolution_px=params.resolution_px,
                invert=params.invert,
                gamma=params.gamma,
                blur_px=params.blur_px,
            )
        except Exception as exc:
            messagebox.showerror("Fehler", f"Vorschau fehlgeschlagen:\n{exc}")
            return
        self.heightmap = heightmap
        thickness = params.base_thickness_mm + (1.0 - heightmap) * params.relief_depth_mm
        keep = sketch_mask(heightmap, params.sketches, params.keep_mode)
        if params.sketches:
            thickness = np.where(keep, thickness, 0.0)

        max_t = thickness.max()
        if max_t > 0:
            gray = (thickness / max_t * 255).astype(np.uint8)
        else:
            gray = np.zeros_like(thickness, dtype=np.uint8)
        preview = Image.fromarray(gray, mode="L").convert("RGB")
        preview = preview.resize(
            display_size(self.image.width, self.image.height), Image.NEAREST
        )
        self.preview_photo = ImageTk.PhotoImage(preview)

        height, width = heightmap.shape
        pixel_size = params.width_mm / width
        self.preview_info.config(
            text=(
                f"{width} x {height} Zellen | Modell: "
                f"{params.width_mm:.1f} x {height * pixel_size:.1f} mm | "
                f"{int(keep.sum())} Zellen aktiv"
            )
        )
        self.redraw()

    # ------------------------------------------------------------- Zeichnen

    def redraw(self) -> None:
        self.canvas.delete("all")
        if self.image is None:
            return
        if self.preview_photo is not None:
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.preview_photo)
        else:
            photo = ImageTk.PhotoImage(
                self.image.resize(
                    display_size(self.image.width, self.image.height),
                    Image.LANCZOS,
                )
            )
            self._base_photo = photo
            self.canvas.create_image(0, 0, anchor=tk.NW, image=photo)

        def draw_polygon(points, closed, color):
            pts = [c * self.display_scale for p in points for c in p]
            if closed and len(points) >= 3:
                self.canvas.create_polygon(pts, outline=color, fill="", width=2)
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=color, width=2)
            for px, py in points:
                x, y = px * self.display_scale, py * self.display_scale
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color)

        for polygon in self.sketches:
            draw_polygon(polygon, True, "#ff5555")
        draw_polygon(self.current_polygon, False, "#ffdd55")

    # -------------------------------------------------------------- Export

    def export(self, extension: str) -> None:
        if self.image is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Bild laden.")
            return
        if self.worker is not None and self.worker.is_alive():
            messagebox.showwarning("Beschäftigt", "Es läuft bereits eine Berechnung.")
            return
        path = filedialog.asksaveasfilename(
            title="Ausgabedatei wählen",
            defaultextension=extension,
            filetypes=[("STEP", "*.step *.stp")] if extension == ".step"
            else [("STL", "*.stl")],
        )
        if not path:
            return
        params = self._collect_params()
        image_path = self.image_path
        self.progress["value"] = 0
        self.status.config(text="Berechnung läuft ...")
        self.worker = threading.Thread(
            target=self._worker, args=(image_path, path, params), daemon=True
        )
        self.worker.start()

    def _worker(self, image_path: str, output_path: str, params: LithophaneParams) -> None:
        try:
            def progress(fraction: float, message: str) -> None:
                self.progress_queue.put(("progress", fraction * 100, message))

            info = generate(image_path, output_path, params, progress=progress)
            self.progress_queue.put((
                "done",
                100,
                f"Gespeichert: {info['output']} | "
                f"{info['width_mm']:.1f} x {info['height_mm']:.1f} mm | "
                f"Volumen {info['volume_cm3']:.1f} cm³",
            ))
        except Exception as exc:
            self.progress_queue.put(("error", 0, str(exc)))

    def _poll_progress(self) -> None:
        try:
            while True:
                kind, value, message = self.progress_queue.get_nowait()
                if kind == "progress":
                    self.progress["value"] = value
                    self.status.config(text=message)
                elif kind == "done":
                    self.progress["value"] = 100
                    self.status.config(text=message)
                    messagebox.showinfo("Fertig", message)
                elif kind == "error":
                    self.progress["value"] = 0
                    self.status.config(text="Fehler.")
                    messagebox.showerror("Fehler", message)
        except queue.Empty:
            pass
        self.after(100, self._poll_progress)


def run_gui() -> None:
    app = LithophaneApp()
    app.mainloop()
