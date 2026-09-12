"""Тесты окна: проверяем логику, а не внешний вид.

Если графической подсистемы нет, тесты пропускаются — на CI под Windows
tkinter доступен, и они выполнятся.
"""

import pytest

from valheim_skills.core import Character
from tests.synthetic import build_fch

tk = pytest.importorskip("tkinter")


@pytest.fixture
def window():
    from valheim_skills.gui import EditorWindow
    try:
        app = EditorWindow()
    except tk.TclError:
        pytest.skip("нет графической подсистемы")
    yield app
    app.destroy()


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "Тест.fch"
    path.write_bytes(build_fch(skills=[(102, 10.0, 1.0), (3, 5.0, 0.0)]))
    return path


def test_opens_file_and_builds_all_rows(window, sample):
    from valheim_skills.skills import all_editable_ids
    window.open_file(sample)
    assert window.safe
    assert len(window.entries) == len(all_editable_ids())
    assert window.entries[102].get() == "10"
    assert window.entries[110].get() == ""      # навык не изучен


def test_rejects_bad_input(window):
    assert window.validate("42.5")
    assert window.validate("")
    assert not window.validate("101")
    assert not window.validate("-1")
    assert not window.validate("сто")


def test_collect_sees_changes_and_additions(window, sample):
    window.open_file(sample)
    window.entries[102].delete(0, "end")
    window.entries[102].insert(0, "88")
    window.entries[110].insert(0, "33")

    changes, added = window.collect()
    assert sorted(changes) == [(102, 88.0), (110, 33.0)]
    assert added == 1


def test_collect_ignores_untouched_fields(window, sample):
    window.open_file(sample)
    assert window.collect() == ([], 0)


def test_save_writes_values_and_backup(window, sample, monkeypatch):
    import valheim_skills.gui as gui
    monkeypatch.setattr(gui, "is_game_running", lambda: False)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)

    before = Character(sample)
    window.open_file(sample)
    window.entries[102].delete(0, "end")
    window.entries[102].insert(0, "77")
    window.on_save()

    after = Character(sample)
    levels = {s: l for s, l, _ in after.player.skills}
    assert levels[102] == 77.0
    assert after.container["hash_ok"]
    assert after.player.header == before.player.header
    assert list(sample.parent.glob("*.bak"))


def test_save_blocked_while_game_runs(window, sample, monkeypatch):
    import valheim_skills.gui as gui
    monkeypatch.setattr(gui, "is_game_running", lambda: True)
    warned = []
    monkeypatch.setattr(gui.messagebox, "showwarning",
                        lambda *a, **k: warned.append(a))

    window.open_file(sample)
    window.entries[102].delete(0, "end")
    window.entries[102].insert(0, "99")
    window.on_save()

    assert warned
    assert {s: l for s, l, _ in Character(sample).player.skills}[102] == 10.0


def test_broken_file_disables_saving(window, tmp_path):
    path = tmp_path / "Битый.fch"
    path.write_bytes(b"\x10\x00\x00\x00" + b"\x00" * 16)
    window.open_file(path)
    assert window.character is None
    assert str(window.btn_save["state"]) == "disabled"
