"""login_item.py — 'Abrir al inicio' que SOBREVIVE a las actualizaciones (self-healing).

El problema (reportado por Alex, ago 2026): activas "Open at login" y, al actualizar la app desde el
launcher, se resetea y hay que reactivarlo. La causa exacta no se pudo fijar por código (ni el updater
ni el launcher borran el login item, y las rutas son estables), pero el arreglo robusto no depende de
la causa: **guardar la INTENCIÓN del usuario y RE-APLICARLA al arrancar**.

Cada app tiene su propio mecanismo por-SO (MirroR = clave `Run`; Launcher = acceso directo en Inicio;
macOS = LaunchAgent). Este módulo NO conoce el mecanismo: la app le pasa sus propias funciones
`set_fn(on)` y `is_enabled_fn()` (las que ya tiene). Uso:

    import login_item
    # al alternar el checkbox, DESPUÉS de aplicar:
    set_login_item(on); login_item.remember(__app_name__, on)
    # al arrancar (tras crear la ventana):
    login_item.reconcile(__app_name__, set_login_item, login_item_enabled)

Requiere PySide6 (QSettings). Vendorizar junto a updater_qt.py.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

_ORG = "CinemaFilmak"          # el mismo que usan las apps para sus QSettings
_KEY = "login/intent"


def remember(app_name: str, on: bool) -> None:
    """Guarda que el usuario QUIERE (o no) abrir al inicio. Llamar al alternar el checkbox, ANTES de
    intentar aplicarlo (así, si aplicar falla, el próximo arranque lo reintenta). Nunca lanza: esta
    misma casilla ya bloqueó una app en Windows una vez (hallazgo del launcher) — no repetirlo."""
    try:
        s = QSettings(_ORG, app_name)
        s.setValue(_KEY, 1 if on else 0)
        s.sync()               # ⚠️ en Windows QSettings no persiste sin sync()
    except Exception:          # noqa: BLE001
        pass


def wants(app_name: str):
    """True/False si hay intención guardada; None si el usuario nunca lo tocó."""
    v = QSettings(_ORG, app_name).value(_KEY, None)
    if v is None:
        return None
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def reconcile(app_name: str, set_fn, is_enabled_fn) -> bool:
    """Al arrancar: si el usuario lo quería activo pero el login item se perdió (p.ej. tras un
    update), lo RESTAURA. No-op si ya está bien o si el usuario nunca lo activó. Devuelve True si
    tuvo que restaurarlo."""
    try:
        if wants(app_name) is True and not is_enabled_fn():
            set_fn(True)
            return True
    except Exception:          # noqa: BLE001  — nunca romper el arranque por esto
        pass
    return False
