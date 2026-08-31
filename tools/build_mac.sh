#!/bin/bash
# Construye LoudnessFixR.app con dist/ LIMPIO. Desde la raíz del repo:  tools/build_mac.sh
#
# El `rm -rf build dist` ANTES de compilar es lo que hace IMPOSIBLE publicar un binario viejo: sin él, si te
# saltas el build (o falla), el `.app` de la vez anterior sobrevive en dist/ y `publish_infomaniak.sh` lo
# empaqueta con el manifiesto NUEVO → el launcher instala, la app se reporta vieja y ofrece update en bucle.
# (Ver missioncontrol/briefs/PUBLISH_STALE_BINARY.md.)
set -euo pipefail
cd "$(dirname "$0")/.."
# `venv/bin/python -m …` en vez de los wrappers pip/pyinstaller (evita shebangs viejos tras renames).
[ -d venv ] || { python3 -m venv venv; venv/bin/python -m pip install -q -r requirements.txt; }
venv/bin/python -m pip install -q pyinstaller
rm -rf build dist
venv/bin/python -m PyInstaller --noconfirm LoudnessFixR.spec
# Re-firma ad-hoc: PyInstaller a veces deja el sello inválido ("a sealed resource is missing or invalid") y
# el gate de publicación (verificar_bundle.sh) lo rechaza. --force --deep re-sella el bundle entero.
codesign --force --deep -s - "dist/LoudnessFixR.app"
echo
du -sh "dist/LoudnessFixR.app"
echo "Listo: dist/LoudnessFixR.app  ·  Publicar: bash tools/publish_infomaniak.sh \"notas del build\""
