"""Allow `python -m forensics` execution."""

from forensics.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
