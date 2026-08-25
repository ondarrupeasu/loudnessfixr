"""Reporte de problemas COMPARTIDO para la suite CinemaFilmak.

"Ayuda → Reportar un problema…": el usuario escribe qué hacía y se envía —junto con el log,
la versión y el SO— al endpoint del box (report.cinemafilmak.com), que avisa a Alex por Telegram.
Sin datos personales. Si no hay red, guarda un .zip local y dice dónde está.

Uso en cada app (Ayuda):
    from report import report_dialog          # ruta según el paquete
    report_dialog(parent, app_name="LiveMixR", version=__build__, log_dir=Path("~/Library/Logs/LiveMixR"))

`log_dir` = carpeta de logs de la app (Mac: ~/Library/Logs/<App>; Windows: %LOCALAPPDATA%/<App>/logs).
El módulo coge el log MÁS RECIENTE y manda sus últimos ~200 KB.
"""
from __future__ import annotations

import json
import os
import platform
import ssl
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPlainTextEdit,
                               QDialogButtonBox, QMessageBox, QApplication)

ENDPOINT = "https://report.cinemafilmak.com/report"
LOG_TAIL_BYTES = 200 * 1024        # últimos 200 KB del log
TIMEOUT = 25


def _default_log_dirs(app_name: str) -> list[Path]:
    """Ubicaciones estándar del log según el SO (si la app no pasa log_dir explícito)."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Logs" / app_name]
    if sys.platform.startswith("win"):
        la = Path(os.environ.get("LOCALAPPDATA", str(home)))
        return [la / app_name / "logs", la / app_name]
    return [home / f".{app_name.lower()}" / "logs"]


def _newest_log(dirs: list[Path]) -> Path | None:
    """El .log/.txt más reciente entre las carpetas dadas."""
    logs = []
    for d in dirs:
        try:
            dd = Path(os.path.expanduser(str(d)))
            logs += [p for p in dd.glob("**/*") if p.is_file() and p.suffix.lower() in (".log", ".txt")]
        except Exception:
            pass
    return max(logs, key=lambda p: p.stat().st_mtime) if logs else None


def _read_tail(path: Path | None) -> str:
    if not path:
        return "(sin log)"
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > LOG_TAIL_BYTES:
                f.seek(size - LOG_TAIL_BYTES)
            data = f.read()
        return data.decode("utf-8", "replace")
    except Exception as e:
        return f"(no pude leer el log: {e})"


def _os_string() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


class _SendWorker(QThread):
    ok = Signal()
    failed = Signal(str)

    def __init__(self, payload: dict) -> None:
        super().__init__()
        self._payload = payload

    def run(self) -> None:
        try:
            body = json.dumps(self._payload).encode("utf-8")
            req = urllib.request.Request(ENDPOINT, data=body,
                                         headers={"Content-Type": "application/json"})
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                if r.status == 200:
                    self.ok.emit(); return
                self.failed.emit(f"HTTP {r.status}")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def _save_local_zip(app_name: str, version: str, note: str, log_text: str) -> str:
    """Fallback offline: guarda un .zip en el Escritorio (o Home) y devuelve la ruta."""
    base = Path(os.path.expanduser("~/Desktop"))
    if not base.is_dir():
        base = Path(os.path.expanduser("~"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zpath = base / f"{app_name}-report-{stamp}.zip"
    try:
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("meta.txt", f"app: {app_name}\nversion: {version}\nos: {_os_string()}\nnota: {note}\n")
            z.writestr("log.txt", log_text)
        return str(zpath)
    except Exception:
        return ""


def report_dialog(parent, app_name: str, version: str, log_dir=None) -> None:
    """Diálogo 'Reportar un problema': nota del usuario + envío (log/versión/SO automáticos).
    `log_dir` explícito o, si es None, se buscan las ubicaciones estándar según el nombre de la app."""
    dirs = [Path(log_dir)] if log_dir else _default_log_dirs(app_name)
    log_text = _read_tail(_newest_log(dirs))

    dlg = QDialog(parent)
    dlg.setWindowTitle("Report a problem")
    dlg.setMinimumWidth(460)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(f"What were you doing when <b>{app_name}</b> failed?\n"
                         "Your note will be sent with the technical log, the version and your OS.\n"
                         "No personal data is sent."))
    note_edit = QPlainTextEdit()
    note_edit.setPlaceholderText("e.g. 'The app quit when I pressed Export with a GH5 clip.'")
    note_edit.setMinimumHeight(110)
    lay.addWidget(note_edit)
    bb = QDialogButtonBox(QDialogButtonBox.Cancel)
    send_btn = bb.addButton("Send report", QDialogButtonBox.AcceptRole)
    lay.addWidget(bb)
    bb.rejected.connect(dlg.reject)

    def _do_send():
        note = note_edit.toPlainText().strip()
        send_btn.setEnabled(False); send_btn.setText("Sending…")
        payload = {"app": app_name, "version": str(version), "os": _os_string(),
                   "note": note, "log": log_text}
        worker = _SendWorker(payload)
        dlg._worker = worker  # mantener viva la referencia

        def _ok():
            QMessageBox.information(parent, "Thanks",
                                   "Report sent. Thanks for helping improve the app!")
            dlg.accept()

        def _fail(msg):
            zpath = _save_local_zip(app_name, version, note, log_text)
            if zpath:
                QMessageBox.warning(parent, "No connection",
                                    "Couldn't send the report (no internet?).\n\n"
                                    f"I saved it here so you can pass it on:\n{zpath}")
            else:
                QMessageBox.warning(parent, "Not sent",
                                    f"Couldn't send the report: {msg}")
            dlg.accept()

        worker.ok.connect(_ok)
        worker.failed.connect(_fail)
        worker.start()

    send_btn.clicked.connect(_do_send)
    dlg.exec()
