import sys
from PySide6.QtGui import QImage, QPainter, QGuiApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

app = QGuiApplication(sys.argv[:1])
src, out, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
h = int(sys.argv[4]) if len(sys.argv) > 4 else size
img = QImage(size, h, QImage.Format_ARGB32)
r = QSvgRenderer(src)
img.fill(Qt.transparent)
p = QPainter(img)
r.render(p)
p.end()
img.save(out)
print("wrote", out, size)
