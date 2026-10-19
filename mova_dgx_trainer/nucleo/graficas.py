"""Gráficas de matplotlib con la paleta MOVA (las usan la UI y el exportador)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=False)
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

FONDO = "#0f1013"
EJES = "#9aa0a6"
SERIE = "#d9b45b"
BASE = "#6b7280"
TEXTO = "#f3f4f6"
MAPA_DORADO = LinearSegmentedColormap.from_list("mova", [FONDO, "#b8892f", "#f0d98c"])


def _figura(ancho: float = 6.4, alto: float = 3.6) -> tuple[Figure, object]:
    fig = Figure(figsize=(ancho, alto), dpi=110, facecolor=FONDO)
    ax = fig.add_subplot(111)
    ax.set_facecolor(FONDO)
    for lado in ax.spines.values():
        lado.set_color(EJES)
    ax.tick_params(colors=EJES, labelsize=8)
    ax.xaxis.label.set_color(EJES)
    ax.yaxis.label.set_color(EJES)
    ax.title.set_color(TEXTO)
    return fig, ax


def comparacion_ejecuciones(ejecuciones: list[dict], valor_base: float | None,
                            nombre_metrica: str) -> Figure:
    """ejecuciones: [{etiqueta, valor}] ; la línea base en gris."""
    fig, ax = _figura()
    etiquetas = [e["etiqueta"] for e in ejecuciones]
    valores = [e["valor"] if e["valor"] is not None else 0 for e in ejecuciones]
    ax.bar(etiquetas, valores, color=SERIE, width=0.6)
    if valor_base is not None:
        ax.axhline(valor_base, color=BASE, linestyle="--", linewidth=1.5,
                   label=f"baseline {valor_base:.3f}")
        ax.legend(facecolor=FONDO, edgecolor=EJES, labelcolor=EJES, fontsize=8)
    ax.set_ylabel(nombre_metrica)
    ax.set_title(f"{nombre_metrica} por ejecución frente a la línea base", fontsize=10)
    fig.tight_layout()
    return fig


def curva_entrenamiento(curva: list[dict]) -> Figure:
    fig, ax = _figura()
    epocas = [c.get("epoca") for c in curva]
    metricas = [c.get("metrica") for c in curva]
    if any(m is not None for m in metricas):
        ax.plot(epocas, metricas, color=SERIE, marker="o", linewidth=1.8, label="métrica (val)")
    perdidas = [c.get("perdida") for c in curva]
    if any(p is not None for p in perdidas):
        ax2 = ax.twinx()
        ax2.plot(epocas, perdidas, color=BASE, marker=".", linewidth=1.2, label="pérdida (val)")
        ax2.tick_params(colors=EJES, labelsize=8)
        for lado in ax2.spines.values():
            lado.set_color(EJES)
        ax2.set_ylabel("pérdida", color=EJES)
    ax.set_xlabel("época / etapa")
    ax.set_ylabel("métrica")
    ax.set_title("Curva de entrenamiento", fontsize=10)
    fig.tight_layout()
    return fig


def matriz_confusion(matriz: dict) -> Figure:
    etiquetas, valores = matriz["etiquetas"], matriz["valores"]
    fig, ax = _figura(5.2, 4.2)
    ax.imshow(valores, cmap=MAPA_DORADO)
    ax.set_xticks(range(len(etiquetas)), labels=etiquetas, rotation=45, ha="right")
    ax.set_yticks(range(len(etiquetas)), labels=etiquetas)
    maximo = max((max(f) for f in valores), default=0) or 1
    for i, fila in enumerate(valores):
        for j, v in enumerate(fila):
            ax.text(j, i, str(v), ha="center", va="center", fontsize=8,
                    color="#1a1405" if v > maximo * 0.6 else TEXTO)
    ax.set_xlabel("predicho")
    ax.set_ylabel("real")
    ax.set_title("Matriz de confusión (test)", fontsize=10)
    fig.tight_layout()
    return fig


def real_frente_predicho(y_real, y_pred) -> Figure:
    fig, ax = _figura(5.2, 4.2)
    ax.scatter(y_real, y_pred, s=10, color=SERIE, alpha=0.75)
    if len(y_real):
        lo, hi = min(min(y_real), min(y_pred)), max(max(y_real), max(y_pred))
        ax.plot([lo, hi], [lo, hi], color=BASE, linestyle="--", linewidth=1.2)
    ax.set_xlabel("real")
    ax.set_ylabel("predicho")
    ax.set_title("Real frente a predicho (test)", fontsize=10)
    fig.tight_layout()
    return fig


def guardar(fig: Figure, ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, facecolor=FONDO, dpi=150)
    return ruta
