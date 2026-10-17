# PyInstaller spec: builds a self-contained app (no Python needed on the user's computer).
#   pyinstaller packaging/ManuscriptAssistant.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
NAME = "ManuscriptAssistant"

datas, binaries, hiddenimports = [], [], []
for package in ("streamlit", "pypdfium2", "pypdfium2_raw"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
for package in ("docx", "spellchecker", "pdfminer"):
    datas += collect_data_files(package)
datas += [
    (str(ROOT / "app.py"), "."),
    (str(ROOT / "data"), "data"),
    (str(ROOT / ".streamlit"), ".streamlit"),
]
# app.py is run by Streamlit as a script, so list what it imports explicitly
hiddenimports += collect_submodules("core") + ["pandas", "lxml.etree", "pdfplumber", "pypdf", "bs4", "requests"]

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
    # python-docx opens templates via "docx/parts/../templates", so its package folders must exist on disk
    module_collection_mode={"docx": "pyz+py"},
)
pyz = PYZ(a.pure)
is_mac = sys.platform == "darwin"
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=not is_mac,  # Windows/Linux: the console window shows the address; closing it quits
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
if is_mac:
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        bundle_identifier="io.github.manuscript-assistant",
        info_plist={"CFBundleDisplayName": "Manuscript Assistant", "NSHighResolutionCapable": True},
    )
