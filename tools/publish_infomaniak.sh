#!/bin/bash
# Publica LoudnessFixR firmada en apps.cinemafilmak.com, en /update/loudnessfixr/ y /dl/loudnessfixr/.
# Uso:  bash tools/publish_infomaniak.sh ["notas"]
# Requiere (FUERA del repo): ~/.cinemafilmak/infomaniak_apps_ftp.env + ~/.cinemafilmak/updater_ed25519.key
# ⚠️ El CUERPO es COMPARTIDO: tools/publish_body.sh (vendorizado desde missioncontrol/shared con
#    sync_updater.sh). Aquí SOLO va el bloque CONFIG. No edites el cuerpo por app.
set -e
# ── CONFIG ────────────────────────────────────────────────────────────────────
APP="LoudnessFixR"
SLUG="loudnessfixr"
PY="venv/bin/python"
BUILD_CMD="import version; print(version.__build__)"
WIN_SRC_REPO="ondarrupeasu/loudnessfixr"
# ──────────────────────────────────────────────────────────────────────────────
. "$(dirname "$0")/publish_body.sh" "$@"
