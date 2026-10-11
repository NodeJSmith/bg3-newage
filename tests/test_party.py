import struct

from bg3_newage.cli import format_member
from bg3_newage.gamedata import GameData
from bg3_newage.guids import from_larian_bytes
from bg3_newage.lsmf import ENTITY_ID_COMPONENT, NewAge
from bg3_newage.party import Item, LevelUp, PartyMember, read_party
from bg3_newage.save import Save, SaveInfoMember
from tests.builder import BlobBuilder, guid

PLAYER, INVENTORY, SWORD, POTION, NPC = range(5)
BARD, SWORDS, DUAL_WIELDER = guid(100), guid(101), guid(102)


def build_save() -> Save:
    b = BlobBuilder(entity_count=5)
    ids = b.add_component(ENTITY_ID_COMPONENT, 16, list(b.entities))

    def ref(entity: int) -> bytes:
        return struct.pack("<Q", ids + 16 * entity)

    b.add_component("game.v0.PlayerComponent", 1, [b"\x01"], owners=[PLAYER])
    b.add_component(
        "game.stats.v3.StatsComponent", 36, [struct.pack("<8x6ii", 8, 15, 14, 12, 10, 18, 3)], owners=[PLAYER]
    )
    b.add_component(
        "game.experience.v0.ExperienceComponent", 12, [struct.pack("<3i", 34359, 34359, 0)], owners=[PLAYER]
    )

    level1 = BARD + bytes(16) + bytes(16) + bytes(48)
    level2 = BARD + SWORDS + DUAL_WIELDER + bytes(48)
    records = b.add_blob(level1 + level2)
    pointers = b.add_blob(struct.pack("<QQ", records, records + 96))
    b.add_component(
        "game.progression.v3.LevelUpComponent", 16, [struct.pack("<QQ", pointers, pointers + 16)], owners=[PLAYER]
    )

    member_data = b.add_blob(ref(INVENTORY) + struct.pack("<h6x", 3) + ref(INVENTORY) + struct.pack("<h6x", 0))
    b.add_component(
        "game.inventory.v0.MemberComponent",
        8,
        [struct.pack("<Q", member_data), struct.pack("<Q", member_data + 16)],
        owners=[SWORD, POTION],
    )
    b.add_component("game.inventory.v1.IsOwnedComponent", 8, [ref(PLAYER)], owners=[INVENTORY])
    b.add_component("game.inventory.v0.WieldingComponent", 8, [ref(PLAYER)], owners=[SWORD])

    return Save(
        newage=NewAge(b.build()),
        item_stats={SWORD: "WPN_Longsword_1", POTION: "OBJ_Potion_Healing"},
        members=(SaveInfoMember("Tav", 34359),),
        difficulty="Balanced",
        location="SCL_Main_A",
    )


GAME = GameData(
    classes={from_larian_bytes(BARD): "Bard", from_larian_bytes(SWORDS): "SwordsCollege"},
    feats={from_larian_bytes(DUAL_WIELDER): "DualWielder"},
)


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


def test_splits_equipped_from_carried():
    [member] = read_party(build_save(), GAME)

    assert member.equipped == (Item(3, "Melee main hand", "WPN_Longsword_1"),)
    assert member.carried == ("OBJ_Potion_Healing",)


def test_unknown_game_data_falls_back_to_guid_prefix():
    [member] = read_party(build_save(), GameData())

    assert member.level_ups[1].feat == "unknown:" + from_larian_bytes(DUAL_WIELDER)[:8]
    assert member.level_ups[0].subclass is None


def test_shared_xp_does_not_guess_a_name():
    save = build_save()
    shared = Save(
        newage=save.newage,
        item_stats=save.item_stats,
        members=(SaveInfoMember("Tav", 34359), SaveInfoMember("Shadowheart", 34359)),
        difficulty=save.difficulty,
        location=save.location,
    )
    [member] = read_party(shared, GAME)
    assert member.name == f"entity {PLAYER}"


def test_player_without_other_components_still_reported():
    b = BlobBuilder(entity_count=1)
    b.add_component("game.v0.PlayerComponent", 1, [b"\x01"], owners=[0])
    save = Save(newage=NewAge(b.build()), item_stats={}, members=(), difficulty="", location="")

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
        "   carrying 1: OBJ_Potion_Healing\n"
    )
