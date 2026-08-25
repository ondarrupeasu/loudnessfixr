"""updater_qt.py — hook de UI (PySide6) para el auto-updater COMPARTIDO.

Una sola llamada al arrancar la ventana principal:
    from .updater_core import Updater, UpdaterConfig
    from .updater_qt import check_and_prompt
    check_and_prompt(self, Updater(UpdaterConfig(...)))

Comprueba en segundo plano (no bloquea el arranque) y, según el caso, muestra el diálogo estándar
—idéntico en todas las apps de la suite—:
  - `is_obsolete` (kill-switch por min_version) → aviso OBLIGATORIO, solo "Update now".
  - `has_newer` → ofrece instalar ("Instalar" / "Ahora no").
Al aceptar: descarga con barra de progreso y cierra la app para que el swap se aplique.

Vendorizar junto a updater_core.py (mismo directorio). Requiere PySide6 + cryptography.
"""
from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

try:  # robusto para vendorizar en layout de paquete o plano
    from .updater_core import Updater
except ImportError:  # pragma: no cover
    from updater_core import Updater  # type: ignore

log = logging.getLogger("cinemafilmak.updater.qt")


class _CheckWorker(QThread):
    done = Signal(object)  # dict | None

    def __init__(self, updater: Updater) -> None:
        super().__init__()
        self._up = updater

    def run(self) -> None:
        self.done.emit(self._up.check_latest())


class _ApplyWorker(QThread):
    progress = Signal(int, int)
    ok = Signal()
    failed = Signal(str)

    def __init__(self, updater: Updater, info: dict) -> None:
        super().__init__()
        self._up = updater
        self._info = info

    def run(self) -> None:
        try:
            self._up.apply_update(self._info, on_progress=lambda g, t: self.progress.emit(g, t))
            self.ok.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def check_and_prompt(parent, updater: Updater, notify_none: bool = False) -> None:
    """Lanza la comprobación de updates en segundo plano. No bloquea.
    - Automático al arrancar (notify_none=False): solo si la app está empaquetada; silencioso si estás al día.
    - Manual desde menú (notify_none=True): comprueba SIEMPRE y avisa también si estás al día o si falló la comprobación."""
    if not notify_none and not bool(getattr(sys, "frozen", False)):
        return
    updater.cleanup_windows_backup()   # limpia un <App>.old.exe que dejara una actualización previa (Windows)
    # 0) GATE DE CADUCIDAD (lease) — SÍNCRONO y offline-proof. Si la versión ha caducado y no se puede
    # renovar (sin internet, o sin build/licencia nueva) → bloquea y cierra. Rápido si NO ha caducado
    # (no toca la red). Va antes del chequeo de fondo para que la app no se use si está caducada.
    _enforce_lease(parent, updater)
    worker = _CheckWorker(updater)
    parent._cf_update_worker = worker  # mantener viva la referencia
    worker.done.connect(lambda info: _on_check(parent, updater, info, notify_none))
    worker.start()


def _enforce_lease(parent, updater) -> None:
    """Gate síncrono de caducidad por tiempo. Solo hace red si la versión ya CADUCÓ (raro). Si bloquea,
    la app se cierra dentro (os._exit). Ante cualquier error del cálculo → fail-open (no bloquear por un bug)."""
    if not bool(getattr(sys, "frozen", False)):
        return
    try:
        if not updater.is_expired():
            return                              # dentro de plazo → sigue, SIN internet
    except Exception:                           # noqa: BLE001
        return
    info = updater.check_latest(timeout=8.0)    # caducada → hay que renovar online
    if not info:
        _blocked(parent, {"eol_message":
            "This version has expired. Connect to the internet to renew it or download the latest.",
            "eol_url": "https://apps.cinemafilmak.com"})
        return                                   # (no vuelve: _blocked hace os._exit)
    try:
        updater.adopt_lease(info)                # ¿el servidor concede más plazo?
        if not updater.is_expired():
            return                               # renovada → sigue
    except Exception:                            # noqa: BLE001
        return
    if updater.has_newer(info):
        _prompt(parent, updater, info, mandatory=True)   # hay build nuevo → actualización obligatoria
    else:
        _blocked(parent, info)                   # caducada y sin renovación posible → bloquear


def _on_check(parent, updater: Updater, info, notify_none: bool = False) -> None:
    if not info:
        if notify_none:
            QMessageBox.information(parent, "Update",
                                    "Couldn't check for updates. Check your connection.")
        return
    try:
        updater.adopt_lease(info)   # renovar la caducidad si el servidor concede más plazo (aunque no haya caducado aún)
    except Exception:  # noqa: BLE001
        pass
    if updater.is_obsolete(info):
        if updater.has_newer(info):
            _prompt(parent, updater, info, mandatory=True)   # hay build más nuevo → forzar actualización
        else:
            _blocked(parent, info)                           # kill-switch: sin ruta de update → bloquear y cerrar
    elif updater.has_newer(info):
        _prompt(parent, updater, info, mandatory=False)
    elif notify_none:
        QMessageBox.information(parent, "Update",
                                f"You're on the latest version ({info.get('build', '?')}).")


def _prompt(parent, updater: Updater, info: dict, *, mandatory: bool) -> None:
    build = info.get("build", "?")
    notes = str(info.get("notes", "") or "")
    box = QMessageBox(parent)
    box.setWindowTitle("Update")
    if mandatory:
        box.setIcon(QMessageBox.Warning)
        box.setText(f"This version has expired.\nYou must update to {build} to keep using the app.")
        box.setStandardButtons(QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Update now")
    else:
        box.setIcon(QMessageBox.Information)
        box.setText(f"A new version is available ({build}).\nInstall now?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("Install")
        box.button(QMessageBox.No).setText("Not now")
    if notes:
        box.setInformativeText(notes)
    resp = box.exec()
    if mandatory or resp == QMessageBox.Yes:
        _apply(parent, updater, info)


def _blocked(parent, info: dict) -> None:
    """KILL-SWITCH: la app está caducada (min_version) y NO hay build al que actualizar → esta versión
    queda inutilizada. Muestra el mensaje (configurable desde el manifiesto) y CIERRA la app.
    Campos opcionales del latest.json: `eol_message` (texto) y `eol_url` (botón 'Descargar')."""
    msg = str(info.get("eol_message") or
              "This version is no longer available.\nDownload the latest official version to keep using it.")
    url = str(info.get("eol_url") or "")
    box = QMessageBox(parent)
    box.setWindowTitle("Update required")
    box.setIcon(QMessageBox.Warning)
    box.setText(msg)
    box.setStandardButtons(QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText("Download" if url else "Close")
    box.exec()
    if url:
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:  # noqa: BLE001
            pass
    os._exit(0)  # la app NO sigue: kill real (no basta con quit() si hay hilos vivos)


def _apply(parent, updater: Updater, info: dict) -> None:
    dlg = QProgressDialog("Downloading update…", None, 0, 100, parent)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setCancelButton(None)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setMinimumDuration(0)
    dlg.show()

    worker = _ApplyWorker(updater, info)
    parent._cf_apply_worker = worker

    def on_prog(got: int, total: int) -> None:
        dlg.setValue(int(got * 100 / total) if total else 0)

    def on_ok() -> None:
        # En Windows el swap se aplica al CERRARSE y la app NO se relanza sola (a propósito: así Defender
        # ya escaneó el .exe cuando la reabres) → avisar de reabrir. En Mac sí se reinicia sola.
        if sys.platform.startswith("win"):
            dlg.close()
            QMessageBox.information(parent, "Update",
                                    "Update downloaded. The app will quit; open it again "
                                    "to use the new version.")
        else:
            dlg.setLabelText("Restarting to apply…")
            QApplication.processEvents()   # pinta el mensaje antes de morir
        # La app DEBE morir para que el swap (ya lanzado y detached, esperando a ESTE PID) reemplace el
        # binario. QApplication.quit() NO basta si hay hilos vivos → os._exit(0) fuerza la salida.
        # (Fix del cuelgue "Reiniciando…" reportado 19 ago.)
        os._exit(0)

    def on_fail(msg: str) -> None:
        dlg.close()
        QMessageBox.critical(parent, "Update failed", msg)

    worker.progress.connect(on_prog)
    worker.ok.connect(on_ok)
    worker.failed.connect(on_fail)
    worker.start()
