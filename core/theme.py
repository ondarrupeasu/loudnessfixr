"""theme.py — la casa de estilo en UN sitio (compartido, lo reparte sync_updater.sh).

Misma idea que app_icon: la MECÁNICA vive aquí (QSS de botón/input/scrollbar, radios, y el
invariante «el borde nunca cambia de grosor»), y cada app aporta solo su ACENTO. QSS no tiene
variables, así que esto es un módulo Python pequeño que DEVUELVE strings QSS; cada app hace
`setStyleSheet(theme.base_qss(ACCENT) + sus_extras)` y encima añade lo suyo propio (los scopes de
PostHandleR, los pads de LiveMixR).

Por qué módulo y no un .qss plano: el acento tiene que ser parámetro (cada app conserva su color)
y el grosor del borde no puede cambiar entre estados (un estilo NO redimensiona nada — el bug MC
THEME_PRIMARY_BUTTON_BORDER: el botón coral llevaba `border:none`, 2px más corto que sus vecinos,
y descolocaba el layout). Bloqueado por test_theme.py.

Adopción OPT-IN, app por app. LiveMixR es el primero: sus 3 helpers (DIALOG_BUTTONS/flat/pad) están
COPIADOS VERBATIM de su b/theme.py ya consolidado, para que pueda borrar el suyo e importar este sin
un solo pixel de cambio. PostHandleR aporta su theme.qss como input para fijar inputs/tokens finos.
"""

# ---- Tokens de la FAMILIA (paleta fría azulada; la referencia es AirCastR/VideoCatchR/AudioPatchR) ----
# El acento va SIEMPRE por parámetro (cada app pasa el suyo; la familia usa coral #ff5a4d).
BG        = "#0e0f12"   # fondo de ventana (frío, ligeramente azulado)
BG2       = "#0a0b0d"   # fondo más hundido
PANEL     = "#16171c"   # paneles
CARD      = "#1c1d23"   # tarjetas / base de botones
CARD_HI   = "#25262e"   # tarjeta resaltada / pressed
LINE      = "#2a2b32"   # filo
LINE_SOFT = "#212228"   # filo suave (disabled)
INPUT     = "#161a22"   # gris azulado de los controles (combos/inputs)
TEXT      = "#f2f2f4"   # texto principal
MUTED     = "#8a8a92"   # texto secundario
MUTED2    = "#666770"   # texto terciario / disabled
ON_ACCENT = "#14060a"   # texto sobre el coral
RADIUS    = 6           # radio por defecto (px)

# Paleta de ESTADO de la casa — UN tono distinto por significado (nunca dos verdes/rojos parecidos):
#   neutro=gris (por defecto) · info=azul · ok=verde · atención=ámbar · live/acción/ERROR=coral (=acento).
# Decisión de Alex (31 ago): un solo rojo = el coral; error y live comparten el coral (la palabra desambigua).
SIG_LO   = "#3fb950"    # verde  — ok / hecho
SIG_MID  = "#d9a441"    # ámbar  — atención / cola
SIG_INFO = "#4a9eff"    # azul   — info / red / enlace (distinto del verde, NO un verde-agua)
# SIG_HI / error = el acento (coral), va por parámetro. En barras, el error usa un coral OSCURO (#5a2a26).

# Aliases hacia el nombre viejo, por si algo los importaba
SURFACE, CONTROL, BORDER, BORDER_HI, INK, INK_DIM = PANEL, CARD, LINE, MUTED, TEXT, MUTED


# ---- Helpers ya consolidados en LiveMixR (VERBATIM — no tocar la firma ni el string) --------
# Standard dialog button box (Close / Ok / Cancel). Was inlined ~18×.
DIALOG_BUTTONS = ("QPushButton{background:#242424;border:1px solid #333;"
                  "border-radius:5px;padding:6px 14px;color:#e8e8e8;}")


def flat(ink):
    """Small flat toolbar button (used by Switcher._flat)."""
    return (f"QPushButton{{background:#242424;border:1px solid #333;"
            f"border-radius:6px;color:{ink};}}"
            f"QPushButton:hover{{background:#2e2e2e;}}")


def pad(color, active, neutral, ink):
    """Bus/pad button. The border is ALWAYS 2px (only its COLOUR changes with state) so a
    pad toggling active↔inactive never changes the widget's SIZE (a style must not resize
    anything — MC THEME_PRIMARY_BUTTON_BORDER). Locked by test_theme.py."""
    if active:
        return (f"QPushButton{{background:{color};border:2px solid {color};"
                f"border-radius:8px;color:#fff;}}")
    return (f"QPushButton{{background:#1e1e1e;border:2px solid {neutral};"
            f"border-radius:8px;color:{ink};}}"
            f"QPushButton:hover{{border-color:#555;}}")


# ---- Base de la FAMILIA (métricas exactas de la referencia; acento por parámetro) ------------
def widget_base():
    """Fondo/color/tipografía base de toda la ventana. Los QLabel van TRANSPARENTES para que no pinten el
    fondo de ventana sobre tarjetas/paneles (el objectName les da su color donde haga falta)."""
    return (f"QWidget{{background:{BG};color:{TEXT};font-size:12px;}}"
            f"QLabel{{background:transparent;}}")


def button(accent):
    """Botón base/secundario CANÓNICO (decidido con Alex, 31 ago 2026, = el de MirroR): fondo CARD, borde
    LINE, radio 8, padding 6×13; hover = BORDE CORAL (solo cambia el color del filo, nunca el grosor →
    invariante). Va a juego con primary() (mismo radio/padding)."""
    return (f"QPushButton{{background:{CARD};color:{TEXT};border:1px solid {LINE};border-radius:8px;"
            f"padding:6px 13px;}}"
            f"QPushButton:hover{{border-color:{accent};}}"
            f"QPushButton:pressed{{background:{CARD_HI};}}"
            f"QPushButton:disabled{{color:{MUTED2};border-color:{LINE_SOFT};background:{PANEL};}}")


def primary(accent, accent2=None):
    """Botón primario/acción CANÓNICO (decidido con Alex, 31 ago 2026, = el de MirroR): coral, TEXTO OSCURO
    #14060a, radio 8, padding 6×13, negrita. CRÍTICO: borde 1px del MISMO grosor que button() — el bug era
    `border:none` aquí (2px más corto → salto de layout); el borde va del color del acento."""
    accent2 = accent2 or accent
    return (f"QPushButton#Primary{{background:{accent};color:{ON_ACCENT};border:1px solid {accent};"
            f"border-radius:8px;padding:6px 13px;font-weight:bold;}}"
            f"QPushButton#Primary:hover{{background:{accent2};border-color:{accent2};}}"
            f"QPushButton#Primary:disabled{{background:#3a2422;color:#8a6a66;border-color:#3a2422;}}")


def ghost(accent):
    """Botón fantasma/secundario (`#Ghost`): transparente, borde LINE, texto atenuado; hover = borde coral +
    texto claro. Ya era unánime en la suite. Mismo radio/padding que el botón base."""
    return (f"QPushButton#Ghost{{background:transparent;color:{MUTED};border:1px solid {LINE};"
            f"border-radius:8px;padding:6px 13px;}}"
            f"QPushButton#Ghost:hover{{border-color:{accent};color:{TEXT};}}")


def combo(accent):
    """QComboBox CANÓNICO (decidido con Alex, 31 ago 2026): fondo INPUT azulado (marca que es un campo),
    radio 8, hover = BORDE CORAL (coherente con todo), flecha propia. Popup: selección con TINTE `#2a1210`
    + TEXTO CORAL (intermedio, ni relleno pleno ni tinte apagado — a juego con el segmentado)."""
    return (f"QComboBox{{background:{INPUT};border:1px solid {LINE};border-radius:8px;padding:5px 10px;color:{TEXT};}}"
            f"QComboBox:hover{{border-color:{accent};}}"
            f"QComboBox:disabled{{color:{MUTED2};border-color:{LINE_SOFT};background:#191a1f;}}"
            f"QComboBox::drop-down{{border:0;width:18px;}}"
            f"QComboBox::down-arrow{{image:none;border-left:4px solid transparent;"
            f"border-right:4px solid transparent;border-top:5px solid {MUTED};margin-right:7px;}}"
            f"QComboBox QAbstractItemView{{background:{PANEL};border:1px solid {LINE};border-radius:8px;"
            f"padding:3px;outline:none;}}"
            f"QComboBox QAbstractItemView::item{{padding:5px 8px;border-radius:5px;}}"
            f"QComboBox QAbstractItemView::item:selected{{background:#22242b;color:{TEXT};}}")


def line_edit(accent):
    """Entradas CANÓNICAS (Alex 31 ago): QLineEdit + numéricos (QSpinBox/QDoubleSpinBox) a juego con el combo
    — fondo INPUT azulado, radio 8, foco = BORDE CORAL. El stepper con valor y `+/−` es el `#Step` aparte."""
    return (f"QLineEdit,QSpinBox,QDoubleSpinBox{{background:{INPUT};border:1px solid {LINE};border-radius:8px;"
            f"padding:5px 10px;color:{TEXT};}}"
            f"QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus{{border-color:{accent};}}"
            f"QLineEdit:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled{{color:{MUTED2};border-color:{LINE_SOFT};background:#191a1f;}}")


def scrollbar():
    """Scrollbar de la casa: 8px, sin flechas, nunca la del sistema (regla de familia).

    ⚠️ La ESQUINA (donde se cruzan la barra vertical y la horizontal) hay que estilarla también: si no, Qt
    pinta ahí el cuadradito NATIVO de macOS — el "resquicio de las barras viejas" que se cuela cuando aparecen
    las dos barras a la vez. `QAbstractScrollArea::corner` transparente lo destierra (detectado en MediaDriveR)."""
    return ("QScrollBar:vertical{background:transparent;width:8px;margin:0;border:none;}"
            "QScrollBar::handle:vertical{background:#3d3e47;border-radius:4px;min-height:24px;}"
            "QScrollBar::handle:vertical:hover{background:#55565e;}"
            "QScrollBar:horizontal{background:transparent;height:8px;margin:0;border:none;}"
            "QScrollBar::handle:horizontal{background:#3d3e47;border-radius:4px;min-width:24px;}"
            "QScrollBar::handle:horizontal:hover{background:#55565e;}"
            "QScrollBar::add-line,QScrollBar::sub-line{background:none;border:none;width:0;height:0;}"
            "QScrollBar::add-page,QScrollBar::sub-page{background:transparent;}"
            "QAbstractScrollArea::corner{background:transparent;border:none;}")


def slider(accent, accent2=None):
    """Slider de la familia (volúmenes/faders): barra FINA de 3px + relleno del acento + tirador
    coral CIRCULAR. Decisión de Alex (31 ago): la barra fina calma el acento; el tirador redondo se
    queda vivo. Opt-in (lo añaden las apps que tienen sliders): setStyleSheet(... + theme.slider(ACC, ACC2))."""
    accent2 = accent2 or accent
    # Tirador = MARCA FINA perpendicular (estilo fader, lee como instrumento de precisión, coherente con la
    # suite A/V). Barra vertical coral 4×16 con radius 2, margin -7 para centrarla sobre el groove de 3px.
    return (f"QSlider::groove:horizontal{{background:{INPUT};height:3px;border-radius:2px;}}"
            f"QSlider::sub-page:horizontal{{background:{accent};height:3px;border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{accent};width:4px;height:16px;margin:-7px 0;border-radius:2px;}}"
            f"QSlider::handle:horizontal:hover{{background:{accent2};}}"
            f"QSlider::handle:horizontal:disabled{{background:{LINE};}}"
            f"QSlider::sub-page:horizontal:disabled{{background:{LINE};}}")


def chip(accent):
    """Chip de ETIQUETA (`#Chip` de etiqueta / ex #FmtChip): mono, pulsable, para formato/carpeta.
    Canónico (Alex 31 ago): transparente, borde LINE, radio 7, texto atenuado; hover = borde coral + texto."""
    return (f'QPushButton#Chip{{background:transparent;border:1px solid {LINE};border-radius:7px;'
            f'color:{MUTED};font-family:Menlo,"SF Mono",ui-monospace,monospace;font-size:11px;padding:5px 10px;}}'
            f'QPushButton#Chip:hover{{border-color:{accent};color:{TEXT};}}')


def filter_chip(accent):
    """Chip de FILTRO con estado (`#FilterChip`): pastilla checkable con TONO semántico. Canónico
    (Alex 31 ago): radio 7 (antes 11), fondo INPUT; al marcarse se enciende en su tono —
    tone="hi"→coral (actuar), "mid"→ámbar, "lo"→verde, "off"/"txt"→neutro. La app pone la prop `tone`."""
    return (f'QPushButton#FilterChip{{background:{INPUT};border:1px solid {LINE};border-radius:7px;'
            f'color:{MUTED2};font-size:11px;font-weight:600;padding:4px 12px;}}'
            f'QPushButton#FilterChip:hover{{border-color:{accent};color:{TEXT};}}'
            f'QPushButton#FilterChip[tone="hi"]:checked{{color:{accent};border-color:{accent};}}'
            f'QPushButton#FilterChip[tone="mid"]:checked{{color:{SIG_MID};border-color:{SIG_MID};}}'
            f'QPushButton#FilterChip[tone="lo"]:checked{{color:{SIG_LO};border-color:{SIG_LO};}}'
            f'QPushButton#FilterChip[tone="off"]:checked{{color:{MUTED};border-color:{LINE};background:{CARD_HI};}}'
            f'QPushButton#FilterChip[tone="txt"]:checked{{color:{TEXT};border-color:#6b7385;background:{CARD_HI};}}')


def segmented(accent, accent2=None):
    """Control SEGMENTADO / selector de modo (`#Seg`), toggle exclusivo (Video/Audio, Cast/AirPlay…).
    Canónico (Alex 31 ago, estilo B = VideoCatchR): sin marcar = fondo INPUT + borde LINE + atenuado;
    MARCADO = tinte coral `#2a1210` + borde y texto coral. El tinte es de la familia coral."""
    accent2 = accent2 or accent
    return (f"QPushButton#Seg{{background:{INPUT};border:1px solid {LINE};border-radius:8px;"
            f"color:{MUTED};font-size:12px;font-weight:600;padding:7px 14px;}}"
            f"QPushButton#Seg:hover{{border-color:#4a5162;color:{TEXT};}}"
            f"QPushButton#Seg:checked{{background:#2a1210;border-color:{accent};color:{accent2};}}")


def small_buttons(accent):
    """Botones utilitarios pequeños (Alex 31 ago): TODOS radio 7 y hover = borde + símbolo coral (unánime).
    El glifo se empuja 2px hacia arriba (`padding-bottom:2`) para centrarlo ópticamente en el cuadrado.
    ⚠️ El empuje va afinado a la fuente del Mac; reverificar en Windows (Segoe UI).
    - `#Step` (+/−) y `#Plus`: cuadrado con fondo CARD.
    - `#IconBtn`: transparente, para iconos y cerrar (la app pone el glifo, p.ej. `×` a 16px)."""
    up = "padding:0 0 2px 0;"
    return (f"QPushButton#Step{{background:{CARD};border:1px solid {LINE};border-radius:7px;color:{TEXT};"
            f"font-size:14px;font-weight:bold;min-width:22px;max-width:22px;min-height:22px;{up}}}"
            f"QPushButton#Step:hover{{border-color:{accent};color:{accent};}}"
            f"QPushButton#Step:disabled{{color:{MUTED2};border-color:{LINE_SOFT};}}"
            f"QPushButton#Plus{{background:{CARD};border:1px solid {LINE};border-radius:7px;color:{MUTED};"
            f"font-size:15px;min-width:28px;max-width:28px;min-height:28px;{up}}}"
            f"QPushButton#Plus:hover{{border-color:{accent};color:{accent};}}"
            f"QPushButton#IconBtn{{background:transparent;border:1px solid {LINE};border-radius:7px;"
            f"color:{MUTED2};font-size:16px;min-width:28px;max-width:28px;min-height:28px;{up}}}"
            f"QPushButton#IconBtn:hover{{border-color:{accent};color:{accent};}}")


def checkbox(accent):
    """Checkbox CANÓNICO (Alex 31 ago): indicador 12px, radio 3 (cuadrado redondeado), marcado = relleno
    coral; hover = borde coral. (Bajado de 14→12px el 1 sep: al lado de un puntito de estado se veía pesado.)

    ⚠️ min-height:20px OBLIGATORIO: con el indicador estilado, QWidgetItem calcula mal el alto del QCheckBox
    (dice 8px aunque se dibuje a ~15) y las casillas APILADAS en columna se solapan entre sí y con su texto.
    `setMinimumHeight` en el widget NO lo corrige; el min-height en el QSS sí. (Lo acorraló la sesión de
    MirroR el 1 sep; afecta a cualquier app con casillas en columna.)"""
    return (f"QCheckBox{{background:transparent;spacing:8px;color:{TEXT};min-height:20px;}}"
            f"QCheckBox::indicator{{width:12px;height:12px;border:1px solid {LINE};border-radius:3px;background:{INPUT};}}"
            f"QCheckBox::indicator:hover{{border-color:{accent};}}"
            f"QCheckBox::indicator:checked{{background:{accent};border-color:{accent};}}"
            f"QCheckBox::indicator:disabled{{border-color:{LINE_SOFT};background:#191a1f;}}")


def radio(accent):
    """Radio CANÓNICO (Alex 31 ago): indicador 14px, radio 7 (CÍRCULO). Marcado = ANILLO + PUNTITO coral
    (clásico, radial-gradient: coral dentro, hueco, borde coral) → se diferencia del checkbox, que se
    rellena entero. Hover = borde coral."""
    return (f"QRadioButton{{background:transparent;spacing:8px;color:{TEXT};}}"
            f"QRadioButton::indicator{{width:12px;height:12px;border:1px solid {LINE};border-radius:6px;background:{INPUT};}}"
            f"QRadioButton::indicator:hover{{border-color:{accent};}}"
            f"QRadioButton::indicator:checked{{border:1px solid {accent};"
            f"background:qradialgradient(cx:0.5,cy:0.5,radius:0.5,fx:0.5,fy:0.5,"
            f"stop:0 {accent},stop:0.5 {accent},stop:0.55 {INPUT},stop:1 {INPUT});}}"
            f"QRadioButton::indicator:disabled{{border-color:{LINE_SOFT};background:#191a1f;}}")


def card(accent):
    """Tarjeta/contenedor CANÓNICO (Alex 31 ago): `#Card` fondo CARD, borde sutil LINE_SOFT, radio 12 (sube
    respecto a los botones r8 → jerarquía). Hover: el borde sube a LINE. SELECCIONADA (`[sel="on"]`) = borde
    CORAL + tinte `#241413`; el borde se queda en 1px (mismo grosor que sin seleccionar) para no mover el
    layout — se lee igual de encendida. `[dim="true"]` la atenúa a PANEL."""
    return (f"QFrame#Card{{background:{CARD};border:1px solid {LINE_SOFT};border-radius:12px;}}"
            f"QFrame#Card:hover{{border-color:{LINE};}}"
            f'QFrame#Card[dim="true"]{{background:{PANEL};}}'
            f'QFrame#Card[sel="on"]{{border-color:{accent};background:#241413;}}')


def divider():
    """Separador de la casa (`#Divider`): 1px de LINE_SOFT, sin borde. Unánime en la suite."""
    return (f"QFrame#Divider{{background:{LINE_SOFT};max-height:1px;min-height:1px;border:none;}}")


def panel(accent=None):
    """Panel/contenedor secundario (`#Panel`): fondo PANEL, borde LINE, radio 8 (más apretado que la tarjeta)."""
    return (f"QFrame#Panel{{background:{PANEL};border:1px solid {LINE};border-radius:8px;}}")


def list_table(accent):
    """Listas / árboles / tablas + cabecera. Canónico (Alex 31 ago): contenedor fondo PANEL, borde LINE_SOFT,
    radio 8; ítems con esquinas r6, hover CARD, SELECCIONADO = tinte `#2a1210` + texto coral (mismo lenguaje
    que el popup del combo). Cabecera discreta con línea inferior. La scrollbar FINA de la casa entra por
    base_qss (la de MirroR/PostHandleR, 8px sin flechas) — nunca la del sistema."""
    return (f"QListWidget,QTreeWidget,QTreeView,QListView,QTableWidget{{background:{PANEL};"
            f"border:1px solid {LINE_SOFT};border-radius:8px;padding:3px;color:{TEXT};outline:none;}}"
            f"QListWidget::item,QTreeWidget::item,QTreeView::item,QListView::item{{padding:6px 8px;border-radius:6px;}}"
            f"QListWidget::item:hover,QTreeWidget::item:hover,QTreeView::item:hover,QListView::item:hover{{background:#22242b;}}"
            f"QListWidget::item:selected,QTreeWidget::item:selected,QTreeView::item:selected,"
            f"QListView::item:selected{{color:{accent};background:transparent;}}"
            f"QTableWidget::item{{padding:5px 8px;}}"
            f"QTableWidget::item:selected{{color:{accent};background:transparent;}}"
            f"QHeaderView::section{{background:{PANEL};border:none;border-bottom:1px solid {LINE};"
            f"padding:6px 8px;color:{MUTED};font-weight:600;}}"
            f"QTableCornerButton::section{{background:{PANEL};border:none;}}"
            f"QTreeWidget::branch,QTreeView::branch{{background:transparent;border-image:none;}}")


def labels():
    """Roles de texto de la casa (jerarquía tipográfica). El objectName marca el rol:
    #Title (grande, negrita), #Section (mayúsculas atenuadas), #Sub/#Hint (secundario), #Mono (datos), #Caption."""
    return (f"QLabel#Title{{font-size:16px;font-weight:bold;letter-spacing:0.3px;}}"
            f"QLabel#Section{{color:{MUTED2};font-size:10px;text-transform:uppercase;font-weight:bold;letter-spacing:0.6px;}}"
            f"QLabel#Sub,QLabel#Hint{{color:{MUTED};font-size:11px;}}"
            f'QLabel#Mono{{font-family:Menlo,"SF Mono",ui-monospace,monospace;color:{MUTED};}}'
            f"QLabel#Caption{{color:{MUTED2};font-size:10px;}}")


def pill():
    """Pill de estado (`#Pill`): badge redondeado con tinte del color de estado + texto del mismo color.
    Estados por propiedad `state`: active=coral, done=verde, error=rojo, pending/neutro=gris (colores de señal)."""
    return (f"QLabel#Pill{{border-radius:9px;padding:3px 10px;font-size:10px;font-weight:600;"
            f"background:#212225;color:{MUTED};}}"
            f'QLabel#Pill[state="active"]{{background:#3a1a16;color:#ff8a7d;}}'
            f'QLabel#Pill[state="error"]{{background:#3a1a16;color:#ff8a7d;}}'
            f'QLabel#Pill[state="done"]{{background:#16241a;color:#7fd68e;}}'
            f'QLabel#Pill[state="warn"]{{background:#2e2612;color:#e6c06a;}}'
            f'QLabel#Pill[state="info"]{{background:#132535;color:#7fb8ff;}}'
            f'QLabel#Pill[state="pending"]{{background:#212225;color:{MUTED2};}}')


def progress(accent):
    """Barra de progreso CANÓNICA (Alex 31 ago): pista INPUT sin borde, FINA 4px (r2), relleno coral. Estados
    por propiedad `state`: done = verde de señal, error = rojo. Colores de señal de la casa."""
    return (f"QProgressBar{{background:{INPUT};border:none;border-radius:2px;max-height:4px;min-height:4px;"
            f"text-align:center;color:transparent;}}"
            f"QProgressBar::chunk{{background:{accent};border-radius:2px;}}"
            f'QProgressBar[state="done"]::chunk{{background:{SIG_LO};}}'
            f'QProgressBar[state="error"]::chunk{{background:#5a2a26;}}')


def overlays(accent):
    """Menú / tooltip / diálogo. Canónico (Alex 31 ago): MENÚ = un solo contorno grande, dentro SOLO texto;
    el ítem resaltado es una FRANJA gris a todo el ancho (sin caja ni línea por opción); la elección activa
    (`:checked`) va en texto coral. Tooltip = PANEL con borde fino. Diálogo = solo fondo PANEL, SIN borde
    (es una ventana; el recuadro con línea sobraba)."""
    return (f"QMenuBar{{background:{BG};}}"
            f"QMenuBar::item{{padding:4px 10px;background:transparent;}}"
            f"QMenuBar::item:selected{{background:{CARD};border-radius:6px;}}"
            f"QMenu{{background:{PANEL};border:1px solid {LINE_SOFT};border-radius:8px;padding:6px 0;}}"
            f"QMenu::item{{padding:7px 18px;background:transparent;color:{TEXT};}}"
            f"QMenu::item:selected{{background:#22242b;color:{TEXT};}}"
            f"QMenu::item:checked{{color:{accent};}}"
            f"QMenu::separator{{height:1px;background:{LINE_SOFT};margin:5px 10px;}}"
            f"QToolTip{{background:{PANEL};color:{TEXT};border:1px solid {LINE};border-radius:6px;padding:5px 8px;}}"
            f"QDialog{{background:{PANEL};}}")


def window():
    """Cromo de ventana propia (sin marco del sistema). Canónico (Alex 31 ago): barra de título (`#Titlebar`)
    y de estado (`#Statusbar`) en fondo PANEL, SIN línea divisoria — se distinguen del cuerpo solo por el TONO
    (PANEL algo más claro que BG). SIN grip de arrastre ni de tamaño: la barra entera arrastra y el SO
    redimensiona por los bordes. La barra oscura de Windows la pone `win_titlebar` (módulo compartido)."""
    return (f"#Titlebar{{background:{PANEL};border:none;}}"
            f"#Statusbar{{background:{PANEL};border:none;color:{MUTED};}}"
            f'#Statusbar QLabel{{color:{MUTED};font-family:Menlo,"SF Mono",ui-monospace,monospace;font-size:11px;}}')


def base_qss(accent, accent2=None):
    """El look COMÚN de la familia en un string: fondo, botones, #Primary, combo, input, checkbox, radio y
    scrollbar. Uso: setStyleSheet(theme.base_qss(ACCENT, ACCENT_2) + tus_extras_propios)."""
    return "\n".join([widget_base(), button(accent), primary(accent, accent2),
                      combo(accent), line_edit(accent), checkbox(accent), radio(accent), scrollbar()])


def full_qss(accent, accent2=None):
    """TODO el sistema de la casa en UNA llamada — el atajo para el rollout. Junta base_qss + los helpers que
    faltan (slider, listas/tablas, overlays, tarjeta, panel, divider, progreso, labels, pill, utilitarios,
    chips, segmentado, ventana). Adopción por app en una línea:
        setStyleSheet(theme.full_qss(ACCENT, ACCENT_2) + tus_widgets_UNICOS)
    Los helpers por objectName (#Chip, #Seg, #Card, #Pill, #Titlebar…) son INERTES si la app no usa ese nombre,
    así que incluirlos todos no molesta. Para caer del todo en la familia, alinea tus objectName a los
    canónicos (#Primary, #Chip, #Seg, #Card, #Pill, #Titlebar, #Statusbar) y borra tu estilo inline duplicado."""
    return "\n".join([
        base_qss(accent, accent2), ghost(accent), slider(accent, accent2), list_table(accent), overlays(accent),
        card(accent), panel(), divider(), progress(accent), labels(), pill(),
        small_buttons(accent), chip(accent), filter_chip(accent), segmented(accent, accent2), window(),
    ])
