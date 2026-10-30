"""Entry point for the frozen app (PyInstaller runs this, not ``python -m yomil``)."""

import sys

from yomil.app.main import main

sys.exit(main())
