"""Fase 1b - normalizacion de texto y extraccion de texto de PDF.

El OCR es opcional a proposito: si Tesseract no esta instalado no se falla,
se marca la publicacion con texto_incompleto y el proceso continua.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata

registro = logging.getLogger(__name__)

_TESSERACT_DISPONIBLE: bool | None = None


def normalizar(texto: str) -> str:
    """Minusculas, sin tildes y con los espacios colapsados."""
    if not texto:
        return ""
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(caracter for caracter in plano if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", plano.lower()).strip()


def normalizar_titulo(titulo: str) -> str:
    """Version del titulo para hash y comparacion difusa: sin puntuacion."""
    plano = normalizar(titulo)
    return re.sub(r"[^a-z0-9 ]+", " ", plano).strip()


def tesseract_disponible() -> bool:
    global _TESSERACT_DISPONIBLE
    if _TESSERACT_DISPONIBLE is None:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            _TESSERACT_DISPONIBLE = True
        except Exception:  # noqa: BLE001 - cualquier fallo significa "no disponible"
            _TESSERACT_DISPONIBLE = False
    return _TESSERACT_DISPONIBLE


def texto_de_pdf(contenido: bytes, paginas_max: int = 12) -> tuple[str, bool]:
    """Devuelve (texto, incompleto). incompleto=True si no se pudo leer entero."""
    try:
        import pdfplumber
    except ImportError:
        return "", True

    partes: list[str] = []
    sin_capa_texto = False
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            for pagina in pdf.pages[:paginas_max]:
                texto = pagina.extract_text() or ""
                if texto.strip():
                    partes.append(texto)
                else:
                    sin_capa_texto = True
                    ocr = _ocr_pagina(pagina)
                    if ocr:
                        partes.append(ocr)
                        sin_capa_texto = False
    except Exception as error:  # noqa: BLE001 - un PDF roto no puede tumbar la ejecucion
        registro.warning("No se pudo leer el PDF: %s", error)
        return "\n".join(partes), True

    return "\n".join(partes).strip(), sin_capa_texto


def _ocr_pagina(pagina) -> str:
    if not tesseract_disponible():
        return ""
    try:
        import pytesseract

        imagen = pagina.to_image(resolution=200).original
        return pytesseract.image_to_string(imagen, lang="spa")
    except Exception as error:  # noqa: BLE001
        registro.warning("OCR fallido: %s", error)
        return ""


def recortar(texto: str, maximo: int = 18000) -> str:
    """Limita el texto que se manda al modelo, para acotar el coste."""
    texto = (texto or "").strip()
    return texto if len(texto) <= maximo else texto[:maximo] + "\n[...texto recortado...]"


def lineas(texto: str) -> int:
    return len([linea for linea in (texto or "").splitlines() if linea.strip()])
