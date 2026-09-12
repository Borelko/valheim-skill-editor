"""Разбор и сборка файлов персонажей Valheim (.fch).\n\nФормат: контейнер [длина][payload][длина][SHA512], внутри профиль\nверсии 46, последним полем которого лежит блок персонажа версии 33.\nВсё, что модуль не разбирает — статистика, миры, инвентарь, известные\nпостройки — сохраняется байт в байт.\n\nМодуль не печатает и не спрашивает: только данные и исключения."""

import hashlib
import struct
from pathlib import Path


class ZReader:
    def __init__(self, data: bytes, name: str = "pkg"):
        self.data, self.pos, self.name = data, 0, name

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise EOFError(f"{self.name}: нужно {n} б на 0x{self.pos:x}, "
                           f"есть {self.remaining()}")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def bool_(self): return self.take(1)[0] != 0
    def int_(self): return struct.unpack("<i", self.take(4))[0]
    def long_(self): return struct.unpack("<q", self.take(8))[0]
    def float_(self): return struct.unpack("<f", self.take(4))[0]
    def vec3(self): return [self.float_() for _ in range(3)]

    def str_(self) -> str:
        """Строка с 7-битным префиксом длины (как C# BinaryWriter)."""
        n, shift = 0, 0
        while True:
            if shift > 35:
                raise ValueError(f"{self.name}: битая длина строки")
            b = self.take(1)[0]
            n |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return self.take(n).decode("utf-8")

    def str_list(self): return [self.str_() for _ in range(self.int_())]
    def str_int_dict(self): return {self.str_(): self.int_()
                                    for _ in range(self.int_())}
    def str_str_dict(self): return {self.str_(): self.str_()
                                    for _ in range(self.int_())}


class ZWriter:
    def __init__(self): self.b = bytearray()

    def raw(self, v): self.b += v; return self
    def bool_(self, v): self.b += bytes([1 if v else 0]); return self
    def int_(self, v): self.b += struct.pack("<i", v); return self
    def long_(self, v): self.b += struct.pack("<q", v); return self
    def float_(self, v): self.b += struct.pack("<f", v); return self
    def vec3(self, v): [self.float_(x) for x in v]; return self

    def str_(self, s: str):
        e = s.encode("utf-8")
        n = len(e)
        while True:
            x, n = n & 0x7F, n >> 7
            self.b += bytes([x | (0x80 if n else 0)])
            if not n:
                break
        self.b += e
        return self

    def str_list(self, lst):
        self.int_(len(lst))
        [self.str_(s) for s in lst]
        return self

    def str_int_dict(self, d):
        self.int_(len(d))
        [(self.str_(k), self.int_(v)) for k, v in d.items()]
        return self

    def str_str_dict(self, d):
        self.int_(len(d))
        [(self.str_(k), self.str_(v)) for k, v in d.items()]
        return self


# ------------------------------------------------------------ контейнер ----

def read_container(raw: bytes):
    z = ZReader(raw, "file")
    payload = z.take(z.int_())
    stored = z.take(z.int_()) if z.remaining() >= 4 else b""
    return payload, {
        "payload_size": len(payload),
        "hash_size": len(stored),
        "hash_ok": bool(stored) and hashlib.sha512(payload).digest() == stored,
        "extra": z.remaining(),
    }


def write_container(payload: bytes) -> bytes:
    w = ZWriter()
    w.int_(len(payload)).raw(payload)
    h = hashlib.sha512(payload).digest()
    w.int_(len(h)).raw(h)
    return bytes(w.b)


# --------------------------------------------------- поиск блока игрока ----

def find_player_blob(payload: bytes):
    """
    Блок данных персонажа — последнее поле профиля: [bool 1][int32 len][data],
    где len совпадает с остатком payload. Ищем по этому признаку, не разбирая
    статистику и миры, устройство которых меняется от патча к патчу.
    """
    for off in range(1, len(payload) - 4):
        n = struct.unpack("<i", payload[off:off + 4])[0]
        if n <= 0 or off + 4 + n != len(payload):
            continue
        if payload[off - 1] != 1:
            continue
        return off - 1, payload[off + 4:]
    raise ValueError("не найден блок данных персонажа")


# ------------------------------------------------------- данные игрока -----

class PlayerData:
    """Разбирает блок персонажа. Голова и хвост хранятся сырыми."""

    FIELDS = ("recipes", "stations", "materials", "tutorials", "uniques",
              "trophies", "biomes", "texts", "beard", "hair",
              "skin_color", "hair_color", "model", "foods", "skills")

    def __init__(self, blob: bytes):
        self.blob = blob
        self.version = struct.unpack("<i", blob[:4])[0]
        self.header = None
        for start in self._candidates():
            try:
                self._parse_chain(start)
            except Exception:
                continue
            self.header = blob[:start]
            self.chain_start = start
            return
        raise ValueError(
            "не найдено начало списка рецептов — возможно, новый формат блока")

    def _candidates(self):
        """
        Голова блока содержит инвентарь и потому имеет переменную длину.
        Ищем начало списка рецептов по признаку: int32 с правдоподобным
        числом элементов, за которым сразу идёт строка-токен вида "$item_...".
        Сначала подходящие места, затем — сплошной перебор как запасной путь.
        """
        likely = []
        for off in range(4, len(self.blob) - 8):
            n = struct.unpack("<i", self.blob[off:off + 4])[0]
            if not (5 <= n <= 3000):
                continue
            ln = self.blob[off + 4]
            if not (2 <= ln <= 0x7F):
                continue
            if self.blob[off + 5:off + 6] != b"$":
                continue
            likely.append(off)
        yield from likely
        seen = set(likely)
        for off in range(4, min(len(self.blob) - 8, 8192)):
            if off not in seen:
                yield off

    def _parse_chain(self, start: int) -> None:
        z = ZReader(self.blob, "player")
        z.pos = start

        recipes = z.str_list()
        if not (5 <= len(recipes) <= 2000):
            raise ValueError("нерелевантный список рецептов")
        if not all(r and r.isprintable() for r in recipes):
            raise ValueError("мусор вместо рецептов")

        stations = z.str_int_dict()
        materials = z.str_list()
        tutorials = z.str_list()
        uniques = z.str_list()
        trophies = z.str_list()
        biomes = z.str_list()
        texts = z.str_str_dict()
        beard, hair = z.str_(), z.str_()
        skin_color, hair_color = z.vec3(), z.vec3()
        model = z.int_()

        foods = []
        for _ in range(z.int_()):
            # запись еды: имя + один float (оставшееся время действия)
            foods.append([z.str_(), z.float_()])

        sk_ver, sk_n = z.int_(), z.int_()
        if not (1 <= sk_ver <= 5 and 0 <= sk_n <= 64):
            raise ValueError("непохоже на навыки")
        skills = []
        for _ in range(sk_n):
            sid, lvl = z.int_(), z.float_()
            acc = z.float_() if sk_ver >= 2 else 0.0
            if not (0 <= sid <= 200 and 0.0 <= lvl <= 100.0):
                raise ValueError("неправдоподобный навык")
            skills.append([sid, lvl, acc])

        # хвост: неразобранный блок (известные постройки и т.п.)
        self.tail = self.blob[z.pos:]
        for k in self.FIELDS:
            setattr(self, k, locals()[k])
        self.skills_version = sk_ver

    def serialize(self) -> bytes:
        w = ZWriter().raw(self.header)
        w.str_list(self.recipes).str_int_dict(self.stations)
        w.str_list(self.materials).str_list(self.tutorials)
        w.str_list(self.uniques).str_list(self.trophies).str_list(self.biomes)
        w.str_str_dict(self.texts)
        w.str_(self.beard).str_(self.hair)
        w.vec3(self.skin_color).vec3(self.hair_color).int_(self.model)
        w.int_(len(self.foods))
        for name, ttl in self.foods:
            w.str_(name).float_(ttl)
        w.int_(self.skills_version).int_(len(self.skills))
        for sid, lvl, acc in self.skills:
            w.int_(sid).float_(lvl)
            if self.skills_version >= 2:
                w.float_(acc)
        return bytes(w.raw(self.tail).b)

    def header_values(self, count: int = 5):
        """Первые числа головы блока: похоже на здоровье, стамину и время
        с момента смерти. Назначение не подтверждено, только для показа."""
        out = []
        for i in range(4, min(4 + count * 4, len(self.header)), 4):
            out.append(struct.unpack("<f", self.header[i:i + 4])[0])
        return out

    # --- редактирование ---
    def set_skill(self, skill_id: int, level: float) -> bool:
        for s in self.skills:
            if s[0] == skill_id:
                s[1] = float(level)
                s[2] = 0.0
                return True
        self.skills.append([skill_id, float(level), 0.0])
        return False


class Character:
    def __init__(self, path: Path):
        self.path = path
        self.raw = path.read_bytes()
        self.payload, self.container = read_container(self.raw)
        self.prefix_end, blob = find_player_blob(self.payload)
        self.prefix = self.payload[:self.prefix_end]
        self.player = PlayerData(blob)

    def rebuild(self) -> bytes:
        blob = self.player.serialize()
        w = ZWriter().raw(self.prefix).bool_(True).int_(len(blob)).raw(blob)
        return write_container(bytes(w.b))

    def verify(self) -> bool:
        return self.rebuild() == self.raw

    def save(self, out: Path) -> None:
        out.write_bytes(self.rebuild())


# ------------------------------------------------------------- вывод ------


# ------------------------------------------------- поиск и сохранение ----

def character_dirs():
    """Стандартные папки Valheim с персонажами."""
    home = Path.home()
    roots = [
        home / "AppData/LocalLow/IronGate/Valheim",
        home / ".config/unity3d/IronGate/Valheim",
        home / (".steam/steam/steamapps/compatdata/892970/pfx/drive_c/users/"
                "steamuser/AppData/LocalLow/IronGate/Valheim"),
    ]
    return [r / sub for r in roots
            for sub in ("characters_local", "characters", "characters_cloud")
            if (r / sub).is_dir()]


def find_character_files():
    """Все файлы .fch в стандартных папках, без резервных копий."""
    out = []
    for d in character_dirs():
        out += sorted(p for p in d.glob("*.fch") if not p.name.endswith(".old"))
    return out


def make_backup(path: Path) -> Path:
    """Копия файла с отметкой времени, чтобы прежние копии не затирались."""
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = path.with_name(f"{path.stem}_{stamp}.fch.bak")
    dest.write_bytes(path.read_bytes())
    return dest


def is_game_running() -> bool:
    """Запущен ли Valheim. Игра держит профиль в памяти и перезапишет файл."""
    import subprocess
    import sys as _sys
    if not _sys.platform.startswith("win"):
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq valheim.exe"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=0x08000000)
    except Exception:
        return False
    return "valheim.exe" in out.stdout.lower()
