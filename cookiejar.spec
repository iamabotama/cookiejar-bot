# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for CookieJar Bot
Creates a standalone .exe that can run on Windows without Python installed.

Usage:
    pyinstaller cookiejar.spec

After building, copy these files/folders next to the .exe:
    - .env (your configuration)
    - knowledge/ (will be created if missing)
    - sources/ (will be created if missing)
"""

import os
from pathlib import Path

block_cipher = None

# Get the project root
PROJECT_ROOT = Path(SPECPATH)

# Data files to include in the bundle
datas = [
    # Guardrails markdown file
    (str(PROJECT_ROOT / 'cookiejar' / 'guardrails_v1.md'), 'cookiejar'),
    # Cookie reaction GIF
    (str(PROJECT_ROOT / 'assets' / 'cookie_reaction.gif'), 'assets'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'telegram',
    'telegram.ext',
    'openai',
    'httpx',
    'dotenv',
    'certifi',
]

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='CookieJarBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for logging output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: icon='assets/cookie.ico'
)
