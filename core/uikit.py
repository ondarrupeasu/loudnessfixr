"""uikit.py — controles con micro-animaciones (QPropertyAnimation) para el pase de pulido de UI.

Inspirado en el acabado de Middle Control (brief de MC). Solo "feel", NO toca coral ni flujos:
- AnimatedToggle: interruptor cuyo pomo DESLIZA al activarse (~200 ms, easing con pelín de rebote).
- ChevronToggle: flechita de disclosure que GIRA (▶→▼) al desplegar.
Ambos exponen la propiedad Qt `p` (0..1) que anima el estado; en render headless se puede fijar a mano.

FUENTE ÚNICA en missioncontrol/shared/ (origen: LiveMixR, pase de pulido 26 sep). Se EDITA SOLO AQUÍ; el
`sync_updater.sh` la vendoriza a cada app (como theme.py). ⚠️No editar la copia vendorizada de ninguna app
(driftaría). El acento entra por parámetro (la casa usa coral #ff5a4d), igual que theme.py; lo específico de
cada app (qué control usa cada widget) vive en la app, no aquí. Gemelo de escritorio de shared/web/casa-estilo.css.
"""
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF, QPixmap, QIcon
from PySide6.QtWidgets import QAbstractButton

_KNOB = "#f2f2f4"        # pomo (INK)
_TRACK_OFF = "#23262e"   # carril apagado (como los botones neutros)


def lucide(name, size=18, color="#f2f2f4", w=1.8):
    """Icono monocromo de TRAZO estilo Lucide (SVG-like), dibujado a mano con QPainter → idéntico en
    Mac y Windows (no depende del estilo nativo). Devuelve QIcon. color = color del texto del botón."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), w); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    s = size; m = s * 0.16
    if name == "video":
        p.drawRoundedRect(QRectF(m, s*0.3, s*0.5, s*0.4), 3, 3)
        p.drawPolygon(QPolygonF([QPointF(s*0.68, s*0.4), QPointF(s*0.86, s*0.3),
                                 QPointF(s*0.86, s*0.7), QPointF(s*0.68, s*0.6)]))
    elif name == "window":
        p.drawRoundedRect(QRectF(m, m, s-2*m, s-2*m), 3, 3)
        p.drawLine(QPointF(m, s*0.36), QPointF(s-m, s*0.36))
    elif name == "audio":
        for x, hh in zip((0.28, 0.44, 0.60, 0.76), (0.24, 0.40, 0.16, 0.30)):
            p.drawLine(QPointF(s*x, s*(0.5-hh)), QPointF(s*x, s*(0.5+hh)))
    elif name == "film":
        p.drawRoundedRect(QRectF(m, m, s-2*m, s-2*m), 3, 3)
        p.drawLine(QPointF(s*0.4, m), QPointF(s*0.4, s-m)); p.drawLine(QPointF(s*0.6, m), QPointF(s*0.6, s-m))
    elif name == "image":
        p.drawRoundedRect(QRectF(m, m, s-2*m, s-2*m), 3, 3)
        p.drawEllipse(QRectF(s*0.3, s*0.28, s*0.14, s*0.14))
        p.drawPolyline(QPolygonF([QPointF(m, s-m), QPointF(s*0.45, s*0.55), QPointF(s-m, s-m)]))
    elif name == "list":
        for y in (0.3, 0.5, 0.7):
            p.drawLine(QPointF(s*0.38, s*y), QPointF(s-m, s*y))
            p.drawEllipse(QRectF(s*0.22, s*y-1.2, 2.4, 2.4))
    elif name == "cast":                      # Stream: pantalla + ondas
        p.drawRoundedRect(QRectF(s*0.34, m, s-m-s*0.34, s*0.46), 2, 2)
        p.drawArc(QRectF(m, s*0.4, s*0.5, s*0.5), 0*16, 90*16)
        p.drawArc(QRectF(m, s*0.55, s*0.28, s*0.28), 0*16, 90*16)
        p.drawEllipse(QRectF(m, s-m-2.6, 2.6, 2.6))
    elif name == "grid":                      # Test pattern: rejilla 2x2
        p.drawRoundedRect(QRectF(m, m, s-2*m, s-2*m), 2, 2)
        p.drawLine(QPointF(s*0.5, m), QPointF(s*0.5, s-m)); p.drawLine(QPointF(m, s*0.5), QPointF(s-m, s*0.5))
    p.end()
    return QIcon(pm)


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class AnimatedToggle(QAbstractButton):
    """Interruptor on/off con pomo deslizante. Checkable como un QCheckBox; emite toggled(bool)."""

    def __init__(self, accent="#ff5a4d", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._accent = QColor(accent)
        self._p = 0.0
        self.setFixedSize(46, 26)
        self._anim = QPropertyAnimation(self, b"p", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutBack)   # el "pelín de rebote"
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._p)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def getP(self):
        return self._p

    def setP(self, v):
        self._p = float(v)
        self.update()

    p = Property(float, getP, setP)

    def sizeHint(self):
        return QSize(46, 26)

    def paintEvent(self, _e):
        pr = self._p
        w, h = self.width(), self.height()
        pad = 3.0
        d = h - 2 * pad
        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.Antialiasing)
        pnt.setPen(Qt.NoPen)
        pnt.setBrush(_lerp_color(QColor(_TRACK_OFF), self._accent, pr))
        pnt.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        x = pad + max(0.0, min(1.0, pr)) * (w - 2 * pad - d)   # pomo dentro del carril (clamp)
        pnt.setBrush(QColor(_KNOB))
        pnt.drawEllipse(QRectF(x, pad, d, d))
        pnt.end()


class ChevronToggle(QAbstractButton):
    """Flechita de disclosure que gira ▶ (cerrado) → ▼ (abierto). Checkable; emite toggled(bool)."""

    def __init__(self, color="#8a8a92", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._color = QColor(color)
        self._p = 0.0
        self.setFixedSize(20, 20)
        self._anim = QPropertyAnimation(self, b"p", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._p)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def getP(self):
        return self._p

    def setP(self, v):
        self._p = float(v)
        self.update()

    p = Property(float, getP, setP)

    def sizeHint(self):
        return QSize(20, 20)

    def paintEvent(self, _e):
        w, h = self.width(), self.height()
        pnt = QPainter(self)
        pnt.setRenderHint(QPainter.Antialiasing)
        pnt.translate(w / 2, h / 2)
        pnt.rotate(self._p * 90.0)              # 0=▶ (apunta a la derecha), 90=▼ (abajo)
        pen = QPen(self._color, 1.8)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        pnt.setPen(pen)
        r = 3.5
        pnt.drawPolyline(QPolygonF([QPointF(-r, -r), QPointF(r, 0), QPointF(-r, r)]))
        pnt.end()
