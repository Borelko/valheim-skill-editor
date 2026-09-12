"""Точка входа: python -m valheim_skills

Без аргументов открывается окно, с аргументами работает консольный режим.
Флаг --cli заставляет использовать консоль в любом случае.
"""

import sys


def main() -> int:
    args = sys.argv[1:]
    if "--cli" in args:
        sys.argv.remove("--cli")
        args = sys.argv[1:]
    elif not args:
        from .gui import main as gui_main
        return gui_main()
    from .cli import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
