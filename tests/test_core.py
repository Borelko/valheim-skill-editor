"""Тесты ядра: разбор, пересборка и правка навыков.

Главная проверка — round-trip: файл, собранный из разобранных структур,
обязан совпасть с исходным байт в байт. Если это так, значит формат понят
верно, и записи можно доверять.
"""

import hashlib
import struct

import pytest

from valheim_skills import (Character, ZReader, ZWriter, read_container,
                            write_container, find_player_blob, skill_name)
from tests.synthetic import build_fch


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "Тест.fch"
    path.write_bytes(build_fch())
    return path


# ---------------------------------------------------------- примитивы ----

def test_string_roundtrip():
    text = "Ragnar Лодброк 日本"
    data = ZWriter().str_(text).b
    assert ZReader(bytes(data)).str_() == text


def test_long_string_uses_multibyte_length():
    text = "x" * 300
    data = bytes(ZWriter().str_(text).b)
    assert data[0] & 0x80          # длина занимает больше одного байта
    assert ZReader(data).str_() == text


def test_numbers_roundtrip():
    w = ZWriter().int_(-42).long_(1 << 40).float_(1.5).bool_(True)
    r = ZReader(bytes(w.b))
    assert r.int_() == -42
    assert r.long_() == 1 << 40
    assert r.float_() == 1.5
    assert r.bool_() is True


def test_reader_refuses_to_read_past_end():
    with pytest.raises(EOFError):
        ZReader(b"\x01\x02").int_()


# ---------------------------------------------------------- контейнер ----

def test_container_roundtrip():
    payload = b"any bytes here"
    raw = write_container(payload)
    back, info = read_container(raw)
    assert back == payload
    assert info["hash_ok"]


def test_container_detects_broken_hash():
    raw = bytearray(write_container(b"payload"))
    raw[-1] ^= 0xFF
    _, info = read_container(bytes(raw))
    assert not info["hash_ok"]


def test_player_blob_is_last_field():
    raw = build_fch()
    payload, _ = read_container(raw)
    off, blob = find_player_blob(payload)
    assert payload[off] == 1
    assert off + 5 + len(blob) == len(payload)


# ------------------------------------------------------------- разбор ----

def test_parses_known_fields(sample):
    ch = Character(sample)
    assert ch.container["hash_ok"]
    assert ch.player.version == 33
    assert ch.player.beard == "Beard2"
    assert ch.player.biomes == ["Луга"]
    assert len(ch.player.recipes) == 6


def test_roundtrip_is_byte_identical(sample):
    ch = Character(sample)
    assert ch.verify()
    assert ch.rebuild() == sample.read_bytes()


def test_roundtrip_with_food_present(tmp_path):
    path = tmp_path / "Сытый.fch"
    path.write_bytes(build_fch(foods=[("Mushroom", 532.0), ("Honey", 100.0)]))
    ch = Character(path)
    assert ch.verify()
    assert ch.player.foods == [["Mushroom", 532.0], ["Honey", 100.0]]


def test_roundtrip_with_long_opaque_header(tmp_path):
    """Голова растёт вместе с инвентарём — разбор не должен на этом падать."""
    path = tmp_path / "Богатый.fch"
    path.write_bytes(build_fch(header_extra=b"\x33" * 400))
    ch = Character(path)
    assert ch.verify()
    assert len(ch.player.header) > 400


def test_unparseable_blob_raises(tmp_path):
    path = tmp_path / "Битый.fch"
    payload = b"\x2e\x00\x00\x00" + b"\x00" * 40
    path.write_bytes(write_container(payload))
    with pytest.raises(Exception):
        Character(path)


# ------------------------------------------------------------- правка ----

def test_set_existing_skill(sample):
    ch = Character(sample)
    assert ch.player.set_skill(3, 77.0) is True
    assert dict((s, l) for s, l, _ in ch.player.skills)[3] == 77.0


def test_set_skill_resets_accumulator(sample):
    ch = Character(sample)
    ch.player.set_skill(13, 50.0)
    acc = [a for s, _, a in ch.player.skills if s == 13][0]
    assert acc == 0.0


def test_add_missing_skill(sample):
    ch = Character(sample)
    before = len(ch.player.skills)
    assert ch.player.set_skill(110, 30.0) is False
    assert len(ch.player.skills) == before + 1


def test_saved_file_reloads_with_new_values(sample, tmp_path):
    ch = Character(sample)
    ch.player.set_skill(102, 99.0)
    ch.player.set_skill(104, 42.0)
    out = tmp_path / "Правленый.fch"
    ch.save(out)

    again = Character(out)
    levels = dict((s, l) for s, l, _ in again.player.skills)
    assert again.container["hash_ok"]
    assert levels[102] == 99.0
    assert levels[104] == 42.0


def test_edit_preserves_opaque_parts(sample, tmp_path):
    """Инвентарь и постройки лежат в неразобранных кусках — их нельзя терять."""
    before = Character(sample)
    ch = Character(sample)
    ch.player.set_skill(3, 100.0)
    out = tmp_path / "Правленый.fch"
    ch.save(out)

    after = Character(out)
    assert after.player.header == before.player.header
    assert after.player.tail == before.player.tail
    assert after.prefix == before.prefix
    assert after.player.recipes == before.player.recipes


def test_level_change_does_not_resize_file(sample, tmp_path):
    ch = Character(sample)
    ch.player.set_skill(3, 100.0)
    out = tmp_path / "Правленый.fch"
    ch.save(out)
    assert out.stat().st_size == sample.stat().st_size


def test_added_skill_grows_file_by_one_record(sample, tmp_path):
    ch = Character(sample)
    ch.player.set_skill(110, 10.0)
    out = tmp_path / "Правленый.fch"
    ch.save(out)
    assert out.stat().st_size == sample.stat().st_size + 12


def test_saved_hash_matches_payload(sample, tmp_path):
    ch = Character(sample)
    ch.player.set_skill(3, 12.0)
    out = tmp_path / "Правленый.fch"
    ch.save(out)

    raw = out.read_bytes()
    size = struct.unpack("<i", raw[:4])[0]
    payload = raw[4:4 + size]
    stored = raw[8 + size:]
    assert hashlib.sha512(payload).digest() == stored


# ------------------------------------------------------------ навыки ----

def test_skill_names_cover_all_known_ids():
    assert skill_name(102) == "Бег"
    assert skill_name(13) == "Рубка древесины"
    assert "id 777" in skill_name(777)
