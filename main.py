import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QAction
from ui.main_window import MainWindow

import version
from core.updater_core import Updater, UpdaterConfig
from core.updater_qt import check_and_prompt
from core.splash import Splash


def _logo_path():
    # Frozen (.app): assets/ va al lado del ejecutable (_MEIPASS). Fuente: junto a main.py.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "logo.png")

DARK_QSS = """
QWidget { background: #16181a; color: #e7e5df; font-size: 12px; }
QGroupBox { border: 1px solid #383c40; border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton { background: #26292d; border: 1px solid #383c40; border-radius: 4px; padding: 4px 8px; }
QPushButton:hover { border-color: #ff5a4d; }
QPushButton:disabled { color: #5a5854; }
QPushButton#Primary { background: #ff5a4d; border: 1px solid #ff5a4d; color: #14060a; font-weight: bold; }
QPushButton#Primary:hover { background: #ff7d72; border-color: #ff7d72; }
QPushButton#Primary:disabled { background: #3a2320; border-color: #3a2320; color: #7a6a66; }
QLineEdit, QComboBox, QDoubleSpinBox, QTableWidget { background: #26292d; border: 1px solid #383c40; border-radius: 4px; padding: 2px 4px; }
QDoubleSpinBox { padding-right: 2px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 18px;
    border-left: 1px solid #383c40;
    background: #2f3338;
}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #383c40; }
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow { width: 9px; height: 9px; }
QSlider::groove:vertical { background: #26292d; width: 6px; border-radius: 3px; }
QSlider::handle:vertical { background: #ff5a4d; height: 14px; margin: 0 -4px; border-radius: 4px; }
QHeaderView::section { background: #1f2225; border: none; padding: 4px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #3d3e47; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #55565e; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #3d3e47; border-radius: 4px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #55565e; }
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    splash = Splash.show(app, _logo_path(), "LoudnessFixR")
    win = MainWindow()
    win.show()
    splash.finish(win)

    # Auto-updater compartido de la suite (solo actúa si la app está empaquetada).
    # Distribución en Infomaniak (privado): baja el manifiesto de apps.cinemafilmak.com/update/.
    win._updater = Updater(UpdaterConfig(
        app_name="LoudnessFixR",
        repo="ondarrupeasu/loudnessfixr-releases",
        current_build=version.__build__,
        public_key_b64="z7ADf21EJCq4XbsmeICVTrVCdjsJ6A1RI5gVlmidEfU=",
        manifest_url="https://apps.cinemafilmak.com/update/loudnessfixr/latest.json",
    ))
    check_and_prompt(win, win._updater)          # chequeo automático al arrancar (silencioso si estás al día)

    # Menú Ayuda → Buscar actualizaciones (chequeo manual con aviso "estás al día")
    _help = win.menuBar().addMenu("Ayuda")
    _act = QAction("Buscar actualizaciones…", win)
    _act.setMenuRole(QAction.NoRole)             # evita que macOS lo reubique en el menú de la app
    _act.triggered.connect(lambda: check_and_prompt(win, win._updater, notify_none=True))
    _help.addAction(_act)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
