# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: ejecutable de ventana (sin consola), con icono, en carpeta (onedir).
# Se empaquetan ui/estilos, ui/recursos y scripts_entrenamiento. NUNCA almacen/.
# Uso: empaquetar.bat  (o: python -m PyInstaller --noconfirm --clean mova_dgx_trainer.spec)

NOMBRE = "MOVA_DGX_Spark_Trainer"

datas = [
    ("ui/estilos", "ui/estilos"),
    ("ui/recursos", "ui/recursos"),
    ("scripts_entrenamiento", "scripts_entrenamiento"),
]

excludes = [
    "tkinter", "torch", "tensorflow", "IPython", "jupyter", "notebook", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOMBRE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # --windowed
    icon="ui/recursos/icono.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=NOMBRE,
)
