"use strict";
/* MOVA Minimis · interactividad. Sin dependencias externas. */

const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const CSRF = (document.querySelector('meta[name="csrf"]') || {}).content || "";

async function api(url, opciones) {
  opciones = opciones || {};
  opciones.headers = Object.assign({"X-CSRF": CSRF}, opciones.headers || {});
  if (opciones.json !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(opciones.json);
    delete opciones.json;
  }
  const r = await fetch(url, Object.assign({credentials: "same-origin"}, opciones));
  let datos = {};
  try { datos = await r.json(); } catch (e) { /* respuesta sin cuerpo JSON */ }
  if (!r.ok) throw new Error(datos.error || ("Error " + r.status));
  return datos;
}

function toast(html, tipo) {
  const x = $("toast");
  if (!x) return;
  const etiqueta = {ok: "Hecho", error: "Error", warn: "Aviso"}[tipo] || "Info";
  const clase = {ok: "ok", error: "err", warn: "warn"}[tipo] || "info";
  x.innerHTML = '<span class="en-tag ' + clase + '"><i></i>' + etiqueta + "</span>" + html;
  x.className = "toast show";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { x.className = "toast"; }, 6000);
}

function euros(x) {
  if (x == null) return "[PENDIENTE]";
  return Number(x).toLocaleString("es-ES", {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " €";
}

function hora(iso) {
  const d = iso ? new Date(iso) : new Date();
  return isNaN(d) ? "" : d.toLocaleTimeString("es-ES");
}

/* Menú lateral en móvil y desplegables (usuario), como en el CRM */
(function armazon() {
  const app = $("app"), btn = $("btnMenu"), velo = $("velo");
  if (btn && app) btn.addEventListener("click", () => app.classList.toggle("menu-abierto"));
  if (velo && app) velo.addEventListener("click", () => app.classList.remove("menu-abierto"));
  document.addEventListener("click", e => {
    const boton = e.target.closest("[data-mv-drop]");
    document.querySelectorAll(".mv-drop.abierto").forEach(d => {
      if (!boton || d !== boton.parentElement) d.classList.remove("abierto");
    });
    if (boton) boton.parentElement.classList.toggle("abierto");
  });
})();

/* Haz de líneas doradas del panel de acceso (igual que el CRM) */
(function ondas() {
  const svg = $("mvLoginOndas");
  if (!svg) return;
  let s = '<defs><linearGradient id="lgOro" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#b8892f" stop-opacity="0"/>' +
          '<stop offset=".45" stop-color="#d9b45b"/><stop offset="1" stop-color="#f0d98c"/></linearGradient></defs>';
  for (let i = 0, N = 30; i < N; i++) {
    const f = i / (N - 1), amp = 26 + 30 * Math.sin(f * Math.PI), d = 118 + (f - .5) * 110, p = [];
    for (let x = 0; x <= 640; x += 20) {
      const t = x / 640;
      p.push(x + " " + (d + amp * Math.sin(t * 3.05 + f * 1.5) * (0.35 + 0.65 * t)).toFixed(1));
    }
    s += '<path d="M' + p[0] + " " + p.slice(1).map(q => "L" + q).join(" ") + '" fill="none" stroke="url(#lgOro)" stroke-width=".9" opacity="' +
         (0.16 + 0.5 * Math.sin(f * Math.PI)).toFixed(2) + '"/>';
  }
  svg.innerHTML = s;
})();

/* Confirmación para botones marcados con data-confirmar */
document.addEventListener("submit", e => {
  const b = e.submitter;
  if (b && b.dataset.confirmar && !window.confirm(b.dataset.confirmar)) e.preventDefault();
});

/* ======================================================= Nueva consulta */
(function nuevaConsulta() {
  if (!$("pagNueva")) return;
  const lista = new Map();     // cif -> cliente
  let errores = [], avisos = [], documentos = [];

  function pintar() {
    const tb = $("tbClientes");
    if (!lista.size) {
      tb.innerHTML = '<tr><td colspan="6"><div class="en-vacio">Añade clientes desde documentos o a mano.</div></td></tr>';
    } else {
      tb.innerHTML = [...lista.values()].map(c => {
        const conf = Math.round((c.confianza || 0) * 100);
        const claseConf = conf >= 80 ? "ok" : "warn";
        const nombre = c.razon_social
          ? esc(c.razon_social)
          : "";
        return "<tr><td><b>" + esc(c.cif) + "</b></td>" +
          '<td><input class="form-control" type="text" data-cif="' + esc(c.cif) + '" value="' + nombre + '" placeholder="[PENDIENTE: la pondrá la BDNS]"></td>' +
          '<td class="en-tenue-td">' + esc(c.origen) + "</td>" +
          '<td><span class="en-tag ' + claseConf + '"><i></i>' + conf + " %</span></td>" +
          '<td class="mini">' + (c.notas ? '<span style="color:var(--mv-warn);font-weight:600">' + esc(c.notas) + "</span>" : "") + "</td>" +
          '<td><button class="enlace-rojo" type="button" data-quitar="' + esc(c.cif) + '">Quitar</button></td></tr>';
      }).join("");
    }
    const avisosHtml = avisos.map(a => '<div class="pend">' + esc(a) + "</div>").join("");
    const erroresHtml = errores.length
      ? '<div class="pend"><b>Entradas no válidas (no se consultarán):</b><ul class="lista-errores" style="margin:.3rem 0 0;padding-left:1.1rem;font-weight:400">' +
        errores.map(e => '<li>[PENDIENTE: confirmación manual] ' +
          esc(e.entrada) + " — " + esc(e.error) + "</li>").join("") + "</ul></div>"
      : "";
    $("errores").innerHTML = avisosHtml + erroresHtml;
    $("cuenta").textContent = lista.size ? lista.size + " cliente(s) en la lista" : "Sin clientes";
    $("btnConsultar").disabled = !lista.size;
  }

  function incorporar(res) {
    (res.clientes || []).forEach(c => {
      const previo = lista.get(c.cif);
      if (!previo) lista.set(c.cif, c);
      else if (!previo.razon_social && c.razon_social) previo.razon_social = c.razon_social;
    });
    errores = errores.concat(res.errores || []);
    avisos = avisos.concat(res.avisos || []);
    pintar();
  }

  $("tbClientes").addEventListener("click", e => {
    const cif = e.target.dataset.quitar;
    if (cif) { lista.delete(cif); pintar(); }
  });
  $("tbClientes").addEventListener("input", e => {
    const cif = e.target.dataset.cif;
    if (cif && lista.has(cif)) lista.get(cif).razon_social = e.target.value;
  });

  async function subir(ficheros) {
    if (!ficheros.length) return;
    const fd = new FormData();
    ficheros.forEach(f => fd.append("ficheros", f));
    const linea = document.createElement("tr");
    linea.innerHTML = "<td>" + ficheros.map(f => esc(f.name)).join(", ") + '</td><td class="en-tenue-td"></td>' +
                      '<td class="num"><span class="en-tag info"><i></i>Leyendo…</span></td>';
    $("listaDocs").appendChild(linea);
    const estado = linea.lastChild.firstChild;
    try {
      const res = await api("/api/documentos", {method: "POST", body: fd});
      documentos = documentos.concat((res.documentos || []).map(d => d.id));
      const n = (res.clientes || []).length;
      estado.className = "en-tag " + (n ? "ok" : "warn");
      estado.innerHTML = "<i></i>" + n + (n === 1 ? " cliente" : " clientes");
      linea.children[1].textContent = (res.documentos || []).map(d => d.metodo || "").join(", ");
      incorporar(res);
      toast((res.clientes || []).length + " cliente(s) leído(s) de los documentos", "ok");
    } catch (err) {
      estado.className = "en-tag err";
      estado.innerHTML = "<i></i>Error";
      toast(esc(err.message), "error");
    }
  }

  const dz = $("drop"), input = $("fileInput");
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("encima"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("encima"); }));
  dz.addEventListener("drop", e => subir([...e.dataTransfer.files]));
  input.addEventListener("change", () => { subir([...input.files]); input.value = ""; });

  $("btnManual").onclick = async () => {
    const texto = $("manual").value;
    if (!texto.trim()) return;
    try {
      const res = await api("/api/analizar-manual", {method: "POST", json: {texto}});
      incorporar(res);
      if ((res.clientes || []).length) $("manual").value = "";
    } catch (err) { toast(esc(err.message), "error"); }
  };

  $("btnVaciar").onclick = () => {
    lista.clear(); errores = []; avisos = []; documentos = [];
    $("listaDocs").innerHTML = "";
    pintar();
  };

  // Periodo
  const anosBox = $("anos");
  const actual = new Date().getFullYear();
  const defecto = (anosBox.dataset.defecto || "").split(",").map(Number);
  for (let a = actual - 7; a <= actual; a++) {
    anosBox.insertAdjacentHTML("beforeend", '<label><input type="checkbox" value="' + a + '"' +
      (defecto.includes(a) ? " checked" : "") + "> " + a + "</label>");
  }
  anosBox.addEventListener("change", e => {
    const marcados = [...anosBox.querySelectorAll("input:checked")];
    if (marcados.length > 3) { e.target.checked = false; toast("Como máximo tres ejercicios.", "warn"); }
  });
  function modo() { return (document.querySelector('input[name="modo"]:checked') || {}).value || "movil"; }
  function alternar() {
    $("bloqueMovil").classList.toggle("oculto", modo() !== "movil");
    $("bloqueEjercicios").classList.toggle("oculto", modo() !== "ejercicios");
  }
  document.querySelectorAll('input[name="modo"]').forEach(r => r.addEventListener("change", alternar));
  alternar();

  $("btnConsultar").onclick = async () => {
    const anos = [...anosBox.querySelectorAll("input:checked")].map(i => Number(i.value));
    if (modo() === "ejercicios" && !anos.length) { toast("Elija al menos un ejercicio.", "warn"); return; }
    $("btnConsultar").disabled = true;
    try {
      const res = await api("/api/consultas", {method: "POST", json: {
        clientes: [...lista.values()], errores, avisos, documentos,
        modo: modo(), fecha_referencia: $("fechaRef").value, anos,
      }});
      window.location = res.url;
    } catch (err) {
      toast(esc(err.message), "error");
      $("btnConsultar").disabled = false;
    }
  };
  pintar();
})();

/* ======================================================= Resultados */
(function resultados() {
  const pag = $("pagResultados");
  if (!pag) return;
  const cid = pag.dataset.cid;
  let ultimo = 0;

  function anadirLog(el, lineas) {
    lineas.forEach(l => {
      ultimo = Math.max(ultimo, l.id);
      const div = document.createElement("div");
      div.className = l.nivel || "";
      div.textContent = "[" + hora(l.hora) + "] " + l.mensaje;
      el.appendChild(div);
    });
    el.scrollTop = el.scrollHeight;
  }

  async function sondear() {
    try {
      const p = await api("/api/progreso/" + cid + "?desde=" + ultimo);
      $("bar").style.width = p.porcentaje + "%";
      $("progresoTxt").textContent = p.fase + " · " + p.porcentaje + " % · " + (p.mensaje || "");
      anadirLog($("logEl"), p.log);
      if (p.estado !== "en_proceso") {
        const ok = p.estado === "completada";
        toast(ok ? 'Consulta terminada. <a href="#exportar">Descargar informe</a>'
                 : "Consulta " + esc(p.estado) + (p.error ? ": " + esc(p.error) : ""), ok ? "ok" : "error");
        setTimeout(() => window.location.reload(), 1600);
        return;
      }
    } catch (err) {
      $("progresoTxt").textContent = "Sin respuesta del servidor, reintentando… (" + err.message + ")";
    }
    setTimeout(sondear, 1000);
  }

  if (pag.dataset.estado === "en_proceso") sondear();

  const btn = $("btnCancelar");
  if (btn) btn.onclick = async () => {
    if (!window.confirm("¿Cancelar la consulta en curso?")) return;
    btn.disabled = true;
    try { await api("/api/consultas/" + cid + "/cancelar", {method: "POST"}); toast("Cancelando…", "warn"); }
    catch (err) { toast(esc(err.message), "error"); btn.disabled = false; }
  };

  const registro = $("registro");
  if (registro) {
    registro.closest("details").addEventListener("toggle", async function cargar() {
      if (registro.dataset.cargado) return;
      registro.dataset.cargado = "1";
      try { anadirLog(registro, (await api("/api/progreso/" + cid + "?desde=0")).log); }
      catch (err) { registro.textContent = err.message; }
    });
  }
})();
