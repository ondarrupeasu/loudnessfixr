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

    def __post_init__(self) -> None:
        if not self.user_agent:
            self.user_agent = f"{self.app_name}-Updater"

    @property
    def latest_json_url(self) -> str:
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
    """Fuerza IPv4 en urllib durante la petición (evita cuelgues por IPv6 mal configurado)."""
    orig = socket.getaddrinfo

    def _v4(host, port, family=0, *a, **k):
        return orig(host, port, socket.AF_INET, *a, **k)

    socket.getaddrinfo = _v4
    try:
        yield
    finally:
        socket.getaddrinfo = orig


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


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

    def _apply_macos(self, info: dict, on_progress=None) -> None:
        """macOS: descarga el .app (zip), verifica, y lanza un script que lo reemplaza con ditto y reabre."""
        zip_url = info.get("zip")
        if not zip_url:
            raise RuntimeError("no-macos-build")
        app = self._app_path()
        if app is None:
            raise RuntimeError("La app no está empaquetada (modo desarrollo).")
        if "AppTranslocation" in str(app):
            raise RuntimeError("translocated")

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
rm -rf "{app}"
ditto "$NEW" "{app}"
xattr -dr com.apple.quarantine "{app}" 2>/dev/null
open "{app}"
rm -rf "{tmp}"
""")
        script.chmod(0o755)
        subprocess.Popen(["/bin/bash", str(script)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("Actualización lanzada; la app se cerrará para reemplazarse.")
