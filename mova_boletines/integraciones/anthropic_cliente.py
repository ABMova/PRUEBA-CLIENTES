"""Unica puerta a la API de Anthropic.

Todo lo que sale hacia el modelo pasa por aqui: reintentos, traduccion de
errores a mensajes accionables y control de que datos se envian.

QUE SALE DEL SISTEMA: solo el texto publico de las publicaciones oficiales
(titulo, organismo, seccion y texto del boletin). Nunca credenciales, nunca
datos de usuarios, nunca el contenido de la base de datos.

PARA SERVIR EL MODELO EN LA RED LOCAL habria que sustituir unicamente este
modulo, manteniendo la firma de llamar_json().
"""
from __future__ import annotations

import json
import logging
import re
import time

import config
from datos import repositorio

registro = logging.getLogger(__name__)


class ErrorModelo(Exception):
    """Error de la API traducido a algo que el usuario pueda accionar."""


def clave_api() -> str:
    """La clave guardada en Ajustes manda; el entorno es el respaldo."""
    return repositorio.ajuste("anthropic_api_key", "") or config.API_KEY_ENTORNO


def hay_clave() -> bool:
    return bool(clave_api())


def _cliente():
    clave = clave_api()
    if not clave:
        raise ErrorModelo("No hay clave de API configurada. Anadela en Ajustes.")
    try:
        from anthropic import Anthropic
    except ImportError as error:  # pragma: no cover
        raise ErrorModelo("El paquete anthropic no esta instalado") from error
    return Anthropic(api_key=clave, max_retries=0)


def _traducir(error: Exception) -> str:
    texto = str(error)
    codigo = getattr(error, "status_code", None)
    if codigo == 401 or "authentication_error" in texto or "invalid x-api-key" in texto:
        return "La clave de API no es valida. Revisa la clave en Ajustes."
    if codigo == 403:
        return "La clave no tiene permiso para este modelo. Revisa la clave en Ajustes."
    if codigo == 400 and "credit balance" in texto.lower():
        return "La cuenta de Anthropic no tiene credito."
    if codigo == 404:
        return "El modelo seleccionado no existe para esta cuenta. Cambialo en Ajustes."
    if codigo == 413 or "too large" in texto.lower():
        return "El texto enviado es demasiado grande para el modelo."
    if codigo == 429:
        return "Limite de peticiones de Anthropic alcanzado; se reintentara."
    if codigo and codigo >= 500:
        return "La API de Anthropic no responde ahora mismo; se reintentara."
    return f"Error inesperado de la API: {texto[:200]}"


def llamar(sistema: str, mensaje: str, modelo: str, max_tokens: int,
           reintentos: int = 3) -> str:
    """Llamada de texto con retroceso exponencial ante 429 y 5xx."""
    cliente = _cliente()
    espera = 2.0
    ultimo: Exception | None = None

    for intento in range(1, reintentos + 1):
        try:
            respuesta = cliente.messages.create(
                model=modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": mensaje}],
            )
            return "".join(bloque.text for bloque in respuesta.content
                           if getattr(bloque, "type", "") == "text")
        except Exception as error:  # noqa: BLE001 - se clasifica justo debajo
            ultimo = error
            codigo = getattr(error, "status_code", None)
            recuperable = codigo == 429 or (codigo is not None and codigo >= 500)
            if not recuperable or intento == reintentos:
                raise ErrorModelo(_traducir(error)) from error
            registro.warning("Reintento %s tras error %s", intento, codigo)
            time.sleep(espera)
            espera *= 2
    raise ErrorModelo(_traducir(ultimo) if ultimo else "Error desconocido")


_BLOQUE_JSON = re.compile(r"\{.*\}", re.S)


def llamar_json(sistema: str, mensaje: str, modelo: str, max_tokens: int) -> dict:
    """Llama al modelo y exige JSON. Si viene envuelto en texto, lo rescata."""
    bruto = llamar(sistema, mensaje, modelo, max_tokens)
    return interpretar_json(bruto)


def interpretar_json(bruto: str) -> dict:
    texto = (bruto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        encontrado = _BLOQUE_JSON.search(texto)
        if encontrado:
            try:
                return json.loads(encontrado.group(0))
            except json.JSONDecodeError as error:
                raise ErrorModelo(f"El modelo no devolvio JSON valido: {error}") from error
        raise ErrorModelo("El modelo no devolvio JSON")


def probar_clave(modelo: str = "claude-haiku-4-5-20251001") -> tuple[bool, str]:
    """Comprobacion desde la pantalla de Ajustes."""
    try:
        llamar("Responde unicamente con la palabra OK.", "Di OK.", modelo, 16, reintentos=1)
        return True, "Clave valida: la API responde"
    except ErrorModelo as error:
        return False, str(error)
