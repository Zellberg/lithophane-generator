# Lithophan-Generator (STEP)

Wandelt Bilddateien in druckfertige Lithophane im **STEP-Format** um (optional STL)
und bietet eine grafische Bedienoberfläche mit Steuerelementen für alle relevanten
Parameter. Zusätzlich lassen sich **2D-Skizzen** (geschlossene Polygone) über das
Motiv zeichnen, die das berechnete Lithophan begrenzen.

## Funktionen

- Bild zu Lithophan: dunkle Bildbereiche werden dick, helle dünn (klassisches Lithophan-Verhalten)
- Export als **STEP** (exakte BREP-Festkörper via OpenCascade/CadQuery) oder STL
- Bedienoberfläche (Tkinter, keine zusätzliche GUI-Abhängigkeit) mit Steuerelementen für:
  - Breite (mm) — die Höhe folgt automatisch dem Bildseitenverhältnis
  - Grundplattendicke (mm) und Relief-Tiefe (mm)
  - Auflösung (Pixel entlang der Breite)
  - Gamma-Korrektur und Weichzeichnen (Gauß) für die Helligkeitsverteilung
  - Invertieren (dunkel = dünn, für Negative/Folien)
- **2D-Skizzen über das Motiv legen:**
  - Linksklick setzt Eckpunkte, Doppelklick (oder Button „Polygon schließen“) schließt die Skizze
  - Rechtsklick / „Letzten Punkt löschen“ entfernt den letzten Punkt
  - Mehrere Skizzen sind möglich und werden vereinigt
  - Umschaltbar: Material **innerhalb** (z. B. Rundpanel, Herzform) oder **außerhalb**
    der Skizze behalten (z. B. rechteckige Aussparung)
  - Die Vorschau zeigt die begrenzte Stärkenverteilung in Graustufen
- Berechnung läuft in einem Hintergrund-Thread mit Fortschrittsbalken

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Benötigt werden `cadquery` (mit OpenCascade), `numpy` und `Pillow`.
Unter Linux kann zusätzlich `libgl1` nötig sein (`sudo apt install libgl1`).

## Nutzung

### Oberfläche

```bash
python main.py
```

1. „Bild laden …“ – Motiv auswählen (PNG, JPG, BMP, TIFF, WebP, GIF).
2. Parameter einstellen, optional „Vorschau aktualisieren“.
3. Skizzen direkt auf dem Bild zeichnen (siehe oben), um das Lithophan zu begrenzen.
4. „STEP exportieren …“ (oder STL) – Zieldatei wählen.

### Kommandozeile (ohne Oberfläche)

```bash
python main.py foto.png lithophan.step --width 120 --resolution 200 --gamma 1.2
python main.py foto.png lithophan.stl --width 90 --base 0.6 --depth 2.5 --blur 1
```

Optionen: `--width`, `--base`, `--depth`, `--resolution`, `--gamma`, `--blur`,
`--invert`.

## Programmstruktur

| Datei | Inhalt |
|---|---|
| `lithophane/core.py` | Bildverarbeitung, Höhenkarte, Punkt-in-Polygon-Maske, Festkörper-Aufbau, STEP/STL-Export |
| `lithophane/gui.py` | Tkinter-Bedienoberfläche mit Zeichenfläche für die 2D-Skizzen |
| `main.py` | Einstiegspunkt (GUI oder Kommandozeile) |
| `tests/test_core.py` | Tests: `python tests/test_core.py` |

## Technischer Hintergrund

- Das Bild wird auf die Zellauflösung skaliert, optional geglättet und gamma-korrigiert.
- Die lokale Materialstärke ist `Grundplatte + (1 − Helligkeit) · Relief-Tiefe`.
- Jede Zelle wird als Planarfläche mit vier Eckhöhen (in zwei Dreiecke aufgeteilt,
  damit alle Flächen planar sind) plus Bodenfläche erzeugt; an den Rändern und an
  ausgesparten Skizzenbereichen entstehen senkrechte Wände.
- Alle Flächen werden mit OpenCascade zu einem geschlossenen Festkörper vernäht
  und als STEP geschrieben; das Ergebnis wurde per Reimport auf Gültigkeit geprüft.

## Hinweise

- Höhere Auflösung = feinere Details, aber deutlich längere Rechenzeit und größere
  STEP-Dateien (Richtwert: 150 Pixel ≈ 30–60 s).
- Skizzenkoordinaten beziehen sich auf die Bildpixel; mehrere Skizzen werden vereinigt.
