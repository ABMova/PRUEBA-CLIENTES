"""Unica puerta a la API de Anthropic.

Todo lo que sale hacia el modelo pasa por aqui: reintentos, traduccion de
errores a mensajes accionables, control de que datos se envian, y el registro
de tokens y coste de cada llamada (panel de coste y tope mensual).

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

# Precios de la API de Anthropic en dolares por millon de tokens (entrada,
# salida), tarifa estandar de primera parte. Comprobados el 18/09/2026.
# Si Anthropic los cambia, basta con tocar esta tabla.
PRECIOS_USD_POR_MILLON: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
# Un modelo que no este en la tabla se cuenta a precio alto: es preferible
# sobreestimar el gasto que dejar pasar el tope mensual.
PRECIO_DESCONOCIDO = (5.00, 25.00)
FACTOR_CACHE_LECTURA = 0.10
FACTOR_CACHE_ESCRITURA = 1.25

# Sonnet 5 y Opus 5 razonan por defecto aunque no se pida, y ese razonamiento
# se factura como salida y consume max_tokens. Para extraer datos de un
# boletin basta un esfuerzo bajo: se fija explicitamente en estos modelos.
# Haiku 4.5 no admite el parametro (daria error), asi que ahi no se envia.
MODELOS_CON_ESFUERZO = {"claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"}
ESFUERZOS_VALIDOS = ("low", "medium", "high")

# Ejecucion en curso, para atribuir el consumo. Solo hay una a la vez (el
# orquestador lo garantiza), asi que una variable de modulo basta y sirve
# tambien para los hilos del ThreadPoolExecutor.
_ejecucion_actual: int | None = None


class ErrorModelo(Exception):
    """Error de la API traducido a algo que el usuario pueda accionar."""


class TopeAlcanzado(ErrorModelo):
    """Se ha llegado al tope de gasto mensual configurado en Ajustes."""


def fijar_ejecucion(ejecucion_id: int | None) -> None:
    global _ejecucion_actual
    _ejecucion_actual = ejecucion_id


def clave_api() -> str:
    """La clave guardada en Ajustes manda; el entorno es el respaldo."""
    return repositorio.ajuste("anthropic_api_key", "") or config.API_KEY_ENTORNO


def hay_clave() -> bool:
    return bool(clave_api())


# -------------------------------------------------------------------- coste --
def calcular_coste(modelo: str, entrada: int, salida: int, cache_lectura: int = 0,
                   cache_escritura: int = 0) -> float:
    precio_entrada, precio_salida = PRECIOS_USD_POR_MILLON.get(modelo, PRECIO_DESCONOCIDO)
    return (entrada * precio_entrada
            + salida * precio_salida
            + cache_lectura * precio_entrada * FACTOR_CACHE_LECTURA
            + cache_escritura * precio_entrada * FACTOR_CACHE_ESCRITURA) / 1_000_000


def presupuesto() -> tuple[bool, float, float]:
    """(queda_presupuesto, gasto_del_mes, tope). Tope 0 = sin limite."""
    try:
        tope = float(repositorio.ajuste("tope_mensual_usd", "30") or 0)
    except ValueError:
        tope = 30.0
    gasto = repositorio.gasto_mes_usd()
    return (tope <= 0 or gasto < tope), gasto, tope


def _registrar_consumo(respuesta, modelo: str, fase: str, resultado: str) -> None:
    uso = getattr(respuesta, "usage", None)
    if uso is None:
        return
    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    salida = int(getattr(uso, "output_tokens", 0) or 0)
    lectura = int(getattr(uso, "cache_read_input_tokens", 0) or 0)
    escritura = int(getattr(uso, "cache_creation_input_tokens", 0) or 0)
    try:
        repositorio.registrar_consumo(
            _ejecucion_actual, fase, modelo, entrada, salida, lectura, escritura,
            calcular_coste(modelo, entrada, salida, lectura, escritura), resultado)
    except Exception as error:  # noqa: BLE001 - la contabilidad no debe tumbar la llamada
        registro.error("No se pudo registrar el consumo: %s", error)


# ------------------------------------------------------------------ llamadas --
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


def _parametros(sistema: str, mensaje: str, modelo: str, max_tokens: int) -> dict:
    parametros = {
        "model": modelo,
        "max_tokens": max_tokens,
        "system": sistema,
        "messages": [{"role": "user", "content": mensaje}],
    }
    if modelo in MODELOS_CON_ESFUERZO:
        esfuerzo = repositorio.ajuste("esfuerzo_modelo", "low")
        parametros["output_config"] = {
            "effort": esfuerzo if esfuerzo in ESFUERZOS_VALIDOS else "low"}
    return parametros


def llamar(sistema: str, mensaje: str, modelo: str, max_tokens: int,
           reintentos: int = 3, fase: str = "") -> str:
    """Llamada de texto con retroceso exponencial ante 429 y 5xx."""
    queda, gasto, tope = presupuesto()
    if not queda:
        raise TopeAlcanzado(
            f"Tope de gasto mensual alcanzado ({gasto:.2f} de {tope:.2f} $). "
            f"Las publicaciones se guardan para revision manual. Sube el tope en Ajustes.")

    cliente = _cliente()
    parametros = _parametros(sistema, mensaje, modelo, max_tokens)
    espera = 2.0
    ultimo: Exception | None = None

    for intento in range(1, reintentos + 1):
        try:
            respuesta = cliente.messages.create(**parametros)
        except Exception as error:  # noqa: BLE001 - se clasifica justo debajo
            ultimo = error
            codigo = getattr(error, "status_code", None)
            recuperable = codigo == 429 or (codigo is not None and codigo >= 500)
            if not recuperable or intento == reintentos:
                raise ErrorModelo(_traducir(error)) from error
            registro.warning("Reintento %s tras error %s", intento, codigo)
            time.sleep(espera)
            espera *= 2
            continue

        motivo = getattr(respuesta, "stop_reason", "end_turn")
        # Los tokens se facturan aunque la respuesta no sirva: se registran siempre.
        _registrar_consumo(respuesta, modelo, fase,
                           "ok" if motivo not in ("refusal", "max_tokens") else motivo)
        if motivo == "refusal":
            raise ErrorModelo("El modelo ha declinado analizar esta publicacion.")
        if motivo == "max_tokens":
            raise ErrorModelo(
                "La respuesta del modelo se corto por el limite de tokens. "
                "Sube los tokens de esta fase en Ajustes.")
        return "".join(bloque.text for bloque in respuesta.content
                       if getattr(bloque, "type", "") == "text")

    raise ErrorModelo(_traducir(ultimo) if ultimo else "Error desconocido")


_BLOQUE_JSON = re.compile(r"\{.*\}", re.S)


def llamar_json(sistema: str, mensaje: str, modelo: str, max_tokens: int,
                fase: str = "") -> dict:
    """Llama al modelo y exige JSON. Si viene envuelto en texto, lo rescata."""
    bruto = llamar(sistema, mensaje, modelo, max_tokens, fase=fase)
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


def normalizar_clave(valor: str) -> tuple[str, str]:
    """Limpia la clave pegada en Ajustes. Devuelve (clave, aviso).

    El campo oculta lo que se escribe, y es facil pegar dos veces: el
    18/09/2026 una clave valida quedo guardada duplicada y la API la rechazaba.
    Si son dos copias identicas se deja una; si son dos claves distintas, error.
    """
    limpia = "".join((valor or "").split()).strip("'\"")
    apariciones = limpia.count("sk-ant-")
    if apariciones <= 1:
        return limpia, ""
    mitad = len(limpia) // apariciones
    trozos = {limpia[i * mitad:(i + 1) * mitad] for i in range(apariciones)}
    if len(limpia) % apariciones == 0 and len(trozos) == 1:
        return trozos.pop(), f"La clave estaba pegada {apariciones} veces seguidas; se ha guardado una sola."
    raise ErrorModelo("Parece que has pegado varias claves distintas juntas. Pega solo una.")


def probar_clave(modelo: str = "claude-haiku-4-5-20251001") -> tuple[bool, str]:
    """Comprobacion desde Ajustes. Consulta la lista de modelos: no tiene coste."""
    del modelo  # se mantiene la firma; la comprobacion ya no gasta tokens
    try:
        disponibles = {m.id for m in _cliente().models.list(limit=100)}
    except ErrorModelo as error:
        return False, str(error)
    except Exception as error:  # noqa: BLE001 - se traduce igual que en llamar()
        return False, _traducir(error)
    configurados = {repositorio.ajuste("modelo_extraccion", "claude-sonnet-5"),
                    repositorio.ajuste("modelo_relevancia", "claude-haiku-4-5-20251001"),
                    repositorio.ajuste("modelo_documentos", "claude-sonnet-5")}
    faltan = sorted(m for m in configurados if m not in disponibles)
    if faltan:
        return False, (f"La clave es valida, pero tu cuenta no tiene acceso a: {', '.join(faltan)}. "
                       f"Elige otro modelo en Ajustes.")
    return True, "Clave valida: la API responde y los modelos elegidos estan disponibles."


def corregir_clave_guardada() -> bool:
    """Al arrancar: repara una clave guardada duplicada (ver normalizar_clave)."""
    guardada = repositorio.ajuste("anthropic_api_key", "")
    if not guardada:
        return False
    try:
        limpia, aviso = normalizar_clave(guardada)
    except ErrorModelo:
        return False
    if aviso and limpia != guardada:
        repositorio.guardar_ajuste("anthropic_api_key", limpia)
        repositorio.registrar_auditoria("sistema", "corregir_clave_api", "",
                                        aviso + " (al arrancar)")
        return True
    return False
