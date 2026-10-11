from dataclasses import replace

from bg3_newage.cli import format_member
from bg3_newage.gamedata import GameData
from bg3_newage.guids import from_larian_bytes
from bg3_newage.lsmf import NewAge
from bg3_newage.party import PartyMember, read_party
from bg3_newage.save import Save, SaveInfoMember
from tests.builder import BlobBuilder
from tests.sample_save import COMPANION, DUAL_WIELDER, GAME, PLAYER, build_save


def test_reads_player_build():
    [member, _] = read_party(build_save(), GAME)

    assert member.entity == PLAYER
    assert member.in_party
    assert (member.hp, member.max_hp) == (59, 59)
    assert member.approval is None
    assert member.tadpole_powers == ("TAD_Charm",)
    assert member.name == "Tav"
    assert member.abilities == {"STR": 8, "DEX": 15, "CON": 14, "INT": 12, "WIS": 10, "CHA": 18}
    assert member.proficiency == 3
    assert [(lu.level, lu.class_name, lu.subclass, lu.feat) for lu in member.level_ups] == [
        (1, "Bard", None, None),
        (2, "Bard", "SwordsCollege", "DualWielder"),
    ]


def test_camp_companion_follows_the_party():
    [_, companion] = read_party(build_save(), GAME)

    assert companion.entity == COMPANION
    assert not companion.in_party
    # Same XP as Tav, but SaveInfo.json only lists the party, so the name comes from the story database
    assert companion.name == "Wyll"
    assert (companion.hp, companion.max_hp) == (40, 71)
    assert companion.approval == 42


def test_unknown_game_data_falls_back_to_guid_prefix():
    [member, _] = read_party(build_save(), GameData())

    assert member.level_ups[1].feat == "unknown:" + from_larian_bytes(DUAL_WIELDER)[:8]
    assert member.level_ups[0].subclass is None


def test_shared_xp_does_not_guess_a_name():
    save = replace(build_save(), members=(SaveInfoMember("Tav", 34359), SaveInfoMember("Shadowheart", 34359)))

    [member, _] = read_party(save, GAME)

    assert member.name == f"entity {PLAYER}"


def test_player_without_other_components_still_reported():
    b = BlobBuilder(entity_count=1)
    b.add_component("game.v0.PlayerComponent", 1, [b"\x01"], owners=[0])
    save = Save(newage=NewAge(b.build()), items={}, members=(), difficulty="", location="", character_names={})

    [member] = read_party(save, GAME)

    assert member == PartyMember(
        entity=0,
        name="entity 0",
        in_party=True,
        total_xp=None,
        hp=None,
        max_hp=None,
        approval=None,
        abilities={},
        point_buy={},
        proficiency=None,
        level_ups=(),
        equipped=(),
        carried=(),
        tadpole_powers=(),
        prepared_spells=(),
    )


def test_format_member_text():
    [member, _] = read_party(build_save(), GAME)

    assert format_member(member) == (
        "== Tav  (XP 34359, HP 59/59)\n"
        "   STR 8  DEX 15  CON 14  INT 12  WIS 10  CHA 18  prof +3\n"
        "   point buy: STR 8  DEX 15  CON 8  INT 8  WIS 8  CHA 15\n"
        "   L1 Bard  racial bonus: DEX +2, CHA +1  skills: Performance  spells: Target_ViciousMockery"
        "  equipment: ARM_Instrument_Drum\n"
        "   L2 Bard  subclass: SwordsCollege  feat: DualWielder  ability increase: DEX +2"
        "  expertise: Performance  passives: FightingStyle_TwoWeaponFighting\n"
        "   classes: Bard 2\n"
        "   tadpole powers: TAD_Charm\n"
        "   [Melee main hand] WPN_Longsword_1\n"
        "   carrying 4: OBJ_Potion_Healing, OBJ_Bag_AlchemyPouch, OBJ_Agate, S_MOO_NightsongLetter\n"
    )
