# Conexión con Mova CRM

Los botones **Enviar al CRM** y **Acciones** del correo diario abren una
pantalla del CRM. Es el CRM quien viene aquí a buscar los datos de la ayuda, no
al revés:

- la clave compartida vive solo en el CRM y nunca viaja en un correo;
- esta herramienta solo expone **lectura**: desde fuera no se escribe nada;
- el CRM exige sesión antes de abrir la pantalla, así que queda registrado quién
  da de alta el programa y solo pueden hacerlo los correos autorizados.

## Lo que se configura aquí (Ajustes → Conexión con el CRM de MOVA)

| Ajuste | Para qué |
|---|---|
| `crm_activo` | Enciende o apaga los botones del correo |
| `crm_url` | `https://crm.movaia.es` |
| `crm_correos` | Quién ve los botones: `antonio@mova.es, j.javier@mova.es`. Vacío = todos |
| `crm_clave` | Se genera con el botón *Generar clave para el CRM* y se copia en el CRM. Queda cifrada y no se puede volver a consultar |

Si solo algunos destinatarios ven los botones, el correo diario sale **dos
veces**: uno con botones para los autorizados y otro sin ellos para el resto.
Los dos llevan exactamente el mismo contenido.

## A dónde apuntan los botones

```
https://crm.movaia.es/Programas/DesdeBoletin?o=<token>            (Enviar al CRM)
https://crm.movaia.es/Programas/DesdeBoletin?o=<token>&accion=tarea   (Acciones)
```

El `token` es el mismo de los botones de resumen (`/d/<token>/...`), con la
caducidad del ajuste `dias_token_documento` (90 días).

## API que consume el CRM

Base: `https://boletines.movaia.es/api/crm` — cabecera `X-Clave-CRM: <clave>` en
todas las llamadas. Sin clave o con clave incorrecta: **401**. Con el CRM
desactivado: **503**. Token inexistente o caducado: **404**. Solo admite GET.

| Ruta | Devuelve |
|---|---|
| `GET /salud` | `{"estado":"ok"}` — para comprobar la clave |
| `GET /publicacion/<token>` | La ayuda en JSON (abajo) |
| `GET /publicacion/<token>/documento/<tipo>` | El PDF del resumen (`corto`, `ampliado`, `infografia`). **202** con `{"estado":"generando"}` mientras se crea: volver a preguntar a los pocos segundos |

El primer `GET` de un documento puede lanzar su generación, que cuesta una
llamada a la API de Anthropic. Solo pedirlos si se van a adjuntar.

### Forma del JSON

```json
{
  "publicacion": {
    "id": 1,
    "codigo_boletin": "DOGV",
    "comunidad": "Comunidad Valenciana",
    "boletin_nombre": "Diari Oficial de la Generalitat Valenciana",
    "fecha_publicacion": "2026-09-17",
    "titulo": "ORDEN 12/2026, de 15 de septiembre, de la Conselleria de ...",
    "titulo_resumido": "Subvenciones para la modernizacion de pymes industriales",
    "resumen": "Subvenciones en concurrencia competitiva para ...",
    "organismo": "Conselleria de Innovacion, Industria, Comercio y Turismo",
    "plazo": "Del 1 al 30 de octubre de 2026",
    "plazo_fin": "2026-10-30",
    "plazo_fin_origen": "modelo",
    "beneficiarios": "Pymes industriales con centro de trabajo en la Comunitat",
    "importe": "12.000.000 euros",
    "url_oficial": "https://dogv.gva.es/es/disposicio-canonica?sig=990001",
    "url_pdf": "https://dogv.gva.es/datos/2026/09/17/pdf/2026_99001_es.pdf",
    "seccion": "I",
    "relevancia": "alta",
    "sectores": "",
    "destinatario": "privado"
  },
  "detalle": { },
  "documentos": { "estado": "pendiente", "tipos": ["corto", "ampliado", "infografia"] }
}
```

`detalle` está vacío mientras nadie haya pedido un resumen de esa ayuda. Cuando
existe, trae los campos que extrajo la IA de las bases: `objeto`, `actuaciones`,
`gastos_elegibles`, `gastos_excluidos`, `cuantia_max`, `intensidad`, `criterios`,
`doc_solicitud`, `plazo_ejecucion`, `compatibilidades`, `tipo_ayuda`
(`general` | `financiacion` | `empleo`) y, según el tipo, los objetos
`financiacion` y `empleo`.

## Correspondencia con el Programa del CRM

| Programa (CRM) | De dónde sale |
|---|---|
| `Nombre` | `titulo_resumido` (si falta, `titulo`) |
| `Descripcion` | `detalle.objeto` o `resumen` |
| `Actuaciones_apoyables` | `detalle.actuaciones` |
| `Costes_apoyables` | `detalle.gastos_elegibles` |
| `Beneficiarios` | `beneficiarios` |
| `Tipo_de_cuantia` | `detalle.cuantia_max` / `detalle.intensidad` |
| `Condiciones_de_financiacion` | `detalle.financiacion` (solo si `tipo_ayuda` = `financiacion`) |
| `Plazo_real` | `plazo_fin` |
| `Ruta_documentacion` | `url_oficial` |
| `AmbitoId` | del boletín: DOGV→10, BOCM→13, DOGC→9, BOJA→1, BORM→14, DOCM→8, BOCYL→7, BOE→20 |
| `OrganismoId` | resolver `organismo` por nombre; si no aparece, dejarlo vacío y avisar (nunca crear organismos a ciegas: `ProvinciaId` es obligatorio) |

Pendiente en el lado del CRM: campo `ReferenciaBoletin` con índice único
(`codigo_boletin` + `id`) para que la misma ayuda no entre dos veces, y la lista
`Integraciones:CorreosAutorizados` en `appsettings.Local.json`.
