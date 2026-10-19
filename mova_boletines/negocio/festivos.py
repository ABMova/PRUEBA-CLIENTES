"""Dias inhabiles para contar plazos administrativos.

Un plazo en dias habiles no cuenta sabados, domingos ni festivos (Ley 39/2015,
art. 30.2), y uno que vence en dia inhabil se prorroga al siguiente habil
(art. 30.5). Para decir una fecha exacta hacen falta, pues, los festivos.

Aqui estan los nacionales (incluidos los que dependen de la Pascua) y los
autonomicos fijos de las comunidades que se vigilan. NO estan los locales, que
cambian de municipio a municipio: por eso el calculo siempre lo advierte.

Si una fecha calculada es critica, se mira el calendario laboral oficial de ese
ano. Esto sirve para ordenar por urgencia y para que el resumen diga una fecha
concreta en vez de "se establece en la convocatoria".
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Fiestas nacionales de fecha fija (las que no se trasladan en la practica).
_NACIONALES_FIJOS = (
    (1, 1),    # Ano Nuevo
    (1, 6),    # Epifania
    (5, 1),    # Fiesta del Trabajo
    (8, 15),   # Asuncion
    (10, 12),  # Fiesta Nacional
    (11, 1),   # Todos los Santos
    (12, 6),   # Constitucion
    (12, 8),   # Inmaculada
    (12, 25),  # Navidad
)

# Autonomicos de fecha fija, por el nombre de comunidad que guarda cada boletin.
_AUTONOMICOS_FIJOS: dict[str, tuple[tuple[int, int], ...]] = {
    "Comunidad Valenciana": ((10, 9),),            # 9 d'Octubre
    "Cataluna": ((6, 24), (9, 11), (12, 26)),      # Sant Joan, Diada, Sant Esteve
    "Andalucia": ((2, 28),),                       # Dia de Andalucia
    "Comunidad de Madrid": ((5, 2),),              # Dos de Mayo
    "Region de Murcia": ((6, 9),),                 # Dia de la Region
    "Castilla-La Mancha": ((5, 31),),              # Dia de la Region
    "Castilla y Leon": ((4, 23),),                 # Villalar
}

# Comunidades donde el Lunes de Pascua es festivo.
_LUNES_DE_PASCUA = ("Cataluna", "Comunidad Valenciana")


def _pascua(ano: int) -> date:
    """Domingo de Resurreccion (algoritmo de Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 - nombre del algoritmo
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


@lru_cache(maxsize=64)
def festivos(ano: int, comunidad: str = "") -> frozenset[date]:
    """Festivos nacionales del ano, mas los de esa comunidad si se conoce."""
    pascua = _pascua(ano)
    dias = {date(ano, mes, dia) for mes, dia in _NACIONALES_FIJOS}
    dias.add(pascua - timedelta(days=2))  # Viernes Santo
    dias.add(pascua - timedelta(days=3))  # Jueves Santo (festivo salvo en Cataluna)

    nombre = (comunidad or "").strip()
    if nombre == "Cataluna":
        dias.discard(pascua - timedelta(days=3))
    for mes, dia in _AUTONOMICOS_FIJOS.get(nombre, ()):
        dias.add(date(ano, mes, dia))
    if nombre in _LUNES_DE_PASCUA:
        dias.add(pascua + timedelta(days=1))
    return frozenset(dias)


def es_habil(dia: date, comunidad: str = "") -> bool:
    """Habil a efectos administrativos: ni sabado, ni domingo, ni festivo."""
    return dia.weekday() < 5 and dia not in festivos(dia.year, comunidad)


def siguiente_habil(dia: date, comunidad: str = "") -> date:
    while not es_habil(dia, comunidad):
        dia += timedelta(days=1)
    return dia
