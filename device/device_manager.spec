from PyInstaller.utils.hooks import collect_all

folders = [
    'library',
    'sdk',
    'driver'
]

files = []
binaries = []
imports = []

for folder in folders:
    files.append((f'../{folder}', folder))

files.append(('icon.png', '.'))

result = collect_all('ctypes')
files += result[0]
binaries += result[1]
imports += result[2]

analysis = Analysis(
    ['device_manager.py'],
    pathex=[],
    binaries=binaries,
    datas=files,
    hiddenimports=[
        'serial',
        'serial.tools.list_ports',
        'pyvisa',
        'pyvisa-py',
        'pyvisa_py',
        'pyvisa_py.tcpip',
        'pyvisa_py.usb',
        'pyvisa_py.serial',
        'numpy',
    ] + imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name='DeviceManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.png'
)
