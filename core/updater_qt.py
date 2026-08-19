"""updater_qt.py — hook de UI (PySide6) para el auto-updater COMPARTIDO.

Una sola llamada al arrancar la ventana principal:
    from .updater_core import Updater, UpdaterConfig
    from .updater_qt import check_and_prompt
    check_and_prompt(self, Updater(UpdaterConfig(...)))

Comprueba en segundo plano (no bloquea el arranque) y, según el caso, muestra el diálogo estándar
—idéntico en todas las apps de la suite—:
  - `is_obsolete` (kill-switch por min_version) → aviso OBLIGATORIO, solo "Actualizar ahora".
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
    worker = _CheckWorker(updater)
    parent._cf_update_worker = worker  # mantener viva la referencia
    worker.done.connect(lambda info: _on_check(parent, updater, info, notify_none))
    worker.start()


def _on_check(parent, updater: Updater, info, notify_none: bool = False) -> None:
    if not info:
        if notify_none:
            QMessageBox.information(parent, "Actualización",
                                    "No se pudo comprobar si hay actualizaciones. Revisa tu conexión.")
        return
    if updater.is_obsolete(info):
        if updater.has_newer(info):
            _prompt(parent, updater, info, mandatory=True)   # hay build más nuevo → forzar actualización
        else:
            _blocked(parent, info)                           # kill-switch: sin ruta de update → bloquear y cerrar
    elif updater.has_newer(info):
        _prompt(parent, updater, info, mandatory=False)
    elif notify_none:
        QMessageBox.information(parent, "Actualización",
                                f"Estás en la última versión ({info.get('build', '?')}).")


def _prompt(parent, updater: Updater, info: dict, *, mandatory: bool) -> None:
    build = info.get("build", "?")
    notes = str(info.get("notes", "") or "")
    box = QMessageBox(parent)
    box.setWindowTitle("Actualización")
    if mandatory:
        box.setIcon(QMessageBox.Warning)
        box.setText(f"Esta versión ha caducado.\nDebes actualizar a {build} para seguir usando la app.")
        box.setStandardButtons(QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Actualizar ahora")
    else:
        box.setIcon(QMessageBox.Information)
        box.setText(f"Hay una nueva versión disponible ({build}).\n¿Instalar ahora?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("Instalar")
        box.button(QMessageBox.No).setText("Ahora no")
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
              "Esta versión ya no está disponible.\nDescarga la última versión oficial para seguir usándola.")
    url = str(info.get("eol_url") or "")
    box = QMessageBox(parent)
    box.setWindowTitle("Actualización requerida")
    box.setIcon(QMessageBox.Warning)
    box.setText(msg)
    box.setStandardButtons(QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText("Descargar" if url else "Cerrar")
    box.exec()
    if url:
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:  # noqa: BLE001
            pass
    os._exit(0)  # la app NO sigue: kill real (no basta con quit() si hay hilos vivos)


def _apply(parent, updater: Updater, info: dict) -> None:
    dlg = QProgressDialog("Descargando actualización…", None, 0, 100, parent)
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
        dlg.setLabelText("Reiniciando para aplicar…")
        QApplication.processEvents()   # pinta el mensaje antes de morir
        # La app DEBE morir para que el script de swap (ya lanzado y detached, esperando a ESTE PID)
        # pueda reemplazar el bundle. QApplication.quit() NO basta: si el worker u otros hilos siguen
        # vivos, el proceso no sale y se queda colgado en "Reiniciando…". os._exit(0) mata el proceso
        # de inmediato; el swap reabre una copia limpia. (Fix del cuelgue reportado 19 ago.)
        os._exit(0)

    def on_fail(msg: str) -> None:
        dlg.close()
        QMessageBox.critical(parent, "Error al actualizar", msg)

    worker.progress.connect(on_prog)
    worker.ok.connect(on_ok)
    worker.failed.connect(on_fail)
    worker.start()
