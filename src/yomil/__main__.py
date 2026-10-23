"""Allow `python -m yomil`."""

from yomil.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
