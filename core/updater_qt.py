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
import sys

from PySide6.QtCore import Qt, QThread, Signal
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


def check_and_prompt(parent, updater: Updater) -> None:
    """Lanza la comprobación de updates en segundo plano. No bloquea. Solo actúa si la app está empaquetada."""
    if not bool(getattr(sys, "frozen", False)):
        return
    worker = _CheckWorker(updater)
    parent._cf_update_worker = worker  # mantener viva la referencia
    worker.done.connect(lambda info: _on_check(parent, updater, info))
    worker.start()


def _on_check(parent, updater: Updater, info) -> None:
    if not info:
        return
    if updater.is_obsolete(info):
        _prompt(parent, updater, info, mandatory=True)
    elif updater.has_newer(info):
        _prompt(parent, updater, info, mandatory=False)


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
        QApplication.instance().quit()  # apply_update ya lanzó el swap; la app DEBE salir

    def on_fail(msg: str) -> None:
        dlg.close()
        QMessageBox.critical(parent, "Error al actualizar", msg)

    worker.progress.connect(on_prog)
    worker.ok.connect(on_ok)
    worker.failed.connect(on_fail)
    worker.start()
