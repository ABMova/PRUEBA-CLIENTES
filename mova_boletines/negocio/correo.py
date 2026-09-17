"""Fase 6 - composicion del correo HTML y envio por SMTP."""
from __future__ import annotations

import logging
import smtplib
import ssl
import time
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from datos import repositorio

registro = logging.getLogger(__name__)

SIN_NOVEDADES = "No se han encontrado nuevas ayudas o subvenciones en los boletines revisados"

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _entorno() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(config.RUTA_PLANTILLAS)),
        autoescape=select_autoescape(["html"]),
    )


def fecha_larga(valor: str | date) -> str:
    if isinstance(valor, str):
        try:
            valor = datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            return valor
    return f"{valor.day} de {_MESES[valor.month - 1]} de {valor.year}"


def url_publica() -> str:
    return (repositorio.ajuste("url_publica", "") or config.URL_PUBLICA).rstrip("/")


def componer(publicaciones: list[dict], fecha: date, resumen_boletines: dict,
             tokens: dict[int, str] | None = None) -> str:
    """Genera el HTML del correo diario. tokens: {publicacion_id: token}."""
    tokens = tokens or {}
    por_comunidad: dict[str, list[dict]] = {}
    for publicacion in publicaciones:
        comunidad = publicacion.get("comunidad") or "Sin comunidad"
        fila = dict(publicacion)
        token = tokens.get(publicacion.get("id"))
        fila["url_descarte"] = f"{url_publica()}/descartar/{token}" if token else ""
        por_comunidad.setdefault(comunidad, []).append(fila)

    for filas in por_comunidad.values():
        filas.sort(key=lambda f: (0 if f.get("relevancia") == "alta" else 1, f.get("titulo", "")))

    plantilla = _entorno().get_template("correo_diario.html")
    return plantilla.render(
        nombre_app=config.NOMBRE_APP,
        fecha=fecha_larga(fecha),
        por_comunidad=dict(sorted(por_comunidad.items())),
        total=len(publicaciones),
        altas=sum(1 for p in publicaciones if p.get("relevancia") == "alta"),
        consultados=resumen_boletines.get("consultados", []),
        fallidos=resumen_boletines.get("fallidos", []),
        sin_novedades=SIN_NOVEDADES,
        marcador=config.MARCADOR_PENDIENTE,
        marcador_revision=config.MARCADOR_REVISION,
        generado=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


def asunto(fecha: date, total: int, altas: int) -> str:
    if total == 0:
        return f"[MOVA Boletines] {fecha_larga(fecha)} - sin novedades"
    return (f"[MOVA Boletines] {fecha_larga(fecha)} - {total} convocatoria(s), "
            f"{altas} de alta relevancia")


# ------------------------------------------------------------------- envio --
class ErrorCorreo(Exception):
    """Fallo de envio ya traducido a lenguaje llano."""


def configuracion_smtp() -> dict:
    return {
        "servidor": repositorio.ajuste("smtp_servidor", ""),
        "puerto": repositorio.ajuste_int("smtp_puerto", 587),
        "seguridad": repositorio.ajuste("smtp_seguridad", "starttls"),
        "usuario": repositorio.ajuste("smtp_usuario", ""),
        "clave": repositorio.ajuste("smtp_clave", ""),
        "remitente": repositorio.ajuste("smtp_remitente", ""),
        "nombre": repositorio.ajuste("smtp_nombre_remitente", config.NOMBRE_APP),
    }


def smtp_configurado() -> bool:
    ajustes = configuracion_smtp()
    return bool(ajustes["servidor"] and ajustes["remitente"])


def enviar(destinatarios: list[str], asunto_correo: str, html: str,
           reintentos: int = 3) -> tuple[bool, str, int]:
    """Envia el correo. Devuelve (exito, detalle, intentos)."""
    if not destinatarios:
        return False, "No hay destinatarios activos", 0
    ajustes = configuracion_smtp()
    if not ajustes["servidor"] or not ajustes["remitente"]:
        return False, "Falta configurar el servidor SMTP y el remitente en Ajustes", 0

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto_correo
    mensaje["From"] = formataddr((ajustes["nombre"], ajustes["remitente"]))
    mensaje["To"] = ", ".join(destinatarios)
    mensaje.set_content(
        "Este correo contiene la vigilancia diaria de boletines oficiales en formato HTML. "
        "Abrelo en un cliente que admita HTML.")
    mensaje.add_alternative(html, subtype="html")

    espera = 2.0
    ultimo = ""
    for intento in range(1, reintentos + 1):
        try:
            _entregar(mensaje, ajustes, destinatarios)
            return True, f"Enviado a {len(destinatarios)} destinatario(s)", intento
        except (smtplib.SMTPException, OSError) as error:
            ultimo = _traducir_smtp(error)
            registro.warning("Envio fallido (intento %s): %s", intento, ultimo)
            if intento < reintentos:
                time.sleep(espera)
                espera *= 2
    return False, ultimo, reintentos


def _entregar(mensaje: EmailMessage, ajustes: dict, destinatarios: list[str]) -> None:
    contexto = ssl.create_default_context()
    seguridad = (ajustes["seguridad"] or "starttls").lower()

    if seguridad == "ssl":
        servidor = smtplib.SMTP_SSL(ajustes["servidor"], ajustes["puerto"], timeout=60,
                                    context=contexto)
    else:
        servidor = smtplib.SMTP(ajustes["servidor"], ajustes["puerto"], timeout=60)
    try:
        servidor.ehlo()
        if seguridad == "starttls":
            servidor.starttls(context=contexto)
            servidor.ehlo()
        if ajustes["usuario"]:
            servidor.login(ajustes["usuario"], ajustes["clave"])
        servidor.send_message(mensaje, to_addrs=destinatarios)
    finally:
        try:
            servidor.quit()
        except smtplib.SMTPException:
            servidor.close()


def _traducir_smtp(error: Exception) -> str:
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "El servidor SMTP rechaza el usuario o la contrasena. Revisalos en Ajustes."
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "El servidor rechazo las direcciones de destino. Revisa Destinatarios."
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "El servidor rechazo la direccion remitente. Revisala en Ajustes."
    if isinstance(error, smtplib.SMTPConnectError | ConnectionRefusedError):
        return "No se pudo conectar con el servidor SMTP. Revisa servidor y puerto."
    if isinstance(error, TimeoutError):
        return "El servidor SMTP no responde (tiempo de espera agotado)."
    return f"Fallo de envio: {str(error)[:200]}"


def guardar_copia(html: str, nombre: str = "correo_ejemplo.html"):
    config.preparar_carpetas()
    destino = config.DATOS / nombre
    destino.write_text(html, encoding="utf-8")
    return destino
