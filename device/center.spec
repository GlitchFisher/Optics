import sys

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

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

matplotlib_datas = collect_data_files('matplotlib')
files += matplotlib_datas

pyvisa_datas = collect_data_files('pyvisa')
files += pyvisa_datas

hidden_imports = [
    'serial',
    'serial.tools.list_ports',
    'pyvisa',
    'pyvisa-py',
    'pyvisa_py',
    'pyvisa_py.tcpip',
    'pyvisa_py.usb',
    'pyvisa_py.serial',
    'pyvisa_py.rpc',
    'pyvisa_py.highlevel',
    'numpy',
    'numpy.core._methods',
    'numpy.lib.format',
    'matplotlib',
    'matplotlib.backends',
    'matplotlib.backends.backend_agg',
    'matplotlib.pyplot',
    'matplotlib.figure',
    'matplotlib.axes',
    'matplotlib.lines',
    'matplotlib.text',
    'matplotlib.patches',
    'matplotlib.image',
    'matplotlib.collections',
    'matplotlib.colors',
    'matplotlib.cm',
    'matplotlib.ticker',
    'matplotlib.gridspec',
    'matplotlib.transforms',
    'matplotlib.quiver',
    'matplotlib.path',
    'matplotlib.contour',
    'matplotlib.table',
    'matplotlib.legend',
    'matplotlib.legend_handler',
    'matplotlib.offsetbox',
    'matplotlib.widgets',
    'matplotlib._pylab_helpers',
    'matplotlib.backends._backend_agg',
    'tkinter',
    'threading',
    'subprocess',
    'datetime',
    'pathlib',
    'os',
    'sys',
    'time',
    're',
    'typing',
    'tempfile',
    'ctypes',
    'ctypes.wintypes' if sys.platform == 'win32' else 'ctypes.util',
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
]

hidden_imports += collect_submodules('pyvisa_py')
hidden_imports += collect_submodules('numpy')
hidden_imports += collect_submodules('matplotlib')

analysis = Analysis(
    ['center.py'],
    pathex=[],
    binaries=binaries,
    datas=files,
    hiddenimports=hidden_imports + imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name='DeviceCenter',
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
