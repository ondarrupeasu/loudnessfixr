"""updater_core.py — auto-updater COMPARTIDO de las apps CinemaFilmak.

Extraído del updater de MediaDriveR (la referencia). Parametrizado por `UpdaterConfig` para que
cada app lo use con su nombre / repo / versión / clave pública. Verifica, en este orden, antes de
instalar nada:
  1. `min_version`  → kill-switch: si la app está por debajo, es OBSOLETA (la app debe bloquear el uso).
  2. descarga completa (no truncada).
  3. `sha256`       → integridad (no corrupto).
  4. firma Ed25519  → autenticidad (aunque comprometan el repo de releases, sin la privada no se forja).

USO en una app:
    from .updater_core import Updater, UpdaterConfig
    up = Updater(UpdaterConfig(
        app_name="MediaDriveR",
        repo="ondarrupeasu/mediadriver-releases",
        current_build=mipaquete.__build__,
        public_key_b64="z7ADf21EJCq4XbsmeICVTrVCdjsJ6A1RI5gVlmidEfU=",
    ))
    info = up.check_latest()
    if info and up.is_obsolete(info):   # kill-switch → la app muestra "actualización obligatoria"
        ...
    elif info and up.has_newer(info):
        up.apply_update(info, on_progress=...)   # la app DEBE salir después

DISTRIBUCIÓN: vendorizar este archivo en cada app (copiar a app/core/updater_core.py); el original
canónico vive en missioncontrol/shared/ y se propaga con tools/sync_updater.sh. Requiere `cryptography`.
"""
from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger("cinemafilmak.updater")


@dataclass
class UpdaterConfig:
    app_name: str            # "MediaDriveR" — base de nombres de archivo (.exe/.app/.zip)
    repo: str                # "ondarrupeasu/mediadriver-releases"
    current_build: str       # build actual de la app (p.ej. mipaquete.__build__)
    public_key_b64: str      # clave pública Ed25519 (base64) para verificar la firma
    user_agent: str = ""     # UA propio (GitHub/Fastly cachean 'latest' por UA); por defecto {app_name}-Updater
    manifest_url: str = ""   # si se define, URL del latest.json (p.ej. Infomaniak /update/<app>/); si no, GitHub

    def __post_init__(self) -> None:
        if not self.user_agent:
            self.user_agent = f"{self.app_name}-Updater"

    @property
    def latest_json_url(self) -> str:
        # Distribución en Infomaniak (apps.cinemafilmak.com/update/<app>/latest.json) si se define manifest_url;
        # si no, el flujo antiguo por releases de GitHub. La firma Ed25519 no cubre la URL → mover el hosting no la invalida.
        if self.manifest_url:
            return self.manifest_url
        return f"https://github.com/{self.repo}/releases/latest/download/latest.json"


# ------------------------- helpers de red / hash (sin estado) -------------------------

def _fresh(url: str) -> str:
    return url + ("&" if "?" in url else "?") + "nocache=" + str(int(time.time()))


def _ssl_ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


@contextlib.contextmanager
def _prefer_ipv4():
    """(Histórico) Antes forzaba IPv4 en urllib para evitar cuelgues con IPv6 mal configurado. Pero en
    redes IPv6-primarias (routers/ONT nuevos) forzar IPv4 provoca fallos intermitentes de resolución
    → la actualización no llegaba (hallazgo de la sesión MediaDriveR con el router nuevo del estudio).
    Ahora NO fuerza nada: doble pila (IPv4+IPv6), que el sistema elija. Se conserva el context manager
    para no tocar las llamadas existentes."""
    yield


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------- caducidad / lease (candado de tiempo) -------------------------
# Cada versión funciona OFFLINE este nº de días desde su FECHA DE BUILD (el prefijo YYYY-MM-DD del
# build). Al caducar, la app exige conectarse: si hay build nuevo, actualiza; si no, el manifiesto
# puede traer un `valid_until` FIRMADO que renueva el plazo (lo gestiona MC). Offline al caducar = bloqueo.
import re as _re
from datetime import date as _date, timedelta as _timedelta

HARD_LEASE_DAYS = 90


def _parse_build_date(build: str):
    """Fecha del prefijo del build ('2026-08-19f' -> date(2026,8,19)). None si no encaja (→ fail-open)."""
    m = _re.match(r"(\d{4})-(\d{2})-(\d{2})", str(build or ""))
    if not m:
        return None
    try:
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_iso(s: str):
    try:
        return _date.fromisoformat(str(s)[:10])
    except Exception:  # noqa: BLE001
        return None


class Updater:
    """Auto-updater de una app empaquetada (Mac + Windows), parametrizado por UpdaterConfig."""

    def __init__(self, cfg: UpdaterConfig) -> None:
        self.cfg = cfg

    # ------------------------- comprobación / decisiones -------------------------

    def check_latest(self, timeout: float = 10.0) -> dict | None:
        """Devuelve el manifiesto latest.json del último release, o None si no se pudo."""
        try:
            url = _fresh(self.cfg.latest_json_url)
            req = Request(url, headers={"User-Agent": self.cfg.user_agent, "Cache-Control": "no-cache"})
            with _prefer_ipv4(), urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
                data = json.loads(r.read().decode("utf-8"))
            log.info("check_latest: build remoto = %s (min=%s)", data.get("build"), data.get("min_version"))
            return data
        except Exception as e:  # noqa: BLE001
            log.warning("check_latest error: %s", e)
            return None

    def has_newer(self, info: dict) -> bool:
        """¿El manifiesto trae un build más nuevo que el instalado? (comparación de strings; los ids
        de build deben ordenarse cronológicamente, p.ej. 'YYYY-MM-DD' + sufijo)."""
        remote = str(info.get("build", ""))
        return bool(remote) and remote > self.cfg.current_build

    def is_obsolete(self, info: dict) -> bool:
        """KILL-SWITCH: True si el build instalado está por debajo de `min_version` del manifiesto.
        La app DEBE bloquear el uso y forzar actualización (no es solo 'hay novedad', es 'caducada')."""
        floor = str(info.get("min_version", "") or "")
        return bool(floor) and self.cfg.current_build < floor

    # ------------------------- lease / caducidad por tiempo -------------------------

    def _lease_path(self) -> Path:
        """Fichero local donde se cachea el `valid_until` FIRMADO (renovación concedida por el servidor)."""
        app = self.cfg.app_name
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / app
        elif sys.platform.startswith("win"):
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / app
        else:
            base = Path.home() / f".{app.lower()}"
        return base / "lease.json"

    def _verify_lease(self, valid_until: str, sig_b64: str) -> bool:
        """Firma Ed25519 sobre 'app|lease|valid_until' (YYYY-MM-DD). Fail-closed: sin firma válida, no vale.
        Así un usuario NO puede extenderse el plazo editando un fichero (solo el servidor, con la privada)."""
        if not valid_until or not sig_b64 or _parse_iso(valid_until) is None:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(self.cfg.public_key_b64))
            pub.verify(base64.b64decode(sig_b64), f"{self.cfg.app_name}|lease|{valid_until}".encode())
            return True
        except Exception:  # noqa: BLE001
            return False

    def _cached_valid_until(self) -> str:
        """`valid_until` firmado guardado en local, o '' si no hay / no verifica (→ se ignora)."""
        try:
            d = json.loads(self._lease_path().read_text())
            vu, sig = str(d.get("valid_until", "")), str(d.get("sig_lease", ""))
            return vu if self._verify_lease(vu, sig) else ""
        except Exception:  # noqa: BLE001
            return ""

    def adopt_lease(self, info: dict) -> None:
        """Si el manifiesto trae un `valid_until` FIRMADO y VÁLIDO más tardío que el cacheado, lo guarda
        (renovación). Idempotente y seguro: solo adopta firmas válidas y fechas posteriores."""
        vu, sig = str(info.get("valid_until", "")), str(info.get("sig_lease", ""))
        if not self._verify_lease(vu, sig):
            return
        if vu > self._cached_valid_until():          # ISO como string ordena cronológicamente
            try:
                p = self._lease_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"valid_until": vu, "sig_lease": sig}))
                log.info("lease renovada hasta %s", vu)
            except Exception as e:  # noqa: BLE001
                log.warning("no pude guardar la lease: %s", e)

    def valid_until(self):
        """Fecha de caducidad EFECTIVA (local, sin red): max(fecha_build + HARD_LEASE_DAYS, lease firmada).
        Si el build no trae fecha reconocible y no hay lease → date.max (NO caduca = fail-open, no romper)."""
        cands = []
        bd = _parse_build_date(self.cfg.current_build)
        if bd:
            cands.append(bd + _timedelta(days=HARD_LEASE_DAYS))
        ld = _parse_iso(self._cached_valid_until())
        if ld:
            cands.append(ld)
        return max(cands) if cands else _date.max

    def is_expired(self) -> bool:
        """True si esta versión ha CADUCADO (fecha local pasada). OFFLINE-PROOF: no necesita internet.
        (Caveat conocido: atrasar el reloj del equipo la esquiva; es candado blando+tiempo, no DRM.)"""
        return _date.today() > self.valid_until()

    # ------------------------- verificación -------------------------

    def _verify_sha(self, path: Path, expected: str | None) -> None:
        if not expected:
            raise RuntimeError("manifiesto sin sha256 — se rechaza por seguridad")
        if _sha256(path) != expected:
            raise RuntimeError("el binario descargado no coincide con su checksum (corrupto)")

    def _verify_sig(self, build: str, platform: str, sha256_hex: str | None, sig_b64: str | None) -> None:
        """Firma Ed25519 sobre la cadena canónica "app|build|plataforma|sha256". Fail-closed.
        El nombre de la app va en la firma: 1 sola clave para toda la suite, sin que una firma de una
        app valga para otra."""
        if not sha256_hex or not sig_b64:
            raise RuntimeError("release sin firma — se rechaza por seguridad")
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(self.cfg.public_key_b64))
        try:
            pub.verify(base64.b64decode(sig_b64), f"{self.cfg.app_name}|{build}|{platform}|{sha256_hex}".encode())
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("firma del release inválida — posible manipulación; no se instala") from e

    # ------------------------- descarga / instalación -------------------------

    def _download(self, url: str, dest: Path, on_progress=None, timeout: float = 300.0) -> None:
        req = Request(_fresh(url), headers={"User-Agent": self.cfg.user_agent})
        with _prefer_ipv4(), urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            total = int(r.headers.get("Content-Length", "0"))
            got = 0
            with dest.open("wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if on_progress and total:
                        on_progress(got, total)
        if total and got < total:
            raise RuntimeError(f"descarga incompleta ({got}/{total} bytes) — no se instala")

    def _app_path(self) -> Path | None:
        if not is_frozen():
            return None
        for parent in Path(sys.executable).resolve().parents:
            if parent.suffix == ".app":
                return parent
        return None

    def cleanup_windows_backup(self) -> None:
        """Borra un <App>.old.exe que pudiera haber quedado de una actualización. El swap intenta borrarlo
        (reintenta 8×), pero a veces Defender lo tiene bloqueado ese instante. Al ARRANCAR ya está libre →
        se limpia. Usa el nombre del .exe en marcha (no app_name), así vale sea cual sea el binario.
        (Hallazgo de la sesión MediaDriveR.) Se llama desde check_and_prompt: cero cambios por app."""
        if not (is_frozen() and sys.platform.startswith("win")):
            return
        try:
            target = Path(sys.executable)
            old = target.with_name(target.stem + ".old" + target.suffix)
            if old.exists():
                old.unlink()
                log.info("update: limpiado respaldo %s", old.name)
        except Exception as e:  # noqa: BLE001
            log.info("update: no pude limpiar el .old.exe: %s", e)

    def apply_update(self, info: dict, on_progress=None) -> dict | None:
        """Descarga el nuevo build (verificando min_version + sha256 + firma) y lanza el reemplazo
        desatendido. El llamador DEBE salir después. Multiplataforma."""
        if not is_frozen():
            raise RuntimeError("La app no está empaquetada (modo desarrollo).")
        if self.is_obsolete(info):
            # No debería llegar aquí para 'actualizar y seguir', pero si la app fuerza el update de una
            # versión caducada, igualmente se instala la nueva (que ya cumple el mínimo).
            log.info("apply_update: versión caducada por min_version=%s", info.get("min_version"))
        if sys.platform.startswith("win"):
            return self._apply_windows(info, on_progress)
        return self._apply_macos(info, on_progress)

    def _apply_windows(self, info: dict, on_progress=None) -> dict:
        """Windows: swap EN EL SITIO sin auto-relanzar. Requiere carpeta escribible (no Program Files)."""
        url = info.get("exe_win")
        if not url:
            raise RuntimeError("no-windows-build")
        build = str(info.get("build", "new"))
        target = Path(sys.executable)
        folder = target.parent
        new_exe = folder / (target.stem + ".new" + target.suffix)
        old_bak = folder / (target.stem + ".old" + target.suffix)
        try:
            self._download(url, new_exe, on_progress)
        except (OSError, PermissionError) as e:
            raise RuntimeError(f"no puedo escribir en la carpeta de la app ({folder}). "
                               f"Muévela a una carpeta de usuario (no Program Files). Detalle: {e}")
        self._verify_sha(new_exe, info.get("sha256_win"))
        self._verify_sig(build, "win", info.get("sha256_win"), info.get("sig_win"))

        pid = os.getpid()
        tmp = Path(tempfile.mkdtemp(prefix="cf-update-"))
        bat = tmp / "swap.bat"
        bat.write_text(
            "@echo off\r\n"
            ":wait\r\n"
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && ('
            ' timeout /t 1 /nobreak >nul & goto wait )\r\n'
            f'if exist "{old_bak}" del /f /q "{old_bak}" >nul 2>&1\r\n'
            f'ren "{target}" "{old_bak.name}" >nul 2>&1\r\n'
            f'move /y "{new_exe}" "{target}" >nul 2>&1\r\n'
            "set /a k=0\r\n"
            ":delold\r\n"
            f'del /f /q "{old_bak}" >nul 2>&1\r\n'
            f'if not exist "{old_bak}" goto done\r\n'
            "set /a k+=1\r\n"
            "if %k% geq 8 goto done\r\n"
            "timeout /t 1 /nobreak >nul\r\n"
            "goto delold\r\n"
            ":done\r\n",
            encoding="utf-8")
        vbs = tmp / "swap.vbs"
        vbs.write_text(f'CreateObject("WScript.Shell").Run "cmd /c ""{bat}""", 0, False\r\n', encoding="utf-8")
        subprocess.Popen(["wscript.exe", "//nologo", str(vbs)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        log.info("Actualización (Windows) descargada; swap al cerrar, sin relanzar.")
        return {"in_place": True, "build": build}

    def _stable_install_target(self) -> Path:
        """Ubicación ESTABLE donde instalar cuando la app corre translocada (Aplicaciones)."""
        name = self.cfg.app_name
        for base in ("/Applications", str(Path.home() / "Applications")):
            b = Path(base)
            if b.is_dir() and os.access(b, os.W_OK):
                return b / f"{name}.app"
        d = Path.home() / "Applications"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{name}.app"

    def _apply_macos(self, info: dict, on_progress=None) -> None:
        """macOS: descarga el .app (zip), verifica, y lanza un script que lo reemplaza con ditto y reabre."""
        zip_url = info.get("zip")
        if not zip_url:
            raise RuntimeError("no-macos-build")
        app = self._app_path()
        if app is None:
            raise RuntimeError("La app no está empaquetada (modo desarrollo).")
        # App "translocada" (descargada + no notarizada, corriendo desde una copia temporal de solo
        # lectura): NO podemos reemplazar nuestro propio bundle. En vez de fallar, instalamos en una
        # ubicación estable (Aplicaciones) y abrimos desde ahí → rompe el ciclo de translocación.
        translocated = "AppTranslocation" in str(app)
        target = self._stable_install_target() if translocated else app
        log.info("apply_macos: translocated=%s → target=%s", translocated, target)

        tmp = Path(tempfile.mkdtemp(prefix="cf-update-"))
        zpath = tmp / f"{self.cfg.app_name}.zip"
        self._download(zip_url, zpath, on_progress)
        self._verify_sha(zpath, info.get("sha256"))
        self._verify_sig(str(info.get("build", "")), "mac", info.get("sha256"), info.get("sig"))

        name = self.cfg.app_name
        pid = os.getpid()
        script = tmp / "swap.sh"
        script.write_text(f"""#!/bin/bash
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
sleep 0.5
ditto -x -k "{zpath}" "{tmp}/x" || exit 1
NEW="{tmp}/x/{name}.app"
[ -d "$NEW" ] || NEW="$(/usr/bin/find "{tmp}/x" -maxdepth 3 -name '{name}.app' -print -quit)"
xattr -dr com.apple.quarantine "$NEW" 2>/dev/null
rm -rf "{target}"
ditto "$NEW" "{target}"
xattr -dr com.apple.quarantine "{target}" 2>/dev/null
open "{target}"
rm -rf "{tmp}"
""")
        script.chmod(0o755)
        subprocess.Popen(["/bin/bash", str(script)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("Actualización lanzada; la app se cerrará para reemplazarse.")
