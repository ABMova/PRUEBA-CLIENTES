"""Regenera icono.ico e imagenes_base64.py a partir de cerebro.png y logo_mova.png.

Uso (herramienta de desarrollo):  python -m ui.recursos.generar_recursos
"""
from __future__ import annotations

import base64
from pathlib import Path

CARPETA = Path(__file__).resolve().parent


def generar_icono() -> Path:
    from PIL import Image  # Pillow llega como dependencia de matplotlib

    img = Image.open(CARPETA / "cerebro.png").convert("RGBA")
    lado = max(img.size)
    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    lienzo.paste(img, ((lado - img.width) // 2, (lado - img.height) // 2))
    destino = CARPETA / "icono.ico"
    lienzo.save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                (256, 256)])
    return destino


def generar_base64() -> Path:
    lineas = ['"""Imágenes embebidas (generado por generar_recursos.py; no editar)."""', ""]
    for nombre, fichero in (("CEREBRO_PNG", "cerebro.png"), ("LOGO_MOVA_PNG", "logo_mova.png")):
        ruta = CARPETA / fichero
        datos = base64.b64encode(ruta.read_bytes()).decode("ascii") if ruta.exists() else ""
        trozos = [datos[i:i + 100] for i in range(0, len(datos), 100)]
        lineas.append(f"{nombre} = (")
        lineas += [f'    "{t}"' for t in trozos] or ['    ""']
        lineas += [")", ""]
    destino = CARPETA / "imagenes_base64.py"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(generar_icono())
    print(generar_base64())
