from dataclasses import replace

from bg3_newage.cli import format_member
from bg3_newage.gamedata import GameData
from bg3_newage.guids import from_larian_bytes
from bg3_newage.lsmf import NewAge
from bg3_newage.party import LevelUp, PartyMember, read_party
from bg3_newage.save import Save, SaveInfoMember
from tests.builder import BlobBuilder
from tests.sample_save import DUAL_WIELDER, GAME, PLAYER, build_save


def test_reads_player_build():
    [member] = read_party(build_save(), GAME)

    assert member.entity == PLAYER
    assert member.name == "Tav"
    assert member.abilities == {"STR": 8, "DEX": 15, "CON": 14, "INT": 12, "WIS": 10, "CHA": 18}
    assert member.proficiency == 3
    assert member.level_ups == (
        LevelUp(1, "Bard", None, None),
        LevelUp(2, "Bard", "SwordsCollege", "DualWielder"),
    )


def test_unknown_game_data_falls_back_to_guid_prefix():
    [member] = read_party(build_save(), GameData())

    assert member.level_ups[1].feat == "unknown:" + from_larian_bytes(DUAL_WIELDER)[:8]
    assert member.level_ups[0].subclass is None


def test_shared_xp_does_not_guess_a_name():
    save = replace(build_save(), members=(SaveInfoMember("Tav", 34359), SaveInfoMember("Shadowheart", 34359)))

    [member] = read_party(save, GAME)

    assert member.name == f"entity {PLAYER}"


def test_player_without_other_components_still_reported():
    b = BlobBuilder(entity_count=1)
    b.add_component("game.v0.PlayerComponent", 1, [b"\x01"], owners=[0])
    save = Save(newage=NewAge(b.build()), items={}, members=(), difficulty="", location="")

    [member] = read_party(save, GAME)

    assert member == PartyMember(0, "entity 0", None, {}, None, (), (), ())


def test_format_member_text():
    [member] = read_party(build_save(), GAME)

    assert format_member(member) == (
        "== Tav  (XP 34359)\n"
        "   STR 8  DEX 15  CON 14  INT 12  WIS 10  CHA 18  prof +3\n"
        "   L1 Bard\n"
        "   L2 Bard  subclass: SwordsCollege  feat: DualWielder\n"
        "   classes: Bard 2\n"
        "   [Melee main hand] WPN_Longsword_1\n"
        "   carrying 3: OBJ_Potion_Healing, OBJ_Bag_AlchemyPouch, OBJ_Agate\n"
    )
