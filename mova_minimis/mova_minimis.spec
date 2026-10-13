# -*- mode: python ; coding: utf-8 -*-
# PyInstaller · MOVA Minimis en un único .exe sin consola.
# Dentro del .exe van plantillas, estáticos y esquema (config.RAIZ_CODIGO = sys._MEIPASS).
# Los datos NUNCA van dentro: config.DATOS apunta a %LOCALAPPDATA%\MOVA Minimis\data
# (o a MOVA_MINIMIS_DATOS del .env que haya junto al .exe).

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
        ("models/schema.sql", "models"),
        ("plantillas_informe", "plantillas_informe"),
    ],
    hiddenimports=[
        "waitress", "routes.auth", "routes.dashboard", "routes.consultas", "routes.resultados", "routes.admin",
        "win32com.client", "pythoncom", "pypdf",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MOVA Minimis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="static/marca/mova_minimis.ico",
    version=None,
)
