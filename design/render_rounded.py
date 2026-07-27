import sys
from PySide6.QtGui import (QImage, QPainter, QColor, QPainterPath,
                           QGuiApplication)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QRectF

app = QGuiApplication(sys.argv[:1])
src = sys.argv[1]
out = sys.argv[2]
on_gray = "--gray" in sys.argv

TILE = 1024
RX = 225

# 1) render svg into a square tile
tile = QImage(TILE, TILE, QImage.Format_ARGB32)
tile.fill(Qt.transparent)
p = QPainter(tile)
p.setRenderHint(QPainter.Antialiasing, True)
QSvgRenderer(src).render(p, QRectF(0, 0, TILE, TILE))
p.end()

# 2) apply real rounded-rect mask
mask = QImage(TILE, TILE, QImage.Format_ARGB32)
mask.fill(Qt.transparent)
mp = QPainter(mask)
mp.setRenderHint(QPainter.Antialiasing, True)
path = QPainterPath()
path.addRoundedRect(0, 0, TILE, TILE, RX, RX)
mp.fillPath(path, QColor("white"))
mp.end()
p = QPainter(tile)
p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
p.drawImage(0, 0, mask)
p.end()

if on_gray:
    size = 760
    m = int(size * 0.11)
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(QColor("#8a8f99"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.drawImage(QRectF(m, m, size - 2*m, size - 2*m),
                tile, QRectF(0, 0, TILE, TILE))
    p.end()
    canvas.save(out)
else:
    tile.save(out)
print("wrote", out)
