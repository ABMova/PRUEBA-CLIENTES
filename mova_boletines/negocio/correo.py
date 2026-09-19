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
from negocio import plazos

registro = logging.getLogger(__name__)

SIN_NOVEDADES = "No se han encontrado nuevas ayudas o subvenciones en los boletines revisados"

# Cabecera del correo segun para que se envia.
MODOS = {
    "diario": "",
    "tarde": ("Comprobacion de la tarde: publicaciones aparecidas despues del correo de la "
              "manana (boletines extraordinarios o publicados tarde)."),
    "alerta": ("Alerta: convocatorias de alta relevancia cuyo plazo de solicitud termina "
               "pronto. Tambien apareceran en el correo diario."),
}

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


def fecha_corta(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return valor


def preparar_fila(publicacion: dict, token: str | None = None, hoy: date | None = None) -> dict:
    """Anade a la fila lo que la plantilla necesita: enlace de descarte y vencimiento."""
    fila = dict(publicacion)
    fila["url_descarte"] = f"{url_publica()}/descartar/{token}" if token else ""
    fila["titulo_resumido"] = fila.get("titulo_resumido") or ""
    restantes = plazos.dias_restantes(fila.get("plazo_fin"), hoy)
    fila["dias_restantes"] = restantes
    fila["plazo_fin_texto"] = fecha_corta(fila.get("plazo_fin"))
    fila["plazo_estimado"] = fila.get("plazo_fin_origen") in ("calculado", "modelo")
    # Botones Resumen corto / Resumen ampliado / Infografia. Llevan un enlace
    # con clave propia de la publicacion (/d/<token>/...): quien recibe el correo
    # puede generarlos y verlos sin tener usuario en la herramienta.
    identificador = fila.get("id")
    token = (repositorio.token_documento_para(
        identificador, repositorio.ajuste_int("dias_token_documento", 90))
        if identificador else None)
    if token:
        fila["url_documentos"] = {tipo: f"{url_publica()}/d/{token}/{tipo}"
                                  for tipo in ("corto", "ampliado", "infografia")}
    elif identificador:
        fila["url_documentos"] = {tipo: f"{url_publica()}/publicaciones/{identificador}/documento/{tipo}"
                                  for tipo in ("corto", "ampliado", "infografia")}
    else:
        fila["url_documentos"] = None
    return fila


def componer(publicaciones: list[dict], fecha: date, resumen_boletines: dict,
             tokens: dict[int, str] | None = None, modo: str = "diario",
             retraso: bool = False) -> str:
    """Genera el HTML del correo. tokens: {publicacion_id: token}.

    modo: "diario" (el de las 07:45), "tarde" (comprobacion de las 20:00) o
    "alerta" (correo urgente aparte). Todos comparten plantilla.
    """
    tokens = tokens or {}
    por_comunidad: dict[str, list[dict]] = {}
    for publicacion in publicaciones:
        comunidad = publicacion.get("comunidad") or "Sin comunidad"
        fila = preparar_fila(publicacion, tokens.get(publicacion.get("id")))
        por_comunidad.setdefault(comunidad, []).append(fila)

    for filas in por_comunidad.values():
        filas.sort(key=lambda f: (0 if f.get("relevancia") == "alta" else 1,
                                  f.get("plazo_fin") or "9999", f.get("titulo", "")))

    plantilla = _entorno().get_template("correo_diario.html")
    return plantilla.render(
        nombre_app=config.NOMBRE_APP,
        modo=modo,
        aviso_modo=MODOS.get(modo, ""),
        retraso=retraso,
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


def asunto(fecha: date, total: int, altas: int, modo: str = "diario",
           retraso: bool = False) -> str:
    texto = _asunto(fecha, total, altas, modo)
    return f"{texto} (enviado con retraso)" if retraso else texto


def _asunto(fecha: date, total: int, altas: int, modo: str) -> str:
    if modo == "alerta":
        return (f"[URGENTE] [MOVA Boletines] {total} convocatoria(s) de alta relevancia "
                f"con plazo corto")
    if modo == "tarde":
        return (f"[MOVA Boletines] {fecha_larga(fecha)} - comprobacion de la tarde: "
                f"{total} nueva(s), {altas} de alta relevancia")
    if total == 0:
        return f"[MOVA Boletines] {fecha_larga(fecha)} - sin novedades"
    return (f"[MOVA Boletines] {fecha_larga(fecha)} - {total} convocatoria(s), "
            f"{altas} de alta relevancia")


def componer_semanal(desde: date, hasta: date, publicaciones: list[dict],
                     vencimientos: list[dict], dias_vencimiento: int,
                     hoy: date | None = None) -> str:
    """Resumen semanal: lo publicado la semana anterior y los plazos que vencen."""
    filas = [preparar_fila(p, hoy=hoy) for p in publicaciones]
    altas = [f for f in filas if f.get("relevancia") == "alta"]
    resto = [f for f in filas if f.get("relevancia") != "alta"]
    por_comunidad: dict[str, int] = {}
    for fila in filas:
        comunidad = fila.get("comunidad") or "Sin comunidad"
        por_comunidad[comunidad] = por_comunidad.get(comunidad, 0) + 1

    plantilla = _entorno().get_template("correo_semanal.html")
    return plantilla.render(
        nombre_app=config.NOMBRE_APP,
        desde=fecha_larga(desde),
        hasta=fecha_larga(hasta),
        total=len(filas),
        altas=altas,
        resto=resto,
        por_comunidad=dict(sorted(por_comunidad.items(), key=lambda x: -x[1])),
        vencimientos=[preparar_fila(v, hoy=hoy) for v in vencimientos],
        dias_vencimiento=dias_vencimiento,
        marcador=config.MARCADOR_PENDIENTE,
        url_publica=url_publica(),
        generado=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


def asunto_semanal(desde: date, hasta: date, total: int, vencen: int) -> str:
    return (f"[MOVA Boletines] Resumen semanal {desde:%d/%m} - {hasta:%d/%m}: "
            f"{total} convocatoria(s), {vencen} plazo(s) por vencer")


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
           reintentos: int = 3, urgente: bool = False) -> tuple[bool, str, int]:
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
    if urgente:
        # Outlook, Thunderbird y Gmail entienden estas cabeceras como "importante".
        mensaje["X-Priority"] = "1"
        mensaje["Importance"] = "High"
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
