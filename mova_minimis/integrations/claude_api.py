"""Cliente de Claude para los agentes que necesitan leer documentos.

Reintenta 3 veces (1 s, 2 s, 4 s) ante 429 y 5xx, avisando por `aviso` con un
mensaje para el usuario; un 4xx aborta. La respuesta se pide como JSON con
esquema (output_config.format), así que nunca hay que "pescar" el JSON en texto.
"""
import json
import time

import anthropic

# Modelos con reintento automático en el servidor si el clasificador de seguridad rechaza
_CON_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5"}


class ErrorClaude(Exception):
    pass


def llamar_json(clave_api: str, modelo: str, sistema: str, contenido: list, esquema: dict,
                max_tokens: int = 4000, aviso=None, cancelado=None) -> tuple[dict, dict]:
    """Devuelve (json_respuesta, uso). `contenido` son bloques de mensaje de usuario."""
    cliente = anthropic.Anthropic(api_key=clave_api, max_retries=0, timeout=180)
    extra = {}
    if modelo in _CON_FALLBACK:
        extra = {"extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                 "extra_body": {"fallbacks": "default"}}
    for intento, espera in enumerate((1, 2, 4, None), start=1):
        if cancelado and cancelado():
            raise ErrorClaude("Cancelado por el usuario")
        try:
            resp = cliente.messages.create(
                model=modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": contenido}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": esquema}},
                **extra,
            )
            if resp.stop_reason == "refusal":
                raise ErrorClaude("El modelo declinó procesar el documento.")
            if resp.stop_reason == "max_tokens":
                raise ErrorClaude("La respuesta del modelo se cortó por longitud; divida el documento.")
            texto = next((b.text for b in resp.content if b.type == "text"), "")
            uso = {"entrada": resp.usage.input_tokens, "salida": resp.usage.output_tokens, "modelo": modelo}
            return json.loads(texto), uso
        except anthropic.AuthenticationError:
            raise ErrorClaude("La clave de la API de Claude no es válida (revise Configuración).")
        except anthropic.RateLimitError:
            msg = "Límite de uso de la API alcanzado. Reintentando..."
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                msg = "Servicio de Claude no disponible. Reintentando..."
            else:
                raise ErrorClaude(f"Error de entrada en la petición a Claude ({e.status_code}).")
        except anthropic.APIConnectionError:
            msg = "Sin conexión con la API de Claude. Reintentando..."
        except json.JSONDecodeError:
            raise ErrorClaude("Claude devolvió una respuesta que no es JSON válido.")
        if espera is None:
            raise ErrorClaude(msg.replace(" Reintentando...", "") + " Se agotaron los reintentos.")
        if aviso:
            aviso(f"{msg} (intento {intento + 1} de 4, espera {espera} s)")
        time.sleep(espera)
    raise ErrorClaude("No se obtuvo respuesta de Claude.")
