# PyInstaller build for YOMIL: windowed, one-folder (`make freeze`).
# One folder starts faster than one file and trips antivirus tools less often.
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

here = Path(SPECPATH)
icon = here.parent / "src" / "yomil" / "app" / "icons" / "yomil.ico"

a = Analysis(
    [str(here / "launcher.py")],
    # Migrations and the icon, plus the package metadata `yomil.__version__` reads.
    datas=collect_data_files("yomil") + copy_metadata("yomil"),
    excludes=["tkinter", "unittest", "pydoc"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="yomil",
    icon=str(icon),
    console=False,  # a windowed app: no console window
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="YOMIL", upx=False)
