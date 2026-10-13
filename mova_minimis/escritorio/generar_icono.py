#!/usr/bin/env python3
"""Genera los .ico del programa a partir de los SVG del icono MOVA IA (static/marca/icono-movaia*.svg).

Cada tamaño usa su versión, porque a tamaño pequeño el detalle no se lee:
  256       -> icono-movaia-completo.svg  (con «MOVA», «IA» y la píldora)
  128,64,48 -> icono-movaia-medio.svg     (sin la píldora)
  32,24,16  -> icono-movaia.svg           (solo anillo e «IA»)

Los SVG se pintan a 512 px con Edge sin ventana (fondo transparente) y se reducen con Pillow.
Escribe escritorio/icono.ico (ventana, instalador, accesos) y static/marca/mova_minimis.ico (motor .exe).

Uso:  C:\\build\\venvs\\mova_minimis\\Scripts\\python escritorio\\generar_icono.py
"""
import io
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
MARCA = RAIZ / "static" / "marca"
TAMANOS = {256: "icono-movaia-completo.svg", 128: "icono-movaia-medio.svg", 64: "icono-movaia-medio.svg",
           48: "icono-movaia-medio.svg", 32: "icono-movaia.svg", 24: "icono-movaia.svg", 16: "icono-movaia.svg"}
EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]


def pintar(svg: Path, tmp: Path) -> Image.Image:
    edge = next((e for e in EDGE if e.exists()), None)
    if not edge:
        sys.exit("No se encuentra Microsoft Edge para pintar los SVG.")
    png = tmp / (svg.stem + ".png")
    # Edge sin ventana a veces deja procesos vivos tras la captura: no se espera a que termine,
    # se espera (con tope) a que el PNG exista y deje de crecer, y luego se cierra su árbol de procesos.
    p = subprocess.Popen([str(edge), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                          "--default-background-color=00000000", f"--user-data-dir={tmp / ('perfil-' + svg.stem)}",
                          "--window-size=512,512", f"--screenshot={png}", svg.as_uri()],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fin, previo = time.monotonic() + 60, -1
    while time.monotonic() < fin:
        if png.exists() and png.stat().st_size == previo and previo > 0:
            break
        previo = png.stat().st_size if png.exists() else -1
        if p.poll() is not None and not png.exists():
            break  # Edge terminó sin captura
        time.sleep(0.5)
    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not png.exists():
        sys.exit(f"Edge no pintó {svg.name} en 60 segundos.")
    im = Image.open(png).convert("RGBA")
    if im.getpixel((0, 0))[3] != 0:
        sys.exit(f"{svg.name} salió con fondo opaco: las esquinas redondeadas no serían transparentes.")
    return im


def escribir_ico(imagenes: dict[int, Image.Image], destino: Path) -> None:
    """ICO con una imagen PNG distinta por tamaño (Pillow solo sabe reducir una misma imagen)."""
    datos = []
    for t in sorted(imagenes, reverse=True):
        b = io.BytesIO()
        imagenes[t].save(b, "PNG")
        datos.append((t, b.getvalue()))
    cab = struct.pack("<HHH", 0, 1, len(datos))
    desplazamiento = 6 + 16 * len(datos)
    entradas, cuerpo = b"", b""
    for t, png in datos:
        entradas += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(png), desplazamiento + len(cuerpo))
        cuerpo += png
    destino.write_bytes(cab + entradas + cuerpo)


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:  # Edge puede tardar en soltar su perfil
        tmp = Path(t)
        lienzos = {f: pintar(MARCA / f, tmp) for f in set(TAMANOS.values())}
        imagenes = {s: lienzos[f].resize((s, s), Image.LANCZOS) for s, f in TAMANOS.items()}
        destino = RAIZ / "escritorio" / "icono.ico"
        escribir_ico(imagenes, destino)
        shutil.copy2(destino, MARCA / "mova_minimis.ico")
        imagenes[256].save(tmp / "comprobacion.png")
    leido = Image.open(destino)
    print(f"{destino.name}: {sorted(leido.info.get('sizes', []))} · {destino.stat().st_size // 1024} KB")
    print(f"{(MARCA / 'mova_minimis.ico').name}: copia idéntica")
    return 0


if __name__ == "__main__":
    sys.exit(main())
