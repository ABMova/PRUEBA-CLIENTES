/* MOVA Boletines Oficiales - comportamiento de la interfaz.
   Sin librerias externas: todo lo que hay aqui es JavaScript del navegador. */

(function () {
  "use strict";

  function porId(id) { return document.getElementById(id); }

  function avisoFlotante(texto) {
    var caja = porId("aviso-flotante");
    if (!caja) { return; }
    caja.textContent = texto;
    caja.classList.add("visible");
    window.setTimeout(function () { caja.classList.remove("visible"); }, 9000);
  }

  /* ------------------------------------------------- progreso de ejecucion -- */
  var sondeo = null;
  var estabaActivo = false;

  function pintarProgreso(datos) {
    var relleno = porId("progreso-relleno");
    if (relleno) { relleno.style.width = (datos.porcentaje || 0) + "%"; }

    var fase = porId("progreso-fase");
    if (fase) {
      if (datos.activo) {
        fase.textContent = "Fase " + datos.numero_fase + "/" + datos.total_fases +
          " - " + datos.fase + (datos.boletin ? " (" + datos.boletin + ")" : "");
      } else if (datos.resultado) {
        fase.textContent = "Terminada: " + datos.resultado;
      } else {
        fase.textContent = "Sin ejecucion en curso";
      }
    }

    var registro = porId("registro-vivo");
    if (registro && datos.registro) {
      var pegado = registro.scrollTop + registro.clientHeight >= registro.scrollHeight - 24;
      registro.textContent = datos.registro.join("\n");
      if (pegado) { registro.scrollTop = registro.scrollHeight; }
    }

    var lanzar = porId("boton-lanzar");
    var cancelar = porId("boton-cancelar");
    if (lanzar) { lanzar.disabled = !!datos.activo; }
    if (cancelar) { cancelar.disabled = !datos.activo; }

    if (estabaActivo && !datos.activo) {
      avisoFlotante("Ejecucion terminada: " + (datos.resultado || "sin detalle"));
      window.setTimeout(function () { window.location.reload(); }, 2500);
    }
    estabaActivo = !!datos.activo;
  }

  function consultarProgreso() {
    fetch("/api/progreso", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (datos) { if (datos) { pintarProgreso(datos); } })
      .catch(function () { /* la interfaz sigue viva aunque falle una consulta */ });
  }

  /* --------------------------------------------------------- confirmaciones -- */
  function activarConfirmaciones() {
    var elementos = document.querySelectorAll("[data-confirmar]");
    Array.prototype.forEach.call(elementos, function (elemento) {
      elemento.addEventListener("click", function (evento) {
        if (!window.confirm(elemento.getAttribute("data-confirmar"))) {
          evento.preventDefault();
        }
      });
    });
  }

  /* ------------------------------------------------- seleccion en tablas -- */
  function activarSeleccionTotal() {
    var maestro = porId("seleccionar-todo");
    if (!maestro) { return; }
    maestro.addEventListener("change", function () {
      var casillas = document.querySelectorAll("input[name='ids']");
      Array.prototype.forEach.call(casillas, function (casilla) {
        casilla.checked = maestro.checked;
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    activarConfirmaciones();
    activarSeleccionTotal();

    if (porId("panel-progreso")) {
      consultarProgreso();
      sondeo = window.setInterval(consultarProgreso, 2000);
      window.addEventListener("beforeunload", function () {
        if (sondeo) { window.clearInterval(sondeo); }
      });
    }

    var mensaje = document.body.getAttribute("data-aviso");
    if (mensaje) { avisoFlotante(mensaje); }
  });
})();
