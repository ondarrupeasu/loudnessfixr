#!/bin/bash
# Publica dist/LoudnessFixR.app como release en el repo PÚBLICO de binarios, para el auto-updater.
# Uso:  bash tools/publish_release.sh ["notas de la versión"]
# El BUILD se toma de version.__build__ (súbelo ahí antes de publicar).
# Env opcional MIN_VERSION="2026-08-05a" → mete un "suelo" (kill-switch) en latest.json: las apps por
# debajo de ese build se consideran caducadas y deben actualizar. (Solo cuando quieras retirar versiones.)
set -e
PROJ="$(cd "$(dirname "$0")/.." && pwd)"; cd "$PROJ"
REPO="ondarrupeasu/loudnessfixr-releases"
SRC_REPO="ondarrupeasu/loudnessfixr"   # repo fuente (de ahí bajamos el .exe de Windows que compiló CI)
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

# Windows: bajar el .exe (onefile) que compiló GitHub Actions para ESTE build, como ARTIFACT del repo
# fuente. Si no hay artifact (¿CI en curso, o build no coincide?), se publica solo Mac y se avisa.
EXE_JSON=""
rm -f "$OUT/$APP.exe"
WINDIR="$OUT/win-artifact"; rm -rf "$WINDIR"; mkdir -p "$WINDIR"
echo "Buscando el .exe de Windows (artifact LoudnessFixR-Windows-$BUILD en $SRC_REPO)…"
if gh run download --repo "$SRC_REPO" -n "$APP-Windows-$BUILD" -D "$WINDIR" 2>/dev/null; then
    EXE="$(/usr/bin/find "$WINDIR" -name "$APP.exe" | head -1)"
    if [ -n "$EXE" ] && [ -f "$EXE" ]; then
        cp "$EXE" "$OUT/$APP.exe"
        EXE_SHA="$(shasum -a 256 "$OUT/$APP.exe" | awk '{print $1}')"
        EXE_SIG="$(sign "$APP|$BUILD|win|$EXE_SHA")"
        EXE_JSON=", \"exe_win\": \"https://github.com/$REPO/releases/latest/download/$APP.exe\", \"sha256_win\": \"$EXE_SHA\", \"sig_win\": \"$EXE_SIG\""
        echo "  ✓ .exe de Windows listo (sha256 $EXE_SHA, firmado)."
    fi
fi
[ -z "$EXE_JSON" ] && echo "  ⚠️  Sin .exe de Windows para $BUILD (¿CI en curso?). Publico solo Mac por ahora."

MINJSON=""
[ -n "$MIN_VERSION" ] && MINJSON=", \"min_version\": \"$MIN_VERSION\""

cat > "$OUT/latest.json" <<JSON
{"build": "$BUILD", "zip": "https://github.com/$REPO/releases/latest/download/$APP.zip", "sha256": "$ZIP_SHA", "sig": "$ZIP_SIG"$EXE_JSON$MINJSON, "notes": "$NOTES"}
JSON

ASSETS="$OUT/$APP.zip $OUT/latest.json"
[ -f "$OUT/$APP.exe" ] && ASSETS="$ASSETS $OUT/$APP.exe"

echo "Publicando release $BUILD en $REPO…"
if gh release view "$BUILD" --repo "$REPO" >/dev/null 2>&1; then
    gh release upload "$BUILD" --repo "$REPO" --clobber $ASSETS
else
    gh release create "$BUILD" --repo "$REPO" --title "$BUILD" --notes "$NOTES" $ASSETS
fi
gh release edit "$BUILD" --repo "$REPO" --latest >/dev/null
echo "✅ Publicado. 'latest' ahora apunta a $BUILD."
