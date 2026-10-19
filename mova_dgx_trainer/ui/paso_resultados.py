"""Paso 5 · Resultados: KPIs, veredicto, ejecuciones y gráficas frente a la línea base."""
from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtWidgets import QHBoxLayout, QWidget

from nucleo import graficas
from ui.paso_base import PasoBase
from ui.widgets.comun import boton, etiqueta
from ui.widgets.distintivo_estado import Distintivo
from ui.widgets.kpi import RejillaKpi
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta

KPI_METRICA, KPI_MEJORA, KPI_DURACION, KPI_REINTENTOS = (
    "Métrica principal (mejor ejecución)", "Mejora sobre la línea base",
    "Duración total (s)", "Reintentos")


class PasoResultados(PasoBase):
    titulo = "Resultados"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        resumen = Tarjeta("Resumen")
        cab = QHBoxLayout()
        self.veredicto = Distintivo("pend")
        self.explicacion = etiqueta("", "apoyo")
        cab.addWidget(etiqueta("Veredicto de la mejor ejecución:"))
        cab.addWidget(self.veredicto)
        cab.addWidget(self.explicacion, 1)
        resumen.anadir(cab)
        self.kpis = RejillaKpi([KPI_METRICA, KPI_MEJORA, KPI_DURACION, KPI_REINTENTOS])
        resumen.anadir(self.kpis)
        acciones = QHBoxLayout()
        acciones.addStretch(1)
        acciones.addWidget(boton("Ir al informe", "principal",
                                 lambda: self.estado_ui.ir_a.emit("informe")))
        resumen.anadir(acciones)
        self.capa.addWidget(resumen)

        graf = Tarjeta("Gráficas", "Serie del modelo en dorado; línea base en gris.")
        self.zona_graficas = QHBoxLayout()
        graf.anadir(self.zona_graficas)
        self.capa.addWidget(graf)

        fila = QHBoxLayout()
        fila.setSpacing(12)
        ej = Tarjeta("Ejecuciones y reintentos")
        self.tabla = TablaExportable(["Id", "Intento", "Motivo", "Estado", "Veredicto",
                                      "Métrica", "Duración (s)", "Motivos del veredicto"],
                                     coord.exportar_tabla, "resultados")
        ej.anadir(self.tabla)
        fila.addWidget(ej, 3)
        met = Tarjeta("Métricas en test: modelo frente a línea base")
        self.tabla_metricas = TablaExportable(["Métrica", "Modelo", "Línea base"],
                                              coord.exportar_tabla, "metricas")
        met.anadir(self.tabla_metricas)
        fila.addWidget(met, 2)
        self.capa.addLayout(fila)
        self._lienzos: list[QWidget] = []

    def al_mostrar(self) -> None:
        if not self.pid:
            return
        r = self.servicio(self.coord.resumen_resultados, self.pid)
        if not r:
            return
        k = r["kpis"]
        nombre = k["metrica_nombre"]
        self.kpis.kpis[KPI_METRICA].fijar(
            f"{k['metrica_valor']:.4f}" if k["metrica_valor"] is not None else None,
            "sin ejecuciones correctas", nombre)
        self.kpis.kpis[KPI_MEJORA].fijar(
            f"{k['mejora']:+.4f}" if k["mejora"] is not None else None, "mejora", nombre)
        self.kpis.kpis[KPI_DURACION].fijar(
            f"{k['duracion_s']:.1f}" if k["duracion_s"] is not None else None, "duración")
        self.kpis.kpis[KPI_REINTENTOS].fijar(
            str(k["reintentos"]) if k["reintentos"] is not None else None, "reintentos")
        mejor = r["mejor"] or {}
        self.veredicto.fijar(mejor.get("veredicto"))
        self.explicacion.setText("; ".join((mejor.get("detalle_veredicto") or {}).get("motivos", [])))

        filas = []
        for e in r["ejecuciones"]:
            v = e.get("detalle_veredicto") or {}
            filas.append([e["id"], e["intento"], e["motivo"], e["estado"], e["veredicto"] or "",
                          f"{e['metrica']:.4f}" if e["metrica"] is not None else "",
                          f"{e['duracion_s']:.1f}" if e["duracion_s"] else "",
                          "; ".join(v.get("motivos", []))])
        self.tabla.cargar(filas, r["ejecuciones"], None, {3: lambda v: v, 4: lambda v: v or "pend"})

        base, m = r["linea_base"], r["metricas_mejor"]
        nombres = [n for n in dict.fromkeys(list(m) + list(base))
                   if n not in ("matriz_confusion", "estrategia")]
        self.tabla_metricas.cargar([[n, f"{m[n]:.4f}" if isinstance(m.get(n), float) else "",
                                     f"{base[n]:.4f}" if isinstance(base.get(n), float) else ""]
                                    for n in nombres])
        self._pintar_graficas(r, nombre)

    def _pintar_graficas(self, r: dict, nombre: str) -> None:
        for w in self._lienzos:
            self.zona_graficas.removeWidget(w)
            w.deleteLater()
        self._lienzos = []
        figuras = []
        ok = [{"etiqueta": f"#{e['id']}", "valor": e["metrica"]}
              for e in r["ejecuciones"] if e["metrica"] is not None]
        if ok:
            figuras.append(graficas.comparacion_ejecuciones(ok, r["linea_base"].get(nombre), nombre))
        m = r["metricas_mejor"]
        if m.get("matriz_confusion"):
            figuras.append(graficas.matriz_confusion(m["matriz_confusion"]))
        elif r.get("ruta_predicciones") and Path(r["ruta_predicciones"]).exists():
            import pandas as pd
            p = pd.read_csv(r["ruta_predicciones"], encoding="utf-8")
            figuras.append(graficas.real_frente_predicho(p["y_real"].astype(float).tolist(),
                                                         p["y_pred"].astype(float).tolist()))
        if r["mejor"] and r["mejor"].get("curva"):
            figuras.append(graficas.curva_entrenamiento(r["mejor"]["curva"]))
        if not figuras:
            aviso = etiqueta("[PENDIENTE: gráficas] Aún no hay ejecuciones correctas.")
            aviso.setProperty("pendiente", "true")
            self.zona_graficas.addWidget(aviso)
            self._lienzos.append(aviso)
            return
        for f in figuras:
            lienzo = FigureCanvasQTAgg(f)
            lienzo.setMinimumHeight(260)
            self.zona_graficas.addWidget(lienzo, 1)
            self._lienzos.append(lienzo)
