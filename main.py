import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QAction
from ui.main_window import MainWindow

import version
from core.updater_core import Updater, UpdaterConfig
from core.updater_qt import check_and_prompt
from core.splash import Splash
from core.report import report_dialog
from core import theme as _theme  # base compartida de la familia (shared/theme.py vendorizado)


def _logo_path():
    # Frozen (.app): assets/ va al lado del ejecutable (_MEIPASS). Fuente: junto a main.py.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "logo.png")

# TODO lo común (botones, #Primary, inputs, tabla, menú, scrollbar…) sale de la Casa de Estilo con una línea;
# encima, SOLO lo propio de LoudnessFixR: grupos, steppers del spinbox y el fader VERTICAL de ganancia.
DARK_QSS = _theme.full_qss("#ff5a4d", "#ff7d72") + """
QGroupBox { border: 1px solid #2a2b32; border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QHeaderView::section { background: #16171c; border: none; padding: 4px; }
/* Steppers −/+ de ganancia y target: son QPushButton estrechos (setFixedWidth 26). El botón canónico lleva
   padding 6×13 → en 26px de ancho el padding se come el glifo y sale VACÍO. Este #Step lo pone a padding 0 y
   centra el −/+ grande y legible (también en disabled, con menos contraste pero visible). */
QPushButton#Step { background: #242530; border: 1px solid #2a2b32; border-radius: 7px;
                   color: #e6e7ea; font-size: 16px; font-weight: 600; padding: 0; }
QPushButton#Step:hover { border-color: #ff5a4d; color: #ff5a4d; }
QPushButton#Step:pressed { background: #2a2b32; }
QPushButton#Step:disabled { color: #7a7b83; background: #191a1f; border-color: #212228; }
/* Fader VERTICAL de ganancia — adaptado a la mecánica de la familia: barra fina + marca (aquí horizontal) */
QSlider::groove:vertical { background: #161a22; width: 4px; border-radius: 2px; }
QSlider::sub-page:vertical { background: #ff5a4d; width: 4px; border-radius: 2px; }
QSlider::handle:vertical { background: #ff5a4d; height: 4px; margin: 0 -6px; border-radius: 2px; }
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
    _act = QAction("Check for updates…", win)
    _act.setMenuRole(QAction.NoRole)             # evita que macOS lo reubique en el menú de la app
    _act.triggered.connect(lambda: check_and_prompt(win, win._updater, notify_none=True))
    _help.addAction(_act)
    _act_r = QAction("Reportar un problema…", win)
    _act_r.setMenuRole(QAction.NoRole)
    _act_r.triggered.connect(lambda: report_dialog(win, "LoudnessFixR", version.__build__))
    _help.addAction(_act_r)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
