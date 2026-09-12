# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

repo_root = Path.cwd()

datas = [
    ('assets', 'assets'),
    ('templates', 'templates'),
    ('tessdata', 'tessdata'),
]

hiddenimports = [
    'Crypto',
    'Crypto.PublicKey.ECC',
    'Crypto.Signature.eddsa',
    'Crypto.Hash.SHA256',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'requests',
    'cv2',
    'numpy',
    'PIL',
    'pytesseract',
]

extra_binaries = []
if sys.platform == 'win32':
    win_tess = Path(r'C:\Program Files\Tesseract-OCR')
    if win_tess.is_dir():
        tess_exe = win_tess / 'tesseract.exe'
        if tess_exe.is_file():
            extra_binaries.append((str(tess_exe), '.'))
        for dll in win_tess.glob('*.dll'):
            extra_binaries.append((str(dll), '.'))

a = Analysis(
    ['main.py'],
    pathex=[str(repo_root)],
    binaries=extra_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['keygen', 'scratch', 'tests'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ApexClashPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/apex_clash_logo.ico' if (repo_root / 'assets' / 'apex_clash_logo.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ApexClashPro',
)
