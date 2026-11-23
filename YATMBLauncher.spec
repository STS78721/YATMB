# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['launcher\\YATMBLauncher.py'],
    pathex=['launcher'],
    binaries=[],
    datas=[
        ('launcher\\assets\\yatmb.ico', 'assets'),
        ('runtime\\yatmb.png', 'assets'),
        ('runtime\\yatmb_book.png', 'assets'),
        ('launcher\\yatmb_version.txt', '.'),
        ('tools\\data\\expected-yoshi102.json', 'tools\\data'),
        ('tools\\extract_nup.py', 'tools'),
    ],
    hiddenimports=['PIL._tkinter_finder', 'yatmb_dump'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YATMBLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['launcher\\assets\\yatmb.ico'],
)
