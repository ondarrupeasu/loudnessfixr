# shellcheck shell=bash
# CUERPO COMPARTIDO del publish de la suite CinemaFilmak — NO editar por app, se vendoriza desde
# missioncontrol/shared/ con sync_updater.sh (como updater_core.py o verificar_bundle.sh).
#
# El wrapper por app (tools/publish_infomaniak.sh) fija el bloque CONFIG y hace:
#     . "$(dirname "$0")/publish_body.sh"
# CONFIG que espera (variables ya puestas por el wrapper):
#   APP          nombre del bundle .app Y de la cadena firmada  (p.ej. "MediaCastR")
#   SLUG         slug en el portal /update/<slug>/ y /dl/<slug>/ (p.ej. "mediacastr")
#   PY           intérprete con 'cryptography' (p.ej. ".venv/bin/python")
#   BUILD_CMD    cómo leer __build__ (p.ej. "import mediacastr; print(mediacastr.__build__)")
#   WIN_SRC_REPO repo con windows-build.yml; VACÍO = app solo-Mac
#   FILE         (opcional) nombre de los FICHEROS hospedados si difiere de APP (launchr: sin espacios)
#
# Origen canónico: launchr (build 2026-08-25k), que estrenó auto-dispatch + verificación de lo servido.
# Historia: MediaCastR 25a (subida FTP fallida en silencio → manifiesto apuntando al .exe viejo) y el
# bloqueo de Actions del 25 ago (build en cada push llenó los 500 MB de la cuenta).

FILE="${FILE:-$APP}"                 # apps normales: el fichero se llama como la app; launchr override
PROJ="$(cd "$(dirname "$0")/.." && pwd)"; cd "$PROJ"
BUILD="$($PY -c "$BUILD_CMD")"
NOTES="${1:-Build $BUILD}"
OUT="$PROJ/dist"; BASEURL="https://apps.cinemafilmak.com/update/$SLUG"

[ -d "dist/$APP.app" ] || { echo "No hay 'dist/$APP.app' — constrúyelo antes (pyinstaller tu .spec)."; exit 1; }
ENVF="$HOME/.cinemafilmak/infomaniak_apps_ftp.env"
[ -f "$ENVF" ] || { echo "Falta $ENVF (credenciales FTPS)."; exit 1; }
set -a; . "$ENVF"; set +a
KEYFILE="${CF_UPDATER_PRIVKEY:-$HOME/.cinemafilmak/updater_ed25519.key}"
[ -f "$KEYFILE" ] || { echo "Falta la clave privada de firma ($KEYFILE). NO publico sin firmar."; exit 1; }

sign() {  # $1 = mensaje -> firma base64. OJO: la cadena firma con $APP, NUNCA con $FILE
  $PY - "$KEYFILE" "$1" <<'PY'
import sys, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
k = Ed25519PrivateKey.from_private_bytes(base64.b64decode(open(sys.argv[1]).read().strip()))
print(base64.b64encode(k.sign(sys.argv[2].encode())).decode())
PY
}
upload() {  # $1 local, $2 ruta remota -> código de la transferencia (2xx = subido)
  # Reintenta: Infomaniak devuelve a veces un código vacío y deja el fichero VIEJO o a medias.
  local code=""
  for intento in 1 2 3; do
    code="$(curl -s --ssl-reqd --ftp-create-dirs -T "$1" --user "$FTP_USER:$FTP_PASS" "ftp://$FTP_HOST/$2" -o /dev/null -w "%{http_code}")"
    case "$code" in 2*) echo "$code"; return 0;; esac
    sleep 2
  done
  echo "${code:-sin-respuesta}"
  return 1
}
servido_ok() {  # $1 ruta remota, $2 sha esperado -> 0 si lo que SIRVE la web coincide (cache-buster)
  local real
  real="$(curl -s "https://apps.cinemafilmak.com/$1?x=$$" | shasum -a 256 | awk '{print $1}')"
  [ "$real" = "$2" ]
}

# Puerta obligatoria: un .app con enlaces rotos se instala DAÑADO en cualquier otro equipo — y el hub
# se niega a instalarlo. (MediaCastR 2026-08-22d, MirroR 2026-08-25f.)
echo "Verificando el bundle antes de empaquetar…"
bash "$PROJ/tools/verificar_bundle.sh" "dist/$APP.app" || { echo "❌ NO publico: el bundle no es válido."; exit 1; }

echo "Empaquetando Mac $BUILD (ditto)…"
rm -f "$OUT/$FILE.zip" "$OUT/latest.json"
ditto -c -k --sequesterRsrc --keepParent "dist/$APP.app" "$OUT/$FILE.zip"
ZIP_SHA="$(shasum -a 256 "$OUT/$FILE.zip" | awk '{print $1}')"
ZIP_SIG="$(sign "$APP|$BUILD|mac|$ZIP_SHA")"

# Windows: baja el .exe que compiló CI para ESTE build (artifact), lo firma y lo hospeda.
EXE_JSON=""
if [ -n "$WIN_SRC_REPO" ]; then
  WINDIR="$OUT/win-artifact"; rm -rf "$WINDIR"; mkdir -p "$WINDIR"
  # Ya NO se compila en cada push (llenaba el almacenamiento de Actions de TODA la cuenta): si no hay
  # .exe para este build, se pide ahora (workflow_dispatch) y se espera. Único momento en que hace falta.
  if ! gh run download --repo "$WIN_SRC_REPO" -n "$FILE-Windows-$BUILD" -D "$WINDIR" 2>/dev/null; then
    echo "  No hay .exe para $BUILD: lanzando el build de Windows…"
    if gh workflow run windows-build.yml --repo "$WIN_SRC_REPO" >/dev/null 2>&1; then
      for _ in $(seq 1 30); do
        sleep 20
        gh run download --repo "$WIN_SRC_REPO" -n "$FILE-Windows-$BUILD" -D "$WINDIR" 2>/dev/null && break
      done
    fi
  fi
  if [ -n "$(ls -A "$WINDIR" 2>/dev/null)" ]; then
    EXE="$(/usr/bin/find "$WINDIR" -name "$FILE.exe" | head -1)"
    if [ -n "$EXE" ] && [ -f "$EXE" ]; then
      cp "$EXE" "$OUT/$FILE.exe"
      EXE_SHA="$(shasum -a 256 "$OUT/$FILE.exe" | awk '{print $1}')"
      EXE_SIG="$(sign "$APP|$BUILD|win|$EXE_SHA")"
      echo "  Win .exe    → /update $(upload "$OUT/$FILE.exe" "update/$SLUG/$FILE.exe")  /dl $(upload "$OUT/$FILE.exe" "dl/$SLUG/$FILE.exe")"
      EXE_JSON=", \"exe_win\": \"$BASEURL/$FILE.exe\", \"sha256_win\": \"$EXE_SHA\", \"sig_win\": \"$EXE_SIG\""
      HAY_EXE=1
    fi
  else
    echo "  ⚠️  sin artifact de Windows para $BUILD. Publico solo Mac (Windows quedará «Unavailable» en el hub)."
  fi
fi

echo "  Mac .zip    → /update $(upload "$OUT/$FILE.zip" "update/$SLUG/$FILE.zip")  /dl $(upload "$OUT/$FILE.zip" "dl/$SLUG/$FILE.zip")"

# Comprobar lo que SIRVE la web ANTES de publicar el manifiesto: si una subida falló en silencio,
# el latest.json no llega a apuntar a un fichero que no existe o que es el viejo (bloquearía a TODOS
# los usuarios, porque el updater verifica el sha).
echo "Verificando lo que sirve la web…"
FALLOS=0
for RUTA in "update/$SLUG/$FILE.zip" "dl/$SLUG/$FILE.zip"; do
  if servido_ok "$RUTA" "$ZIP_SHA"; then echo "  ✅ $RUTA"; else echo "  ❌ $RUTA no coincide"; FALLOS=$((FALLOS+1)); fi
done
if [ -n "${HAY_EXE:-}" ]; then
  for RUTA in "update/$SLUG/$FILE.exe" "dl/$SLUG/$FILE.exe"; do
    if servido_ok "$RUTA" "$EXE_SHA"; then echo "  ✅ $RUTA"; else echo "  ❌ $RUTA no coincide"; FALLOS=$((FALLOS+1)); fi
  done
fi
[ "$FALLOS" -eq 0 ] || { echo "❌ NO publico el manifiesto: $FALLOS fichero(s) mal subidos. Repite el publish."; exit 1; }

cat > "$OUT/latest.json" <<JSON
{"build": "$BUILD", "zip": "$BASEURL/$FILE.zip", "sha256": "$ZIP_SHA", "sig": "$ZIP_SIG"$EXE_JSON, "notes": "$NOTES"}
JSON
echo "  latest.json → /update $(upload "$OUT/latest.json" "update/$SLUG/latest.json")"
BUILD_SERVIDO="$(curl -s "$BASEURL/latest.json?x=$$" | sed -n 's/.*"build": *"\([^"]*\)".*/\1/p')"
[ "$BUILD_SERVIDO" = "$BUILD" ] || { echo "❌ el manifiesto servido dice '$BUILD_SERVIDO' y no '$BUILD'. Repite."; exit 1; }
echo "✅ Publicado $APP $BUILD (firmado) en /update/ y /dl/."
echo "   Recuerda: una línea arriba del todo en missioncontrol/RELEASES.md (es donde MC se entera)."
