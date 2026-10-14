// MOVA Minimis · versión de escritorio.
// La ventana arranca por dentro el servidor de MOVA Minimis (Python, empaquetado con PyInstaller)
// en un puerto libre de 127.0.0.1 y lo muestra. Cada petición de la ventana lleva un token
// aleatorio que el servidor exige: ningún otro programa del equipo ni ninguna web abierta en el
// navegador puede usar ese puerto. Sin inicio de sesión: la administración tiene su propia contraseña.
const { app, BrowserWindow, ipcMain, shell, session } = require('electron');
const { spawn, execFile } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

const ESPERA_ARRANQUE_MS = 90000; // el primer arranque crea la base y hace la copia de seguridad
let servidor = null;
let base = null;
let credencial = null; // { puerto, token } del motor en marcha
let ventana = null;
let saliendo = false;

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (ventana) { if (ventana.isMinimized()) ventana.restore(); ventana.focus(); }
  });
}

// ── Tamaño y posición de la ventana ───────────────────────────────────
const ficheroVentana = () => path.join(app.getPath('userData'), 'ventana.json');
function leerVentana() {
  try { return JSON.parse(fs.readFileSync(ficheroVentana(), 'utf8')); } catch (_) { return null; }
}
function guardarVentana(win) {
  try {
    if (!win || win.isDestroyed()) return;
    const b = win.getNormalBounds ? win.getNormalBounds() : win.getBounds();
    fs.writeFileSync(ficheroVentana(), JSON.stringify({
      x: b.x, y: b.y, width: b.width, height: b.height, maximizada: win.isMaximized(),
    }));
  } catch (_) { /* no es crítico */ }
}

// Solo http/https salen al navegador del sistema (enlaces a la BDNS). Sin este filtro,
// openExternal ejecutaría rutas file://, UNC o protocolos del sistema.
function esExternoSeguro(url) {
  try { const u = new URL(url); return u.protocol === 'http:' || u.protocol === 'https:'; }
  catch (_) { return false; }
}

// ── Servidor interno ──────────────────────────────────────────────────
function puertoLibre() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.unref();
    s.on('error', reject);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

function rutaServidor() {
  // Empaquetado: resources/servidor/MOVAMinimisServidor.exe (extraResources, fuera del .asar)
  const exe = path.join(process.resourcesPath, 'servidor', 'MOVAMinimisServidor.exe');
  if (app.isPackaged) return { cmd: exe, args: [] };
  // En desarrollo: el app.py del proyecto con el entorno virtual de compilación
  return { cmd: 'C:\\build\\venvs\\mova_minimis\\Scripts\\python.exe', args: [path.join(__dirname, '..', 'app.py')] };
}

function preguntarSalud(puerto, token) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port: puerto, path: '/salud', timeout: 2000,
      headers: { 'X-MOVA-Token': token } }, (res) => { res.resume(); resolve(res.statusCode === 200); });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

async function arrancarServidor() {
  const puerto = await puertoLibre();
  const token = crypto.randomBytes(32).toString('hex');
  const datos = path.join(app.getPath('userData'), 'datos');
  fs.mkdirSync(datos, { recursive: true });
  const { cmd, args } = rutaServidor();
  servidor = spawn(cmd, args, {
    windowsHide: true,
    stdio: 'ignore',
    env: Object.assign({}, process.env, {
      MOVA_MODO_ESCRITORIO: '1',
      MOVA_TOKEN: token,
      MOVA_HOST: '127.0.0.1',
      MOVA_PUERTO: String(puerto),
      MOVA_ABRIR_NAVEGADOR: '0',
      MOVA_MINIMIS_DATOS: datos,
      MOVA_PID_PADRE: String(process.pid),
    }),
  });
  let terminado = null;
  servidor.on('exit', (codigo) => { terminado = codigo; if (!saliendo) mostrarError(
    'El motor de MOVA Minimis se ha detenido (código ' + codigo + ').', datos); });
  servidor.on('error', (e) => { terminado = -1; mostrarError('No se pudo iniciar el motor: ' + e.message, datos); });

  // Espera con tope, y mirando si el proceso esperado ya murió
  const fin = Date.now() + ESPERA_ARRANQUE_MS;
  while (Date.now() < fin) {
    if (terminado !== null) return null;
    if (await preguntarSalud(puerto, token)) return { puerto, token };
    await new Promise((r) => setTimeout(r, 400));
  }
  mostrarError('El motor de MOVA Minimis no respondió en ' + (ESPERA_ARRANQUE_MS / 1000) + ' segundos.', datos);
  return null;
}

// Cierre ordenado: el motor cierra antes su Word invisible (Windows lo arranca aparte y no muere con él).
// Con tope de 4 s; si no responde, pararServidor() lo fuerza.
function pedirCierre() {
  return new Promise((resolve) => {
    if (!credencial || !servidor || servidor.exitCode !== null) return resolve();
    const fin = setTimeout(resolve, 4000);
    servidor.once('exit', () => { clearTimeout(fin); resolve(); });
    const req = http.get({ host: '127.0.0.1', port: credencial.puerto, path: '/escritorio/cerrar', timeout: 2000,
      headers: { 'X-MOVA-Token': credencial.token } }, (res) => res.resume());
    req.on('error', () => {});
    req.on('timeout', () => req.destroy());
  });
}

function pararServidor() {
  saliendo = true;
  if (servidor && servidor.pid && servidor.exitCode === null) {
    // /T por si el motor hubiera abierto procesos hijos
    execFile('taskkill', ['/PID', String(servidor.pid), '/T', '/F'], { windowsHide: true }, () => {});
  }
}

function mostrarError(texto, datos) {
  if (!ventana || ventana.isDestroyed()) return;
  ventana.loadFile(path.join(__dirname, 'index.html'), {
    query: { error: texto, registro: path.join(datos, 'logs', 'app.log') },
  });
}

// ── Ventana ───────────────────────────────────────────────────────────
function crearVentana() {
  const g = leerVentana();
  ventana = new BrowserWindow({
    width: (g && g.width) || 1366,
    height: (g && g.height) || 880,
    x: g ? g.x : undefined,
    y: g ? g.y : undefined,
    minWidth: 980,
    minHeight: 640,
    autoHideMenuBar: true,
    backgroundColor: '#f6f5f1', // fondo claro del CRM: evita el destello al arrancar
    show: false,
    title: 'MOVA Minimis',
    icon: path.join(__dirname, 'icono.ico'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  if (g && g.maximizada) ventana.maximize();
  ventana.setMenuBarVisibility(false);
  ventana.loadFile(path.join(__dirname, 'index.html')); // pantalla de arranque
  ventana.once('ready-to-show', () => ventana.show());

  ventana.webContents.setWindowOpenHandler(({ url }) => {
    if (esExternoSeguro(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  // Dentro de la ventana solo se navega por la propia aplicación; lo demás sale al navegador
  ventana.webContents.on('will-navigate', (e, url) => {
    if (base && url.startsWith(base)) return;
    e.preventDefault();
    if (esExternoSeguro(url)) shell.openExternal(url);
  });
  ventana.webContents.on('will-attach-webview', (e) => e.preventDefault());

  let temporizador = null;
  const apuntar = () => { clearTimeout(temporizador); temporizador = setTimeout(() => guardarVentana(ventana), 400); };
  ventana.on('resize', apuntar);
  ventana.on('move', apuntar);
  ventana.on('close', () => guardarVentana(ventana));
}

app.whenReady().then(async () => {
  crearVentana();
  const listo = await arrancarServidor();
  if (!listo) return;
  base = 'http://127.0.0.1:' + listo.puerto + '/';
  credencial = listo;
  // El token viaja en cada petición de la ventana al motor, y solo a él
  session.defaultSession.webRequest.onBeforeSendHeaders({ urls: [base + '*'] }, (det, cb) => {
    det.requestHeaders['X-MOVA-Token'] = listo.token;
    cb({ requestHeaders: det.requestHeaders });
  });
  ventana.loadURL(base);
});

// Botón «Salir» de la interfaz: cierra la ventana y se sigue el camino de window-all-closed
ipcMain.on('mova-salir', (e) => {
  if (ventana && !ventana.isDestroyed() && e.sender === ventana.webContents) ventana.close();
});

app.on('before-quit', pararServidor);
app.on('window-all-closed', async () => {
  saliendo = true;
  await pedirCierre();
  pararServidor();
  app.quit();
});
