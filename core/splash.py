"""Splash de arranque COMPARTIDO para la suite CinemaFilmak.

Look "casa de estilo" (oscuro + acento coral) con el logo de cada app centrado,
al estilo de Adobe / DaVinci: el usuario ve que la app está iniciando.

Uso en el `main()` de cada app (ANTES de construir la ventana, que es lo que tarda):

    from splash import Splash                       # vendorizado plano en la app
    app = QApplication(sys.argv)
    splash = Splash.show(app, LOGO_PATH, "LoudnessFixR")
    win = MainWindow()                              # init pesado: el splash tapa la espera
    win.show()
    splash.finish(win)                              # respeta un tiempo mínimo y cierra

`LOGO_PATH` puede ser .png o .svg (se resuelve vía QIcon). Un tiempo mínimo en
pantalla evita el parpadeo en apps que arrancan muy rápido.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QEventLoop, QTimer, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPainterPath, QIcon
from PySide6.QtWidgets import QSplashScreen, QApplication

# Paleta casa de estilo (idéntica a la de las apps)
_BG      = QColor("#16181a")
_BORDER  = QColor("#2a2d31")
_INK     = QColor("#e7e5df")
_MUTED   = QColor("#7a7d82")
_CORAL   = QColor("#ff5a4d")

_W, _H   = 460, 300          # tamaño lógico del splash
_RADIUS  = 18
_LOGO    = 120               # lado del logo
_MIN_MS  = 1200              # tiempo mínimo visible (anti-parpadeo)


def _build_pixmap(logo_path: str | Path, app_name: str, subtitle: str) -> QPixmap:
    dpr = 2                                            # nitidez en pantallas retina
    pm = QPixmap(_W * dpr, _H * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(dpr, dpr)                                  # a partir de aquí, coords lógicas

    # Tarjeta redondeada
    card = QRectF(0.5, 0.5, _W - 1, _H - 1)
    path = QPainterPath()
    path.addRoundedRect(card, _RADIUS, _RADIUS)
    p.fillPath(path, _BG)
    p.setPen(_BORDER)
    p.drawPath(path)

    # Logo centrado (arriba)
    if logo_path and Path(logo_path).exists():
        logo = QIcon(str(logo_path)).pixmap(_LOGO, _LOGO)
        if not logo.isNull():
            p.drawPixmap((_W - _LOGO) // 2, 44, logo)

    # Nombre de la app
    p.setPen(_INK)
    f = QFont()
    f.setPointSize(20)
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.drawText(QRectF(0, 188, _W, 34), Qt.AlignHCenter | Qt.AlignVCenter, app_name)

    # Regla coral corta bajo el nombre
    bar = QRectF((_W - 44) / 2, 230, 44, 3)
    bp = QPainterPath()
    bp.addRoundedRect(bar, 1.5, 1.5)
    p.fillPath(bp, _CORAL)

    # Subtítulo "Iniciando…"
    p.setPen(_MUTED)
    f2 = QFont()
    f2.setPointSize(11)
    p.setFont(f2)
    p.drawText(QRectF(0, 246, _W, 22), Qt.AlignHCenter | Qt.AlignVCenter, subtitle)

    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


class Splash:
    """Envuelve un QSplashScreen con logo + tiempo mínimo en pantalla."""

    def __init__(self, sp: QSplashScreen, t0: float):
        self._sp = sp
        self._t0 = t0

    @classmethod
    def show(cls, app: QApplication, logo_path: str | Path,
             app_name: str, subtitle: str = "Iniciando…") -> "Splash":
        pm = _build_pixmap(logo_path, app_name, subtitle)
        sp = QSplashScreen(pm, Qt.WindowStaysOnTopHint)
        sp.setAttribute(Qt.WA_TranslucentBackground)   # esquinas redondeadas reales
        sp.show()
        app.processEvents()                            # pintarlo ya, antes del init pesado
        return cls(sp, time.monotonic())

    def finish(self, window) -> None:
        """Cierra el splash tras garantizar `_MIN_MS` en pantalla."""
        elapsed_ms = (time.monotonic() - self._t0) * 1000
        remaining = int(max(0, _MIN_MS - elapsed_ms))
        if remaining:
            loop = QEventLoop()
            QTimer.singleShot(remaining, loop.quit)
            loop.exec()                                # la ventana ya pinta detrás
        self._sp.finish(window)
