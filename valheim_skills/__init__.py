"""Редактор навыков персонажей Valheim.

Публичный интерфейс:
    from valheim_skills import Character, SKILL_NAMES
    ch = Character(path)
    ch.player.set_skill(102, 50)
    if ch.verify():
        ch.save(out)
"""

from .core import (Character, PlayerData, ZReader, ZWriter,
                   read_container, write_container, find_player_blob)
from .core import (character_dirs, find_character_files,
                   is_game_running, make_backup)
from .skills import (SKILL_LIST, SKILL_NAMES, OBSERVED_IDS,
                     all_editable_ids, skill_name, is_known)

__version__ = "1.0.0"
__all__ = [
    "Character", "PlayerData", "ZReader", "ZWriter",
    "read_container", "write_container", "find_player_blob",
    "character_dirs", "find_character_files", "is_game_running",
    "make_backup",
    "SKILL_LIST", "SKILL_NAMES", "OBSERVED_IDS",
    "all_editable_ids", "skill_name", "is_known", "__version__",
]
