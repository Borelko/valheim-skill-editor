"""Консольный интерфейс редактора навыков."""

import argparse
import json
import sys
from pathlib import Path

from .core import Character, find_character_files
from .skills import (SKILL_LIST, all_editable_ids, is_known,
                     skill_name)


def print_skill_table(ch=None) -> None:
    have = {s for s, _, _ in ch.player.skills} if ch else set()
    print(f"\nВ игре {len(SKILL_LIST)} навыков: " + ", ".join(SKILL_LIST))
    print("\nВсе идентификаторы, которые можно задать:")
    for sid in all_editable_ids():
        mark = ("" if ch is None
                else "изучен" if sid in have else "не изучен")
        print(f"  id {sid:<5} {skill_name(sid):<40} {mark}")



# --------------------------------------------------------------- чтение ----


def show(ch: Character) -> None:
    c, pl = ch.container, ch.player
    print(f"Файл:          {ch.path.name} ({len(ch.raw)} б)")
    print(f"Контейнер:     payload {c['payload_size']} б, SHA512 "
          f"{'совпал' if c['hash_ok'] else 'НЕ совпал'}")
    print(f"Блок игрока:   версия {pl.version}, {len(pl.blob)} б "
          f"(голова {len(pl.header)} б, хвост {len(pl.tail)} б — не разобраны)")
    head = pl.header_values()
    print(f"Числа в голове: {[round(x, 2) for x in head]}"
          f"   (похоже на HP/стамину/время — не подтверждено)")
    print(f"\nВнешность:     борода {pl.beard}, волосы {pl.hair}, "
          f"модель {pl.model}")
    print(f"Цвет волос:    {[round(x, 3) for x in pl.hair_color]}")
    print(f"Рецептов:      {len(pl.recipes)}")
    print(f"Материалов:    {len(pl.materials)}")
    print(f"Станки:        {pl.stations}")
    print(f"Трофеи:        {pl.trophies}")
    print(f"Биомы:         {pl.biomes}")
    print(f"Туториалы:     {len(pl.tutorials)}, уникальные: {pl.uniques}")
    print(f"Еда:           " + (", ".join(f"{n} (осталось {t:.0f} с)"
                                          for n, t in pl.foods) or "нет"))
    print(f"\nНавыки (v{pl.skills_version}):")
    for sid, lvl, acc in sorted(pl.skills, key=lambda s: -s[1]):
        print(f"  {sid:>4}  {skill_name(sid):<40} {lvl:6.2f}"
              f"   (накоплено {acc:.2f})")


def to_json(ch: Character) -> dict:
    pl = ch.player
    return {
        "file": ch.path.name,
        "container": ch.container,
        "player_version": pl.version,
        "beard": pl.beard, "hair": pl.hair, "model": pl.model,
        "skin_color": pl.skin_color, "hair_color": pl.hair_color,
        "recipes": pl.recipes, "stations": pl.stations,
        "materials": pl.materials, "tutorials": pl.tutorials,
        "uniques": pl.uniques, "trophies": pl.trophies, "biomes": pl.biomes,
        "texts": pl.texts, "foods": pl.foods,
        "skills": [{"id": s, "name": SKILL_NAMES.get(s, "?"),
                    "level": l, "accumulator": a} for s, l, a in pl.skills],
    }


# --------------------------------------------------------------- CLI ------




def parse_assignments(items):
    """Разбор строк вида '3=50' в список (id, уровень)."""
    out = []
    for raw in items:
        sid, _, lvl = raw.replace(" ", "").partition("=")
        if not sid.isdigit() or not lvl:
            raise ValueError(f"не понял '{raw}', нужен формат ID=УРОВЕНЬ")
        level = float(lvl)
        if not 0.0 <= level <= 100.0:
            raise ValueError(f"уровень {level} вне диапазона 0..100")
        out.append((int(sid), level))
    return out


def apply_and_save(ch: Character, pairs, out: Path, backup: bool,
                   check: bool = True) -> bool:
    """Меняет навыки и сохраняет. Пишет только если round-trip чистый."""
    if check and not ch.verify():
        print("Файл не пересобирается байт в байт — правка отменена.",
              file=sys.stderr)
        return False
    for sid, level in pairs:
        existed = ch.player.set_skill(sid, level)
        name = skill_name(sid)  # noqa: F841
        print(f"  {sid:>4} {name:<40} -> {level:g}"
              + ("" if existed else "   (навык добавлен)"))
        if not existed and not is_known(sid):
            print(f"       ВНИМАНИЕ: id {sid} нет в таблице навыков. "
                  f"Если такого навыка в игре не существует, запись будет "
                  f"лишней.")
    if backup and out == ch.path:
        bak = out.with_suffix(out.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(ch.raw)
            print(f"Бэкап оригинала: {bak}")
    ch.save(out)
    print(f"Сохранено: {out}")
    return True


def ask(prompt: str) -> str:
    """input() с понятным сообщением, если ввод недоступен."""
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit(
            "\nВвод недоступен в этой консоли.\n"
            "В PyCharm: Run -> Edit Configurations -> Modify options ->\n"
            "  отметить 'Emulate terminal in output console'.\n"
            "Либо задавай правки аргументами: --set-skill 3=50 --in-place")


def choose_character(files):
    if len(files) == 1:
        print(f"Персонаж: {files[0].name}\n")
        return files[0]
    print("Найденные персонажи:")
    for i, f in enumerate(files, 1):
        try:
            ch = Character(f)
            top = max(ch.player.skills, key=lambda s: s[1])
            info = (f"{len(ch.player.skills)} навыков, "
                    f"макс {skill_name(top[0])} {top[1]:.1f}")
        except Exception:
            info = "не разобран"
        print(f"  {i}. {f.name:<24} {info}")
    while True:
        raw = ask("Номер персонажа (Enter — выход): ")
        if not raw:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            print()
            return files[int(raw) - 1]
        print("Нет такого номера.")


def show_skills(ch: Character) -> None:
    have = {s for s, _, _ in ch.player.skills}
    print("\nИзученные навыки:")
    for sid, lvl, _ in sorted(ch.player.skills, key=lambda s: -s[1]):
        print(f"  id {sid:<5} {skill_name(sid):<20} {lvl:6.2f}")
    missing = [i for i in all_editable_ids() if i not in have]
    if missing:
        print("\nЕщё не изучены (можно добавить, указав уровень):")
        for sid in missing:
            print(f"  id {sid:<5} {skill_name(sid)}")


def edit_loop(ch: Character) -> bool:
    """Правки до пустой строки. True, если что-то изменено."""
    changed = False
    have = {sk for sk, _, _ in ch.player.skills}
    missing = [i for i in all_editable_ids() if i not in have]
    if missing:
        print(f"\nНе изучено {len(missing)} навыков — их можно добавить, "
              f"просто указав уровень:")
        for sid in missing:
            print(f"  id {sid:<5} {skill_name(sid)}")
    else:
        print("\nУ персонажа изучены все известные навыки.")
    print("\nВводи правки: ID=УРОВЕНЬ через пробел, например  3=50 7=40")
    print("  все=100    — выставить уровень изученным навыкам")
    print("  нет=100    — добавить только неизученные навыки")
    print("  всё+=100   — и добавить неизученные, и выставить уровень всем")
    print("  список     — показать таблицу всех идентификаторов")
    print("  Enter      — закончить правки")
    while True:
        line = ask("> ")
        if not line:
            return changed
        if line.lower() in ("список", "list", "?"):
            print_skill_table(ch)
            continue
        try:
            head = line.lower().split("=")[0].rstrip("+")
            if head in ("нет", "новые", "missing"):
                level = float(line.split("=", 1)[1])
                have = {sk for sk, _, _ in ch.player.skills}
                pairs = [(i, level) for i in all_editable_ids()
                         if i not in have]
                if not pairs:
                    print("  У персонажа уже изучены все известные навыки.")
                    continue
            elif head in ("все", "всё", "all", "*"):
                level = float(line.split("=", 1)[1])
                add_missing = "+" in line.split("=")[0]
                ids = (all_editable_ids() if add_missing
                       else [s for s, _, _ in ch.player.skills])
                pairs = [(i, level) for i in ids]
            else:
                pairs = parse_assignments(line.split())
        except (ValueError, IndexError) as exc:
            print(f"  {exc if str(exc) else 'не понял ввод'}")
            continue
        for sid, level in pairs:
            existed = ch.player.set_skill(sid, level)
            mark = "" if existed else "   (навык добавлен)"
            print(f"  {sid:>4} {skill_name(sid):<40} -> {level:g}{mark}")
        changed = True
        show_skills(ch)


def interactive(files) -> int:
    path = choose_character(files)
    if path is None:
        return 0

    try:
        ch = Character(path)
    except Exception as exc:
        print(f"{path.name}: разобрать не удалось: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2
    show(ch)
    if not ch.verify():
        print("\nФайл не пересобирается байт в байт — правка небезопасна.",
              file=sys.stderr)
        return 2

    if not edit_loop(ch):
        print("Изменений нет, файл не тронут.")
        return 0

    print("\nКуда сохранить?")
    print("  Enter          — перезаписать оригинал (бэкап .bak рядом)")
    print("  имя файла      — сохранить копию в ту же папку")
    dest = ask("> ")
    out = path if not dest else (Path(dest) if Path(dest).is_absolute()
                                 else path.parent / dest)
    print()
    if not apply_and_save(ch, [], out, backup=True, check=False):
        return 2
    print("\nЗакрой Valheim полностью перед запуском, иначе игра "
          "перезапишет файл своей версией.")
    return 0


def diff_skills(a: Path, b: Path) -> None:
    """Показывает, какие навыки изменились между двумя файлами.
    Так можно опытным путём установить, какому навыку какой ID соответствует."""
    sa = {s: (l, acc) for s, l, acc in Character(a).player.skills}
    sb = {s: (l, acc) for s, l, acc in Character(b).player.skills}
    print(f"{a.name} -> {b.name}")
    for sid in sorted(set(sa) | set(sb)):
        la = sa.get(sid, (0.0, 0.0))
        lb = sb.get(sid, (0.0, 0.0))
        if la != lb:
            print(f"  {sid:>4} {skill_name(sid):<40} "
                  f"{la[0]:6.2f} -> {lb[0]:6.2f}   "
                  f"(накоплено {la[1]:.2f} -> {lb[1]:.2f})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Чтение и правка .fch Valheim")
    ap.add_argument("path", type=Path, nargs="?")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--verify", action="store_true",
                    help="проверить, что файл пересобирается байт в байт")
    ap.add_argument("--set-skill", action="append", default=[],
                    metavar="ID=УРОВЕНЬ", help="например --set-skill 3=50")
    ap.add_argument("--set-all", type=float, metavar="УРОВЕНЬ",
                    help="выставить этот уровень навыкам, которые уже есть")
    ap.add_argument("--add-all", type=float, metavar="УРОВЕНЬ",
                    help="то же, но добавляя все известные навыки, "
                         "которых у персонажа нет")
    ap.add_argument("--add-missing", type=float, metavar="УРОВЕНЬ",
                    help="добавить навыки, которых у персонажа ещё нет")
    ap.add_argument("--list-skills", action="store_true",
                    help="показать таблицу идентификаторов и выйти")
    ap.add_argument("--out", type=Path, help="куда сохранить результат")
    ap.add_argument("--in-place", action="store_true",
                    help="перезаписать оригинал, сделав рядом бэкап .bak")
    ap.add_argument("--diff", type=Path, metavar="ФАЙЛ2",
                    help="сравнить навыки двух файлов")
    args = ap.parse_args()

    if args.list_skills:
        print_skill_table()
        return 0

    files = ([args.path] if args.path and args.path.is_file()
             else sorted(args.path.glob("*.fch")) if args.path
             else find_character_files())
    if not files:
        print("Файлы .fch не найдены. Укажи путь первым аргументом.",
              file=sys.stderr)
        return 1

    if args.diff:
        diff_skills(files[0], args.diff)
        return 0

    editing = (bool(args.set_skill) or args.set_all is not None
               or args.add_all is not None or args.add_missing is not None)
    if not editing and not args.verify and not args.json:
        return interactive(files)

    dumps = []
    for i, f in enumerate(files):
        if i:
            print("\n" + "=" * 60 + "\n")
        try:
            ch = Character(f)
        except Exception as exc:
            print(f"{f.name}: не разобран: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            continue

        show(ch)
        dumps.append(to_json(ch))

        if args.verify and not editing:
            print(f"\nRound-trip: "
                  f"{'совпал байт в байт' if ch.verify() else 'РАСХОЖДЕНИЕ'}")

        if editing:
            if not ch.verify():
                print("\nФайл не пересобирается байт в байт — правка отменена.",
                      file=sys.stderr)
                continue
            pairs = parse_assignments(args.set_skill)
            if args.set_all is not None:
                pairs += [(s, args.set_all) for s, _, _ in ch.player.skills]
            if args.add_all is not None:
                pairs += [(i, args.add_all) for i in all_editable_ids()]
            if args.add_missing is not None:
                have = {sk for sk, _, _ in ch.player.skills}
                pairs += [(i, args.add_missing) for i in all_editable_ids()
                          if i not in have]
            out = args.out or (f if args.in_place else None)
            if out is None:
                print("\nУкажи --out ФАЙЛ или --in-place.", file=sys.stderr)
                continue
            print()
            apply_and_save(ch, pairs, out, backup=True, check=False)

    if args.json and dumps:
        args.json.write_text(json.dumps(dumps if len(dumps) > 1 else dumps[0],
                                        ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"\nJSON: {args.json}")
    return 0


def is_frozen() -> bool:
    """True, если запущено из собранного exe."""
    return getattr(sys, "frozen", False)


def run() -> int:
    """Обёртка для exe: ловит ошибки и не даёт окну закрыться."""
    code = 1
    try:
        code = main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(exc.code if isinstance(exc.code, str) else "")
        code = exc.code if isinstance(exc.code, int) else 1
    except BrokenPipeError:
        code = 0
    except KeyboardInterrupt:
        print("\nПрервано.")
        code = 1
    except Exception as exc:
        import traceback
        print("\nНеожиданная ошибка. Покажи этот текст автору скрипта:\n",
              file=sys.stderr)
        traceback.print_exc()
        code = 1
    # пауза нужна только при запуске двойным кликом (без аргументов),
    # иначе она мешает вызову из командной строки
    if is_frozen() and len(sys.argv) == 1:
        try:
            input("\nНажми Enter, чтобы закрыть окно...")
        except EOFError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(run())
