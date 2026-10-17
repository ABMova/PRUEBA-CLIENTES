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
from typing import Callable, NamedTuple

import config
from datos import repositorio
from integraciones import anthropic_cliente
from negocio import correo, crm, deduplicador, palabras, prefiltro, relevancia, titulos
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
        candidatas = _fase2(crudas, contadores, ejecucion_id)
        guardadas = _fases345(candidatas, ejecucion_id, contadores)
        fallos_correo: list[str] = []
        _fase6(guardadas, fecha, consultados, fallidos, ejecucion_id, enviar_correo, tipo,
               _avisos_del_dia(fecha, contadores), fallos_correo)

        coste = repositorio.coste_de_ejecucion(ejecucion_id)
        if coste:
            progreso.anotar(f"Coste de la ejecucion en la API: {coste:.4f} $")

        if fallidos or fallos_correo:
            estado = "con_avisos"
            partes = []
            if fallidos:
                partes.append("Boletines fallidos: " + ", ".join(f["codigo"] for f in fallidos))
            if fallos_correo:
                partes.append("Sin correo: " + ", ".join(fallos_correo))
            detalle = ". ".join(partes)
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


def _fase2(crudas: list[dict], contadores: dict, ejecucion_id: int | None = None) -> list[dict]:
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

    ruido: dict[str, int] = {}

    for publicacion in crudas:
        _comprobar_cancelacion()
        texto = f"{publicacion['titulo']} {publicacion.get('texto', '')}"
        coincidencia = palabras.buscar(texto, terminos)
        if not coincidencia.hay:
            continue
        # Puestos de trabajo, licitaciones y tramites llevan "convocatoria" o
        # "resolucion" y pasaban el filtro de palabras: se apartan sin pagar al
        # modelo. Si el titulo nombra una ayuda, no se descartan aqui.
        motivo = prefiltro.motivo_ruido(publicacion["titulo"], publicacion.get("seccion", ""),
                                        publicacion.get("organismo", ""))
        if motivo:
            ruido[motivo] = ruido.get(motivo, 0) + 1
            # Se guarda para poder revisarlo en el panel y recuperarlo si hizo falta.
            try:
                repositorio.guardar_apartada(dict(publicacion, motivo=motivo,
                                                  ejecucion_id=ejecucion_id))
            except Exception as error:  # noqa: BLE001 - no tumba la ejecucion
                progreso.anotar(f"No se pudo guardar la apartada: {error}")
            continue
        publicacion["terminos"] = ", ".join(coincidencia.terminos)
        publicacion["contextos"] = repositorio.json_seguro(coincidencia.contextos)
        publicacion["_puntuacion"] = coincidencia.puntuacion
        candidatas.append(publicacion)

    if ruido:
        detalle = ", ".join(f"{n} de {familia}" for familia, n in sorted(ruido.items()))
        progreso.anotar(f"Apartadas sin coste {sum(ruido.values())} publicaciones que nunca son "
                        f"ayudas: {detalle}")
    encontradas = len(candidatas)
    tope = repositorio.ajuste_int("max_candidatas_ejecucion", 150)
    if tope > 0 and encontradas > tope:
        candidatas.sort(key=lambda p: p.get("_puntuacion", 0), reverse=True)
        descartadas = encontradas - tope
        candidatas = candidatas[:tope]
        contadores["sin_analizar"] = descartadas
        progreso.anotar(
            f"AVISO: {encontradas} candidatas superan el tope de {tope}. Se analizan las "
            f"{tope} con coincidencias mas fuertes y quedan {descartadas} sin analizar. "
            f"Sube el tope en Ajustes o afina las palabras clave si quieres cubrirlas.")

    contadores["candidatas"] = len(candidatas)
    progreso.fijar_fase(2, porcentaje=38)
    progreso.anotar(f"Fase 2 terminada: {len(candidatas)} candidatas de {len(crudas)} "
                    f"({encontradas} con coincidencia, {sum(ruido.values())} apartadas sin coste)")
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
            # Dos cosas entran aunque no abran plazo: los planes estrategicos
            # (anuncian por donde iran las ayudas) y las resoluciones que cambian
            # algo de una convocatoria ya publicada (listas de reserva, mas
            # credito, correccion de bases), que afectan a quien la pidio.
            es_estrategia = bool(extraccion.datos.get("es_estrategia"))
            es_seguimiento = bool(extraccion.datos.get("es_seguimiento"))
            if (not extraccion.datos.get("es_convocatoria_ayuda", True)
                    and not es_estrategia and not es_seguimiento):
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
            if (extraccion.datos.get("destinatario") in relevancia.DESTINATARIOS_FUERA
                    and not es_estrategia):
                # Para administraciones publicas o personas fisicas: no interesa.
                # Se guarda oculta (su hash evita volver a pagar al modelo) y no
                # hace falta clasificar su relevancia.
                return {
                    "publicacion": publicacion,
                    "extraccion": extraccion,
                    "clasificacion": {"relevancia": "baja", "sectores": [],
                                      "justificacion": "Fuera de destinatario: se dirige a "
                                                       + ("administraciones publicas"
                                                          if extraccion.datos["destinatario"] == "publico"
                                                          else "personas fisicas"),
                                      "llamadas": 0},
                    "es_ayuda": False,
                    "estado": "fuera_destinatario",
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
            "destinatario": datos.get("destinatario", "no_consta"),
            "es_estrategia": int(bool(datos.get("es_estrategia"))),
            "es_seguimiento": int(bool(datos.get("es_seguimiento"))),
            "estado": ("nueva" if salida.get("es_ayuda", True)
                       else salida.get("estado", "no_convocatoria")),
            "json_modelo": relevancia.json_crudo(datos, clasificacion),
        }
        try:
            fila["id"] = repositorio.guardar_publicacion(fila)
        except Exception as error:  # noqa: BLE001 - un choque de hash no tumba la ejecucion
            progreso.anotar(f"No se pudo guardar '{fila['titulo'][:50]}': {error}")
            continue
        if fila["estado"] in repositorio.ESTADOS_OCULTOS:
            if fila["estado"] == "fuera_destinatario":
                contadores["fuera_destinatario"] = contadores.get("fuera_destinatario", 0) + 1
            continue  # queda trazada, pero no va al correo ni cuenta como novedad
        guardadas.append(fila)
        if fila["relevancia"] == "alta":
            contadores["alta_relevancia"] += 1

    contadores["nuevas"] = len(guardadas)
    fuera = contadores.pop("fuera_destinatario", 0)
    progreso.anotar(f"Fases 3-5 terminadas: {len(guardadas)} publicaciones guardadas "
                    f"({contadores['alta_relevancia']} de alta relevancia)"
                    + (f"; {fuera} descartada(s) por ir a administraciones o personas"
                       if fuera else ""))
    return guardadas


def _avisos_del_dia(fecha: date, contadores: dict) -> list[str]:
    """Lo que hay que decirle al usuario porque puede haberse perdido algo."""
    avisos = []
    sin_exito = repositorio.boletines_sin_exito(fecha.strftime("%Y-%m-%d"))
    if sin_exito:
        avisos.append(
            f"{', '.join(sin_exito)} no ha respondido en ninguna pasada de hoy: lo que publicara "
            f"ese dia no se ha revisado. Se reintenta manana automaticamente.")
    sin_analizar = contadores.pop("sin_analizar", 0)
    if sin_analizar:
        avisos.append(
            f"{sin_analizar} publicacion(es) con palabras clave se han quedado sin analizar por el "
            f"tope diario. Sube el tope en Ajustes si quieres cubrirlas.")
    return avisos


class Envio(NamedTuple):
    """Como fue el envio de un correo que puede salir en dos tandas."""

    alguno: bool                 # llego al menos a una persona
    detalle: str
    rutas: list
    sin_correo: list[str]        # a quien NO le llego, si fallo alguna tanda

    @property
    def completo(self) -> bool:
        return self.alguno and not self.sin_correo


def _enviar_correo(destinatarios: list[str], hacer_html, asunto: str, ejecucion_id: int | None,
                   nombre_copia: str, publicaciones_n: int, enviar_correo: bool,
                   urgente: bool = False) -> Envio:
    """Envia el correo. Si solo algunos ven los botones del CRM, salen dos correos.

    El HTML no puede ser el mismo para todos: los botones de alta en el CRM solo
    se pintan a los destinatarios autorizados (ajuste `crm_correos`). Cuando no
    hay CRM, o lo ve todo el equipo, sigue saliendo un unico correo.

    Si una de las dos tandas falla, el correo llega a medio equipo. Eso no puede
    quedar en silencio: se devuelve a quien no le llego para que la ejecucion
    termine con aviso y se vea en el panel.
    """
    con_crm, sin_crm = crm.reparto(destinatarios)
    grupos = [(grupo, marca) for grupo, marca in ((con_crm, True), (sin_crm, False)) if grupo]
    if not grupos:
        return Envio(False, "No hay destinatarios activos", [], list(destinatarios))

    alguno = False
    detalles: list[str] = []
    rutas = []
    sin_correo: list[str] = []
    for grupo, con in grupos:
        html = hacer_html(con)
        sufijo = "-crm" if con and len(grupos) > 1 else ""
        ruta = correo.guardar_copia(html, nombre_copia.format(sufijo=sufijo))
        rutas.append(ruta)
        if not enviar_correo:
            repositorio.registrar_envio(ejecucion_id, ", ".join(grupo), asunto, "omitido", 0,
                                        "Envio omitido por peticion", publicaciones_n, str(ruta))
            detalles.append("omitido")
            continue
        exito, detalle, intentos = correo.enviar(grupo, asunto, html, urgente=urgente)
        repositorio.registrar_envio(ejecucion_id, ", ".join(grupo), asunto,
                                    "enviado" if exito else "error", intentos, detalle,
                                    publicaciones_n, str(ruta))
        if exito:
            alguno = True
        else:
            sin_correo.extend(grupo)
            detalle = f"{detalle} (no les llego a: {', '.join(grupo)})"
        detalles.append(detalle)
    return Envio(alguno, "; ".join(detalles), rutas, sin_correo)


def _fase6(guardadas: list[dict], fecha: date, consultados: list[str], fallidos: list[dict],
           ejecucion_id: int, enviar_correo: bool, tipo: str = "manual",
           avisos: list[str] | None = None, fallos_correo: list[str] | None = None) -> None:
    progreso.fijar_fase(6, porcentaje=86)
    fallos_correo = fallos_correo if fallos_correo is not None else []
    destinatarios = [fila["correo"] for fila in repositorio.destinatarios(solo_activos=True)]
    dias_token = repositorio.ajuste_int("dias_token_descarte", 90)
    modo = "tarde" if tipo in ("tarde", "tarde_recuperada") else "diario"
    # Un dia que se repite porque un boletin estaba caido solo escribe si trae algo.
    if tipo == "boletin_recuperado" and not guardadas and not avisos:
        progreso.anotar("Reintento del boletin caido sin novedades: no se envia correo")
        repositorio.registrar_envio(ejecucion_id, "", "Reintento de boletin caido", "omitido", 0,
                                    "Sin publicaciones nuevas", 0, "")
        progreso.fijar_fase(6, porcentaje=100)
        return
    # Recuperada al encender el equipo: el correo avisa de que llega tarde.
    retraso = tipo in ("recuperada", "tarde_recuperada", "boletin_recuperado")

    # La comprobacion de la tarde solo escribe si ha aparecido algo nuevo desde
    # la manana: un segundo "sin novedades" al dia seria ruido.
    if modo == "tarde" and not guardadas and not avisos:
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

    def hacer_html(con_crm: bool) -> str:
        return correo.componer(guardadas, fecha,
                               {"consultados": consultados, "fallidos": fallidos}, tokens,
                               modo=modo, retraso=retraso, avisos=avisos or [], con_crm=con_crm)

    sufijo = "-tarde" if modo == "tarde" else ""
    asunto = correo.asunto(fecha, len(guardadas),
                           sum(1 for f in guardadas if f["relevancia"] == "alta"), modo=modo,
                           retraso=retraso)
    envio = _enviar_correo(
        destinatarios, hacer_html, asunto, ejecucion_id,
        f"correo-{fecha:%Y%m%d}-{ejecucion_id}{sufijo}{{sufijo}}.html", len(guardadas),
        enviar_correo)

    if not enviar_correo:
        if envio.rutas:
            progreso.anotar(f"Correo generado sin enviar: {envio.rutas[0].name}")
        return

    if envio.alguno:
        # Se marcan como enviadas aunque haya fallado una tanda: a quien si le
        # llego no se le puede mandar otra vez lo mismo manana.
        repositorio.marcar_enviadas([f["id"] for f in guardadas if f.get("id")])
        progreso.anotar(f"Correo enviado: {envio.detalle}")
    else:
        progreso.anotar(f"Correo NO enviado: {envio.detalle}")
    if envio.sin_correo:
        progreso.anotar(f"AVISO: el correo no ha llegado a {', '.join(envio.sin_correo)}. "
                        f"Revisa el SMTP y reenvialo desde Publicaciones.")
        fallos_correo.extend(envio.sin_correo)
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

    def hacer_html(con_crm: bool) -> str:
        return correo.componer(urgentes, hoy, {"consultados": [], "fallidos": []}, tokens,
                               modo="alerta", con_crm=con_crm)

    asunto = correo.asunto(hoy, len(urgentes), len(urgentes), modo="alerta")
    progreso.anotar(f"ALERTA: {len(urgentes)} convocatoria(s) de alta relevancia vencen en "
                    f"{dias} dias o menos")
    envio = _enviar_correo(
        destinatarios, hacer_html, asunto, ejecucion_id,
        f"alerta-{hoy:%Y%m%d}-{ejecucion_id}{{sufijo}}.html", len(urgentes), enviar_correo,
        urgente=True)

    if not enviar_correo:
        return

    if envio.alguno:
        repositorio.marcar_alertadas([u["id"] for u in urgentes])
        progreso.anotar(f"Alerta enviada: {envio.detalle}")
    else:
        progreso.anotar(f"Alerta NO enviada: {envio.detalle}")
    if envio.sin_correo:
        progreso.anotar(f"AVISO: la alerta no ha llegado a {', '.join(envio.sin_correo)}")


def analizar_apartada(apartada_id: int, usuario: str = "sistema") -> tuple[bool, str]:
    """Pasa por la IA una publicacion que el filtro previo habia apartado.

    Es lo que ocurre al pulsar "Analizar" en la pantalla de descartadas: cuesta
    una llamada al modelo y, si resulta ser una ayuda, entra en el historico.
    """
    fila = repositorio.apartada(apartada_id)
    if fila is None:
        return False, "Esa publicacion apartada ya no existe"
    if fila["estado"] == "analizada":
        return False, "Ya se analizo"
    if not anthropic_cliente.hay_clave():
        return False, "No hay clave de API configurada"

    publicacion = {
        "codigo_boletin": fila["codigo_boletin"], "comunidad": fila["comunidad"],
        "boletin_nombre": fila["boletin_nombre"], "fecha_publicacion": fila["fecha_publicacion"],
        "titulo": fila["titulo"], "seccion": fila["seccion"], "organismo": fila["organismo"],
        "url_oficial": fila["url_oficial"], "url_pdf": fila["url_pdf"],
        "texto": fila["texto"] or fila["titulo"], "terminos": "", "contextos": "",
    }
    modelo = repositorio.ajuste("modelo_extraccion", "claude-haiku-4-5-20251001")
    tokens = repositorio.ajuste_int("max_tokens_extraccion", 2000)
    extraccion = relevancia.extraer(publicacion, modelo, tokens)
    datos = extraccion.datos
    clasificacion = relevancia.clasificar(
        publicacion, datos, repositorio.ajuste("modelo_relevancia", "claude-haiku-4-5-20251001"),
        repositorio.ajuste_int("max_tokens_relevancia", 600),
        [t.strip() for t in repositorio.ajuste("terminos_refuerzo", "").split(",") if t.strip()])

    plazo_fin, plazo_origen = relevancia.fin_de_plazo(datos, fila["fecha_publicacion"])
    hash_contenido = deduplicador.calcular_hash(fila["codigo_boletin"], fila["titulo"])
    guardada = {
        "ejecucion_id": None, "codigo_boletin": fila["codigo_boletin"],
        "comunidad": fila["comunidad"], "boletin_nombre": fila["boletin_nombre"],
        "fecha_publicacion": fila["fecha_publicacion"],
        "titulo": datos.get("titulo") or fila["titulo"],
        "titulo_resumido": datos.get("titulo_resumido") or titulos.resumir(fila["titulo"]),
        "resumen": datos.get("resumen", config.MARCADOR_PENDIENTE),
        "organismo": datos.get("organismo_convocante") or fila["organismo"],
        "plazo": datos.get("plazo_solicitud", config.MARCADOR_PENDIENTE),
        "plazo_fin": plazo_fin, "plazo_fin_origen": plazo_origen,
        "beneficiarios": datos.get("beneficiarios", config.MARCADOR_PENDIENTE),
        "importe": datos.get("importe", config.MARCADOR_PENDIENTE),
        "url_oficial": fila["url_oficial"], "url_pdf": fila["url_pdf"],
        "seccion": fila["seccion"], "relevancia": clasificacion.get("relevancia", "media"),
        "sectores": ", ".join(clasificacion.get("sectores", [])),
        "justificacion": clasificacion.get("justificacion", ""),
        "confianza": datos.get("confianza", ""), "motivo_confianza": datos.get("motivo_confianza", ""),
        "hash_contenido": hash_contenido,
        "titulo_normalizado": normalizar_titulo(fila["titulo"]),
        "terminos": "", "contextos": "", "texto_incompleto": 0,
        "revision_manual": int(extraccion.revision_manual), "motivo_revision": extraccion.motivo,
        "duplicado_de": None, "destinatario": datos.get("destinatario", "no_consta"),
        "es_estrategia": int(bool(datos.get("es_estrategia"))),
        "es_seguimiento": int(bool(datos.get("es_seguimiento"))),
        "estado": "nueva", "json_modelo": relevancia.json_crudo(datos, clasificacion),
    }
    if repositorio.existe_hash(hash_contenido):
        repositorio.marcar_apartada(apartada_id, "analizada")
        return False, "Esa publicacion ya estaba en el historico"
    repositorio.guardar_publicacion(guardada)
    repositorio.marcar_apartada(apartada_id, "analizada")
    repositorio.registrar_auditoria(usuario, "apartada_analizada", str(apartada_id),
                                    guardada["titulo"][:120])
    return True, f"Analizada y guardada como {clasificacion.get('relevancia', 'media')} relevancia"


# --------------------------------------------------------------- resumen semanal --
def enviar_seguimiento(usuario: str = "planificador", enviar: bool = True) -> tuple[bool, str]:
    """Correo con la lista de seguimiento del equipo (lunes, miercoles y viernes).

    Lleva lo que alguien marco con el boton Seguimiento y sigue con el plazo
    abierto; lo vencido sale solo de la lista. Si no hay nada marcado no se
    manda nada: un correo vacio cada dos dias seria ruido.
    """
    filas = [dict(f) for f in repositorio.en_seguimiento()]
    destinatarios = [fila["correo"] for fila in repositorio.destinatarios(solo_activos=True)]
    if not filas:
        return True, "No hay nada en seguimiento: no se envia correo"
    if not destinatarios:
        return False, "No hay destinatarios activos"

    hoy = date.today()
    dias_token = repositorio.ajuste_int("dias_token_descarte", 90)
    tokens = {f["id"]: repositorio.crear_token_descarte(f["id"], destinatarios[0], dias_token)
              for f in filas}

    def hacer_html(con_crm: bool) -> str:
        return correo.componer(filas, hoy, {"consultados": [], "fallidos": []}, tokens,
                               modo="seguimiento", con_crm=con_crm)

    asunto = correo.asunto_seguimiento(len(filas))
    envio = _enviar_correo(destinatarios, hacer_html, asunto, None,
                           f"seguimiento-{hoy:%Y%m%d}{{sufijo}}.html", len(filas), enviar)
    repositorio.registrar_auditoria(usuario, "correo_seguimiento", str(len(filas)), envio.detalle,
                                    resultado="ok" if envio.completo or not enviar else "error")
    if not enviar:
        return True, f"Seguimiento generado sin enviar: {envio.rutas[0].name if envio.rutas else ''}"
    return envio.completo, envio.detalle


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
    if exito:  # la recuperacion al encender no lo vuelve a mandar esta semana
        repositorio.guardar_ajuste("semanal_ultima_semana", lunes.isoformat())
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

    def hacer_html(con_crm: bool) -> str:
        return correo.componer(filas, fecha_ref,
                               {"consultados": sorted({f["codigo_boletin"] for f in filas}),
                                "fallidos": []}, tokens, con_crm=con_crm)

    # Como el correo diario: los botones del CRM solo para quien puede usarlos.
    asunto = f"[MOVA Boletines] Reenvio manual - {len(filas)} publicacion(es)"
    envio = _enviar_correo(destinatarios, hacer_html, asunto, None,
                           f"reenvio-{fecha_ref:%Y%m%d}{{sufijo}}.html", len(filas), True)
    exito, detalle = envio.completo, envio.detalle
    repositorio.registrar_auditoria(usuario, "reenvio_manual", ",".join(str(i) for i in ids),
                                    detalle, resultado="ok" if exito else "error")
    return exito, detalle
