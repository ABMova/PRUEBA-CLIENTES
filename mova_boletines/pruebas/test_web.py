"""Pruebas 2 y 7 - la aplicacion responde y la sesion funciona.

Arranca el servidor real (waitress) en un puerto de pruebas y comprueba con
peticiones HTTP: portada y login, redireccion de las rutas protegidas sin
sesion, cambio obligatorio de contrasena del usuario inicial y permisos.

    .venv\\Scripts\\python.exe pruebas\\test_web.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
PUERTO = 8779
BASE = f"http://127.0.0.1:{PUERTO}"
HOST_PUBLICO = "antonio-mova.prueba.ts.net"

fallos: list[str] = []


def comprobar(condicion: bool, mensaje: str) -> None:
    print(f"  {'OK   ' if condicion else 'FALLO'} {mensaje}")
    if not condicion:
        fallos.append(mensaje)


def arrancar(carpeta: Path) -> subprocess.Popen:
    entorno = dict(os.environ,
                   MOVA_DATOS=str(carpeta),
                   MOVA_PUERTO=str(PUERTO),
                   MOVA_ABRIR_NAVEGADOR="0",
                   MOVA_RECUPERACION="0",
                   MOVA_URL_PUBLICA=f"https://{HOST_PUBLICO}",
                   MOVA_LOG_NIVEL="WARNING")
    proceso = subprocess.Popen(
        [sys.executable, str(RAIZ / "app.py")],  # el mismo Python que ejecuta la prueba
        cwd=str(RAIZ), env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace")

    for _ in range(60):
        try:
            if requests.get(f"{BASE}/salud", timeout=2).status_code == 200:
                return proceso
        except requests.RequestException:
            time.sleep(0.5)
    raise RuntimeError("El servidor no arranco a tiempo")


def main() -> int:  # noqa: PLR0915 - prueba lineal
    carpeta = Path(tempfile.mkdtemp(prefix="mova-web-"))
    print(f"Carpeta de datos de prueba: {carpeta}")
    proceso = arrancar(carpeta)

    try:
        print("\n1) La aplicacion responde")
        salud = requests.get(f"{BASE}/salud", timeout=10)
        comprobar(salud.status_code == 200, f"GET /salud -> {salud.status_code}")

        login = requests.get(f"{BASE}/login", timeout=10)
        comprobar(login.status_code == 200, f"GET /login -> {login.status_code}")
        comprobar("MOVA Boletines Oficiales" in login.text,
                  "la respuesta de /login lleva la cabecera MOVA")
        comprobar("Vigilancia diaria de ayudas y subvenciones" in login.text,
                  "la cabecera lleva el lema de la herramienta")
        comprobar("MOVA</span>" in login.text and "IA</span>" in login.text,
                  "el logotipo MOVA IA se dibuja en la cabecera")

        print("\n2) Sin sesion, las rutas protegidas redirigen (302)")
        for ruta in ("/", "/publicaciones", "/ejecuciones", "/ajustes", "/usuarios", "/copias"):
            respuesta = requests.get(f"{BASE}{ruta}", allow_redirects=False, timeout=10)
            comprobar(respuesta.status_code == 302 and "/login" in respuesta.headers.get("Location", ""),
                      f"GET {ruta} sin sesion -> {respuesta.status_code} hacia login")

        print("\n3) Inicio de sesion con el usuario inicial")
        sesion = requests.Session()
        malo = sesion.post(f"{BASE}/login", data={"usuario": "admin", "clave": "incorrecta"},
                           timeout=10)
        comprobar("Usuario o contrasena incorrectos" in malo.text,
                  "una contrasena incorrecta no deja entrar")

        entrada = sesion.post(f"{BASE}/login",
                              data={"usuario": "admin", "clave": "MovaBoletines2026"},
                              timeout=10, allow_redirects=True)
        comprobar(entrada.status_code == 200, "el usuario inicial entra")
        comprobar("mova_boletines" in sesion.cookies.get_dict(), "se recibe la cookie de sesion")

        print("\n4) El sistema obliga a cambiar la contrasena provisional")
        panel = sesion.get(f"{BASE}/", allow_redirects=False, timeout=10)
        comprobar(panel.status_code == 302 and "cambiar-clave" in panel.headers.get("Location", ""),
                  "el panel redirige al cambio de contrasena")
        formulario = sesion.get(f"{BASE}/cambiar-clave", timeout=10)
        comprobar("obligatorio cambiar la contrasena" in formulario.text,
                  "la pantalla dice que el cambio es obligatorio")

        corta = sesion.post(f"{BASE}/cambiar-clave",
                            data={"actual": "MovaBoletines2026", "nueva": "corta123",
                                  "repetida": "corta123"}, timeout=10)
        comprobar("al menos 10 caracteres" in corta.text, "rechaza contrasenas cortas")

        distintas = sesion.post(f"{BASE}/cambiar-clave",
                                data={"actual": "MovaBoletines2026", "nueva": "ClaveLarga2026!",
                                      "repetida": "OtraDistinta2026!"}, timeout=10)
        comprobar("no coinciden" in distintas.text, "rechaza que las dos nuevas no coincidan")

        cambio = sesion.post(f"{BASE}/cambiar-clave",
                             data={"actual": "MovaBoletines2026", "nueva": "ClaveLarga2026!",
                                   "repetida": "ClaveLarga2026!"}, timeout=10)
        comprobar(cambio.status_code == 200, "acepta la contrasena nueva")

        print("\n5) Ya con sesion, las pantallas responden 200")
        for ruta, texto in (("/", "Resumen de hoy"),
                            ("/ejecuciones", "Ejecucion en curso"),
                            ("/publicaciones", "Filtros"),
                            ("/descartes", "descartadas"),
                            ("/boletines", "Boletines vigilados"),
                            ("/palabras-clave", "Palabras clave"),
                            ("/destinatarios", "Destinatarios"),
                            ("/usuarios", "Usuarios y roles"),
                            ("/ajustes", "Claves y modelos"),
                            ("/copias", "Copias de seguridad"),
                            ("/coste", "Gasto en la API de Anthropic")):
            respuesta = sesion.get(f"{BASE}{ruta}", timeout=15)
            comprobar(respuesta.status_code == 200 and texto in respuesta.text,
                      f"GET {ruta} -> {respuesta.status_code} con su contenido")
            comprobar("MOVA Boletines Oficiales" in respuesta.text,
                      f"  y con la cabecera MOVA en {ruta}")

        print("\n6) Los siete boletines aparecen en el panel")
        panel = sesion.get(f"{BASE}/", timeout=15)
        for codigo in ("DOGV", "BOCM", "DOGC", "BOJA", "BORM", "DOCM", "BOCYL"):
            comprobar(codigo in panel.text, f"  {codigo} listado")

        print("\n7) El progreso se consulta por API")
        progreso = sesion.get(f"{BASE}/api/progreso", timeout=10)
        comprobar(progreso.status_code == 200 and "porcentaje" in progreso.json(),
                  "GET /api/progreso devuelve el estado")

        print("\n8) Permisos: un usuario de consulta no puede administrar")
        sesion.post(f"{BASE}/usuarios", data={"usuario": "consultor", "clave": "ClaveConsulta1",
                                              "rol": "consulta", "nombre": "Solo lectura"},
                    timeout=10)
        otra = requests.Session()
        otra.post(f"{BASE}/login", data={"usuario": "consultor", "clave": "ClaveConsulta1"},
                  timeout=10)
        otra.post(f"{BASE}/cambiar-clave", data={"actual": "ClaveConsulta1",
                                                 "nueva": "ClaveConsulta2026",
                                                 "repetida": "ClaveConsulta2026"}, timeout=10)
        ajustes = otra.get(f"{BASE}/ajustes", allow_redirects=False, timeout=10)
        comprobar(ajustes.status_code == 302,
                  f"un rol de consulta no entra en /ajustes ({ajustes.status_code})")
        lanzar = otra.post(f"{BASE}/ejecuciones/lanzar", data={"fecha": "2026-09-17"},
                           allow_redirects=False, timeout=10)
        comprobar(lanzar.status_code == 302 and "aviso=sin_permiso" in lanzar.headers.get("Location", ""),
                  "un rol de consulta no puede lanzar ejecuciones")
        ve = otra.get(f"{BASE}/publicaciones", timeout=10)
        comprobar(ve.status_code == 200, "pero si puede consultar publicaciones")

        print("\n9) La ruta de descarte es publica pero exige token valido")
        anonimo = requests.Session()
        falso = anonimo.get(f"{BASE}/descartar/tokenQueNoExiste0000000000000", timeout=10)
        comprobar(falso.status_code == 404 and "no es valido" in falso.text,
                  "un token inexistente da 404 con pagina de la herramienta")
        comprobar("MOVA Boletines Oficiales" in falso.text,
                  "la pagina de descarte lleva la identidad visual")

        print("\n10) Cierre de sesion")
        salida = sesion.get(f"{BASE}/salir", allow_redirects=False, timeout=10)
        comprobar(salida.status_code == 302, "salir redirige")
        tras_salir = sesion.get(f"{BASE}/", allow_redirects=False, timeout=10)
        comprobar(tras_salir.status_code == 302, "tras salir, el panel vuelve a pedir acceso")

        print("\n11) Proteccion para publicarla en internet")
        cookie = requests.get(f"{BASE}/login", timeout=10)
        falsa_ip = requests.post(f"{BASE}/login", data={"usuario": "nadie", "clave": "x"},
                                 headers={"X-Forwarded-For": "203.0.113.77"}, timeout=10)
        comprobar(falsa_ip.status_code == 200, "un intento con cabecera X-Forwarded-For inventada")
        import sqlite3
        con = sqlite3.connect(carpeta / "mova.db")
        ultima_ip = con.execute("SELECT ip FROM auditoria WHERE usuario='nadie' "
                                "ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.close()
        comprobar(ultima_ip == "127.0.0.1",
                  f"sin proxy declarado se ignora la IP falsificada (registra {ultima_ip})")

        bloqueo = requests.Session()
        for _ in range(5):
            bloqueo.post(f"{BASE}/login", data={"usuario": "admin", "clave": "mala"}, timeout=10)
        buena = bloqueo.post(f"{BASE}/login", data={"usuario": "admin", "clave": "ClaveLarga2026!"},
                             timeout=10)
        comprobar("Demasiados intentos fallidos" in buena.text,
                  "tras 5 fallos, el usuario queda bloqueado 15 minutos aunque acierte")
        comprobar("mova_boletines" not in bloqueo.cookies.get_dict()
                  or bloqueo.get(f"{BASE}/", allow_redirects=False, timeout=10).status_code == 302,
                  "y no obtiene sesion")
        comprobar("HttpOnly" in cookie.headers.get("Set-Cookie", "HttpOnly")
                  and "Secure" not in cookie.headers.get("Set-Cookie", ""),
                  "en http local la cookie no se marca Secure (con https si)")

        print("\n12) Desde internet solo responden los enlaces del correo")
        publico = {"Host": HOST_PUBLICO}
        for ruta in ("/login", "/", "/publicaciones", "/ajustes", "/usuarios", "/api/progreso"):
            r = requests.get(f"{BASE}{ruta}", headers=publico, allow_redirects=False, timeout=10)
            comprobar(r.status_code == 404 and "Direccion reservada" in r.text,
                      f"desde la direccion publica, {ruta} no existe ({r.status_code})")
        r = requests.get(f"{BASE}/d/claveInventadaQueNoExiste1234567/corto", headers=publico,
                         timeout=10)
        comprobar(r.status_code == 404 and "no es valido" in r.text,
                  "los botones del correo si llegan (y validan su clave)")
        r = requests.get(f"{BASE}/estaticos/mova.css", headers=publico, timeout=10)
        comprobar(r.status_code == 200, "con sus estilos")
        r = requests.get(f"{BASE}/login", headers={"Tailscale-Funnel-Request": "?1"},
                         allow_redirects=False, timeout=10)
        comprobar(r.status_code == 404, "lo que llega por el tunel de Tailscale tambien se filtra")
        r = requests.get(f"{BASE}/login", timeout=10)
        comprobar(r.status_code == 200, "y en local la herramienta sigue entera")

    finally:
        proceso.terminate()
        try:
            proceso.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proceso.kill()

    print(f"\n{'TODAS LAS COMPROBACIONES PASAN' if not fallos else 'FALLOS: ' + str(fallos)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
