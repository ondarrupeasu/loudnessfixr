"""render_icon.py — genera el icono de LoudnessFixR con el PLATO COMPARTIDO de la suite.

No dibuja el plato: importa `app_icon` (shared, vendorizado por sync_updater.sh) y solo aporta el
GLIFO (`loudnessfixr_glyph.svg` = símbolo sin fondo). El glifo se rasteriza con Qt (QSvgRenderer) y
`app_icon.render_image` lo recorta a su contenido y lo encaja al 86% del plato (margen 0.101 + sombra
+ filo «C»). Ver missioncontrol/briefs/ICON_DOCK_MARGIN.md.

Salidas:
  design/LoudnessFixR.icns          (macOS, iconset completo)
  design/loudnessfixr.ico           (Windows)
  design/loudnessfixr_preview_1024.png
  assets/logo.png                   (el que usa el splash en runtime → mismo icono)

Uso:  ./venv/bin/python design/render_icon.py
"""
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

DESIGN = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(DESIGN)
sys.path.insert(0, DESIGN)          # app_icon.py vive aquí (vendorizado)
import app_icon                     # noqa: E402

GLYPH_SVG = os.path.join(DESIGN, "loudnessfixr_glyph.svg")


def glyph_image(px: int = 1024) -> QImage:
    """Rasteriza el glifo SVG a una QImage transparente de px×px."""
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(GLYPH_SVG).render(p, QRectF(0, 0, px, px))
    p.end()
    return img


def main() -> None:
    QApplication(sys.argv[:1])
    glyph = glyph_image(1024)

    def icon(size: int) -> QImage:
        return app_icon.render_image(size, glyph)   # plato + glifo, rasterizado con Qt

    # --- .icns (iconset con todos los tamaños de Apple) ---
    iconset = tempfile.mkdtemp(suffix=".iconset")
    names = [("icon_16x16", 16), ("icon_16x16@2x", 32), ("icon_32x32", 32),
             ("icon_32x32@2x", 64), ("icon_128x128", 128), ("icon_128x128@2x", 256),
             ("icon_256x256", 256), ("icon_256x256@2x", 512), ("icon_512x512", 512),
             ("icon_512x512@2x", 1024)]
    for name, size in names:
        icon(size).save(os.path.join(iconset, name + ".png"))
    icns = os.path.join(DESIGN, "LoudnessFixR.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)

    # --- .ico (Windows): empaquetar PNGs YA rasterizados con Qt, magick solo ensambla ---
    icodir = tempfile.mkdtemp()
    ico_pngs = []
    for size in (16, 32, 48, 64, 128, 256):
        pth = os.path.join(icodir, f"{size}.png")
        icon(size).save(pth)
        ico_pngs.append(pth)
    ico = os.path.join(DESIGN, "loudnessfixr.ico")
    subprocess.run(["magick", *ico_pngs, ico], check=True)

    # --- preview + logo del splash (mismo icono en runtime) ---
    icon(1024).save(os.path.join(DESIGN, "loudnessfixr_preview_1024.png"))
    icon(512).save(os.path.join(PROJ, "assets", "logo.png"))

    print("OK:", icns)
    print("OK:", ico)
    print("OK:", os.path.join(DESIGN, "loudnessfixr_preview_1024.png"))
    print("OK:", os.path.join(PROJ, "assets", "logo.png"))


if __name__ == "__main__":
    main()
