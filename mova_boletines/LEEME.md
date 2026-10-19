# MOVA Boletines Oficiales

Vigilancia diaria de ayudas y subvenciones en el Boletín Oficial del Estado y en
los boletines oficiales de siete comunidades autónomas. Cada día laborable a las
07:45 revisa los ocho boletines, localiza las convocatorias relevantes para empresas industriales y
pymes, y envía un correo HTML consolidado por comunidad, sin repetir lo ya
enviado y sin mostrar lo descartado.

| Comunidad | Boletín | Código |
|---|---|---|
| Estatal | Boletín Oficial del Estado (secciones I, III y V-B) | BOE |
| Comunidad Valenciana | Diari Oficial de la Generalitat Valenciana | DOGV |
| Madrid | Boletín Oficial de la Comunidad de Madrid | BOCM |
| Cataluña | Diari Oficial de la Generalitat de Catalunya | DOGC |
| Andalucía | Boletín Oficial de la Junta de Andalucía | BOJA |
| Murcia | Boletín Oficial de la Región de Murcia | BORM |
| Castilla-La Mancha | Diario Oficial de Castilla-La Mancha | DOCM |
| Castilla y León | Boletín Oficial de Castilla y León | BOCYL |

### Novedades de las versiones 1.21 y 1.22: el resumen se hace con toda la normativa

Lo que publica un boletín suele ser un **extracto** de media página que remite al
texto completo. Resumiendo solo eso, el resultado se llenaba de «se establece en
la correspondiente convocatoria». Ahora, antes de resumir, la herramienta reúne
la normativa que falta:

| Fuente | Cómo se consigue |
|---|---|
| **La convocatoria completa** | El extracto cita su código BDNS. Con él se piden a la Base de Datos Nacional de Subvenciones la ficha oficial (plazo, presupuesto, beneficiarios, régimen de minimis) y el PDF íntegro |
| **Las bases reguladoras** | La cita trae el boletín y el día exacto («BORM n.º 130 de 7 de junio 2025»), así que se pide el sumario de ese día al adaptador que ya existe y se localiza el anuncio dentro |
| **Las modificaciones y ampliaciones** | Igual que las bases, y se leen antes: son dos páginas que pueden haber cambiado el plazo o la cuantía |

Para elegir el anuncio correcto dentro de un sumario se pesan las palabras por
lo **raras que son ese día**: en un boletín lleno de «orden», «consejería» y
«subvenciones», lo que distingue a la norma buscada es «bodegas» o «turismo». Si
ninguna candidata destaca con claridad **no se descarga nada** y la cita se le
pasa al modelo tal cual: antes sin las bases que con las bases equivocadas.

Medido sobre el extracto de las bodegas de las rutas del vino (BORM, 19/10/2026):
de **3 páginas a 61** (extracto, convocatoria de 40, bases de 15 y la
modificación de abril de 2026), y el resumen pasa a dar plazo, cuantía máxima,
intensidad, crédito y gastos subvencionables en vez de remitir a la
convocatoria. El resumen ampliado termina con la lista de **normativa
analizada**, enlazada, para poder comprobar de dónde sale cada dato.

**Lo que cuesta**: un resumen con toda la normativa son unos 0,24 $ frente a los
0,02 $ de antes, porque se analiza unas veinte veces más texto. Solo se paga al
pulsar el botón, y el tope mensual de gasto sigue cortando igual.

### Novedades de la versión 1.16: que no se escape ninguna ayuda

Cinco cambios para poder **comprobar** que no se pierde nada, no solo confiarlo:

| Cambio | Por qué |
|---|---|
| **Palabras clave nuevas**: ayuda, subvención, premio, premios, extracto, BDNS, préstamo, aval, bonificación, línea de financiación, subvencionable | El buscador exige palabra completa, así que «ayudas» no encontraba «ayuda». Faltaba también «extracto», que es como se publican los extractos de la BDNS. Medido sobre tres días reales: entraban 27 publicaciones más, unos 1,50 $ al mes |
| **Trámites que nombran ayudas**: las notificaciones personales, la mesa de contratación y la libre designación se apartan aunque el título hable de ayudas | «Notificación de resolución sobre ayudas de la PAC» se salvaba por la regla de oro y se pagaba al modelo para que la descartara |
| **Pantalla *Filtradas*** | Todo lo que no llegó al correo, con su motivo. Lo que apartó el filtro previo se puede **Analizar** (pasa por la IA, ~0,01 $) y lo que descartó la IA se puede **Recuperar** sin volver a pagar |
| **Avisos en el correo** | Si un boletín no respondió en ninguna pasada del día, o si el tope diario dejó publicaciones sin analizar, sale destacado arriba. Antes solo se veía en el registro de la ejecución |
| **Reintento del boletín caído** | Un boletín que falla todo el día se vuelve a intentar al día siguiente (hasta tres veces). Era la única vía por la que se perdía un día entero |

Lo que aparta el filtro previo se guarda en la tabla `apartadas`, sin coste y sin
tocar el histórico, y eso es lo que hace auditable el sistema: antes no quedaba
ni rastro de lo que se descartaba por el título.

### Novedades de la versión 1.15: el logotipo MOVA IA en todas partes

Donde antes se escribía «MOVA» con tipografía, ahora va el logotipo de la marca
(`web/estaticos/marca/mova-ia-negro.png` y `mova-ia-blanco.png`), en la versión
que corresponda al fondo: el negro sobre claro (página de espera de los botones)
y el blanco sobre oscuro (cabecera del panel y del correo). **Los resúmenes y la
infografía mantienen el logotipo anterior**, por decisión del usuario.

En el correo el logotipo viaja **dentro del mensaje** como adjunto en línea
(`cid:logo-mova`), no como enlace a internet: así lo muestran Outlook y Gmail sin
pedir permiso para descargar imágenes. La copia que se guarda en disco lleva la
imagen incrustada en el propio fichero para poder verla suelta.

### Novedades de la versión 1.10: estructura propia para financiación y empleo

Al analizar la convocatoria, la IA clasifica la ayuda como **financiación**
(préstamos, líneas bonificadas, avales, bonificación de intereses, capital),
**empleo** (contratación, cuotas, autoempleo, formación) o **general**.

En las de **financiación**, el resumen corto y el ampliado sustituyen el apartado
«Tipo de Ayuda y Cuantía» por **«Condiciones de financiación»**, con diez datos
que antes no se extraían: inversión mínima y máxima, inicio del proyecto,
financiación máxima, intereses, amortización, carencia, tramo no reembolsable,
garantías y comisión de apertura. También desaparece la frase de ejecución y
pago, que en un préstamo no encaja. El ampliado mantiene el resto de apartados
(criterios, documentación, plazos, crédito, referencias) y conserva régimen,
compatibilidades e incompatibilidades.

La **infografía** pasa a fondo claro desde la 1.14 (papel blanco, texto negro y el dorado
corporativo como acento; el logo, en negro). Y se adapta al tipo de ayuda (1.12): en financiación, las cifras
destacadas pasan a ser inversión máxima, financiación máxima y fin de plazo, y
se añade el bloque completo de condiciones; en empleo, son la ayuda por contrato
(el rango entre el importe menor y el mayor), el tipo de contrato y el fin de
plazo, con las personas destinatarias, los requisitos de la contratación y la
cuantía de cada colectivo. Las ayudas generales mantienen la estructura de
siempre. Los documentos generados antes de esta versión no llevan tipo, así que
se muestran como generales. Sigue la regla de la casa: una condición que no
figure en la convocatoria se escribe con su aviso, nunca con un valor plausible.

En las de **empleo**, el resumen corto y el ampliado pasan a tener estos
apartados, según el modelo del usuario (*Ayuda Contratación jóvenes
cualificados*): Nombre/objeto, **Personas Destinatarias** (a quién hay que
contratar, que no es lo mismo que quién cobra la ayuda), Beneficiarios,
**Requisitos de la Contratación**, **Requisitos de los trabajadores**,
Exclusiones, **Obligaciones del Empresario**, **Tipo de Contrato y Cuantía**
(modalidad y jornada, más el importe de cada colectivo: hombres, mujeres,
diversidad funcional, víctimas de violencia de género) y Plazo. Desaparecen
«Actuaciones Apoyables» y «Costes Apoyables», que en una ayuda a la
contratación no aplican. El ampliado añade además sus apartados de siempre.

### Novedades de la versión 1.9: solo ayudas para empresas y entidades privadas

Al correo solo llegan las convocatorias dirigidas a **empresas, pymes, autónomos,
fundaciones, asociaciones y demás entidades privadas** (con o sin ánimo de lucro).
Agricultores, ganaderos, pescadores y titulares de explotaciones cuentan como
privados: son actividad económica.

| Qué | Qué pasa |
|---|---|
| Para administraciones públicas (ayuntamientos, diputaciones, universidades y centros públicos) | No se envía ni se ve en el panel |
| Para personas físicas (estudiantes, familias, particulares) | No se envía ni se ve en el panel |
| Empleo público, contratación y trámites sin convocatoria nueva (oposiciones, libre designación, listas de admitidos, licitaciones, notificaciones, resoluciones de concesión) | No es una ayuda: no se envía ni se ve |
| El título no dice a quién va | Se envía con la marca **«DESTINATARIO SIN CONFIRMAR»** |

Las descartadas se guardan ocultas solo para no volver a pagar a la IA por ellas
cada día. Red de seguridad: si el título nombra empresas, pymes, autónomos,
fundaciones, asociaciones o agricultores, cuenta como privado aunque la IA dude.

Medido con 40 publicaciones reales ya enviadas (22/09/2026): 24 no eran ayudas
(sobre todo puestos de trabajo público), 7 iban a personas o administraciones y
9 siguen llegando. El correo trae bastante menos ruido.

**Filtro previo sin IA** (`negocio/prefiltro.py`, 1.9.3). Antes de llamar al
modelo se apartan las publicaciones que nunca son ayudas: puestos de trabajo
(libre designación, concursos de méritos, listas de admitidos, nombramientos),
contratación pública (licitaciones, mesas de contratación) y trámites
(notificaciones personales, información pública, impacto ambiental,
expropiaciones). Pasaban el filtro de palabras clave porque llevan
«convocatoria» o «resolución», y se pagaba al modelo por leerlas.

> **Regla de oro:** si el título nombra una ayuda (subvención, ayuda, premio,
> incentivo, bases reguladoras, BDNS…), **no se aparta aquí** aunque también
> hable de puestos o contratos. En la duda decide el modelo: perder una
> convocatoria cuesta mucho más que analizar una de más.

Comprobado sobre las 669 publicaciones del histórico: apartaría 312 (46 %), de
las que 193 ya las descartaba el modelo después de pagarlas. Las 119 restantes
se revisaron una a una y ninguna era una ayuda. El ahorro esperado ronda la
mitad del gasto mensual de la API.

### Novedades de la versión 1.7: el BOE

Se vigila también el **Boletín Oficial del Estado**, por su API de datos abiertos.
En el correo sale el primero, como «Estatal (BOE)», y sus publicaciones tienen
los mismos botones de resumen corto, ampliado e infografía.

Solo se leen las secciones donde se publican ayudas: **I** (reales decretos y
órdenes de concesión directa), **III** (convocatorias y bases reguladoras) y
**V-B** (extractos de la BDNS). Nombramientos, oposiciones, justicia y
contratación se dejan fuera: son la otra mitad del BOE y nunca son ayudas. Se
puede desactivar como cualquier boletín en la pantalla *Boletines*.

### Novedades de la versión 1.6: si el equipo estaba apagado, se hace al encenderlo

Si a las 07:45 (o a las 20:00, o el lunes a las 08:30) el equipo está apagado o
dormido, la herramienta lo hace en cuanto vuelve a estar encendida: unos 2 minutos
después de arrancar, y lo comprueba cada 10 minutos, así que también sirve al
volver de la suspensión.

- Cada día que faltó se vigila con **su** fecha y manda **su** correo, con lo
  publicado ese día, del más antiguo al más reciente. El asunto termina en
  «(enviado con retraso)» y el correo lleva un aviso arriba.
- La comprobación de la tarde solo se recupera si hace falta: si la vigilancia
  de ese día se recuperó ya pasadas las 20:00, esa misma la cubre.
- El resumen semanal se manda una sola vez por semana, aunque sea con retraso.
- Nunca repite lo ya hecho, ni lo lanzado a mano desde *Ejecutar*.
- Sin conexión no lanza nada (al encender, la red tarda en llegar): espera al
  siguiente intento. Tras 3 intentos fallidos de un mismo día, deja de insistir.
- Como mucho recupera 7 días hacia atrás, y nada anterior al día en que se
  instaló la 1.6. Las dos cosas se cambian en *Ajustes → Horario de la vigilancia*, donde
  también se puede desactivar.

### Novedades de la versión 1.5: los documentos se descargan en PDF

El botón **Descargar PDF** de cada documento entrega un PDF, ya no un HTML. El
resumen corto y el ampliado salen en A4 con el membrete en cada página (logo
arriba, edificio de fondo, pie con la dirección al final de cada hoja). La
infografía sale en una sola hoja alta, sin cortes. El botón **Imprimir** sigue
abriendo la impresora del navegador.

El PDF lo crea el Edge del propio equipo, sin ventana y sin conexión a internet
(unos 2 segundos). En Windows no hay que instalar nada. Si en algún equipo no
hubiera Edge ni Chrome, se descarga el HTML y queda aviso en el registro. Para
usar otro navegador: variable `MOVA_NAVEGADOR_PDF` con la ruta del ejecutable.

### Novedades de la versión 1.2: resumen corto, ampliado e infografía

Las fichas del correo y de la aplicación ya **no muestran Resumen, Plazo,
Beneficiarios ni Importe**. En su lugar, cada publicación tiene tres botones,
como en la aplicación Resumen Ayudas:

| Botón | Qué genera |
|---|---|
| **Resumen corto** | Documento con membrete MOVA: objeto, beneficiarios, actuaciones, costes, cuantía y plazo. |
| **Resumen ampliado** | Lo anterior más exclusiones, criterios de valoración, documentación de solicitud y de justificación, plazos de ejecución y justificación, crédito y referencias. |
| **Infografía** | Ficha oscura de datos clave: ayuda máxima, intensidad, fin de plazo, beneficiarios, régimen, crédito y ámbito. |

Al pulsar cualquiera de los tres, la herramienta descarga el PDF oficial, lo lee
entero y la IA extrae los datos **una sola vez** con las mismas instrucciones que
Resumen Ayudas. Los tres documentos salen de esa extracción y quedan guardados:
abrir los otros dos, o volver a abrirlos, no tiene coste. Se pueden imprimir o
descargar en PDF (desde la 1.5).

- Los botones del correo abren la aplicación, que pide iniciar sesión. Solo
  funcionan desde este equipo mientras la URL pública sea `127.0.0.1`.
- Generarlos requiere rol de editor o administrador (tiene coste). Un usuario de
  consulta puede ver los que ya estén generados.
- Coste orientativo con Sonnet 5: de 0,05 a 0,30 $ por publicación según la
  longitud del PDF. Se contabiliza en la pantalla *Coste* (fase «documentos») y
  respeta el tope mensual. El modelo se elige en *Ajustes*.
- Resumen, plazo, beneficiarios e importe se siguen extrayendo por dentro: los
  usan la clasificación de relevancia, las alertas de plazo corto y el resumen
  semanal. El correo de **alerta** mantiene la fecha de vencimiento, porque es el
  motivo del aviso.

### Novedades de la versión 1.1

| Qué | Cómo funciona | Dónde se ajusta |
|---|---|---|
| **Título resumido** | El modelo redacta en una línea qué se subvenciona y a quién. Encabeza cada ficha del correo y de la pantalla; el título oficial literal se mantiene debajo. Sin modelo, se obtiene recortando la referencia normativa del título oficial. | — |
| **Comprobación de las 20:00** | Segunda pasada del día por los ocho boletines, para números extraordinarios y publicaciones tardías. Solo manda correo si aparece algo nuevo. | Ajustes → Avisos |
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
dos disparos:

- **Al iniciar sesión**: arranca la herramienta sin ventana y sin abrir el
  navegador.
- **Cada 10 minutos, todos los días**: si la herramienta se ha cerrado o caído,
  la vuelve a arrancar. Mientras está en marcha, Windows no lanza nada.

Desde la 1.6.1 el ejecutable **no tiene ventana**: antes abría una consola negra
y, si alguien la cerraba, la herramienta se apagaba y los botones del correo
daban «HTTP ERROR 502». El registro sigue en `DATOS\registros\mova.log`. Para
pararla a propósito: Administrador de tareas → «MOVA Boletines Oficiales» →
Finalizar tarea (el vigilante la volverá a arrancar en 10 minutos salvo que
quites la tarea con `desinstalar_tarea.bat`).

Si la herramienta ya está en marcha, el segundo arranque se detecta solo y no
hace nada: antes de tocar nada comprueba si su puerto ya responde. Esto importa,
porque dos procesos sobre la misma base de datos se pisarían (el segundo
marcaría como «interrumpida» la ejecución que el primero está haciendo).

Opciones:

```
instalar_tarea.bat -CadaMinutos 5      comprueba cada 5 minutos en vez de 10
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

### Linux: el servidor de producción (VPS de IONOS)

Desde el 19/09/2026 la herramienta vive en un VPS de IONOS (Ubuntu 24.04, IP
`31.70.150.4`) y se usa en **https://boletines.movaia.es**. El panel se abre desde
cualquier navegador con usuario y contraseña; los botones del correo, sin sesión.
El equipo de Windows ya no la ejecuta (tarea programada desactivada).

| Qué | Dónde |
|---|---|
| Código | `/opt/mova-boletines` (propiedad de root, solo lectura para el servicio) |
| Datos, claves y copias | `/var/lib/mova-boletines` (usuario `mova`) |
| Servicio | `systemctl status mova-boletines` · `journalctl -u mova-boletines -f` |
| Web y HTTPS | Nginx + certificado Let's Encrypt que se renueva solo (avisos a boletines@mova.es) |
| Copias | una diaria a las 03:30 y otra en cada arranque; se conservan 10 |

Se entra por SSH solo con clave (`ssh -i %USERPROFILE%\.ssh\mova_vps root@31.70.150.4`);
la contraseña de root no sirve por SSH. En una emergencia, la consola del panel de
IONOS sigue funcionando.

Instalación desde cero (lo que se hizo el 19/09/2026):

```bash
apt install -y python3-venv nginx certbot ufw fail2ban unattended-upgrades sqlite3 \
  fonts-liberation2 fonts-dejavu-core fonts-noto-core tesseract-ocr tesseract-ocr-spa
# Google Chrome para los PDF: el Chromium de Ubuntu 24.04 es un snap y falla sin ventana.
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt update && apt install -y google-chrome-stable
adduser --system --group --home /var/lib/mova-boletines --shell /usr/sbin/nologin mova
# El código se sube con `git archive HEAD` (finales de línea de Linux), no copiando la carpeta.
python3 -m venv /opt/mova-boletines/.venv
/opt/mova-boletines/.venv/bin/pip install -r /opt/mova-boletines/requirements.txt
certbot certonly --webroot -w /var/www/letsencrypt -d boletines.movaia.es \
  --deploy-hook "systemctl reload nginx"
cp despliegue/nginx-mova-boletines.conf /etc/nginx/sites-available/mova-boletines
ln -s /etc/nginx/sites-available/mova-boletines /etc/nginx/sites-enabled/
cp despliegue/mova-boletines.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now mova-boletines
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
| BORM | API REST XML | `borm.es/services/boletin/fecha/DD-MM-AAAA/sumario` (PDF: `services/anuncio/{id}/pdf`) |
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

Salidas a internet: los ocho boletines, `api.anthropic.com` y el servidor
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
- Bases reguladoras citadas **sin decir en qué boletín y día** se publicaron:
  hoy no se localizan (se le pasa la cita al modelo). Haría falta buscar por
  título en el buscador de cada boletín, o barrer los sumarios de las semanas
  siguientes a la fecha de la norma.
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
