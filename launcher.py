"""Точка входа для собранного exe.

PyInstaller запускает этот файл: без аргументов открывается окно,
с аргументами работает консольный режим.
"""

import sys

from valheim_skills.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
