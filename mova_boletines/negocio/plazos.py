"""Calculo determinista del fin del plazo de solicitud.

El plazo llega como texto libre ("del 1 al 30 de octubre de 2026", "10 dias
habiles desde el dia siguiente a la publicacion", "un mes a contar desde..."):
para alertar, ordenar por urgencia y decirlo en el resumen hace falta una fecha.
Este modulo la saca del texto SIN IA, porque los modelos calculan fechas mal, y
deja escrito como la ha sacado:

  - "fecha_literal": el texto trae la fecha escrita. Se toma la mas tardia.
  - "calculado": el texto da una duracion contada desde la publicacion.

Reglas (Ley 39/2015, arts. 30 y 31):
  - se cuenta desde el DIA SIGUIENTE al de la publicacion;
  - en dias habiles no cuentan sabados, domingos ni festivos;
  - en dias naturales cuentan todos, pero si el ultimo cae en inhabil, el plazo
    se prorroga al siguiente habil;
  - los meses van de fecha a fecha, y si no existe el dia equivalente (31 en un
    mes de 30), vence el ultimo del mes.

Si no se puede deducir sin suponer nada, devuelve None. Nunca adivina.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import NamedTuple

from negocio.extraccion import normalizar
from negocio.festivos import es_habil, siguiente_habil

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}
_NOMBRE_MES = {numero: nombre for nombre, numero in MESES.items() if nombre != "setiembre"}

_NUMEROS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veinticinco": 25, "treinta": 30, "cuarenta": 40,
    "cuarenta y cinco": 45, "sesenta": 60, "noventa": 90,
}

_FECHA_TEXTO = re.compile(
    r"(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")(?:\s+(?:de|del)\s+(\d{4}))?")
_FECHA_NUMERICA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_NUMERO = r"(\d{1,3}|" + "|".join(sorted(_NUMEROS, key=len, reverse=True)) + r")"
_DIAS = re.compile(_NUMERO + r"\s+dias?(\s+habiles|\s+naturales)?")
_MESES_DURACION = re.compile(_NUMERO + r"\s+(mes|meses)\b")

# Una duracion solo se calcula si se cuenta desde la publicacion. "Un mes desde
# la notificacion" o "diez dias desde la solicitud" no dan una fecha fija.
_DESDE_PUBLICACION = re.compile(
    r"(publicacion|publicado|publique|entrada en vigor|a partir del dia siguiente)")
_OTRO_ORIGEN = re.compile(r"desde (la|su) (notificacion|solicitud|resolucion|recepcion)")

# Unas bases reguladoras no abren plazo: dicen cuanto durara el que abra algun
# dia la convocatoria ("se establecera en la convocatoria y sera como minimo de
# quince dias"). Calcular una fecha con eso es inventarse un plazo abierto, que
# es peor que no decir nada. Lo mismo con los topes: un minimo no es un plazo.
_SIN_PLAZO_CIERTO = re.compile(
    r"se\s+(establecer|determinar|fijar|concretar|senalar|indicar)[a-z]*"
    r"[^.]{0,60}?convocatoria"
    r"|en\s+(cada|la\s+respectiva|la\s+correspondiente)\s+convocatoria"
    r"|como\s+(minimo|maximo)|(minimo|maximo)\s+de"
    r"|no\s+(sera|podra\s+ser)\s+(inferior|superior)")

AVISO_LOCALES = "No incluye festivos locales."


class Plazo(NamedTuple):
    """Fecha de fin, de donde sale y como se ha llegado a ella."""

    fin: str | None
    origen: str          # fecha_literal | calculado | ""
    explicacion: str = ""

    @property
    def hay(self) -> bool:
        return bool(self.fin)


def mas_concreta(frases) -> str:
    """De varias frases de plazo, la que mas dice.

    Una que precisa "dias habiles" o "dias naturales" vale mas que un "20 dias"
    a secas, aunque esta ultima venga de una fuente oficial: la ley manda estar
    al texto literal de la convocatoria.
    """
    candidatas = [f.strip() for f in frases if f and "[pendiente" not in f.lower()]
    if not candidatas:
        return ""
    precisas = [f for f in candidatas if re.search(r"dias?\s+(habiles|naturales)", normalizar(f))]
    return (precisas or candidatas)[0]


def fecha_iso(texto: str) -> date | None:
    """Convierte 'AAAA-MM-DD' en fecha; None si no lo es."""
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def en_letra(dia: date) -> str:
    return f"{dia.day} de {_NOMBRE_MES[dia.month]} de {dia.year}"


def _numero(texto: str) -> int | None:
    texto = texto.strip()
    if texto.isdigit():
        return int(texto)
    return _NUMEROS.get(texto)


def _sumar_habiles(publicacion: date, dias: int, comunidad: str) -> date:
    """Cuenta dias habiles a partir del dia siguiente al de la publicacion."""
    actual = publicacion
    contados = 0
    while contados < dias:
        actual += timedelta(days=1)
        if es_habil(actual, comunidad):
            contados += 1
    return actual


def _sumar_meses(publicacion: date, meses: int) -> date:
    """De fecha a fecha: un mes desde el 31 de enero vence el 28 (o 29) de febrero."""
    mes = publicacion.month - 1 + meses
    ano = publicacion.year + mes // 12
    mes = mes % 12 + 1
    dia = min(publicacion.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _prorrogar(vencimiento: date, comunidad: str, motivo: str) -> tuple[date, str]:
    """Si vence en inhabil, pasa al siguiente habil (art. 30.5)."""
    if es_habil(vencimiento, comunidad):
        return vencimiento, ""
    habil = siguiente_habil(vencimiento, comunidad)
    dia_semana = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
    return habil, (f" El dia {motivo} cae en {dia_semana[vencimiento.weekday()]} "
                   f"({vencimiento.strftime('%d/%m/%Y')}), inhabil, por lo que el plazo pasa al "
                   f"siguiente dia habil.")


def fin_de_plazo(plazo: str, fecha_publicacion: str, comunidad: str = "",
                 solo_escritas: bool = False) -> Plazo:
    """Fecha de fin del plazo a partir de su texto y de la fecha de publicacion.

    solo_escritas: la publicacion no es una convocatoria (es una modificacion
    de bases, una adjudicacion, una lista de reserva...), asi que contar dias
    desde SU fecha daria un plazo que no existe. Solo vale una fecha escrita.
    """
    if not plazo or "[pendiente" in plazo.lower():
        return Plazo(None, "")
    try:
        publicada = datetime.strptime(fecha_publicacion, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return Plazo(None, "")

    texto = normalizar(plazo)

    # 1) Fechas escritas: se toma la mas tardia que no sea anterior a la publicacion.
    fechas: list[date] = []
    for dia, mes, ano in _FECHA_TEXTO.findall(texto):
        anio = int(ano) if ano else publicada.year
        try:
            candidata = date(anio, MESES[mes], int(dia))
        except ValueError:
            continue
        if not ano and candidata < publicada:
            candidata = date(anio + 1, MESES[mes], int(dia))
        fechas.append(candidata)
    for dia, mes, ano in _FECHA_NUMERICA.findall(texto):
        try:
            fechas.append(date(int(ano), int(mes), int(dia)))
        except ValueError:
            continue
    validas = [f for f in fechas if f >= publicada]
    if validas:
        fin = max(validas)
        return Plazo(fin.isoformat(), "fecha_literal",
                     f"Finaliza el {en_letra(fin)}. La fecha figura escrita en la convocatoria.")

    # 2) Duraciones contadas desde la publicacion, salvo que la frase sea la de
    #    unas bases y no la de una convocatoria con plazo abierto.
    if solo_escritas or _SIN_PLAZO_CIERTO.search(texto):
        return Plazo(None, "")
    if _OTRO_ORIGEN.search(texto) or not _DESDE_PUBLICACION.search(texto):
        return Plazo(None, "")

    desde = (f"a contar desde el dia siguiente a la publicacion "
             f"({publicada.strftime('%d/%m/%Y')})")

    encontrado = _DIAS.search(texto)
    if encontrado:
        cantidad = _numero(encontrado.group(1))
        if cantidad:
            calificativo = (encontrado.group(2) or "").strip()
            if calificativo == "naturales":
                bruto = publicada + timedelta(days=cantidad)
                fin, prorroga = _prorrogar(bruto, comunidad, str(cantidad))
                return Plazo(fin.isoformat(), "calculado",
                             f"Finaliza el {en_letra(fin)}. Calculo: {cantidad} dias naturales, "
                             f"segun la propia frase del plazo, {desde}.{prorroga} {AVISO_LOCALES}")
            # Sin calificativo, los plazos administrativos se cuentan en habiles.
            fin = _sumar_habiles(publicada, cantidad, comunidad)
            matiz = "" if calificativo else (" El texto no dice si son habiles o naturales: se "
                                             "cuentan habiles, como manda la Ley 39/2015.")
            return Plazo(fin.isoformat(), "calculado",
                         f"Finaliza el {en_letra(fin)}. Calculo: {cantidad} dias habiles (sin "
                         f"sabados, domingos ni festivos), {desde}.{matiz} {AVISO_LOCALES}")

    encontrado = _MESES_DURACION.search(texto)
    if encontrado:
        cantidad = _numero(encontrado.group(1))
        if cantidad:
            bruto = _sumar_meses(publicada, cantidad)
            fin, prorroga = _prorrogar(bruto, comunidad, "de vencimiento")
            plural = "mes" if cantidad == 1 else "meses"
            return Plazo(fin.isoformat(), "calculado",
                         f"Finaliza el {en_letra(fin)}. Calculo: {cantidad} {plural} de fecha a "
                         f"fecha, {desde}.{prorroga} {AVISO_LOCALES}")

    return Plazo(None, "")


def dias_restantes(plazo_fin: str | None, hoy: date | None = None) -> int | None:
    if not plazo_fin:
        return None
    try:
        fin = datetime.strptime(plazo_fin, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (fin - (hoy or date.today())).days
