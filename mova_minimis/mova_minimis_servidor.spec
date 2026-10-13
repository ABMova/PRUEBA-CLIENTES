# -*- mode: python ; coding: utf-8 -*-
# PyInstaller · motor de la versión de escritorio (lo arranca la ventana Electron).
# Carpeta (onedir) y no un único .exe: arranca en un par de segundos porque no tiene que
# descomprimirse en cada apertura, y es un solo proceso, fácil de cerrar con la ventana.

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
    [],
    exclude_binaries=True,
    name="MOVAMinimisServidor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="static/marca/mova_minimis.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MOVAMinimisServidor",
)
