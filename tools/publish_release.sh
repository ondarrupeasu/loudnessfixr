#!/bin/bash
# Publica dist/LoudnessFixR.app como release en el repo PÚBLICO de binarios, para el auto-updater.
# Uso:  bash tools/publish_release.sh ["notas de la versión"]
# El BUILD se toma de version.__build__ (súbelo ahí antes de publicar).
# Env opcional MIN_VERSION="2026-08-05a" → mete un "suelo" (kill-switch) en latest.json: las apps por
# debajo de ese build se consideran caducadas y deben actualizar. (Solo cuando quieras retirar versiones.)
set -e
PROJ="$(cd "$(dirname "$0")/.." && pwd)"; cd "$PROJ"
REPO="ondarrupeasu/loudnessfixr-releases"
APP="LoudnessFixR"
BUILD="$(./venv/bin/python -c 'import version; print(version.__build__)')"
NOTES="${1:-Build $BUILD}"
OUT="$PROJ/dist"

[ -d "dist/$APP.app" ] || { echo "No hay dist/$APP.app — construye antes con PyInstaller."; exit 1; }

# --- FIRMA (clave ÚNICA de la suite; privada SOLO local, nunca en git/CI) ---
KEYFILE="${CF_UPDATER_PRIVKEY:-$HOME/.cinemafilmak/updater_ed25519.key}"
[ -f "$KEYFILE" ] || { echo "Falta la clave de firma ($KEYFILE). NO publico sin firmar."; exit 1; }
sign() {  # $1 = mensaje  ->  firma base64
  ./venv/bin/python - "$KEYFILE" "$1" <<'PY'
import sys, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
k = Ed25519PrivateKey.from_private_bytes(base64.b64decode(open(sys.argv[1]).read().strip()))
print(base64.b64encode(k.sign(sys.argv[2].encode())).decode())
PY
}

echo "Empaquetando $BUILD (zip con permisos, vía ditto)…"
rm -f "$OUT/$APP.zip" "$OUT/latest.json"
ditto -c -k --sequesterRsrc --keepParent "dist/$APP.app" "$OUT/$APP.zip"
ZIP_SHA="$(shasum -a 256 "$OUT/$APP.zip" | awk '{print $1}')"
ZIP_SIG="$(sign "$APP|$BUILD|mac|$ZIP_SHA")"

MINJSON=""
[ -n "$MIN_VERSION" ] && MINJSON=", \"min_version\": \"$MIN_VERSION\""

cat > "$OUT/latest.json" <<JSON
{"build": "$BUILD", "zip": "https://github.com/$REPO/releases/latest/download/$APP.zip", "sha256": "$ZIP_SHA", "sig": "$ZIP_SIG"$MINJSON, "notes": "$NOTES"}
JSON

echo "Publicando release $BUILD en $REPO…"
if gh release view "$BUILD" --repo "$REPO" >/dev/null 2>&1; then
    gh release upload "$BUILD" --repo "$REPO" --clobber "$OUT/$APP.zip" "$OUT/latest.json"
else
    gh release create "$BUILD" --repo "$REPO" --title "$BUILD" --notes "$NOTES" "$OUT/$APP.zip" "$OUT/latest.json"
fi
gh release edit "$BUILD" --repo "$REPO" --latest >/dev/null
echo "✅ Publicado. 'latest' ahora apunta a $BUILD."
