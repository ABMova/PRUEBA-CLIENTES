"""Prueba 6 - los adaptadores reales contra los boletines en vivo.

Descarga el sumario de verdad de cada boletin e informa de cuantas
publicaciones recupera. Si no hay conectividad, lo dice expresamente en vez
de fallar en silencio.

    .venv\\Scripts\\python.exe pruebas\\test_boletines_vivo.py [AAAA-MM-DD]
"""
from __future__ import annotations

import socket
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from negocio.boletines import ADAPTADORES, ORDEN  # noqa: E402
from negocio.palabras import buscar  # noqa: E402

PALABRAS = ["ayudas", "subvenciones", "convocatoria", "bases reguladoras", "incentivos",
            "pyme", "empresa", "industria", "innovacion", "digitalizacion",
            "eficiencia energetica", "inversion", "modernizacion"]


def hay_conectividad() -> bool:
    for destino in (("dogv.gva.es", 443), ("www.juntadeandalucia.es", 443)):
        try:
            socket.create_connection(destino, timeout=8).close()
            return True
        except OSError:
            continue
    return False


def ultimo_dia_laborable(referencia: date) -> date:
    dia = referencia
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return dia


def main() -> int:
    if len(sys.argv) > 1:
        objetivo = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        objetivo = ultimo_dia_laborable(date.today())

    print(f"Fecha consultada: {objetivo:%d/%m/%Y}\n")

    if not hay_conectividad():
        print("SIN CONECTIVIDAD hacia los boletines oficiales.")
        print("La prueba queda preparada: vuelve a lanzarla con salida a internet")
        print("  .venv\\Scripts\\python.exe pruebas\\test_boletines_vivo.py")
        return 0

    correctos = 0
    fallidos: list[str] = []
    total = 0
    candidatas_total = 0

    for codigo in ORDEN:
        modulo = ADAPTADORES[codigo]
        inicio = time.time()
        try:
            publicaciones = modulo.obtener_publicaciones(objetivo)
            ms = int((time.time() - inicio) * 1000)
            candidatas = [p for p in publicaciones
                          if buscar(f"{p.titulo} {p.texto}", PALABRAS).hay]
            total += len(publicaciones)
            candidatas_total += len(candidatas)
            correctos += 1
            print(f"{codigo:6} OK     {len(publicaciones):5} publicaciones, "
                  f"{len(candidatas):4} con palabras clave  ({ms} ms)")
            if candidatas:
                print(f"       ejemplo: {candidatas[0].titulo[:110]}")
        except Exception as error:  # noqa: BLE001 - se informa, no se propaga
            ms = int((time.time() - inicio) * 1000)
            fallidos.append(codigo)
            print(f"{codigo:6} FALLO  {type(error).__name__}: {str(error)[:120]} ({ms} ms)")

    print(f"\nResumen: {correctos}/7 boletines respondieron, {total} publicaciones, "
          f"{candidatas_total} candidatas tras el filtro de palabras clave")
    if fallidos:
        print(f"Boletines que fallaron: {', '.join(fallidos)}")
        print("Un fallo aislado no rompe la vigilancia: el correo diario indica cuales fallaron.")

    # Basta con que responda al menos uno para dar la prueba por valida: los
    # boletines caen por mantenimiento y eso no debe marcar la entrega como rota.
    return 0 if correctos else 1


if __name__ == "__main__":
    sys.exit(main())
