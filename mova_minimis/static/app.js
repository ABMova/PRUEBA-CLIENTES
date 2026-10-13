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
  const etiqueta = {ok: "OK", error: "ERROR", warn: "AVISO"}[tipo] || "INFO";
  const clase = {ok: "ok", error: "error", warn: "warn"}[tipo] || "procesando";
  x.innerHTML = '<span class="badge ' + clase + '">' + etiqueta + "</span> " + html;
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
      tb.innerHTML = '<tr><td colspan="6" class="muted">Añada clientes desde documentos o a mano.</td></tr>';
    } else {
      tb.innerHTML = [...lista.values()].map(c => {
        const conf = Math.round((c.confianza || 0) * 100);
        const claseConf = conf >= 80 ? "ok" : "warn";
        const nombre = c.razon_social
          ? esc(c.razon_social)
          : "";
        return "<tr><td><b>" + esc(c.cif) + "</b></td>" +
          '<td><input type="text" data-cif="' + esc(c.cif) + '" value="' + nombre + '" placeholder="[PENDIENTE: la pondrá la BDNS]"></td>' +
          '<td class="mini">' + esc(c.origen) + "</td>" +
          '<td><span class="badge ' + claseConf + '">' + conf + " %</span></td>" +
          '<td class="mini">' + (c.notas ? '<span class="pendiente-txt">' + esc(c.notas) + "</span>" : "") + "</td>" +
          '<td><button class="btn btn-sm btn-danger" type="button" data-quitar="' + esc(c.cif) + '">Quitar</button></td></tr>';
      }).join("");
    }
    const avisosHtml = avisos.map(a => '<div class="banner warn" style="margin-top:.4rem">' + esc(a) + "</div>").join("");
    const erroresHtml = errores.length
      ? '<div class="banner warn" style="margin-top:.4rem"><b>Entradas no válidas (no se consultarán):</b><ul class="mini">' +
        errores.map(e => '<li><span class="pendiente-txt">[PENDIENTE: confirmación manual]</span> ' +
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
    const linea = document.createElement("div");
    linea.className = "file";
    linea.innerHTML = "<span>" + ficheros.map(f => esc(f.name)).join(", ") + '</span><span></span><span></span><span class="badge procesando">LEYENDO</span>';
    $("listaDocs").appendChild(linea);
    try {
      const res = await api("/api/documentos", {method: "POST", body: fd});
      documentos = documentos.concat((res.documentos || []).map(d => d.id));
      linea.lastChild.className = "badge ok";
      linea.lastChild.textContent = (res.clientes || []).length + " CLIENTE(S)";
      linea.children[1].innerHTML = '<span class="hint">' +
        (res.documentos || []).map(d => esc(d.metodo || "")).join(", ") + "</span>";
      incorporar(res);
      toast((res.clientes || []).length + " cliente(s) leído(s) de los documentos", "ok");
    } catch (err) {
      linea.lastChild.className = "badge error";
      linea.lastChild.textContent = "ERROR";
      toast(esc(err.message), "error");
    }
  }

  const dz = $("drop"), input = $("fileInput");
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("drag"); }));
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
