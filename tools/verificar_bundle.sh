#!/usr/bin/env bash
# verificar_bundle.sh — comprueba que un .app de macOS es PUBLICABLE, no solo que arranca aquí.
#
# CANÓNICO en missioncontrol/shared. Se vendoriza a cada app en tools/ vía sync_updater.sh: NO editar las
# copias locales (se pierden en la próxima sync); edita esta. Origen: la MediaCastR 2026-08-22d se publicó
# con 16 enlaces simbólicos colgando (poda de Qt) y macOS la daba por DAÑADA en cualquier OTRO equipo
# («a sealed resource is missing or invalid») — en la máquina de build arrancaba igual. La firma solo se
# comprueba de verdad cuando el archivo viene de FUERA, así que hay que verificar SOBRE EL ZIP EXTRAÍDO,
# no sobre el build local.
#
# ⚠️ EXTRAE EL ZIP CON `ditto -x -k archivo.zip destino/`, NUNCA con `unzip`. `unzip` no restaura bien los
# symlinks de los frameworks y además crea un `__MACOSX/` con un .app basura → codesign da «bundle format
# unrecognized» y verás un FALSO «dañado». `ditto` es lo que usan Finder/Archive Utility (= lo que hace el
# usuario). Comprobado 2026-08-23: 8/8 apps daban firma VÁLIDA con ditto y falso fallo con unzip.
#
# ⚠️ Y NUNCA copies un `.app` con `cp -R`: no respeta los enlaces simbólicos de los frameworks y la app
# muere al ARRANCAR saliendo con código 0 y SIN mensaje (fallo silencioso, dificilísimo de diagnosticar).
# Para copiar/comprimir/montar cualquier `.app` (dmg incluido): `ditto`. Misma familia de fallo que los
# symlinks colgando de la poda de Qt (detectado en MirroR/make_dmg.sh, 25 ago 2026).
#
# Uso:
#   bash verificar_bundle.sh <ruta/al/App.app>                 # 3 chequeos estáticos (symlinks, firma, Gatekeeper)
#   bash verificar_bundle.sh <App.app> --run "<cmd>" [--expect "texto"]
#         # además LANZA la app (p.ej. su --selftest) y re-verifica que arrancar NO rompió su firma
#         # (causa nº2: apps que escriben logs/cachés DENTRO del bundle tras firmar). --expect: texto que
#         # debe aparecer en la salida para dar el arranque por bueno.
#
# Devuelve el nº de fallos como código de salida (0 = PUBLICABLE). Pensado para meter en el publish:
#   bash tools/verificar_bundle.sh "dist/$APP.app" || { echo "no publico: bundle inválido"; exit 1; }
set -uo pipefail

APP=""; RUN=""; EXPECT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --run)    RUN="${2:-}"; shift 2;;
    --expect) EXPECT="${2:-}"; shift 2;;
    *)        APP="$1"; shift;;
  esac
done
[ -n "$APP" ] && [ -d "$APP" ] || { echo "Uso: verificar_bundle.sh <App.app> [--run \"cmd\"] [--expect \"txt\"]"; exit 2; }

fallos=0

echo "→ enlaces simbólicos rotos"
rotos=0
while IFS= read -r l; do
  [ -e "$l" ] || { echo "   ROTO: ${l#"$APP"/}"; rotos=$((rotos+1)); }
done < <(find "$APP" -type l)
[ "$rotos" -eq 0 ] && echo "   ninguno" || { echo "   ❌ $rotos"; fallos=$((fallos+1)); }

echo "→ la firma cubre el bundle (codesign --verify --deep --strict)"
if codesign --verify --deep --strict "$APP" 2>/dev/null; then
  echo "   ✅ válida"
else
  echo "   ❌ $(codesign --verify --deep --strict "$APP" 2>&1 | tail -1)"; fallos=$((fallos+1))
fi

echo "→ veredicto de Gatekeeper"
veredicto=$(spctl --assess --type execute -vv "$APP" 2>&1 | tail -1)
echo "   $veredicto"
case "$veredicto" in
  *"sealed resource"*|*damaged*|*"resource envelope"*) echo "   ❌ macOS lo dará por DAÑADO"; fallos=$((fallos+1));;
  *"not signed"*|*"Unnotarized"*|*rejected*)           echo "   ⚠️ sin certificado de Apple: pedirá clic derecho → Abrir";;
esac

# --- Arranque opcional: caza la causa nº2 (escribir DENTRO del bundle rompe la firma) ---
if [ -n "$RUN" ]; then
  echo "→ arranca (--run) sin romper su propia firma"
  # ⚠️ Nada de `... | grep -q` aquí: con pipefail, grep -q sale al primer acierto, la app muere con SIGPIPE
  # (141) y ese código se convierte en el de la tubería → fallo INTERMITENTE aunque el texto esté. Se
  # captura la salida y se busca sobre ella.
  salida=$(cd "$APP/Contents/MacOS" && eval "$RUN" 2>/dev/null || true)
  if [ -n "$EXPECT" ] && ! printf '%s' "$salida" | grep -qF "$EXPECT"; then
    echo "   ❌ no arrancó bien (no apareció: «$EXPECT»)"; fallos=$((fallos+1))
  elif codesign --verify --deep --strict "$APP" 2>/dev/null; then
    echo "   ✅ la firma sigue válida tras arrancar"
  else
    echo "   ❌ arrancar la app ROMPE su propia firma (escribe dentro del bundle)"; fallos=$((fallos+1))
  fi
fi

echo ""
[ "$fallos" -eq 0 ] && echo "PUBLICABLE" || echo "NO PUBLICAR: $fallos problema(s)"
exit "$fallos"
