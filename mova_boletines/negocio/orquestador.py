"""Orquestador del proceso diario: seis fases en un hilo de fondo.

El progreso vive en memoria (la interfaz lo consulta cada 2 segundos), de ahi
que la aplicacion deba correr en UN solo proceso con varios hilos.
"""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Callable

import config
from datos import repositorio
from integraciones import anthropic_cliente
from negocio import correo, deduplicador, palabras, relevancia, titulos
from negocio.boletines import ADAPTADORES, ORDEN
from negocio.boletines.base import ErrorBoletin
from negocio.extraccion import normalizar_titulo, recortar

registro = logging.getLogger(__name__)

FASES = [
    "Extraccion de boletines",
    "Filtro de palabras clave",
    "Extraccion de datos con IA",
    "Analisis de relevancia",
    "Deduplicacion e historico",
    "Correo diario",
]


class Progreso:
    """Estado compartido de la ejecucion en curso."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reiniciar()

    def reiniciar(self) -> None:
        with self._lock:
            self.activo = False
            self.ejecucion_id: int | None = None
            self.fase = ""
            self.numero_fase = 0
            self.boletin = ""
            self.porcentaje = 0
            self.registro: list[str] = []
            self.resultado = ""
            self.cancelar = False
            self.terminado_en: str | None = None

    def preparar(self) -> None:
        """Marca la ejecucion como activa ANTES de arrancar el hilo.

        Si se dejara para el hilo, una consulta de progreso inmediata (o un
        segundo clic en Ejecutar ahora) veria el sistema libre.
        """
        self.reiniciar()
        with self._lock:
            self.activo = True

    def iniciar(self, ejecucion_id: int) -> None:
        with self._lock:
            self.activo = True
            self.ejecucion_id = ejecucion_id

    def anotar(self, mensaje: str) -> None:
        marca = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.registro.append(f"[{marca}] {mensaje}")
            if len(self.registro) > 800:
                self.registro = self.registro[-800:]
        registro.info(mensaje)

    def fijar_fase(self, numero: int, boletin: str = "", porcentaje: int | None = None) -> None:
        with self._lock:
            self.numero_fase = numero
            self.fase = FASES[numero - 1] if 1 <= numero <= len(FASES) else ""
            self.boletin = boletin
            if porcentaje is not None:
                self.porcentaje = max(0, min(100, porcentaje))

    def pedir_cancelacion(self) -> None:
        with self._lock:
            self.cancelar = True
        self.anotar("Cancelacion solicitada por el usuario")

    def cancelado(self) -> bool:
        with self._lock:
            return self.cancelar

    def terminar(self, resultado: str) -> None:
        with self._lock:
            self.activo = False
            self.porcentaje = 100
            self.resultado = resultado
            self.terminado_en = datetime.now().strftime("%H:%M:%S")

    def instantanea(self) -> dict:
        with self._lock:
            return {
                "activo": self.activo,
                "ejecucion_id": self.ejecucion_id,
                "fase": self.fase,
                "numero_fase": self.numero_fase,
                "total_fases": len(FASES),
                "boletin": self.boletin,
                "porcentaje": self.porcentaje,
                "registro": list(self.registro[-200:]),
                "resultado": self.resultado,
                "terminado_en": self.terminado_en,
            }


progreso = Progreso()
_hilo: threading.Thread | None = None
_lock_lanzamiento = threading.Lock()


class Cancelada(Exception):
    """Se levanta cuando el usuario cancela la ejecucion."""


def hay_ejecucion() -> bool:
    return progreso.instantanea()["activo"]


def lanzar(fecha: date | None = None, tipo: str = "manual", usuario: str = "sistema",
           enviar_correo: bool = True) -> tuple[bool, str]:
    """Arranca el pipeline en un hilo. Devuelve (aceptada, mensaje)."""
    global _hilo
    with _lock_lanzamiento:
        if hay_ejecucion():
            return False, "Ya hay una ejecucion en curso"
        objetivo = fecha or date.today()
        progreso.preparar()
        _hilo = threading.Thread(
            target=_ejecutar, args=(objetivo, tipo, usuario, enviar_correo),
            name="pipeline-boletines", daemon=True)
        try:
            _hilo.start()
        except RuntimeError as error:
            progreso.terminar(f"No se pudo arrancar el hilo: {error}")
            return False, f"No se pudo arrancar la ejecucion: {error}"
        return True, f"Ejecucion lanzada para el {objetivo:%d/%m/%Y}"


def cancelar() -> None:
    progreso.pedir_cancelacion()


# ------------------------------------------------------------------ pipeline --
def _ejecutar(fecha: date, tipo: str, usuario: str, enviar_correo: bool) -> None:
    ejecucion_id = repositorio.crear_ejecucion(fecha.strftime("%Y-%m-%d"), tipo, usuario)
    progreso.iniciar(ejecucion_id)
    anthropic_cliente.fijar_ejecucion(ejecucion_id)
    contadores = {"boletines_ok": 0, "boletines_fallidos": 0, "publicaciones_brutas": 0,
                  "candidatas": 0, "nuevas": 0, "alta_relevancia": 0, "llamadas_modelo": 0}
    estado = "correcta"
    detalle = ""

    try:
        progreso.anotar(f"Ejecucion {ejecucion_id} ({tipo}) para el {fecha:%d/%m/%Y}")
        crudas, consultados, fallidos = _fase1(fecha, ejecucion_id, contadores)
        candidatas = _fase2(crudas, contadores)
        guardadas = _fases345(candidatas, ejecucion_id, contadores)
        _fase6(guardadas, fecha, consultados, fallidos, ejecucion_id, enviar_correo, tipo)

        coste = repositorio.coste_de_ejecucion(ejecucion_id)
        if coste:
            progreso.anotar(f"Coste de la ejecucion en la API: {coste:.4f} $")

        if fallidos:
            estado = "con_avisos"
            detalle = "Boletines fallidos: " + ", ".join(f["codigo"] for f in fallidos)
        else:
            detalle = f"{contadores['nuevas']} publicacion(es) nueva(s)"
        progreso.terminar(detalle)

    except Cancelada:
        estado = "cancelada"
        detalle = "Cancelada por el usuario"
        progreso.terminar(detalle)
    except Exception as error:  # noqa: BLE001 - la ejecucion nunca debe tumbar el servicio
        estado = "error"
        detalle = f"{type(error).__name__}: {error}"
        progreso.anotar(f"ERROR: {detalle}")
        registro.error("Fallo de la ejecucion %s: %s", ejecucion_id, traceback.format_exc())
        progreso.terminar(detalle)
    finally:
        anthropic_cliente.fijar_ejecucion(None)
        instantanea = progreso.instantanea()
        repositorio.cerrar_ejecucion(ejecucion_id, estado, detalle,
                                     "\n".join(instantanea["registro"]), contadores)
        repositorio.registrar_auditoria(usuario, "ejecucion_pipeline", str(ejecucion_id),
                                        f"estado={estado}; {detalle}")
        repositorio.cerrar_conexion()


def _comprobar_cancelacion() -> None:
    if progreso.cancelado():
        raise Cancelada


def _fase1(fecha: date, ejecucion_id: int, contadores: dict):
    """Descarga los sumarios. Un boletin caido no tumba a los demas."""
    progreso.fijar_fase(1, porcentaje=2)
    activos = [fila["codigo"] for fila in repositorio.boletines(solo_activos=True)]
    codigos = [codigo for codigo in ORDEN if codigo in activos]
    reintentos = repositorio.ajuste_int("reintentos_boletin", config.REINTENTOS_BOLETIN)
    config.REINTENTOS_BOLETIN = reintentos

    crudas: list[dict] = []
    consultados: list[str] = []
    fallidos: list[dict] = []

    for indice, codigo in enumerate(codigos, start=1):
        _comprobar_cancelacion()
        progreso.fijar_fase(1, codigo, 2 + int(28 * indice / max(1, len(codigos))))
        ficha = repositorio.boletin(codigo)
        inicio = datetime.now()
        try:
            publicaciones = ADAPTADORES[codigo].obtener_publicaciones(fecha)
            duracion = int((datetime.now() - inicio).total_seconds() * 1000)

            # Filtro de fecha: solo entra lo publicado el dia vigilado. Si un
            # boletin devolviera el ultimo numero disponible en lugar de nada,
            # o mezclara dias, aqui se para y queda anotado.
            objetivo = fecha.strftime("%Y-%m-%d")
            de_otro_dia = [p for p in publicaciones if p.fecha and p.fecha != objetivo]
            if de_otro_dia:
                fechas_ajenas = ", ".join(sorted({p.fecha for p in de_otro_dia}))
                progreso.anotar(f"{codigo}: {len(de_otro_dia)} publicacion(es) de otra fecha "
                                f"({fechas_ajenas}) descartadas: solo cuenta el {fecha:%d/%m/%Y}")
                publicaciones = [p for p in publicaciones if not p.fecha or p.fecha == objetivo]
            for publicacion in publicaciones:
                crudas.append({
                    "codigo_boletin": codigo,
                    "comunidad": ficha["comunidad"] if ficha else ADAPTADORES[codigo].COMUNIDAD,
                    "boletin_nombre": ficha["nombre"] if ficha else ADAPTADORES[codigo].NOMBRE,
                    "titulo": publicacion.titulo,
                    "organismo": publicacion.organismo,
                    "seccion": publicacion.seccion,
                    "url_oficial": publicacion.url_oficial,
                    "url_pdf": publicacion.url_pdf,
                    "fecha_publicacion": publicacion.fecha or fecha.strftime("%Y-%m-%d"),
                    "texto": publicacion.texto or publicacion.titulo,
                    "identificador": publicacion.identificador,
                })
            estado = "correcto" if publicaciones else "vacio"
            mensaje = (f"{len(publicaciones)} publicacion(es)" if publicaciones
                       else "sin boletin publicado ese dia")
            repositorio.registrar_scraping(ejecucion_id, codigo, fecha.strftime("%Y-%m-%d"),
                                           estado, len(publicaciones), 1, duracion,
                                           ADAPTADORES[codigo].URL_COMPROBADA, mensaje)
            repositorio.actualizar_estado_boletin(codigo, estado, mensaje)
            consultados.append(codigo)
            contadores["boletines_ok"] += 1
            progreso.anotar(f"{codigo}: {mensaje}")
        except (ErrorBoletin, Exception) as error:  # noqa: BLE001
            duracion = int((datetime.now() - inicio).total_seconds() * 1000)
            motivo = f"{type(error).__name__}: {error}"[:300]
            repositorio.registrar_scraping(ejecucion_id, codigo, fecha.strftime("%Y-%m-%d"),
                                           "error", 0, reintentos, duracion,
                                           ADAPTADORES[codigo].URL_COMPROBADA, motivo)
            repositorio.actualizar_estado_boletin(codigo, "error", motivo)
            fallidos.append({"codigo": codigo, "motivo": motivo})
            contadores["boletines_fallidos"] += 1
            progreso.anotar(f"{codigo}: FALLO - {motivo}")

    contadores["publicaciones_brutas"] = len(crudas)
    progreso.anotar(f"Fase 1 terminada: {len(crudas)} publicaciones brutas")
    return crudas, consultados, fallidos


def _fase2(crudas: list[dict], contadores: dict) -> list[dict]:
    """Filtro determinista. Pasa lo que tenga al menos una palabra clave.

    Un boletin como el BOCM publica su texto integro y terminos como "orden" o
    "empleo" aparecen en casi todo: un dia corriente deja mas de mil candidatas.
    Por eso hay un tope configurable (max_candidatas_ejecucion) que se aplica
    despues de ordenar por fuerza de la coincidencia, para que el presupuesto
    de modelo se gaste primero en lo que de verdad parece una convocatoria.
    """
    progreso.fijar_fase(2, porcentaje=32)
    terminos = [fila["termino"] for fila in repositorio.palabras_clave(solo_activas=True)]
    candidatas: list[dict] = []

    for publicacion in crudas:
        _comprobar_cancelacion()
        texto = f"{publicacion['titulo']} {publicacion.get('texto', '')}"
        coincidencia = palabras.buscar(texto, terminos)
        if coincidencia.hay:
            publicacion["terminos"] = ", ".join(coincidencia.terminos)
            publicacion["contextos"] = repositorio.json_seguro(coincidencia.contextos)
            publicacion["_puntuacion"] = coincidencia.puntuacion
            candidatas.append(publicacion)

    encontradas = len(candidatas)
    tope = repositorio.ajuste_int("max_candidatas_ejecucion", 150)
    if tope > 0 and encontradas > tope:
        candidatas.sort(key=lambda p: p.get("_puntuacion", 0), reverse=True)
        descartadas = encontradas - tope
        candidatas = candidatas[:tope]
        progreso.anotar(
            f"AVISO: {encontradas} candidatas superan el tope de {tope}. Se analizan las "
            f"{tope} con coincidencias mas fuertes y quedan {descartadas} sin analizar. "
            f"Sube el tope en Ajustes o afina las palabras clave si quieres cubrirlas.")

    contadores["candidatas"] = len(candidatas)
    progreso.fijar_fase(2, porcentaje=38)
    progreso.anotar(f"Fase 2 terminada: {len(candidatas)} candidatas de {len(crudas)} "
                    f"({encontradas} con coincidencia)")
    return candidatas


def _fases345(candidatas: list[dict], ejecucion_id: int, contadores: dict) -> list[dict]:
    """Extraccion con IA, relevancia y deduplicacion."""
    progreso.fijar_fase(3, porcentaje=40)
    if not candidatas:
        progreso.anotar("Sin candidatas: no se llama al modelo")
        return []

    modelo_extraccion = repositorio.ajuste("modelo_extraccion", "claude-sonnet-5")
    modelo_relevancia = repositorio.ajuste("modelo_relevancia", "claude-haiku-4-5-20251001")
    tokens_extraccion = repositorio.ajuste_int("max_tokens_extraccion", 2000)
    tokens_relevancia = repositorio.ajuste_int("max_tokens_relevancia", 600)
    hilos = max(1, repositorio.ajuste_int("hilos_modelo", 3))
    refuerzos = [t.strip() for t in repositorio.ajuste("terminos_refuerzo", "").split(",") if t.strip()]
    hay_modelo = anthropic_cliente.hay_clave()
    motivo_sin_modelo = "No hay clave de API configurada: sin analisis del modelo"
    if not hay_modelo:
        progreso.anotar("AVISO: no hay clave de API; las publicaciones se guardan para revision manual")
    else:
        queda, gasto, tope = anthropic_cliente.presupuesto()
        if not queda:
            hay_modelo = False
            motivo_sin_modelo = (f"Tope de gasto mensual alcanzado ({gasto:.2f} de {tope:.2f} $): "
                                 f"sin analisis del modelo")
            progreso.anotar(f"AVISO: {motivo_sin_modelo}. Se guardan para revision manual.")
        elif tope > 0:
            progreso.anotar(f"Gasto del mes antes de esta ejecucion: {gasto:.2f} de {tope:.2f} $")

    # ---- Fase 5 primero sobre el hash, para no pagar modelo por duplicados ----
    umbral = repositorio.ajuste_int("umbral_difuso", 92)
    dias = repositorio.ajuste_int("dias_dedup", 30)
    recientes = [dict(fila) for fila in repositorio.titulos_recientes(dias)]
    vistos_en_esta_tanda: set[str] = set()
    filtradas: list[dict] = []

    for publicacion in candidatas:
        hash_contenido = deduplicador.calcular_hash(publicacion["codigo_boletin"],
                                                    publicacion["titulo"])
        if hash_contenido in vistos_en_esta_tanda:
            continue
        veredicto = deduplicador.comprobar(
            publicacion["codigo_boletin"], publicacion["titulo"], hash_contenido,
            repositorio.existe_hash(hash_contenido), recientes, umbral)
        if veredicto.duplicada:
            progreso.anotar(f"Duplicada ({veredicto.motivo}): {publicacion['titulo'][:70]}")
            continue
        vistos_en_esta_tanda.add(hash_contenido)
        publicacion["hash_contenido"] = hash_contenido
        publicacion["duplicado_de"] = veredicto.original_id
        filtradas.append(publicacion)

    progreso.anotar(f"Fase 5 (previa): {len(filtradas)} publicaciones nuevas tras deduplicar")

    resultados: list[dict] = []
    total = len(filtradas)

    def procesar(indice_publicacion):
        indice, publicacion = indice_publicacion
        _comprobar_cancelacion()
        publicacion = dict(publicacion)
        publicacion["texto"] = recortar(publicacion.get("texto", ""))

        if not hay_modelo:
            datos = relevancia._esqueleto(publicacion)  # noqa: SLF001 - mismo paquete
            extraccion = relevancia.ResultadoExtraccion(
                datos=datos, revision_manual=True, motivo=motivo_sin_modelo)
            clasificacion = {"relevancia": "media", "sectores": [],
                             "justificacion": config.MARCADOR_PENDIENTE, "llamadas": 0}
        else:
            extraccion = relevancia.extraer(publicacion, modelo_extraccion, tokens_extraccion)
            if not extraccion.datos.get("es_convocatoria_ayuda", True):
                # No es una convocatoria (nombramiento, licitacion, correccion...).
                # Se guarda igualmente con estado 'no_convocatoria' para que su hash
                # quede registrado y no se vuelva a pagar al modelo por lo mismo.
                return {
                    "publicacion": publicacion,
                    "extraccion": extraccion,
                    "clasificacion": {"relevancia": "baja", "sectores": [],
                                      "justificacion": "El modelo la descarta: no es una "
                                                       "convocatoria de ayudas", "llamadas": 0},
                    "es_ayuda": False,
                    "indice": indice,
                }
            clasificacion = relevancia.clasificar(publicacion, extraccion.datos,
                                                 modelo_relevancia, tokens_relevancia, refuerzos)

        return {
            "publicacion": publicacion,
            "extraccion": extraccion,
            "clasificacion": clasificacion,
            "es_ayuda": True,
            "indice": indice,
        }

    with ThreadPoolExecutor(max_workers=hilos, thread_name_prefix="modelo") as ejecutor:
        for numero, salida in enumerate(ejecutor.map(procesar, enumerate(filtradas, start=1)), start=1):
            progreso.fijar_fase(3 if numero <= total / 2 else 4, "",
                                40 + int(40 * numero / max(1, total)))
            if salida is None:
                continue
            resultados.append(salida)
            contadores["llamadas_modelo"] += (salida["extraccion"].llamadas
                                              + salida["clasificacion"].get("llamadas", 0))

    progreso.fijar_fase(5, porcentaje=82)
    guardadas: list[dict] = []
    for salida in resultados:
        publicacion = salida["publicacion"]
        datos = salida["extraccion"].datos
        clasificacion = salida["clasificacion"]
        plazo_fin, plazo_origen = relevancia.fin_de_plazo(datos, publicacion["fecha_publicacion"])
        fila = {
            "ejecucion_id": ejecucion_id,
            "codigo_boletin": publicacion["codigo_boletin"],
            "comunidad": publicacion["comunidad"],
            "boletin_nombre": publicacion["boletin_nombre"],
            "fecha_publicacion": publicacion["fecha_publicacion"],
            "titulo": datos.get("titulo") or publicacion["titulo"],
            "titulo_resumido": (datos.get("titulo_resumido")
                                or titulos.resumir(datos.get("titulo") or publicacion["titulo"])),
            "resumen": datos.get("resumen", config.MARCADOR_PENDIENTE),
            "organismo": datos.get("organismo_convocante") or publicacion.get("organismo")
                         or config.MARCADOR_PENDIENTE,
            "plazo": datos.get("plazo_solicitud", config.MARCADOR_PENDIENTE),
            "plazo_fin": plazo_fin,
            "plazo_fin_origen": plazo_origen,
            "beneficiarios": datos.get("beneficiarios", config.MARCADOR_PENDIENTE),
            "importe": datos.get("importe", config.MARCADOR_PENDIENTE),
            "url_oficial": publicacion.get("url_oficial", ""),
            "url_pdf": publicacion.get("url_pdf", ""),
            "seccion": publicacion.get("seccion", ""),
            "relevancia": clasificacion.get("relevancia", "media"),
            "sectores": ", ".join(clasificacion.get("sectores", [])),
            "justificacion": clasificacion.get("justificacion", ""),
            "confianza": datos.get("confianza", ""),
            "motivo_confianza": datos.get("motivo_confianza", ""),
            "hash_contenido": publicacion["hash_contenido"],
            "titulo_normalizado": normalizar_titulo(publicacion["titulo"]),
            "terminos": publicacion.get("terminos", ""),
            "contextos": publicacion.get("contextos", ""),
            "texto_incompleto": int(publicacion.get("texto_incompleto", 0)),
            "revision_manual": int(salida["extraccion"].revision_manual),
            "motivo_revision": salida["extraccion"].motivo,
            "duplicado_de": publicacion.get("duplicado_de"),
            "estado": "nueva" if salida.get("es_ayuda", True) else "no_convocatoria",
            "json_modelo": relevancia.json_crudo(datos, clasificacion),
        }
        try:
            fila["id"] = repositorio.guardar_publicacion(fila)
        except Exception as error:  # noqa: BLE001 - un choque de hash no tumba la ejecucion
            progreso.anotar(f"No se pudo guardar '{fila['titulo'][:50]}': {error}")
            continue
        if fila["estado"] == "no_convocatoria":
            continue  # queda trazada, pero no va al correo ni cuenta como novedad
        guardadas.append(fila)
        if fila["relevancia"] == "alta":
            contadores["alta_relevancia"] += 1

    contadores["nuevas"] = len(guardadas)
    progreso.anotar(f"Fases 3-5 terminadas: {len(guardadas)} publicaciones guardadas "
                    f"({contadores['alta_relevancia']} de alta relevancia)")
    return guardadas


def _fase6(guardadas: list[dict], fecha: date, consultados: list[str], fallidos: list[dict],
           ejecucion_id: int, enviar_correo: bool, tipo: str = "manual") -> None:
    progreso.fijar_fase(6, porcentaje=86)
    destinatarios = [fila["correo"] for fila in repositorio.destinatarios(solo_activos=True)]
    dias_token = repositorio.ajuste_int("dias_token_descarte", 90)
    modo = "tarde" if tipo == "tarde" else "diario"

    # La comprobacion de la tarde solo escribe si ha aparecido algo nuevo desde
    # la manana: un segundo "sin novedades" al dia seria ruido.
    if modo == "tarde" and not guardadas:
        repositorio.registrar_envio(ejecucion_id, ", ".join(destinatarios),
                                    "Comprobacion de la tarde", "omitido", 0,
                                    "Sin publicaciones nuevas desde la manana: no se envia correo",
                                    0, "")
        progreso.anotar("Comprobacion de la tarde sin novedades: no se envia correo")
        progreso.fijar_fase(6, porcentaje=100)
        return

    tokens: dict[int, str] = {}
    for fila in guardadas:
        if fila.get("id"):
            destino = destinatarios[0] if destinatarios else ""
            tokens[fila["id"]] = repositorio.crear_token_descarte(fila["id"], destino, dias_token)

    _alertas(guardadas, tokens, destinatarios, ejecucion_id, enviar_correo)

    html = correo.componer(guardadas, fecha,
                           {"consultados": consultados, "fallidos": fallidos}, tokens, modo=modo)
    sufijo = "-tarde" if modo == "tarde" else ""
    ruta = correo.guardar_copia(html, f"correo-{fecha:%Y%m%d}-{ejecucion_id}{sufijo}.html")
    asunto = correo.asunto(fecha, len(guardadas),
                           sum(1 for f in guardadas if f["relevancia"] == "alta"), modo=modo)

    if not enviar_correo:
        repositorio.registrar_envio(ejecucion_id, ", ".join(destinatarios), asunto, "omitido", 0,
                                    "Envio omitido por peticion", len(guardadas), str(ruta))
        progreso.anotar(f"Correo generado sin enviar: {ruta.name}")
        return

    exito, detalle, intentos = correo.enviar(destinatarios, asunto, html)
    repositorio.registrar_envio(ejecucion_id, ", ".join(destinatarios), asunto,
                                "enviado" if exito else "error", intentos, detalle,
                                len(guardadas), str(ruta))
    if exito:
        repositorio.marcar_enviadas([f["id"] for f in guardadas if f.get("id")])
        progreso.anotar(f"Correo enviado: {detalle}")
    else:
        progreso.anotar(f"Correo NO enviado: {detalle}")
    progreso.fijar_fase(6, porcentaje=100)


def _alertas(guardadas: list[dict], tokens: dict[int, str], destinatarios: list[str],
             ejecucion_id: int, enviar_correo: bool) -> None:
    """Correo urgente aparte para lo de alta relevancia con el plazo a punto de vencer.

    Se evalua al descubrir la convocatoria. Las que entran mas tarde en la
    ventana de vencimiento las recoge el resumen semanal.
    """
    if repositorio.ajuste("alerta_activa", "1") != "1":
        return
    dias = repositorio.ajuste_int("dias_alerta", 15)
    hoy = date.today()
    ids = [f["id"] for f in guardadas if f.get("id")]
    urgentes = [dict(f) for f in repositorio.pendientes_de_alerta(
        ids, hoy.isoformat(), (hoy + timedelta(days=dias)).isoformat())]
    if not urgentes:
        return

    html = correo.componer(urgentes, hoy, {"consultados": [], "fallidos": []}, tokens,
                           modo="alerta")
    asunto = correo.asunto(hoy, len(urgentes), len(urgentes), modo="alerta")
    ruta = correo.guardar_copia(html, f"alerta-{hoy:%Y%m%d}-{ejecucion_id}.html")
    progreso.anotar(f"ALERTA: {len(urgentes)} convocatoria(s) de alta relevancia vencen en "
                    f"{dias} dias o menos")

    if not enviar_correo:
        repositorio.registrar_envio(ejecucion_id, ", ".join(destinatarios), asunto, "omitido", 0,
                                    "Envio omitido por peticion", len(urgentes), str(ruta))
        return

    exito, detalle, intentos = correo.enviar(destinatarios, asunto, html, urgente=True)
    repositorio.registrar_envio(ejecucion_id, ", ".join(destinatarios), asunto,
                                "enviado" if exito else "error", intentos, detalle,
                                len(urgentes), str(ruta))
    if exito:
        repositorio.marcar_alertadas([u["id"] for u in urgentes])
        progreso.anotar(f"Alerta enviada: {detalle}")
    else:
        progreso.anotar(f"Alerta NO enviada: {detalle}")


# --------------------------------------------------------------- resumen semanal --
def enviar_resumen_semanal(hoy: date | None = None, usuario: str = "planificador",
                           enviar: bool = True) -> tuple[bool, str]:
    """Lo publicado la semana anterior (lunes a domingo) y los plazos que vencen."""
    hoy = hoy or date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    desde = lunes - timedelta(days=7)
    hasta = lunes - timedelta(days=1)
    dias_vencimiento = repositorio.ajuste_int("dias_vencimiento_semanal", 30)

    publicaciones = [dict(f) for f in repositorio.publicaciones_entre(
        desde.isoformat(), hasta.isoformat())]
    vencimientos = [dict(f) for f in repositorio.plazos_que_vencen(
        hoy.isoformat(), (hoy + timedelta(days=dias_vencimiento)).isoformat())]

    html = correo.componer_semanal(desde, hasta, publicaciones, vencimientos, dias_vencimiento,
                                   hoy)
    ruta = correo.guardar_copia(html, f"resumen-semanal-{hasta:%Y%m%d}.html")
    asunto = correo.asunto_semanal(desde, hasta, len(publicaciones), len(vencimientos))
    destinatarios = [fila["correo"] for fila in repositorio.destinatarios(solo_activos=True)]

    if not enviar:
        repositorio.registrar_envio(None, ", ".join(destinatarios), asunto, "omitido", 0,
                                    "Resumen generado sin enviar", len(publicaciones), str(ruta))
        return True, f"Resumen generado sin enviar: {ruta.name}"

    exito, detalle, intentos = correo.enviar(destinatarios, asunto, html)
    repositorio.registrar_envio(None, ", ".join(destinatarios), asunto,
                                "enviado" if exito else "error", intentos, detalle,
                                len(publicaciones), str(ruta))
    repositorio.registrar_auditoria(usuario, "resumen_semanal", f"{desde}..{hasta}", detalle,
                                    resultado="ok" if exito else "error")
    return exito, detalle


# --------------------------------------------------------------- reenvio manual --
def reenviar(ids: list[int], usuario: str) -> tuple[bool, str]:
    """Reenvia por correo una seleccion de publicaciones del historico."""
    filas = [dict(fila) for fila in repositorio.publicaciones_por_ids(ids)]
    if not filas:
        return False, "No se encontraron las publicaciones indicadas"

    destinatarios = [fila["correo"] for fila in repositorio.destinatarios(solo_activos=True)]
    dias_token = repositorio.ajuste_int("dias_token_descarte", 90)
    tokens = {fila["id"]: repositorio.crear_token_descarte(
        fila["id"], destinatarios[0] if destinatarios else "", dias_token) for fila in filas}

    fecha_ref = date.today()
    html = correo.componer(filas, fecha_ref,
                           {"consultados": sorted({f["codigo_boletin"] for f in filas}),
                            "fallidos": []}, tokens)
    asunto = f"[MOVA Boletines] Reenvio manual - {len(filas)} publicacion(es)"
    exito, detalle, intentos = correo.enviar(destinatarios, asunto, html)
    repositorio.registrar_envio(None, ", ".join(destinatarios), asunto,
                                "enviado" if exito else "error", intentos, detalle,
                                len(filas), "")
    repositorio.registrar_auditoria(usuario, "reenvio_manual", ",".join(str(i) for i in ids),
                                    detalle, resultado="ok" if exito else "error")
    return exito, detalle
