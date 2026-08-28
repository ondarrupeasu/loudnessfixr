"""app_icon.py — el PLATO común de los iconos de la suite (la «misma madre»).

Todos los iconos de escritorio de CinemaFilmak comparten el mismo plato: fondo oscuro
redondeado, con el margen de Apple, una sombra horneada y un filo de luz arriba. Lo único que
cambia de una app a otra es el GLIFO de dentro (la carpeta de MirroR, el cohete del launcher…).

Antes cada app dibujaba su propio plato y salían todos distintos («de su madre»): unos con
brillo, otros planos, tamaños desiguales. Este módulo centraliza el plato para que sean
hermanos idénticos. Cada app solo aporta su glifo.

⚠️ **El brillo NO lo pone macOS.** Se comprobó en el Dock (mismo macOS, unos iconos con brillo y
otros no → va horneado en el arte, no lo añade el sistema). Por eso el plato lo trae ESTE módulo.
Detalle: `missioncontrol/briefs/ICON_DOCK_MARGIN.md`.

⚠️ **Esto es SOLO para el icono de app** (.icns/.ico/PNG del Dock, y el PNG de `setWindowIcon`).
La imagen de la **barra de menús / tray NO usa este plato**: va a sangre, de un color, sin margen.

Valores canónicos (medidos contra Notes/Maps/Reminders + nivel «C» validado por Alex):
  - Margen de Apple .............. 0.101 (plato del 10,1% al 89,8% del lienzo)
  - Sombra ....................... silueta negra desenfocada, alfa 150, caída 2,2%
  - Cuerpo ....................... degradado #25262e → #1b1c22 → #131419
  - Filo «C» ..................... blanco alfa 92→28→0 en el borde superior
  - Ocupación del glifo .......... 86% del plato

Uso (Qt / PySide6):

    from app_icon import render, glyph_box
    def dibuja_glifo(p: QPainter, caja: QRectF) -> None:
        ...  # pinta TU símbolo dentro de `caja` (mide su bbox y escálalo a caja)
    icono = render(1024, dibuja_glifo)      # QImage lista para guardar/iconset

Uso (PIL / Pillow, p. ej. AirCastR):

    from app_icon import plate_pil, glyph_box_tuple
    fondo = plate_pil(1024)                  # el plato ya con margen+sombra+filo
    x, y, w, h = glyph_box_tuple(1024)
    fondo.paste(mi_glifo_pil, (x, y), mi_glifo_pil)   # pega tu glifo centrado

Requiere PySide6 (lo tienen todas las apps de la suite). PIL solo si usas las funciones *_pil.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen

# --- valores canónicos (no tocar sin actualizar el brief ICON_DOCK_MARGIN.md) ---------------
MARGEN = 0.101
RADIO_RATIO = 0.2227          # radio de esquina respecto al lado del plato (el de macOS)
OCUPACION = 0.86              # cuánto del plato ocupa el glifo
PLATE_TOP = "#25262e"
PLATE_MID = "#1b1c22"
PLATE_BOT = "#131419"
FILO_ALFA = (92, 28, 0)       # nivel «C»: (arriba, 30%, abajo)
FILO_ANCHO = 0.019            # grosor del filo respecto al lado del plato
SOMBRA_ALFA = 150             # la de Apple deja ~181 justo debajo del plato
SOMBRA_CAIDA = 0.022          # cuánto baja la sombra, en tanto por uno del lienzo
_SUELO_BLUR = 40              # ⚠️ encoger a <40px convierte la sombra en un CUADRO gris


def _caja_plato(size: int) -> QRectF:
    """El rectángulo del plato dentro del lienzo (con el margen de Apple)."""
    lado = size * (1 - 2 * MARGEN)
    off = (size - lado) / 2
    return QRectF(off, off, lado, lado)


def glyph_box(size: int) -> QRectF:
    """Dónde va el glifo: cuadrado centrado, al 86% del plato. Escala TU símbolo a esta caja."""
    lado = size * (1 - 2 * MARGEN) * OCUPACION
    off = (size - lado) / 2
    return QRectF(off, off, lado, lado)


def glyph_box_tuple(size: int) -> tuple[int, int, int, int]:
    """glyph_box en enteros (x, y, w, h), para pegar con PIL."""
    b = glyph_box(size)
    return (int(round(b.x())), int(round(b.y())),
            int(round(b.width())), int(round(b.height())))


def _sombra(size: int, caja: QRectF) -> QImage:
    """La silueta del plato en negro, desenfocada — la sombra horneada que llevan los iconos
    del sistema. Desenfoque sin dependencias: encoger con suavizado y volver a estirar."""
    sil = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    sil.fill(Qt.GlobalColor.transparent)
    sp = QPainter(sil)
    sp.setRenderHint(QPainter.RenderHint.Antialiasing)
    sp.setPen(Qt.PenStyle.NoPen)
    sp.setBrush(QColor(0, 0, 0, SOMBRA_ALFA))
    r = RADIO_RATIO * caja.width()
    sp.drawRoundedRect(caja, r, r)
    sp.end()
    chico = max(_SUELO_BLUR, size // 9)
    return (sil.scaled(chico, chico, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
            .scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))


def _pinta_plato(p: QPainter, caja: QRectF) -> None:
    """Sombra + cuerpo con degradado + filo de luz. `p` pinta sobre un lienzo tamaño completo."""
    r = RADIO_RATIO * caja.width()

    # Cuerpo del plato: degradado vertical muy contenido.
    grad = QLinearGradient(caja.topLeft(), caja.bottomLeft())
    grad.setColorAt(0.0, QColor(PLATE_TOP))
    grad.setColorAt(0.55, QColor(PLATE_MID))
    grad.setColorAt(1.0, QColor(PLATE_BOT))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(caja, r, r)

    # Filo de luz arriba (nivel «C»).
    luz = QLinearGradient(caja.topLeft(),
                          QPointF(caja.left(), caja.top() + caja.height() * 0.55))
    luz.setColorAt(0.0, QColor(255, 255, 255, FILO_ALFA[0]))
    luz.setColorAt(0.30, QColor(255, 255, 255, FILO_ALFA[1]))
    luz.setColorAt(1.0, QColor(255, 255, 255, FILO_ALFA[2]))
    pluma = QPen()
    pluma.setBrush(luz)
    pluma.setWidthF(max(1.0, caja.width() * FILO_ANCHO))
    d = pluma.widthF() / 2
    p.setPen(pluma)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(caja.adjusted(d, d, -d, -d), r - d, r - d)
    p.setPen(Qt.PenStyle.NoPen)


def plate(size: int = 1024) -> QImage:
    """El plato SOLO (sombra + cuerpo + filo, con el margen), sin glifo. QImage ARGB completa."""
    out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    caja = _caja_plato(size)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if size >= 64:                        # a 16/32 px la sombra solo emborrona
        p.drawImage(QPointF(0, size * SOMBRA_CAIDA), _sombra(size, caja))
    _pinta_plato(p, caja)
    p.end()
    return out


def render(size: int, draw_glyph) -> QImage:
    """Icono completo: el plato común + TU glifo. `draw_glyph(painter, caja)` pinta el símbolo
    dentro de `caja` (usa `glyph_box`). Devuelve la QImage lista para guardar/iconset.

    ⚠️ `draw_glyph` debe LLENAR `caja`: si dibuja tu símbolo con márgenes vacíos alrededor, saldrá
    pequeño dentro del plato. Si tu glifo lo tienes como QImage (dibujada sobre el lienzo entero),
    usa `render_image()` en su lugar — recorta a su contenido por ti (hallazgo de MirroR)."""
    out = plate(size)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    draw_glyph(p, glyph_box(size))
    p.end()
    return out


def _alpha_bbox(img: QImage):
    """Caja (x, y, w, h) del contenido no transparente del glifo; None si está vacío."""
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    raw = bytes(img.constBits())[: w * h * 4]
    top = bottom = left = right = None
    for y in range(h):
        fila = raw[y * w * 4 + 3: (y + 1) * w * 4: 4]   # alfa de la fila, longitud w
        izq = next((x for x in range(w) if fila[x] > 8), None)
        if izq is None:
            continue
        der = next(x for x in range(w - 1, -1, -1) if fila[x] > 8)
        top = y if top is None else top
        bottom = y
        left = izq if left is None else min(left, izq)
        right = der if right is None else max(right, der)
    if top is None:
        return None
    return (left, top, right - left + 1, bottom - top + 1)


def fit_glyph(img: QImage, box: QRectF):
    """Recorta el glifo a su contenido y da (recorte, rect_destino) escalado para llenar `box`."""
    bb = _alpha_bbox(img)
    if not bb:
        return img, box
    x, y, w, h = bb
    crop = img.copy(x, y, w, h)
    escala = min(box.width() / w, box.height() / h)
    tw, th = w * escala, h * escala
    return crop, QRectF(box.x() + (box.width() - tw) / 2,
                        box.y() + (box.height() - th) / 2, tw, th)


def render_image(size: int, glyph: QImage) -> QImage:
    """Como `render()`, pero recibe el glifo YA dibujado (QImage) y lo **recorta a su contenido**
    + escala para llenar el 86% del plato. Úsalo si tu glifo no llena el lienzo por sí solo."""
    out = plate(size)
    crop, target = fit_glyph(glyph, glyph_box(size))
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(target, crop)
    p.end()
    return out


# ------------------------------------------------------------------- puente a PIL (AirCastR)
def qimage_to_pil(img: QImage):
    """Convierte una QImage a PIL.Image RGBA (para apps que pintan su glifo con Pillow)."""
    from PIL import Image
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    return Image.frombytes("RGBA", (w, h), bytes(ptr[: w * h * 4]))


def plate_pil(size: int = 1024):
    """El plato común, como PIL.Image RGBA. Pega tu glifo (PIL) en `glyph_box_tuple(size)`."""
    return qimage_to_pil(plate(size))


if __name__ == "__main__":
    # Autotest: pinta el plato con un glifo de muestra (un círculo coral) y lo guarda.
    import os
    from PySide6.QtWidgets import QApplication

    QApplication([])

    def _muestra(p: QPainter, caja: QRectF) -> None:
        p.setBrush(QColor("#ff5a4d"))
        p.setPen(Qt.PenStyle.NoPen)
        m = caja.width() * 0.18
        p.drawEllipse(caja.adjusted(m, m, -m, -m))

    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_app_icon_selftest.png")
    render(1024, _muestra).save(dest)
    print("->", dest)
