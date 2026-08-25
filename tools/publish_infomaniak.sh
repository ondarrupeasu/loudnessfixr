#!/bin/bash
# Publica esta app FIRMADA en apps.cinemafilmak.com, en LAS DOS zonas de una pasada:
#   /update/<slug>/  → auto-updater (latest.json firmado + payloads)
#   /dl/<slug>/      → catálogo de descarga humano
# Un solo comando = release consistente. Uso:  bash tools/publish_infomaniak.sh ["notas"]
# Requiere (FUERA del repo): ~/.cinemafilmak/infomaniak_apps_ftp.env  +  ~/.cinemafilmak/updater_ed25519.key
# Estructura idéntica en todas las apps: SOLO cambia el bloque CONFIG. Ver missioncontrol/RELEASE.md.
set -e
# ── CONFIG (lo único que cambia por app) ──────────────────────────────────────
APP="LoudnessFixR"
SLUG="loudnessfixr"
PY="venv/bin/python"                                  # intérprete con 'cryptography' (venv de la app)
BUILD_CMD="import version; print(version.__build__)"  # cómo leer __build__
WIN_SRC_REPO="ondarrupeasu/loudnessfixr"              # repo con windows-build.yml; VACÍO = sin Windows
# ──────────────────────────────────────────────────────────────────────────────
PROJ="$(cd "$(dirname "$0")/.." && pwd)"; cd "$PROJ"
BUILD="$($PY -c "$BUILD_CMD")"
NOTES="${1:-Build $BUILD}"
OUT="$PROJ/dist"; BASEURL="https://apps.cinemafilmak.com/update/$SLUG"

[ -d "dist/$APP.app" ] || { echo "No hay dist/$APP.app — construye antes."; exit 1; }
ENVF="$HOME/.cinemafilmak/infomaniak_apps_ftp.env"
[ -f "$ENVF" ] || { echo "Falta $ENVF (credenciales FTPS)."; exit 1; }
set -a; . "$ENVF"; set +a
KEYFILE="${CF_UPDATER_PRIVKEY:-$HOME/.cinemafilmak/updater_ed25519.key}"
[ -f "$KEYFILE" ] || { echo "Falta la clave privada de firma ($KEYFILE). NO publico sin firmar."; exit 1; }

sign() {  # $1 = mensaje -> firma base64
  $PY - "$KEYFILE" "$1" <<'PY'
import sys, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
k = Ed25519PrivateKey.from_private_bytes(base64.b64decode(open(sys.argv[1]).read().strip()))
print(base64.b64encode(k.sign(sys.argv[2].encode())).decode())
PY
}
upload() {  # $1 local, $2 ruta remota -> código HTTP
  curl -s --ssl-reqd --ftp-create-dirs -T "$1" --user "$FTP_USER:$FTP_PASS" "ftp://$FTP_HOST/$2" -o /dev/null -w "%{http_code}"
}

echo "Verificando el bundle antes de empaquetar…"
bash "$PROJ/tools/verificar_bundle.sh" "dist/$APP.app" || { echo "❌ NO publico: el bundle no es válido."; exit 1; }

echo "Empaquetando Mac $BUILD (ditto)…"
rm -f "$OUT/$APP.zip" "$OUT/latest.json"
ditto -c -k --sequesterRsrc --keepParent "dist/$APP.app" "$OUT/$APP.zip"
ZIP_SHA="$(shasum -a 256 "$OUT/$APP.zip" | awk '{print $1}')"
ZIP_SIG="$(sign "$APP|$BUILD|mac|$ZIP_SHA")"

# Windows: baja el .exe (onefile) que compiló CI para ESTE build (artifact), re-firma y re-hospeda.
EXE_JSON=""
if [ -n "$WIN_SRC_REPO" ]; then
  WINDIR="$OUT/win-artifact"; rm -rf "$WINDIR"; mkdir -p "$WINDIR"
  if gh run download --repo "$WIN_SRC_REPO" -n "$APP-Windows-$BUILD" -D "$WINDIR" 2>/dev/null; then
    EXE="$(/usr/bin/find "$WINDIR" -name "$APP.exe" | head -1)"
    if [ -n "$EXE" ] && [ -f "$EXE" ]; then
      cp "$EXE" "$OUT/$APP.exe"
      EXE_SHA="$(shasum -a 256 "$OUT/$APP.exe" | awk '{print $1}')"
      EXE_SIG="$(sign "$APP|$BUILD|win|$EXE_SHA")"
      echo "  Win .exe    → /update $(upload "$OUT/$APP.exe" "update/$SLUG/$APP.exe")  /dl $(upload "$OUT/$APP.exe" "dl/$SLUG/$APP.exe")"
      EXE_JSON=", \"exe_win\": \"$BASEURL/$APP.exe\", \"sha256_win\": \"$EXE_SHA\", \"sig_win\": \"$EXE_SIG\""
    fi
  else
    echo "  ⚠️  sin artifact de Windows para $BUILD (¿CI en curso o falló?). Publico solo Mac."
  fi
fi

cat > "$OUT/latest.json" <<JSON
{"build": "$BUILD", "zip": "$BASEURL/$APP.zip", "sha256": "$ZIP_SHA", "sig": "$ZIP_SIG"$EXE_JSON, "notes": "$NOTES"}
JSON

echo "  Mac .zip    → /update $(upload "$OUT/$APP.zip" "update/$SLUG/$APP.zip")  /dl $(upload "$OUT/$APP.zip" "dl/$SLUG/$APP.zip")"
echo "  latest.json → /update $(upload "$OUT/latest.json" "update/$SLUG/latest.json")"
echo "✅ Publicado $APP $BUILD (firmado) en /update/ y /dl/."
