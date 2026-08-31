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
#   BUILD_FILE   (opcional, SOLO si hay WIN_SRC_REPO) ruta relativa del fichero con __build__ (p.ej.
#                "mirror/__init__.py"); activa la guarda de "bump sin empujar" (el CI de Win compila del remoto)
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

# ⚠️ El build del manifiesto se lee del CÓDIGO, pero lo que se empaqueta es lo que haya en dist/. Si subes
# `__build__` y publicas sin recompilar, el manifiesto anuncia una versión y el zip lleva otra: el actualizador
# instala, sigue viendo la vieja y VUELVE A OFRECER la actualización — bucle infinito para el usuario. Pasó de
# verdad, y a tres apps a la vez (AirCastR 29a/30b, AudioPatchR 29a/30a, VideoCatchR 21l/30a): no fueron tres
# despistes, era este agujero. Se comprueba antes de tocar el portal.
BUILD_APP="$(/usr/bin/defaults read "$PROJ/dist/$APP.app/Contents/Info.plist" CFBundleVersion 2>/dev/null)"
# FAIL-CLOSED: "no puedo verificar" NO es "está bien". Tres casos:
if [ -z "$BUILD_APP" ]; then
  # (c) la app no escribe su build en el Info.plist → el launcher la lee mal SIEMPRE → bucle permanente
  #     que republicar no arregla (le pasó a PostHandleR: plist clavado en "1.0"). Arreglar la .spec ANTES.
  echo "❌ NO publico: el .app no declara CFBundleVersion → no puedo verificar que sea de este build."
  echo "   Arregla tu .spec para que escriba __build__ en las DOS claves del Info.plist"
  echo "   (receta: mirror/tools/MirroR.spec:60-61, regex sobre el fichero de versión, SIN importar el paquete):"
  echo '     "CFBundleShortVersionString": _BUILD,   "CFBundleVersion": _BUILD,'
  exit 1
fi
if [ "$BUILD_APP" != "$BUILD" ]; then
  # (b) EL bug: dist/ viejo (no recompilaste) → manifiesto anuncia una versión y el zip lleva otra.
  echo "❌ NO publico: el .app empaquetado es $BUILD_APP y el código dice $BUILD."
  echo "   dist/ está viejo. Recompila y vuelve a intentarlo:"
  echo "     rm -rf build dist && .venv/bin/python -m PyInstaller --noconfirm tools/$APP.spec"
  echo "   (Mejor: usa tools/build_mac.sh, que borra dist/ antes de compilar y esto no puede pasar.)"
  exit 1
fi
# (a) coincide → seguimos.

# Ángulo Windows/CI: el .exe lo compila el CI desde la rama REMOTA. Si el bump de __build__ está sin
# commitear/empujar, el CI compila la versión ANTERIOR (portal nuevo, .exe viejo — le pasó a MirroR).
# Solo aplica si hay build de Windows y el wrapper declaró BUILD_FILE (dónde vive __build__, ruta relativa).
if [ -n "${WIN_SRC_REPO:-}" ]; then
  # FAIL-CLOSED también aquí: si el wrapper no declaró BUILD_FILE, lo DERIVAMOS del BUILD_CMD (todas lo tienen
  # y lleva el paquete dentro). Si aun así no se localiza el fichero → ABORTA (no saltarse la guarda en
  # silencio: "no puedo verificar" ≠ "está bien"). Sin esto, la guarda solo protegía a la única app que
  # declara BUILD_FILE (mirror) y quedaba apagada en las otras 8 sin avisar.
  # Deriva del BUILD_CMD si el wrapper no lo declaró: prueba <pkg>/__init__.py y luego <pkg>.py. No cubre
  # paquetes bajo subdir (app/, src/) ni BUILD_CMD que no importan su paquete (livemixr lee su fichero con
  # regex) → esos declaran BUILD_FILE a mano. IMPORTANTE: si no se localiza, esta guarda (SECUNDARIA, para el
  # .exe de Windows) AVISA pero NO bloquea — bloquear aquí frenaría publishes legítimos (p.ej. PostHandleR
  # republicando). El gate de CFBundleVersion de arriba, que es el que caza EL bug, sí es fail-closed.
  if [ -z "${BUILD_FILE:-}" ]; then
    _pkg="$(printf '%s' "$BUILD_CMD" | sed -n 's/.*import \([A-Za-z_][A-Za-z0-9_]*\).*/\1/p' | head -1)"
    for _cand in "$_pkg/__init__.py" "$_pkg.py"; do [ -n "$_pkg" ] && [ -f "$PROJ/$_cand" ] && { BUILD_FILE="$_cand"; break; }; done
  fi
  if [ -z "${BUILD_FILE:-}" ] || [ ! -f "$PROJ/$BUILD_FILE" ]; then
    echo "⚠️  No localizo el fichero de __build__ (declara BUILD_FILE en tu wrapper: ruta relativa del fichero"
    echo "    con __build__) → NO verifico que el bump esté empujado; el CI de Windows podría compilar la versión"
    echo "    anterior. (El binario de Mac SÍ está protegido por el gate de CFBundleVersion de arriba.)"
  elif git -C "$PROJ" rev-parse @{u} >/dev/null 2>&1; then
    git -C "$PROJ" diff --quiet @{u} -- "$BUILD_FILE" || {
      echo "❌ NO publico: '$BUILD_FILE' no coincide con el remoto (@{u}): cambios sin commitear o sin empujar."
      echo "   El CI de Windows compila desde el remoto → el .exe saldría con la versión ANTERIOR. Commit + push y reintenta."
      exit 1; }
  elif [ -n "$(git -C "$PROJ" status --porcelain -- "$BUILD_FILE" 2>/dev/null)" ]; then
    echo "❌ NO publico: '$BUILD_FILE' con cambios sin commitear y sin rama de seguimiento para verificar el push."
    exit 1
  fi
fi
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
    # ⚠️ NO degradar a solo-Mac por las bravas en una app que YA publica Windows. No es que Windows quede
    # «Unavailable»: es que el cliente Windows CASCA. `updater_core._apply_windows` hace
    # `raise RuntimeError("no-windows-build")` si el manifiesto no trae `exe_win`, así que a quien tenga la
    # versión anterior le sale la actualización, la acepta y le revienta con un error. Comprobado en MediaCastR.
    # Publicar a medias es peor que no publicar: se aborta y no se toca el manifiesto que hay servido.
    echo "  ❌ sin artifact de Windows para $BUILD y esta app publica Windows."
    echo "     Abortado SIN tocar el portal: un manifiesto sin 'exe_win' hace cascar al updater de Windows."
    echo "     Arregla el build de Windows y repite. Si de verdad quieres publicar solo Mac: PUBLISH_MAC_ONLY=1"
    [ "${PUBLISH_MAC_ONLY:-0}" = "1" ] || exit 1
    echo "     PUBLISH_MAC_ONLY=1 → sigo, bajo tu responsabilidad."
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
