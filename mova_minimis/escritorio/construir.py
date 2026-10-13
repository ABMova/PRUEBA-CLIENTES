#!/usr/bin/env python3
"""Compila el instalador de escritorio de MOVA Minimis (MOVAMinimis-Setup-X.Y.Z.exe).

Pasos:
  1. Copia el código a C:\\build\\mova_minimis y empaqueta el motor Python en carpeta
     (mova_minimis_servidor.spec) con el entorno C:\\build\\venvs\\mova_minimis.
  2. Monta el proyecto Electron en una ruta corta (makensis no admite rutas de más de
     260 caracteres) con la carpeta del motor como extraResources.
  3. npm install + electron-builder, preparando antes la caché de firma sin los symlinks
     de macOS que Windows no sabe crear (ver la skill mova-escritorio, compilacion.md).

Uso:  python escritorio\\construir.py
Deja el instalador en escritorio\\dist\\ y dice dónde. Devuelve código distinto de 0 si falla.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ESCRITORIO = Path(__file__).resolve().parent
PROYECTO = ESCRITORIO.parent
COPIA = Path(r"C:\build\mova_minimis")
VENV_PY = Path(r"C:\build\venvs\mova_minimis\Scripts\python.exe")
CORTA = Path(os.environ.get("LOCALAPPDATA", r"C:\Temp")) / "Temp" / "mova-minimis-esc"


def ejecutar(cmd, cwd, titulo) -> None:
    print(f"\n>>> {titulo}", flush=True)
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str))
    if r.returncode != 0:
        print(f"\nERROR: {titulo} ha fallado (código {r.returncode})")
        sys.exit(r.returncode or 1)


def copiar_codigo() -> None:
    # robocopy devuelve < 8 si fue bien
    r = subprocess.run(["robocopy", str(PROYECTO), str(COPIA), "/MIR", "/XD", "data", "data-dev", "build", "dist",
                        "__pycache__", ".git", "tests", "node_modules", "/XF", ".env", "*.db", "cipher.key",
                        "/NFL", "/NDL", "/NJH", "/NJS"])
    if r.returncode >= 8:
        print("ERROR: no se pudo copiar el código a", COPIA)
        sys.exit(1)


def arreglar_cache_firma(build_dir: Path) -> None:
    cache = Path(os.environ.get("LOCALAPPDATA", "")) / "electron-builder" / "Cache" / "winCodeSign"
    destino = cache / "winCodeSign-2.6.0"
    if destino.is_dir() and any(destino.iterdir()):
        return
    siete = build_dir / "node_modules" / "7zip-bin" / "win" / "x64" / "7za.exe"
    archivos = glob.glob(str(cache / "*.7z"))
    if not siete.is_file() or not archivos:
        return
    print("\n>>> Preparando la caché de firma sin los symlinks de macOS")
    shutil.rmtree(destino, ignore_errors=True)
    subprocess.run([str(siete), "x", "-bd", archivos[0], "-o" + str(destino), "-x!darwin", "-y"], capture_output=True)


def main() -> int:
    if shutil.which("node") is None:
        print("ERROR: no se encuentra Node.js.")
        return 1
    version = json.loads((ESCRITORIO / "package.json").read_text(encoding="utf-8"))["version"]
    print(f"MOVA Minimis escritorio {version}")

    # 1 · motor Python
    copiar_codigo()
    ejecutar([str(VENV_PY), "-m", "PyInstaller", "--noconfirm", "--clean", "mova_minimis_servidor.spec"],
             COPIA, "Empaquetando el motor Python (PyInstaller, carpeta)")
    motor = COPIA / "dist" / "MOVAMinimisServidor"
    if not (motor / "MOVAMinimisServidor.exe").is_file():
        print("ERROR: no se generó", motor / "MOVAMinimisServidor.exe")
        return 1

    # 2 · proyecto Electron en ruta corta
    pj = json.loads((ESCRITORIO / "package.json").read_text(encoding="utf-8"))
    nm = CORTA / "node_modules"
    if CORTA.exists():  # se conserva node_modules entre compilaciones: npm install tarda
        for p in CORTA.iterdir():
            if p != nm:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    CORTA.mkdir(parents=True, exist_ok=True)
    for f in pj["build"]["files"] + ["package.json"]:
        shutil.copy2(ESCRITORIO / f, CORTA / f)
    shutil.copytree(motor, CORTA / "servidor")
    print(f"ruta corta: {CORTA} ({len(str(CORTA))} caracteres)")

    # 3 · instalador
    ejecutar("npm install --no-audit --no-fund", CORTA, "Instalando dependencias de Electron")
    arreglar_cache_firma(CORTA)
    r = subprocess.run("npx electron-builder --win nsis", cwd=CORTA, shell=True)
    if r.returncode != 0:
        arreglar_cache_firma(CORTA)
        ejecutar("npx electron-builder --win nsis", CORTA, "Generando el instalador (2º intento)")
    instalador = CORTA / "dist" / f"MOVAMinimis-Setup-{version}.exe"
    if not instalador.is_file():
        print("ERROR: no aparece", instalador)
        return 1
    salida = ESCRITORIO / "dist"
    salida.mkdir(exist_ok=True)
    shutil.copy2(instalador, salida / instalador.name)
    print(f"\n== Instalador: {salida / instalador.name} ({instalador.stat().st_size / 1e6:.1f} MB)")
    print(f"== Sin instalar, para probar: {CORTA / 'dist' / 'win-unpacked' / 'MOVAMinimis.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
