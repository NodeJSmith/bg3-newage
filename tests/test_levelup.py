import struct

import pytest

from bg3_newage.levelup import (
    BONUS_SELECTOR,
    SELECTOR,
    LevelUp,
    read_ability_points,
    read_choices,
    read_level_ups,
    read_point_buy,
    read_racial_bonus,
    read_skills,
)
from bg3_newage.lsmf import EMPTY_RANGE, NewAge
from tests.builder import BlobBuilder
from tests.sample_save import COMPANION, GAME, PLAYER, build_save


def test_level_up_choices_by_kind():
    level1, level2 = read_level_ups(build_save().newage, PLAYER, GAME)

    assert level1 == LevelUp(
        1,
        "Bard",
        None,
        None,
        {
            "racial bonus": ("DEX +2", "CHA +1"),
            "skills": ("Performance",),
            "spells": ("Target_ViciousMockery",),
            "equipment": ("ARM_Instrument_Drum",),
        },
    )
    # Two ASI points spent on the same ability add up
    assert level2.choices == {
        "ability increase": ("DEX +2",),
        "expertise": ("Performance",),
        "fighting style": ("FightingStyle_TwoWeaponFighting",),
        "spells swapped": ("Target_ViciousMockery -> Target_Thunderwave",),
    }


def test_point_buy_adds_increments_to_eight():
    assert read_point_buy(build_save().newage, PLAYER) == {
        "STR": 8,
        "DEX": 15,
        "CON": 8,
        "INT": 8,
        "WIS": 8,
        "CHA": 15,
    }


def test_no_creation_stats_means_no_point_buy():
    assert read_point_buy(build_save().newage, COMPANION) == {}


def test_no_level_ups_component():
    blob = build_save().newage
    assert read_level_ups(blob, COMPANION, GAME) == ()
    assert read_level_ups(NewAge(BlobBuilder(entity_count=1).build()), 0, GAME) == ()


def test_level_without_selectors_has_no_choices():
    assert read_choices(build_save().newage, EMPTY_RANGE) == {}


def test_unknown_enum_ids_fall_back_to_the_number():
    b = BlobBuilder(entity_count=1)
    table = b.add_component("game.character_creation.v1.ESkill", 8, [struct.pack("<q", 99)])
    slots = b.add_blob(struct.pack("<Q", table))
    selector = b.add_blob(SELECTOR.pack(0, slots, slots + 8))
    blob = NewAge(b.build())

    assert read_skills(blob, selector) == ["skill 99"]
    assert read_ability_points(blob, selector) == ["ability 99 +1"]


def test_racial_bonus_with_missing_amounts_is_an_error():
    b = BlobBuilder(entity_count=1)
    table = b.add_component("game.character_creation.v1.EAbility", 8, [struct.pack("<q", 2)])
    slots = b.add_blob(struct.pack("<Q", table))
    selector = b.add_blob(BONUS_SELECTOR.pack(0, slots, slots + 8, EMPTY_RANGE, EMPTY_RANGE))
    blob = NewAge(b.build())

    with pytest.raises(ValueError, match="1 picks but 0 amounts"):
        read_racial_bonus(blob, selector)
