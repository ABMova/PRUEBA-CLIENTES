# MOVA Boletines Oficiales

Vigilancia diaria de ayudas y subvenciones en los boletines oficiales de siete
comunidades autónomas. Cada día laborable a las 07:45 revisa los siete
boletines, localiza las convocatorias relevantes para empresas industriales y
pymes, y envía un correo HTML consolidado por comunidad, sin repetir lo ya
enviado y sin mostrar lo descartado.

| Comunidad | Boletín | Código |
|---|---|---|
| Comunidad Valenciana | Diari Oficial de la Generalitat Valenciana | DOGV |
| Madrid | Boletín Oficial de la Comunidad de Madrid | BOCM |
| Cataluña | Diari Oficial de la Generalitat de Catalunya | DOGC |
| Andalucía | Boletín Oficial de la Junta de Andalucía | BOJA |
| Murcia | Boletín Oficial de la Región de Murcia | BORM |
| Castilla-La Mancha | Diario Oficial de Castilla-La Mancha | DOCM |
| Castilla y León | Boletín Oficial de Castilla y León | BOCYL |

### Novedades de la versión 1.1

| Qué | Cómo funciona | Dónde se ajusta |
|---|---|---|
| **Título resumido** | El modelo redacta en una línea qué se subvenciona y a quién. Encabeza cada ficha del correo y de la pantalla; el título oficial literal se mantiene debajo. Sin modelo, se obtiene recortando la referencia normativa del título oficial. | — |
| **Comprobación de las 20:00** | Segunda pasada del día por los siete boletines, para números extraordinarios y publicaciones tardías. Solo manda correo si aparece algo nuevo. | Ajustes → Avisos |
| **Alerta inmediata** | Correo urgente aparte, marcado como importante, cuando aparece una convocatoria de alta relevancia cuyo plazo vence en 15 días o menos. | Ajustes → Avisos |
| **Resumen semanal** | Lunes a las 08:30: lo publicado la semana anterior (lunes a domingo) y los plazos que vencen en los próximos 30 días. | Ajustes → Avisos |
| **Panel de coste** | Tokens y dólares por llamada, por ejecución, por día y por mes, con tope de gasto mensual (30 $ de inicio). | Pantalla Coste y Ajustes → Coste |

Para las alertas y el resumen, la herramienta calcula el **fin de plazo** a partir
del texto: si trae la fecha escrita la usa tal cual; si da una duración contada
desde la publicación («10 días hábiles…», «un mes…») la calcula y la marca como
**estimada** (los días hábiles no descuentan festivos locales). Si el plazo se
cuenta desde otra cosa, como una notificación, no se inventa ninguna fecha.

Si se alcanza el tope de gasto, la vigilancia **no se detiene**: sigue
recogiendo publicaciones y las guarda para revisión manual, sin llamar al modelo.

---

## 1. Puesta en marcha en tres pasos

1. **Arranca la aplicación** (doble clic en el `.exe`, o `python app.py` desde
   el código). Se abre el navegador en `http://127.0.0.1:8770`. Entra con
   usuario `admin` y la contraseña provisional `MovaBoletines2026`: la
   aplicación obliga a cambiarla en el primer acceso.
2. **Rellena Ajustes**: la clave de API de Anthropic y el servidor SMTP
   (servidor, puerto, usuario, contraseña y remitente). Ambas cosas se guardan
   cifradas. Usa los botones *Probar la clave* y *Enviar correo de prueba*.
3. **Lanza una ejecución manual** desde *Ejecuciones* con la fecha de ayer y
   revisa el correo que genera. Si te convence, doble clic en
   `instalar_tarea.bat` para que la herramienta se encienda sola, y a las 07:45
   del siguiente día laborable la vigilancia se dispara sin que hagas nada.

Mientras no haya clave de API, la herramienta sigue funcionando: recoge las
publicaciones y las guarda marcadas como `[REVISIÓN MANUAL]`, pero no las
resume ni las clasifica.

---

## 2. Instalación

### Windows (ejecutable de doble clic)

```
construir.bat
```

Crea el entorno virtual, instala dependencias, pasa las pruebas y genera
`dist\MOVA Boletines Oficiales.exe`. Copia ese `.exe` a su carpeta definitiva.
Al arrancar crea junto a él una carpeta `DATOS\` con la base de datos, la clave
de cifrado, los registros y las copias de seguridad.

> **Compila desde una ruta corta y fuera de OneDrive** (por ejemplo
> `C:\build\mova_boletines`). PyInstaller falla con rutas largas y OneDrive
> puede bloquear ficheros a medio escribir.

### Windows: que se encienda sola (tarea programada)

La vigilancia la dispara el planificador interno de la herramienta, así que
para que salte a las 07:45 la herramienta tiene que estar encendida. De eso se
ocupa una tarea programada de Windows:

```
instalar_tarea.bat
```

No necesita permisos de administrador: la tarea es del usuario actual. Registra
tres disparos:

- **Al iniciar sesión**: arranca la herramienta minimizada y sin abrir el
  navegador.
- **Cada día laborable a las 07:30 y a las 19:45**: la vuelve a levantar por si
  el equipo se encendió tarde o la herramienta se cerró, quince minutos antes de
  la vigilancia de la mañana y de la comprobación de la tarde.

Si la herramienta ya está en marcha, el segundo arranque se detecta solo y no
hace nada: antes de tocar nada comprueba si su puerto ya responde. Esto importa,
porque dos procesos sobre la misma base de datos se pisarían (el segundo
marcaría como «interrumpida» la ejecución que el primero está haciendo).

Opciones:

```
instalar_tarea.bat -Hora 06:45          cambia el disparo de respaldo de la manana
instalar_tarea.bat -HoraTarde 19:30     cambia el de la tarde
instalar_tarea.bat -Dias Diaria         tambien fines de semana
instalar_tarea.bat -Puerto 8880         si el 8770 esta ocupado
instalar_tarea.bat -Programa "C:\ruta\MOVA Boletines Oficiales.exe"
desinstalar_tarea.bat                   quita la tarea (no borra ningun dato)
```

Comprobar o forzar desde PowerShell:

```powershell
Get-ScheduledTaskInfo -TaskName "MOVA Boletines Oficiales"
Start-ScheduledTask   -TaskName "MOVA Boletines Oficiales"
```

El script busca qué arrancar en este orden: lo que le digas con `-Programa`, el
`.exe` que esté a su lado, el `.exe` recién compilado en `dist\`, y por último el
código fuente con su entorno virtual. Así que después de compilar e instalar,
basta con volver a ejecutar `instalar_tarea.bat` desde la carpeta de instalación
para que la tarea apunte al ejecutable.

**Si el equipo está apagado a las 07:45**, la vigilancia se hace al encenderlo:
la tarea arranca la herramienta al iniciar sesión y el planificador interno
recupera el disparo perdido si han pasado menos de 60 minutos. Más allá de esa
hora, ese día se salta y hay que lanzarla a mano desde *Ejecuciones* con la
fecha correspondiente. Si necesitas que corra siempre, sin depender de que
alguien encienda el equipo, el sitio es el servidor Linux.

### Linux (servicio interno)

```bash
sudo mkdir -p /opt/mova-boletines && sudo chown mova:mova /opt/mova-boletines
sudo -u mova git clone <repositorio> /opt/mova-boletines
cd /opt/mova-boletines
sudo -u mova python3.11 -m venv .venv
sudo -u mova .venv/bin/pip install -r requirements.txt
sudo cp despliegue/mova-boletines.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mova-boletines
sudo cp despliegue/nginx-mova-boletines.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/nginx-mova-boletines.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

> **UN SOLO PROCESO.** La aplicación guarda el progreso de la ejecución en
> memoria. No la arranques con varios *workers* ni repliques el servicio: dos
> procesos mostrarían estados distintos y podrían lanzar la vigilancia dos
> veces el mismo día. El paralelismo interno son hilos, no procesos.

En Nginx, `proxy_read_timeout` está subido a 600 s porque una ejecución manual
puede tardar varios minutos.

---

## 3. Estructura de carpetas

```
app.py                  arranque, waitress, planificador, apertura del navegador
config.py               configuración y rutas (compatible con PyInstaller)
requirements.txt        dependencias con versión fijada
.env.ejemplo            variables de entorno comentadas
construir.bat           compila el .exe de Windows
instalar_tarea.bat      registra la tarea programada de Windows
desinstalar_tarea.bat   quita la tarea programada
mova_boletines.spec     receta de PyInstaller (incluye recursos, excluye datos)

web/rutas.py            rutas: validan entrada, comprueban permisos, eligen plantilla
web/auth.py             autenticación y permisos, en un único sitio
web/plantillas/         Jinja2: pantallas + correo_diario.html + descarte_ok.html
web/estaticos/          mova.css y mova.js (sin CDN, sin Google Fonts)

negocio/orquestador.py  pipeline de seis fases, hilo de fondo, progreso, cancelación
negocio/boletines/      base.py + un adaptador por boletín
negocio/palabras.py     filtro determinista de palabras clave
negocio/extraccion.py   PDF, OCR opcional, normalización de texto
negocio/deduplicador.py hash + comparación difusa
negocio/relevancia.py   extracción estructurada, relevancia y bucle de calidad
negocio/correo.py       composición del HTML y envío SMTP

integraciones/anthropic_cliente.py  única puerta a la API de Anthropic
datos/repositorio.py    ÚNICO módulo que habla con la base de datos
datos/esquema.sql       esquema completo e idempotente, con semillas
datos/copias.py         copias automáticas, manuales y restauración
despliegue/             tarea de Windows, unidad systemd y ejemplo de Nginx
pruebas/                comprobaciones ejecutables

DATOS/                  (en ejecución, junto al .exe) mova.db, clave.key,
                        adjuntos/, registros/, copias/
```

> **Ojo con `DATOS` y `datos`.** Windows no distingue mayúsculas en los nombres
> de carpeta, así que al ejecutar desde el código fuente serían la misma
> carpeta y los datos acabarían mezclados con los módulos. Por eso, ejecutando
> desde código los datos van a `_DATOS/`; en el `.exe` empaquetado no existe el
> paquete `datos/` al lado, y se usa `DATOS/` tal cual. Con `MOVA_DATOS` puedes
> ponerlos donde quieras.

---

## 4. El proceso diario, fase a fase

| Fase | Qué hace | Quién |
|---|---|---|
| 1 | Descarga el sumario de cada boletín | Python |
| 2 | Filtra por las 25 palabras clave configurables | Python |
| 3 | Extrae los datos estructurados de cada candidata, título resumido incluido | Claude Sonnet |
| 4 | Clasifica la relevancia para empresa industrial o pyme | Claude Haiku |
| 4 bis | Valida la respuesta; un reintento; si falla, `[REVISIÓN MANUAL]` | Python + Claude |
| 5 | Deduplica por hash y por similitud de título | Python |
| 6 | Compone el correo HTML y lo envía por SMTP | Python |

**Fallo aislado, no fallo global**: si el BOJA no responde, los otros seis se
procesan igual y el correo dice expresamente cuáles fallaron.

**Nada se inventa**: si un dato no aparece en la publicación se escribe
literalmente `[PENDIENTE: dato]` y se marca en ámbar. Nunca se rellena con un
valor plausible.

### Vías de acceso de cada boletín (comprobadas el 17/09/2026)

| Boletín | Vía | Endpoint |
|---|---|---|
| DOGV | API REST JSON | `dogv.gva.es/dogv-portal/dogv/{num}?lang=es_es&ordenSumario=1` |
| BOCM | XML de sumario | `bocm.es/boletin/CM_Boletin_BOCM/AAAA/MM/DD/BOCM-AAAAMMDDNNN.xml` |
| DOGC | API REST JSON | `portaldogc.gencat.cat/eadop-rest/api/dogc/summaryDOGC` |
| BOJA | Feed Atom | `juntadeandalucia.es/boja/distribucion/boja.xml` |
| BORM | API REST XML | `borm.es/services/boletin/fecha/DD-MM-AAAA/sumario` |
| DOCM | HTML de sumario | `docm.castillalamancha.es/portaldocm/sumario.do?fecha=AAAAMMDD` |
| BOCYL | HTML de sumario | `bocyl.jcyl.es/boletin.do?fechaBoletin=DD/MM/AAAA` |

Volumen medido el 17/09/2026: **288 publicaciones** entre los siete, de las
que **107** pasan el filtro de palabras clave.

---

## 5. Cómo reparar un adaptador cuando cambie la web de origen

Los boletines cambian su web cada pocos años. Cuando uno falle:

1. En *Boletines* verás el último resultado y el mensaje de error de cada uno.
   En *Ejecuciones → Detalle* está el registro completo.
2. Abre el módulo del boletín en `negocio/boletines/`. Su cabecera dice la URL
   que usa, la fecha en que se comprobó y dónde mirar si cambia.
3. Comprueba la URL a mano:
   ```bash
   curl -s "URL_DEL_ADAPTADOR" | head -c 2000
   ```
   - Si devuelve datos pero con otra forma, ajusta el análisis del módulo.
   - Si devuelve 404, abre la web del boletín en el navegador, entra en el
     sumario del día y mira en el inspector (pestaña Red) qué peticiones hace.
     Así se encontraron las vías actuales del DOGV, el DOGC y el BORM.
4. Prueba solo ese adaptador:
   ```bash
   .venv\Scripts\python.exe pruebas\test_boletines_vivo.py 2026-09-17
   ```
5. Actualiza `URL_COMPROBADA` y `FECHA_COMPROBACION` del módulo.

Mientras tanto, desactiva ese boletín en la pantalla *Boletines* para que no
ensucie el correo con errores.

---

## 6. Datos, copias y actualización

- **Copia automática** al arrancar, con la API `backup()` de SQLite: funciona
  con la aplicación en marcha y no corrompe el WAL. Se conservan las 10 más
  recientes (configurable).
- **Copia manual y restauración** desde *Copias*. Antes de restaurar se guarda
  una copia del estado actual.
- **Exportación** del histórico a Excel y JSON, sin credenciales ni hashes.
- **Actualizar** es sustituir el `.exe` (o hacer `git pull` y reiniciar el
  servicio). La carpeta de datos no se toca. El esquema se reaplica solo y
  añade las columnas que falten sin borrar nada.

---

## 7. Seguridad

- Roles **administrador**, **editor** y **consulta**. Los permisos se comprueban
  en **cada** petición, no solo al iniciar sesión.
- Contraseñas con PBKDF2-HMAC-SHA256, sal por usuario, 200.000 iteraciones y
  comparación en tiempo constante.
- Clave de API y contraseña SMTP cifradas con Fernet. La clave de cifrado vive
  en `DATOS/clave.key`, **fuera** de la base de datos. Nunca se muestran
  enteras en pantalla ni se escriben en los registros.
- Cookies de sesión `HttpOnly`, `SameSite=Lax`, con caducidad de 12 horas y
  secreto persistente entre reinicios.
- El sistema no permite quedarse sin el último administrador activo.
- La auditoría registra cada acción y no se puede borrar desde la interfaz.
- `GET /descartar/<token>` es la **única** ruta sin sesión: token aleatorio de
  32 caracteres, de un solo uso, caducidad de 90 días y limitación de intentos
  por IP (20 cada 10 minutos), reforzada en Nginx.

### Qué datos salen del sistema

Hacia la API de Anthropic sale **solo el texto público de las publicaciones
oficiales**: título, organismo, sección y texto del boletín. Nunca credenciales,
nunca datos de usuarios, nunca el contenido de la base de datos.

Para servir el modelo en la red local basta con sustituir
`integraciones/anthropic_cliente.py`, manteniendo la firma de `llamar_json()`.
Ningún otro módulo habla con la API.

Salidas a internet: los siete boletines, `api.anthropic.com` y el servidor
SMTP. Nada más: no hay CDN, ni Google Fonts, ni analítica.

---

## 8. Decisiones abiertas, pendientes de confirmar

Están implementadas con el valor propuesto y son configurables:

| Decisión | Valor implementado | Dónde se cambia |
|---|---|---|
| Vía de acceso de cada boletín | La de la tabla del apartado 4 | Módulo del boletín |
| Deduplicación | Hash de título+boletín y similitud ≥ 92 % a 30 días | Ajustes |
| Descartes | Enlace con token de un solo uso, 90 días | Ajustes |
| Reintentos por boletín | 3, con retroceso exponencial | Ajustes |
| Alta relevancia | Decide el modelo, reforzado por lista de términos | Ajustes |
| Tope de candidatas por ejecución | 150 (0 = sin tope) | Ajustes |

**El tope de candidatas merece una decisión explícita.** Es el freno de coste:
un día corriente deja unas 107 candidatas, así que 150 no estorba. Pero si se
amplían las palabras clave o un boletín publica mucho, el tope evita una
factura inesperada: se analizan las 150 con coincidencias más fuertes (los
términos «ayudas», «subvenciones», «convocatoria», «bases reguladoras»… pesan
diez veces más) y el registro dice cuántas quedaron fuera.

---

## 9. Riesgos conocidos

- **BORM y anti-bot.** `borm.es` está detrás de Radware Bot Manager. El
  adaptador se identifica como navegador y funciona hoy, pero si el BORM
  endurece la protección devolverá un reto que **no se intenta resolver**: se
  registra como error controlado. Solución: pedir al BORM autorización para la
  IP del servidor, o darse de alta en sus alertas.
- **DOGC y TLS antiguo.** Su servidor negocia cifrados que OpenSSL 3 rechaza.
  Se usa un adaptador TLS permisivo solo para ese dominio, manteniendo la
  verificación del certificado. Si algún día lo actualizan, puede quitarse.
- **BOJA y el feed.** El feed Atom solo cubre los últimos boletines. Para
  fechas antiguas no devuelve nada (no es un error: sale como «sin boletín»).
- **DOCM y BOCYL son HTML.** Son los dos más frágiles: cualquier rediseño de su
  web rompe el análisis. Están aislados y se reparan por separado.
- **Sumarios sin texto completo.** DOGV, DOGC, BOJA, BORM, DOCM y BOCYL dan
  título y organismo, no el texto íntegro. El modelo trabaja con eso salvo que
  se active la descarga del PDF; el BOCM sí incluye el texto en su XML.
- **OCR opcional.** Si Tesseract no está instalado, un PDF escaneado se marca
  con `texto_incompleto` en vez de fallar.
- **Coste.** Con unas 107 candidatas al día y Sonnet 5 en la fase 3 (2 $ por
  millón de tokens de entrada y 10 $ de salida), el gasto ronda 1 $ diario. La
  pantalla *Coste* da la cifra real. Dos palancas en *Ajustes*: el tope mensual
  y el **esfuerzo de razonamiento**. Sonnet 5 y Opus 5 razonan antes de
  responder aunque no se les pida, y ese razonamiento se factura como salida; la
  herramienta lo fija en «bajo», que basta para extraer datos de un boletín.
- **Fechas de fin de plazo estimadas.** Los días hábiles se cuentan sin
  festivos, que dependen de la comunidad y del municipio. Una fecha marcada como
  estimada puede adelantarse uno o dos días a la real: confírmala en la
  publicación antes de presentar nada.
- **Comprobación de la tarde con el equipo apagado.** Como la de la mañana,
  depende de que el equipo esté encendido. Si a las 20:00 está apagado, la
  herramienta la recupera si se enciende antes de las 21:00; si no, las
  publicaciones de la tarde saldrán en el correo del día siguiente.
- **Equipo apagado.** En Windows la vigilancia depende de que alguien encienda
  el equipo e inicie sesión. La tarea programada y el margen de 60 minutos del
  planificador cubren los retrasos normales, pero un día de vacaciones con el
  equipo apagado no se vigila. El servidor Linux no tiene este problema.

---

## 10. Mejoras futuras

- Descarga del PDF y extracción del texto íntegro para los boletines que solo
  dan título, con caché en `DATOS/adjuntos/`.
- Cruce automático con la Base de Datos Nacional de Subvenciones (BDNS) a
  partir del identificador BDNS que ya aparece en algunas publicaciones.
- Alertas cuando una convocatoria ya conocida entra en la ventana de
  vencimiento (hoy se avisa al descubrirla, y el resumen semanal recoge el resto).
- Más comunidades: añadir un módulo en `negocio/boletines/` y registrarlo.
- Migración a PostgreSQL sustituyendo solo `datos/repositorio.py`.

---

## 11. Comprobaciones

```
.venv\Scripts\python.exe pruebas\test_esquema.py           esquema idempotente
.venv\Scripts\python.exe pruebas\test_pipeline.py          pipeline simulado
.venv\Scripts\python.exe pruebas\test_web.py               servidor y sesiones
.venv\Scripts\python.exe pruebas\generar_correo_ejemplo.py correo de ejemplo
.venv\Scripts\python.exe pruebas\test_boletines_vivo.py    boletines en vivo
```

Las cuatro primeras no salen a internet ni llaman a la API. La última sí
descarga los sumarios reales; si no hay conectividad, lo dice y no falla.
