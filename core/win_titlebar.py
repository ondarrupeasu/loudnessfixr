"""win_titlebar.py — barra de título OSCURA en Windows. No-op en macOS/Linux.

En Windows 10 las apps abren con la barra de título **blanca** aunque su interfaz sea oscura; eso
hace que el icono de la ventana (con partes blancas) se pierda sobre ella y queda incoherente con
la UI oscura de la casa. Esto le dice a Windows que pinte la barra de título en **oscuro**
(`DWMWA_USE_IMMERSIVE_DARK_MODE`), que casa con la barra de tareas y con la propia app.

Uso: tras crear la ventana principal, `win_titlebar.apply(ventana)`. Da igual si es antes o después
de `show()` (fuerza el handle nativo con `winId()`). Llamar en CADA ventana de nivel superior que
quieras oscura (la principal como mínimo).

Requiere `sys.platform == "win32"`; en el resto no hace nada. Sin dependencias (ctypes + DWM).
Ref: missioncontrol/briefs/ICON_DOCK_MARGIN.md (sección Windows).
"""
from __future__ import annotations

import ctypes
import sys

# Atributos DWM. 20 = Win10 1903+/Win11 (el bueno); 19 = el valor viejo de Win10 1809. Probamos los
# dos: el que no exista devuelve error y se ignora.
_DWMWA_USE_IMMERSIVE_DARK_MODE = (20, 19)


def apply(widget) -> bool:
    """Pinta en oscuro la barra de título de `widget` en Windows.

    Aplica YA y, además, RE-APLICA cuando el bucle de eventos ha arrancado: al abrir la ventana
    maximizada, el marco todavía se está asentando y el atributo puesto «demasiado pronto» no
    prende hasta un cambio de tamaño. Los reintentos diferidos (0 ms y 250 ms) lo cubren.
    """
    ok = _apply_now(widget)
    try:                                     # re-aplicar cuando la ventana ya está asentada
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: _apply_now(widget))
        QTimer.singleShot(250, lambda: _apply_now(widget))
    except Exception:                        # noqa: BLE001
        pass
    return ok


def _apply_now(widget) -> bool:
    if sys.platform != "win32":
        return False
    try:
        hwnd = int(widget.winId())          # fuerza el handle nativo si aún no existe
    except Exception:                        # noqa: BLE001
        return False
    valor = ctypes.c_int(1)
    ok = False
    for attr in _DWMWA_USE_IMMERSIVE_DARK_MODE:
        try:
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(valor), ctypes.sizeof(valor))
            if res == 0:
                ok = True
                break
        except Exception:                    # noqa: BLE001
            pass
    if ok:
        # ⚠️ Sin esto, en Win10 la barra NO se repinta hasta que minimizas/restauras: al abrir
        # maximizada se ve BLANCA hasta el primer cambio de tamaño. Forzamos el recálculo del marco
        # (SetWindowPos con SWP_FRAMECHANGED) para que la barra salga oscura desde el primer pintado.
        try:
            SWP = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP)
        except Exception:                    # noqa: BLE001
            pass
    return ok
