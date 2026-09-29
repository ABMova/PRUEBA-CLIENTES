"""La marca verde que aparece en el correo cuando una ayuda ya esta en el CRM.

Un correo ya entregado no puede cambiar solo: su HTML es el que es. Lo unico que
vuelve a pedirle al servidor al abrirlo son las imagenes, asi que el aviso de
"esto ya esta hecho" viaja como una imagen. Cuando alguien del equipo pulsa el
boton, el CRM avisa; la proxima vez que cualquiera abra el correo, la imagen que
devuelve el servidor ya es la verde, con quien lo hizo.

Si el cliente de correo no descarga imagenes, no se ve nada y los botones siguen
funcionando igual: la marca es un aviso, nunca un requisito.
"""
from __future__ import annotations

import io
import unicodedata
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

# Verde claro, legible sobre el fondo blanco de la ficha del correo.
VERDE_FONDO = (223, 245, 228)
VERDE_BORDE = (34, 139, 78)
VERDE_TEXTO = (22, 101, 57)

ALTO = 22
MARGEN = 9
RADIO = 6

_FUENTES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


@lru_cache(maxsize=4)
def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for ruta in _FUENTES:
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def _sin_tildes(texto: str) -> str:
    """La fuente de respaldo puede no tener acentos; el aviso debe leerse siempre."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


@lru_cache(maxsize=256)
def verde(texto: str) -> bytes:
    """PNG con la marca verde y el texto dado."""
    texto = _sin_tildes(texto)[:60]
    fuente = _fuente(12)
    medidor = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    ancho_texto = int(medidor.textlength(texto, font=fuente))
    ancho = ancho_texto + MARGEN * 2 + 16  # hueco para la marca de verificacion

    imagen = Image.new("RGBA", (ancho, ALTO), (255, 255, 255, 0))
    lienzo = ImageDraw.Draw(imagen)
    lienzo.rounded_rectangle((0, 0, ancho - 1, ALTO - 1), RADIO, fill=VERDE_FONDO,
                             outline=VERDE_BORDE)
    # Marca de verificacion a mano: la fuente puede no traer el simbolo.
    lienzo.line((MARGEN, ALTO // 2, MARGEN + 4, ALTO - 7), fill=VERDE_BORDE, width=2)
    lienzo.line((MARGEN + 4, ALTO - 7, MARGEN + 10, 6), fill=VERDE_BORDE, width=2)
    lienzo.text((MARGEN + 15, ALTO // 2), texto, font=fuente, fill=VERDE_TEXTO, anchor="lm")

    memoria = io.BytesIO()
    imagen.save(memoria, format="PNG", optimize=True)
    return memoria.getvalue()


@lru_cache(maxsize=1)
def transparente() -> bytes:
    """Un punto invisible: lo que se sirve mientras la ayuda no se ha tocado."""
    memoria = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 255, 255, 0)).save(memoria, format="PNG")
    return memoria.getvalue()
