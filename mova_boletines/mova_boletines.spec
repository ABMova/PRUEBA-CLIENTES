# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado de MOVA Boletines Oficiales con PyInstaller.

Se incluyen los recursos de solo lectura (plantillas, estaticos, esquema.sql).
NO se incluye la carpeta de datos: asi actualizar es sustituir el .exe y el
historico, la clave y las copias siguen donde estaban.
"""

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web/plantillas', 'web/plantillas'),
        ('web/estaticos', 'web/estaticos'),
        ('datos/esquema.sql', 'datos'),
    ],
    hiddenimports=[
        'negocio.boletines.dogv',
        'negocio.boletines.bocm',
        'negocio.boletines.dogc',
        'negocio.boletines.boja',
        'negocio.boletines.borm',
        'negocio.boletines.docm',
        'negocio.boletines.bocyl',
        'apscheduler.triggers.cron',
        'apscheduler.executors.pool',
        'apscheduler.jobstores.memory',
        'waitress',
        'openpyxl',
        'tzdata',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # La carpeta de datos jamas se empaqueta.
    excludes=['DATOS', '_DATOS', 'tkinter', 'matplotlib', 'numpy', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MOVA Boletines Oficiales',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # consola visible: el registro se ve al arrancar
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='web/estaticos/mova.ico' if __import__('os').path.exists('web/estaticos/mova.ico') else None,
)
