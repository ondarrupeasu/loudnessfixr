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
#   WIN_FORMAT   (opcional) formato del binario de Windows: "exe" (onefile, POR DEFECTO) o "zip" (onedir).
#                onedir = la app es una CARPETA (arranque en <1s en vez de ~25s); el updater reemplaza la
#                carpeta entera (updater_core, rama zip_win). Apps onedir hoy: posthandler, livemixr,
#                stemsplitter (antes con publish forkeado; unificado aquí 12 sep para que hereden el swap atómico).
#
# Origen canónico: launchr (build 2026-08-25k), que estrenó auto-dispatch + verificación de lo servido.
# Historia: MediaCastR 25a (subida FTP fallida en silencio → manifiesto apuntando al .exe viejo) y el
# bloqueo de Actions del 25 ago (build en cada push llenó los 500 MB de la cuenta).

FILE="${FILE:-$APP}"                 # apps normales: el fichero se llama como la app; launchr override
WIN_FORMAT="${WIN_FORMAT:-exe}"      # binario de Windows: exe (onefile, por defecto) | zip (onedir/carpeta)
case "$WIN_FORMAT" in
  exe) WIN_FILE="$FILE.exe";         WIN_KEY="exe_win" ;;   # onefile: se sustituye el .exe
  zip) WIN_FILE="$FILE-Windows.zip"; WIN_KEY="zip_win" ;;   # onedir: se reemplaza la carpeta (updater_core la extrae)
  *) echo "❌ WIN_FORMAT inválido: '$WIN_FORMAT' (usa exe | zip)"; exit 1 ;;
esac
# De dónde baja el binario de Windows que compiló el CI:
#   artifact (por defecto) → `gh run download -n "$FILE-Windows-$BUILD"` (artifacts de Actions).
#   release                → `gh release download win-$BUILD` (RELEASE de handoff del repo privado). Para apps
#                            PESADAS (torch = cientos de MB): los artifacts comparten una cuota de 500 MB en TODA
#                            la cuenta y llenarla bloquea Actions para todos los repos (pasó 25 ago). Las releases no.
WIN_SOURCE="${WIN_SOURCE:-artifact}"                 # artifact | release
WIN_RELEASE_ASSET="${WIN_RELEASE_ASSET:-$FILE-win.zip}"  # (solo release) nombre del asset DENTRO de la release
WIN_WAIT_ITERS="${WIN_WAIT_ITERS:-30}"               # nº de esperas de 20s por el build de Windows (release/torch: subir a 60)
RESIGN_ADHOC="${RESIGN_ADHOC:-0}"                    # 1 = re-firmar ad-hoc el .app antes de empaquetar (un smoke-test deja
                                                     #     caché de Qt dentro → rompe el sello; re-firmar lo arregla)
PROJ="$(cd "$(dirname "$0")/.." && pwd)"; cd "$PROJ"
BUILD="$($PY -c "$BUILD_CMD")"
NOTES="${1:-Build $BUILD}"
# Las notas van DENTRO del JSON del manifiesto → hay que ESCAPARLAS. Publicando con unas notas que
# llevaban comillas dobles, StemSplitteR (v0.9) generó un latest.json que NO parseaba: el updater no
# leía NADA — ni la versión ni el kill-switch. json.dumps las escapa (y añade las comillas → en el
# heredoc se usa SIN comillas alrededor). Al final se valida que el manifiesto parsea antes de darlo por bueno.
NOTES_JSON="$($PY -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$NOTES")"
OUT="$PROJ/dist"; BASEURL="https://apps.cinemafilmak.com/update/$SLUG"
# KILL-SWITCH (min_version) bakeado en el manifiesto. ⚠️El manifiesto se REESCRIBE ENTERO en cada publish:
# si aquí no ponemos min_version, el suelo que YA estaba servido DESAPARECE (bug silencioso — publicas, todo
# verde, y el kill-switch ya no está; lo pilló StemSplitteR 19 sep: le habría resucitado los builds del
# Roformer mudo en Windows, cuyo suelo estaba puesto justo por eso). Regla: BAJAR/quitar el suelo es un acto
# EXPLÍCITO, nunca el valor por defecto:
#   MIN_VERSION="2026-09-10f"  (definida, no vacía) → pone/eleva ese suelo.
#   MIN_VERSION=""             (definida y vacía)   → quita el suelo A PROPÓSITO.
#   MIN_VERSION sin definir                          → CONSERVA el min_version que ya sirve el manifiesto.
if [ -n "${MIN_VERSION+x}" ]; then
  MIN_VERSION_EFF="$MIN_VERSION"
else
  # Conservar el min_version servido, pero DISTINGUIENDO "no hay suelo" de "no pude leerlo": quitar un
  # kill-switch NUNCA debe pasar por accidente (aviso StemSplitteR, 19 sep). 200 → parsear (JSON corrupto =
  # ABORTAR: no sé si había suelo). 404 → primer publish, sin manifiesto → sin suelo (legítimo). Cualquier
  # otro (5xx / timeout / red caída = 000) → ABORTAR: fallar ruidoso, no borrar el suelo por un corte de red.
  _mf="$(mktemp)"
  _code="$(curl -sL --max-time 20 -o "$_mf" -w '%{http_code}' "$BASEURL/latest.json?nc=$$" 2>/dev/null)" || _code="000"
  if [ "$_code" = "200" ]; then
    MIN_VERSION_EFF="$($PY -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("min_version","") or ""); sys.exit(0)
except Exception:
    sys.exit(3)' "$_mf" 2>/dev/null)" || { rm -f "$_mf"; echo "❌ NO publico: el manifiesto servido no parsea; no puedo saber si llevaba kill-switch. Pasa MIN_VERSION a mano (o MIN_VERSION=\"\" para quitarlo a propósito)."; exit 1; }
    [ -n "$MIN_VERSION_EFF" ] && echo "  · kill-switch conservado del manifiesto servido: min_version=$MIN_VERSION_EFF"
  elif [ "$_code" = "404" ]; then
    MIN_VERSION_EFF=""; echo "  · sin manifiesto servido (404): primer publish, no había kill-switch."
  else
    rm -f "$_mf"; echo "❌ NO publico: no pude leer el manifiesto servido (HTTP $_code) para conservar el kill-switch. Reintenta, o pasa MIN_VERSION a mano (MIN_VERSION=\"\" para quitarlo a propósito)."; exit 1
  fi
  rm -f "$_mf"
fi
MIN_JSON=""; [ -n "$MIN_VERSION_EFF" ] && MIN_JSON=", \"min_version\": \"$MIN_VERSION_EFF\""

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
swap() {  # $1 ruta remota REAL -> renombra $1.new SOBRE $1 (atomico server-side; Infomaniak soporta RNFR/RNTO-over). Reintenta.
  local dir code=""
  dir="$(dirname "$1")"
  for intento in 1 2 3; do
    code="$(curl -s --ssl-reqd --user "$FTP_USER:$FTP_PASS" "ftp://$FTP_HOST/$dir/" -Q "RNFR /$1.new" -Q "RNTO /$1" -o /dev/null -w "%{http_code}")"
    case "$code" in 2*) return 0;; esac
    sleep 2
  done
  return 1
}

# Re-firma ad-hoc opcional (RESIGN_ADHOC=1): el sello ad-hoc se rompe si algo toca el bundle tras
# firmarlo (lanzar la app en un smoke-test deja caché de Qt dentro). Re-firmar y verificar, o macOS lo
# marca «dañado» al bajarlo. Solo si la app lo pide (por defecto no, para no cambiar el flujo de las demás).
if [ "$RESIGN_ADHOC" = "1" ]; then
  codesign --force --deep --sign - "dist/$APP.app" >/dev/null 2>&1
  codesign --verify --deep --strict "dist/$APP.app" >/dev/null 2>&1 \
    && echo "  ✅ sello ad-hoc íntegro tras re-firmar" \
    || { echo "  ❌ el sello sigue roto tras re-firmar — abortando"; exit 1; }
fi

# Puerta obligatoria: un .app con enlaces rotos se instala DAÑADO en cualquier otro equipo — y el hub
# se niega a instalarlo. (MediaCastR 2026-08-22d, MirroR 2026-08-25f.)
echo "Verificando el bundle antes de empaquetar…"
bash "$PROJ/tools/verificar_bundle.sh" "dist/$APP.app" || { echo "❌ NO publico: el bundle no es válido."; exit 1; }

echo "Empaquetando Mac $BUILD (ditto)…"
rm -f "$OUT/$FILE.zip" "$OUT/latest.json"
ditto -c -k --sequesterRsrc --keepParent "dist/$APP.app" "$OUT/$FILE.zip"
ZIP_SHA="$(shasum -a 256 "$OUT/$FILE.zip" | awk '{print $1}')"
ZIP_SIG="$(sign "$APP|$BUILD|mac|$ZIP_SHA")"

# Windows: baja el binario que compiló CI para ESTE build (artifact), lo firma y lo hospeda.
# Según WIN_FORMAT, el fichero es $FILE.exe (onefile) o $FILE-Windows.zip (onedir/carpeta).
EXE_JSON=""
if [ -n "$WIN_SRC_REPO" ]; then
  WINDIR="$OUT/win-artifact"; rm -rf "$WINDIR"; mkdir -p "$WINDIR"
  # win_fetch: intenta traer el binario de Windows para ESTE build al $WINDIR. Dos fuentes (WIN_SOURCE).
  win_fetch() {
    if [ "$WIN_SOURCE" = "release" ]; then
      gh release download "win-$BUILD" --repo "$WIN_SRC_REPO" --dir "$WINDIR" --clobber 2>/dev/null
    else
      gh run download --repo "$WIN_SRC_REPO" -n "$FILE-Windows-$BUILD" -D "$WINDIR" 2>/dev/null
    fi
  }
  # win_asset: el fichero recién bajado que nos interesa. En 'release' el asset se llama $WIN_RELEASE_ASSET
  # (p.ej. StemSplitteR-win.zip) y lo hospedamos como $WIN_FILE; en 'artifact' ya viene como $WIN_FILE.
  win_asset() { /usr/bin/find "$WINDIR" -name "$([ "$WIN_SOURCE" = release ] && echo "$WIN_RELEASE_ASSET" || echo "$WIN_FILE")" 2>/dev/null | head -1; }
  # Ya NO se compila en cada push (llenaba el almacenamiento de Actions de TODA la cuenta): si no hay
  # binario para este build, se pide ahora (workflow_dispatch) y se espera. Único momento en que hace falta.
  if ! win_fetch; then
    echo "  No hay binario de Windows para $BUILD: lanzando el build…"
    if gh workflow run windows-build.yml --repo "$WIN_SRC_REPO" >/dev/null 2>&1; then
      for _ in $(seq 1 "$WIN_WAIT_ITERS"); do
        sleep 20
        win_fetch && break
      done
    fi
  fi
  EXE="$(win_asset)"
  if [ -n "$EXE" ] && [ -f "$EXE" ]; then
    cp "$EXE" "$OUT/$WIN_FILE"
    EXE_SHA="$(shasum -a 256 "$OUT/$WIN_FILE" | awk '{print $1}')"
    EXE_SIG="$(sign "$APP|$BUILD|win|$EXE_SHA")"
    echo "  Win $WIN_FORMAT    → /update $(upload "$OUT/$WIN_FILE" "update/$SLUG/$WIN_FILE.new")  /dl $(upload "$OUT/$WIN_FILE" "dl/$SLUG/$WIN_FILE.new")"
    EXE_JSON=", \"$WIN_KEY\": \"$BASEURL/$WIN_FILE\", \"sha256_win\": \"$EXE_SHA\", \"sig_win\": \"$EXE_SIG\""
    HAY_EXE=1
  fi
  # ⚠️ NO degradar a solo-Mac por las bravas en una app que YA publica Windows. No es que Windows quede
  # «Unavailable»: es que el cliente Windows CASCA. `updater_core._apply_windows` hace
  # `raise RuntimeError("no-windows-build")` si el manifiesto no trae exe_win/zip_win, así que a quien tenga
  # la versión anterior le sale la actualización, la acepta y le revienta con un error. Comprobado en MediaCastR.
  # Cubre los DOS casos: artifact vacío, y artifact con OTRO formato del esperado ($WIN_FILE no está dentro —
  # p.ej. CI aún en onefile y aquí WIN_FORMAT=zip). Publicar a medias es peor que no publicar.
  if [ -z "${HAY_EXE:-}" ]; then
    echo "  ❌ sin binario de Windows válido ($WIN_FILE) para $BUILD y esta app publica Windows."
    echo "     Abortado SIN tocar el portal: un manifiesto sin $WIN_KEY hace cascar al updater de Windows."
    echo "     Revisa que el CI produzca $WIN_FILE (WIN_FORMAT=$WIN_FORMAT). Solo Mac a propósito: PUBLISH_MAC_ONLY=1"
    [ "${PUBLISH_MAC_ONLY:-0}" = "1" ] || exit 1
    echo "     PUBLISH_MAC_ONLY=1 → sigo, bajo tu responsabilidad."
  fi
fi

echo "  Mac .zip    → /update $(upload "$OUT/$FILE.zip" "update/$SLUG/$FILE.zip.new")  /dl $(upload "$OUT/$FILE.zip" "dl/$SLUG/$FILE.zip.new")"

# Comprobar lo que SIRVE la web ANTES de publicar el manifiesto: si una subida falló en silencio,
# el latest.json no llega a apuntar a un fichero que no existe o que es el viejo (bloquearía a TODOS
# los usuarios, porque el updater verifica el sha).
echo "Verificando lo que sirve la web…"
FALLOS=0
for RUTA in "update/$SLUG/$FILE.zip.new" "dl/$SLUG/$FILE.zip.new"; do
  if servido_ok "$RUTA" "$ZIP_SHA"; then echo "  ✅ $RUTA"; else echo "  ❌ $RUTA no coincide"; FALLOS=$((FALLOS+1)); fi
done
if [ -n "${HAY_EXE:-}" ]; then
  for RUTA in "update/$SLUG/$WIN_FILE.new" "dl/$SLUG/$WIN_FILE.new"; do
    if servido_ok "$RUTA" "$EXE_SHA"; then echo "  ✅ $RUTA"; else echo "  ❌ $RUTA no coincide"; FALLOS=$((FALLOS+1)); fi
  done
fi
[ "$FALLOS" -eq 0 ] || {
  echo "❌ NO publico el manifiesto: $FALLOS fichero(s) mal subidos (lo servido sigue siendo lo anterior, coherente)."
  echo "   ⚠️ Antes de repetir, MIRA la conexión: si el FTP devuelve 227 (entrar en pasivo) y NUNCA 226"
  echo "      (transferencia completa), o hasta un fichero de 20 bytes falla, la RED está bloqueando/cortando"
  echo "      el canal de datos del FTP (pasa con el wifi de Tartanga) — repetir desde ahí no arregla nada."
  echo "      Y por datos móviles suele ir a ~25 KB/s (una publicación normal = horas). Publica desde otra red."
  exit 1
}

# Todo verificado en .new (los ficheros VIVOS no se han tocado). Swap atomico .new -> definitivo, y solo
# entonces el manifiesto. Si algo hubiera fallado arriba, lo servido seguia intacto y coherente con su manifiesto:
# se acabo la ventana en la que un usuario baja el binario NUEVO con el manifiesto VIEJO (sha desparejado ->
# "checksum mismatch"). Rompio MediaDriveR 11g.
echo "Intercambiando (.new → definitivo, atomico)…"
for RUTA in "update/$SLUG/$FILE.zip" "dl/$SLUG/$FILE.zip"; do
  swap "$RUTA" || { echo "❌ swap fallo en $RUTA — lo servido sigue siendo lo anterior (coherente). Repite el publish."; exit 1; }
done
if [ -n "${HAY_EXE:-}" ]; then
  for RUTA in "update/$SLUG/$WIN_FILE" "dl/$SLUG/$WIN_FILE"; do
    swap "$RUTA" || { echo "❌ swap fallo en $RUTA. Repite el publish."; exit 1; }
  done
fi

cat > "$OUT/latest.json" <<JSON
{"build": "$BUILD", "zip": "$BASEURL/$FILE.zip", "sha256": "$ZIP_SHA", "sig": "$ZIP_SIG"$EXE_JSON$MIN_JSON, "notes": $NOTES_JSON}
JSON
# Validar que el manifiesto PARSEA antes de publicarlo: si no, el updater no leería nada (ni versión ni
# kill-switch) y bloquearía a todos. Fail-closed. (Lo que cazó las notas con comillas de StemSplitteR.)
$PY -m json.tool "$OUT/latest.json" >/dev/null 2>&1 || {
  echo "❌ NO publico: el latest.json generado no es JSON válido. Revisa las notas."; cat "$OUT/latest.json"; exit 1; }
echo "  latest.json → /update $(upload "$OUT/latest.json" "update/$SLUG/latest.json")"
# Verificar lo SERVIDO parseándolo (como el cliente), NO con sed: un manifiesto roto contiene igual la
# cadena "build" y el gate por sed lo daba por bueno mientras el updater no podía leer nada. De paso,
# si pedimos kill-switch, comprobar que el manifiesto servido REALMENTE lo lleva.
SERVIDO="$(curl -s "$BASEURL/latest.json?x=$$" | $PY -c 'import json,sys; d=json.load(sys.stdin); print(d["build"], d.get("min_version",""))' 2>/dev/null)" \
  || { echo "❌ el manifiesto servido no parsea como JSON. Repite."; exit 1; }
[ "${SERVIDO%% *}" = "$BUILD" ] || { echo "❌ el manifiesto servido dice '${SERVIDO%% *}' y no '$BUILD'. Repite."; exit 1; }
[ -z "$MIN_VERSION_EFF" ] || [ "${SERVIDO##* }" = "$MIN_VERSION_EFF" ] \
  || { echo "❌ el suelo kill-switch $MIN_VERSION_EFF (puesto o conservado) no está en el manifiesto servido. Repite."; exit 1; }
echo "✅ Publicado $APP $BUILD (firmado) en /update/ y /dl/."
echo "   Recuerda: una línea arriba del todo en missioncontrol/RELEASES.md (es donde MC se entera)."
