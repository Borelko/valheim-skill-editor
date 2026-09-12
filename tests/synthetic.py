"""Генератор синтетических файлов персонажей.

Нужен, чтобы тесты не зависели от настоящих сохранений: в них лежит
идентификатор игрока, и класть их в репозиторий не стоит.

Файлы повторяют структуру реального формата: контейнер с SHA512, профиль
версии 46 с непрозрачной для нас головой, блок персонажа версии 33.
"""

import hashlib
import struct


class Writer:
    def __init__(self):
        self.b = bytearray()

    def raw(self, v):
        self.b += v
        return self

    def i(self, v):
        self.b += struct.pack("<i", v)
        return self

    def f(self, v):
        self.b += struct.pack("<f", v)
        return self

    def bo(self, v):
        self.b += bytes([1 if v else 0])
        return self

    def s(self, text):
        data = text.encode("utf-8")
        n = len(data)
        while True:
            x, n = n & 0x7F, n >> 7
            self.b += bytes([x | (0x80 if n else 0)])
            if not n:
                break
        self.b += data
        return self

    def slist(self, items):
        self.i(len(items))
        for x in items:
            self.s(x)
        return self

    def sidict(self, d):
        self.i(len(d))
        for k, v in d.items():
            self.s(k).i(v)
        return self

    def ssdict(self, d):
        self.i(len(d))
        for k, v in d.items():
            self.s(k).s(v)
        return self


def build_player(skills, foods=(), header_extra=b"", recipes=None):
    """Блок персонажа версии 33."""
    w = Writer()
    w.i(33).f(25.0).f(0.81).f(50.0).f(1234.5).f(0.0)
    # непрозрачная часть головы: у настоящих файлов тут инвентарь
    w.raw(b"\x00" * 20 + header_extra)

    w.slist(recipes or ["$item_axe_stone", "$item_club", "$item_torch",
                        "$piece_workbench", "$piece_forge", "$item_wood"])
    w.sidict({"$piece_workbench": 2})
    w.slist(["$item_wood", "$item_stone"])
    w.slist(["temple1", "inventory"])
    w.slist(["invrows 4"])
    w.slist(["TrophyBoar"])
    w.slist(["Луга"])
    w.ssdict({"$tutorial_label": "$tutorial_text"})
    w.s("Beard2").s("Hair6")
    w.f(1.0).f(1.0).f(1.0)
    w.f(0.1).f(0.05).f(0.03)
    w.i(0)

    w.i(len(foods))
    for name, ttl in foods:
        w.s(name).f(ttl)

    w.i(2).i(len(skills))
    for sid, level, acc in skills:
        w.i(sid).f(level).f(acc)

    # хвост: у настоящих файлов тут известные постройки
    w.raw(b"\x00" * 16)
    return bytes(w.b)


def build_profile(player_blob, name="Тест"):
    """Профиль версии 46. Голова намеренно непрозрачная, как в игре."""
    w = Writer()
    w.i(46).i(3).i(10)
    for v in (1.0, 2.0, 3.0):
        w.f(v)
    w.raw(b"\x11" * 24)          # произвольные данные, должны уцелеть
    w.s(name)
    w.raw(b"\x22" * 8)
    w.bo(True).i(len(player_blob)).raw(player_blob)
    return bytes(w.b)


def build_fch(skills=None, foods=(), name="Тест", header_extra=b""):
    """Готовый файл .fch с контейнером и корректным SHA512."""
    skills = skills or [(102, 10.5, 1.0), (3, 5.0, 0.0), (13, 20.0, 3.0)]
    payload = build_profile(build_player(skills, foods, header_extra), name)
    w = Writer()
    w.i(len(payload)).raw(payload)
    digest = hashlib.sha512(payload).digest()
    w.i(len(digest)).raw(digest)
    return bytes(w.b)
