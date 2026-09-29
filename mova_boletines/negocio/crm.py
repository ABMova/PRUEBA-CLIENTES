"""Lo que esta herramienta le ofrece al CRM de MOVA.

El correo diario lleva dos botones ("Enviar al CRM" y "Acciones") que abren una
pantalla del CRM. Es el CRM quien viene aqui a buscar los datos de la ayuda, no
al reves. Se hace en ese sentido a proposito:

  - la clave compartida vive solo en el CRM, nunca viaja en un correo;
  - esta herramienta solo expone LECTURA: desde fuera no se puede escribir nada;
  - el CRM exige sesion antes de abrir la pantalla, asi que queda registrado
    quien da de alta el programa y solo pueden hacerlo los correos autorizados.

Los botones se pintan solo a los destinatarios que figuran en el ajuste
`crm_correos`; al resto del equipo el correo le llega igual, pero sin ellos.
"""
from __future__ import annotations

import json
import secrets
from urllib.parse import quote

from datos import repositorio

CABECERA_CLAVE = "X-Clave-CRM"


def url() -> str:
    return (repositorio.ajuste("crm_url", "") or "").strip().rstrip("/")


def clave() -> str:
    return (repositorio.ajuste("crm_clave", "") or "").strip()


def activo() -> bool:
    """Hay CRM configurado y con clave: si falta algo, los botones no se pintan."""
    return repositorio.ajuste("crm_activo", "0") == "1" and bool(url()) and bool(clave())


def correos_autorizados() -> list[str]:
    """Quien ve los botones. Vacio = todos los destinatarios."""
    crudo = repositorio.ajuste("crm_correos", "") or ""
    return [t.strip().lower() for t in crudo.replace(";", ",").split(",") if t.strip()]


def ve_botones(destinatario: str) -> bool:
    autorizados = correos_autorizados()
    return not autorizados or (destinatario or "").strip().lower() in autorizados


def reparto(destinatarios: list[str]) -> tuple[list[str], list[str]]:
    """Separa los destinatarios en (con botones del CRM, sin ellos)."""
    if not activo():
        return [], list(destinatarios)
    con = [d for d in destinatarios if ve_botones(d)]
    sin = [d for d in destinatarios if d not in con]
    return con, sin


def enlaces(token: str) -> dict[str, str]:
    """Direcciones del CRM a las que apuntan los dos botones del correo.

    "programa" abre el alta del programa para revisarla; "tarea" (el boton
    Acciones) crea directamente una tarea a nombre de quien pulsa.
    """
    if not activo() or not token:
        return {}
    clave = quote(token)
    return {"programa": f"{url()}/Programas/DesdeBoletin?o={clave}",
            "tarea": f"{url()}/Programas/TareaDesdeBoletin?o={clave}"}


ACCIONES = {"programa": "En el CRM", "tarea": "Tarea creada"}


def nombre_de(correo: str) -> str:
    """De 'j.javier@mova.es' a 'J. Javier': el correo entero no cabe en la marca."""
    usuario = (correo or "").split("@")[0].replace("_", ".").replace("-", ".")
    partes = [t for t in usuario.split(".") if t]
    return " ".join(t.capitalize() if len(t) > 1 else t.upper() + "." for t in partes)


def resumen_hecho(filas) -> str:
    """Texto de la marca verde del correo, o cadena vacia si no se ha hecho nada.

    Sale el nombre de quien lo hizo para que el resto del equipo no repita el
    trabajo: es justo lo que se quiere ver desde la bandeja de entrada.
    """
    if not filas:
        return ""
    acciones = []
    personas = []
    for fila in filas:
        rotulo = ACCIONES.get(fila["accion"], fila["accion"])
        if rotulo not in acciones:
            acciones.append(rotulo)
        nombre = nombre_de(fila["usuario"])
        if nombre and nombre not in personas:
            personas.append(nombre)
    texto = " y ".join(acciones)
    return f"{texto} - {', '.join(personas)}" if personas else texto


def clave_valida(recibida: str | None) -> bool:
    guardada = clave()
    if not guardada or not recibida:
        return False
    return secrets.compare_digest(recibida.strip(), guardada)


# Campos de la publicacion que se le entregan al CRM. Lista explicita: asi no se
# escapa nada interno (hash, terminos, justificacion del modelo...) por anadir
# una columna a la tabla.
_CAMPOS = ("id", "codigo_boletin", "comunidad", "boletin_nombre", "fecha_publicacion",
           "titulo", "titulo_resumido", "resumen", "organismo", "plazo", "plazo_fin",
           "plazo_fin_origen", "beneficiarios", "importe", "url_oficial", "url_pdf",
           "seccion", "relevancia", "sectores", "destinatario")


def ficha(fila) -> dict:
    """La ayuda tal y como la recibe el CRM, con el detalle del resumen si lo hay.

    `detalle` es el JSON que extrajo la IA para los resumenes (actuaciones,
    gastos, cuantias, condiciones de financiacion...). Solo existe si alguien ha
    pulsado antes alguno de los botones de resumen; si no, el CRM rellena la
    ficha con lo basico y el resto lo completa la persona.
    """
    datos = {campo: fila[campo] for campo in _CAMPOS}
    documento = repositorio.documento(fila["id"])
    detalle = {}
    if documento is not None and documento["estado"] == "listo":
        try:
            detalle = json.loads(documento["datos_json"] or "{}")
        except json.JSONDecodeError:
            detalle = {}
    return {
        "publicacion": datos,
        "detalle": detalle,
        "documentos": {
            "estado": documento["estado"] if documento is not None else "pendiente",
            "tipos": ["corto", "ampliado", "infografia"],
        },
    }
