"""Agente 2a · Consultor de la Base Nacional de Subvenciones.

Para cada CIF localiza al beneficiario en la BDNS y trae TODAS sus concesiones
de minimis (el filtrado por periodo es cosa del Calculador, para que el informe
pueda enseñar también lo que queda fuera). No inventa nada: si la BDNS no
responde, el cliente queda como búsqueda incompleta.

El acceso a red y la caché se inyectan (`fuente`, `cache_get`, `cache_set`):
este módulo no sabe de HTTP ni de SQL.
"""
import re
import time
import unicodedata

HORAS_CACHE_MINIMIS = 12
HORAS_CACHE_CONVOCATORIA = 24 * 30
SEGUNDOS_POR_CLIENTE = 45


def clase_reglamento(texto: str | None) -> str:
    t = (texto or "").upper()
    if "2023/2831" in t or "1407/2013" in t:
        return "general"
    if "1408/2013" in t:
        return "agricola"
    if "717/2014" in t:
        return "pesca"
    if "2023/2832" in t or "360/2012" in t:
        return "sieg"
    return "otro"


def _normalizar(nombre: str | None) -> set[str]:
    t = unicodedata.normalize("NFKD", (nombre or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\b(S\.?\s?L\.?\s?U?|S\.?\s?A\.?\s?U?|SOCIEDAD|LIMITADA|ANONIMA|UNIPERSONAL|COOP)\b\.?", " ", t)
    return {p for p in re.findall(r"[A-Z0-9]{2,}", t)}


def nombres_coinciden(a: str | None, b: str | None) -> bool:
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return True  # sin nombre de partida no hay contradicción que señalar
    return len(na & nb) / min(len(na), len(nb)) >= 0.5


def _ayuda_desde_bdns(c: dict, fuente) -> dict:
    fecha = c.get("fechaConcesion")
    return {
        "origen": "bdns",
        "codigo_concesion": c.get("codigoConcesion"),
        "fecha_concesion": fecha,
        "ano_fiscal": int(fecha[:4]) if fecha else None,
        "programa": None,
        "numero_convocatoria": c.get("numeroConvocatoria"),
        "convocante": (c.get("convocante") or "").strip() or None,
        "reglamento": c.get("reglamento"),
        "clase_reglamento": clase_reglamento(c.get("reglamento")),
        "instrumento": c.get("instrumento"),
        "importe_concedido": float(c.get("ayudaEquivalente") or 0),
        "fuente": "BDNS · registro " + (c.get("fechaRegistro") or "s/f"),
        "url_referencia": fuente.url_convocatoria(c.get("numeroConvocatoria")),
        "fecha_publicacion": c.get("fechaRegistro"),
        "sector_actividad": c.get("sectorActividad"),
    }


def consultar(clientes: list[dict], fuente, cache_get=None, cache_set=None, progreso=None,
              cancelado=None) -> dict:
    """`fuente` es integrations.web_scraper (o un doble en las pruebas)."""
    cache_get = cache_get or (lambda clave, horas: None)
    cache_set = cache_set or (lambda clave, datos: None)
    resultados, no_encontrados = [], []

    for i, cli in enumerate(clientes):
        if cancelado and cancelado():
            break
        cif = cli["cif"]
        if progreso:
            progreso(i, len(clientes), f"Consultando {cif} {cli.get('razon_social') or ''}".strip())
        inicio = time.monotonic()
        notas = []
        try:
            clave = f"minimis:{cif}"
            datos = cache_get(clave, HORAS_CACHE_MINIMIS)
            if datos is None:
                personas = [p for p in fuente.buscar_beneficiarios(cif, cancelado) if p["cif"] == cif]
                concesiones = []
                for p in personas:
                    concesiones += fuente.concesiones_minimis(p["id"], cancelado)
                datos = {"personas": personas, "concesiones": concesiones, "consultado": time.time()}
                cache_set(clave, datos)
            else:
                notas.append("Datos de la BDNS reutilizados de una consulta de las últimas "
                             f"{HORAS_CACHE_MINIMIS} horas.")
        except Exception as e:  # ErrorBDNS o red caída
            if cancelado and cancelado():
                break
            resultados.append({
                "cif": cif, "razon_social": cli.get("razon_social"), "razon_social_bdns": None,
                "ids_bdns": [], "ayudas_minimis_encontradas": [],
                "confianza_busqueda": "no encontrado", "busqueda_completa": False,
                "notas_busqueda": f"Búsqueda incompleta, requiere revisión manual: {e}",
            })
            continue

        personas, concesiones = datos["personas"], datos["concesiones"]
        if not personas:
            no_encontrados.append({
                "cif": cif, "razon_social": cli.get("razon_social"),
                "razon": "El CIF no figura como beneficiario de ayudas de minimis en la BDNS.",
            })
            resultados.append({
                "cif": cif, "razon_social": cli.get("razon_social"), "razon_social_bdns": None,
                "ids_bdns": [], "ayudas_minimis_encontradas": [], "confianza_busqueda": "no encontrado",
                "busqueda_completa": True,
                "notas_busqueda": "No se han registrado ayudas de minimis para este CIF en la BDNS.",
            })
            continue

        nombre_bdns = personas[0]["nombre"]
        dudas = len(notas)
        if len(personas) > 1:
            notas.append(f"El CIF aparece con {len(personas)} registros de beneficiario en la BDNS; se suman todos.")
        if not nombres_coinciden(cli.get("razon_social"), nombre_bdns):
            notas.append(f"La razón social de la entrada ('{cli.get('razon_social')}') no coincide con la "
                         f"registrada en la BDNS ('{nombre_bdns}'). Confirmar que es el mismo cliente.")

        ayudas = [_ayuda_desde_bdns(c, fuente) for c in concesiones]
        # Títulos de convocatoria: mejor esfuerzo, con tope de tiempo por cliente
        for a in ayudas:
            num = a["numero_convocatoria"]
            if not num:
                continue
            ficha = cache_get(f"conv:{num}", HORAS_CACHE_CONVOCATORIA)
            if ficha is None and time.monotonic() - inicio < SEGUNDOS_POR_CLIENTE:
                try:
                    ficha = fuente.ficha_convocatoria(num, cancelado)
                    cache_set(f"conv:{num}", ficha)
                except Exception:
                    ficha = None
            if ficha:
                a["programa"] = ficha.get("titulo")
                a["url_bases"] = ficha.get("url_bases")
        if any(a["numero_convocatoria"] and not a["programa"] for a in ayudas):
            notas.append("Algunos títulos de convocatoria no se pudieron obtener a tiempo.")

        resultados.append({
            "cif": cif,
            "razon_social": cli.get("razon_social") or nombre_bdns,
            "razon_social_bdns": nombre_bdns,
            "ids_bdns": [p["id"] for p in personas],
            "url_beneficiario": fuente.url_beneficiario(personas[0]["id"]),
            "ayudas_minimis_encontradas": ayudas,
            "confianza_busqueda": "alta" if len(notas) == dudas else "media",
            "busqueda_completa": True,
            "notas_busqueda": " ".join(notas),
        })

    return {"resultados": resultados, "no_encontrados": no_encontrados}
