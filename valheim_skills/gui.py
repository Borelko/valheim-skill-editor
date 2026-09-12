"""Окно редактора навыков.

Интерфейс поверх valheim_skills.core: сам разбор формата здесь не живёт.
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (Character, find_character_files, is_game_running,
                   make_backup)
from .skills import all_editable_ids, skill_name

TITLE = "Valheim Skill Editor"
MIN_LEVEL, MAX_LEVEL = 0.0, 100.0


class EditorWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITLE)
        self.geometry("620x680")
        self.minsize(520, 480)

        self.character = None          # текущий Character
        self.path = None               # путь к открытому файлу
        self.safe = False              # прошла ли проверка пересборки
        self.entries = {}              # id навыка -> Entry
        self.original = {}             # id навыка -> исходный уровень
        self.files = []

        self._build()
        self.refresh_files()

    # ------------------------------------------------------- разметка ----

    def _build(self):
        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.pack(fill="x")

        ttk.Label(top, text="Персонаж:").pack(side="left")
        self.combo = ttk.Combobox(top, state="readonly", width=30)
        self.combo.pack(side="left", padx=6)
        self.combo.bind("<<ComboboxSelected>>", self.on_pick)
        ttk.Button(top, text="Обновить", command=self.refresh_files
                   ).pack(side="left")
        ttk.Button(top, text="Открыть файл…", command=self.on_browse
                   ).pack(side="left", padx=6)

        self.info = ttk.Label(self, text="Персонаж не выбран",
                              padding=(10, 0, 10, 6), foreground="#555")
        self.info.pack(fill="x")

        # прокручиваемый список навыков
        body = ttk.Frame(self, padding=(10, 0))
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, highlightthickness=0)
        bar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        self.rows = ttk.Frame(canvas)
        self.rows.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=self.rows, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(window, width=e.width))
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x")
        self.btn_all = ttk.Button(bottom, text="Всем 100",
                                  command=lambda: self.fill_all(100))
        self.btn_all.pack(side="left")
        self.btn_reset = ttk.Button(bottom, text="Сбросить",
                                    command=self.load_values)
        self.btn_reset.pack(side="left", padx=6)
        self.btn_save = ttk.Button(bottom, text="Сохранить",
                                   command=self.on_save)
        self.btn_save.pack(side="right")

        self.status = ttk.Label(self, text="", padding=(10, 0, 10, 8),
                                foreground="#555", wraplength=580,
                                justify="left")
        self.status.pack(fill="x")
        self.set_buttons(False)

    def set_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for b in (self.btn_all, self.btn_reset, self.btn_save):
            b.configure(state=state)

    def say(self, text: str, bad: bool = False):
        self.status.configure(text=text, foreground="#b00" if bad else "#555")

    # ---------------------------------------------------- выбор файла ----

    def refresh_files(self):
        self.files = find_character_files()
        self.combo["values"] = [f.name for f in self.files]
        if self.files:
            self.say(f"Найдено персонажей: {len(self.files)}")
        else:
            self.say("Персонажи не найдены. Открой файл .fch вручную.")

    def on_pick(self, _event=None):
        i = self.combo.current()
        if 0 <= i < len(self.files):
            self.open_file(self.files[i])

    def on_browse(self):
        name = filedialog.askopenfilename(
            title="Выбери файл персонажа",
            filetypes=[("Персонаж Valheim", "*.fch"), ("Все файлы", "*.*")])
        if name:
            self.open_file(Path(name))

    def open_file(self, path: Path):
        try:
            self.character = Character(path)
        except Exception as exc:
            self.character = None
            self.clear_rows()
            self.set_buttons(False)
            self.info.configure(text=f"{path.name}: не удалось разобрать")
            self.say(f"{type(exc).__name__}: {exc}\n"
                     f"Возможно, вышел новый патч игры и формат изменился. "
                     f"Сообщи об этом в issues проекта.", bad=True)
            return

        self.path = path
        self.safe = self.character.verify()
        pl = self.character.player
        self.info.configure(
            text=f"{path.name}  ·  блок версии {pl.version}  ·  "
                 f"изучено навыков: {len(pl.skills)}")
        self.build_rows()
        self.load_values()
        self.set_buttons(True)

        if self.safe:
            self.say("Файл разобран, проверка пересборки пройдена.")
        else:
            self.btn_save.configure(state="disabled")
            self.say("Файл читается, но не пересобирается точно. "
                     "Сохранение отключено, чтобы не повредить персонажа.",
                     bad=True)

    # ------------------------------------------------------- таблица ----

    def clear_rows(self):
        for w in self.rows.winfo_children():
            w.destroy()
        self.entries.clear()

    def build_rows(self):
        self.clear_rows()
        have = {s for s, _, _ in self.character.player.skills}
        check = (self.register(self.validate), "%P")

        for row, sid in enumerate(all_editable_ids()):
            known = sid in have
            frame = ttk.Frame(self.rows)
            frame.pack(fill="x", pady=1)

            ttk.Label(frame, text=skill_name(sid), width=22, anchor="w",
                      foreground="black" if known else "#888").pack(side="left")
            entry = ttk.Entry(frame, width=8, justify="right",
                              validate="key", validatecommand=check)
            entry.pack(side="left", padx=6)
            ttk.Label(frame, text="" if known else "не изучен", width=12,
                      foreground="#888").pack(side="left")
            self.entries[sid] = entry

    @staticmethod
    def validate(text: str) -> bool:
        if text == "":
            return True
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return False
        return MIN_LEVEL <= value <= MAX_LEVEL

    def load_values(self):
        if not self.character:
            return
        self.original = {s: l for s, l, _ in self.character.player.skills}
        for sid, entry in self.entries.items():
            entry.delete(0, "end")
            if sid in self.original:
                entry.insert(0, f"{self.original[sid]:g}")
        self.say("Значения сброшены к тем, что в файле.")

    def fill_all(self, level: float):
        for entry in self.entries.values():
            entry.delete(0, "end")
            entry.insert(0, f"{level:g}")
        self.say(f"Во все поля вписано {level:g}. "
                 f"Пустые поля означали бы неизученный навык.")

    def collect(self):
        """Изменения: список (id, уровень) и сколько из них новых навыков."""
        changes, added = [], 0
        for sid, entry in self.entries.items():
            text = entry.get().strip().replace(",", ".")
            if not text:
                continue
            level = float(text)
            was = self.original.get(sid)
            if was is None:
                changes.append((sid, level))
                added += 1
            elif abs(was - level) > 1e-6:
                changes.append((sid, level))
        return changes, added

    # ----------------------------------------------------- сохранение ----

    def on_save(self):
        if not self.character or not self.safe:
            return
        try:
            changes, added = self.collect()
        except ValueError:
            self.say("В каком-то поле не число.", bad=True)
            return
        if not changes:
            self.say("Менять нечего: значения совпадают с файлом.")
            return

        if is_game_running():
            messagebox.showwarning(
                TITLE,
                "Valheim сейчас запущен. Игра держит персонажа в памяти и "
                "перезапишет файл при выходе.\n\nЗакрой игру полностью и "
                "попробуй снова.")
            return

        note = f", из них новых навыков: {added}" if added else ""
        if not messagebox.askyesno(
                TITLE, f"Изменений: {len(changes)}{note}.\n\n"
                       f"Оригинал будет скопирован рядом. Сохранить?"):
            return

        try:
            backup = make_backup(self.path)
            for sid, level in changes:
                self.character.player.set_skill(sid, level)
            self.character.save(self.path)
            self.character = Character(self.path)
            self.safe = self.character.verify()
        except Exception as exc:
            self.say(f"Не удалось сохранить: {type(exc).__name__}: {exc}",
                     bad=True)
            return

        self.build_rows()
        self.load_values()
        self.info.configure(
            text=f"{self.path.name}  ·  блок версии "
                 f"{self.character.player.version}  ·  изучено навыков: "
                 f"{len(self.character.player.skills)}")
        self.say(f"Сохранено. Копия оригинала: {backup.name}")


def main() -> int:
    try:
        EditorWindow().mainloop()
    except tk.TclError as exc:
        print(f"Не удалось открыть окно: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
