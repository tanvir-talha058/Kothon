# PyInstaller spec for Kothon — build with: python -m PyInstaller kothon.spec
# Output: dist/Kothon/ (onedir). Models are NOT bundled; the installer (or the
# user) places model folders in a "models" directory next to Kothon.exe.
from PyInstaller.utils.hooks import collect_all

datas = [("ui", "ui")]
binaries = []
# keyring picks its backend by entry point at runtime; PyInstaller can't see
# that, so name the Windows Credential Manager backend explicitly.
hiddenimports = [
    "keyring.backends.Windows",
    "keyring.backends.chainer",
    "keyring.backends.fail",
]

for pkg in ("vosk", "sherpa_onnx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc",
        # Heavy libraries present on dev machines that Kothon never uses —
        # optional imports inside collected submodules would drag them in
        "torch", "torchvision", "torchaudio", "scipy", "matplotlib",
        "pandas", "sympy", "networkx", "IPython", "jedi", "optree",
        "onnx", "sklearn", "numba", "cv2",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kothon",
    icon="assets/kothon.ico",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    version="version_info.txt",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Kothon",
)
