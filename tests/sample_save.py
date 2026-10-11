"""A small synthetic save: one Bard, an equipped sword, a potion, a bag with a gem, and a camp chest."""

import base64
import struct
from pathlib import Path

from bg3_newage.gamedata import GameData
from bg3_newage.guids import from_larian_bytes
from bg3_newage.inventory import MEMBER_DATA
from bg3_newage.lsmf import ENTITY_ID_COMPONENT, GUID_SIZE, NewAge
from bg3_newage.save import ItemInfo, Save, SaveInfoMember
from tests.builder import BlobBuilder, guid

ENTITIES = PLAYER, INVENTORY, SWORD, POTION, BAG, BAG_INVENTORY, GEM, CHEST, CHEST_INVENTORY, HELM = range(10)
BARD, SWORDS, DUAL_WIELDER = guid(100), guid(101), guid(102)
CHEST_TEMPLATE = "96eab9d1-74b1-42f7-b1ad-061a9fcea8c4"

GAME = GameData(
    classes={from_larian_bytes(BARD): "Bard", from_larian_bytes(SWORDS): "SwordsCollege"},
    feats={from_larian_bytes(DUAL_WIELDER): "DualWielder"},
    camp_chest_templates=frozenset({CHEST_TEMPLATE}),
)
NO_GAME_DATA = GameData()
ITEMS = {
    SWORD: ItemInfo("WPN_Longsword_1", None),
    POTION: ItemInfo("OBJ_Potion_Healing", None),
    BAG: ItemInfo("OBJ_Bag_AlchemyPouch", None),
    GEM: ItemInfo("OBJ_Agate", None),
    CHEST: ItemInfo("OBJ_ImmutableContainer", CHEST_TEMPLATE),
    HELM: ItemInfo("ARM_Helmet_1", None),
}


def build_blob() -> bytes:
    b = BlobBuilder(entity_count=len(ENTITIES))
    ids = b.add_component(ENTITY_ID_COMPONENT, GUID_SIZE, list(b.entities))

    def ref_offset(entity: int) -> int:
        """An entity reference is the offset of that entity's GUID in the EntityId table."""
        return ids + GUID_SIZE * entity

    def ref(entity: int) -> bytes:
        return struct.pack("<Q", ref_offset(entity))

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

    # (item, containing inventory, slot). The sword is wielded, so its slot 3 is the "Melee main hand"
    # equipment slot; every other slot is just a position in its container.
    placements = [
        (SWORD, INVENTORY, 3),
        (POTION, INVENTORY, 0),
        (BAG, INVENTORY, 1),
        (GEM, BAG_INVENTORY, 0),
        (HELM, CHEST_INVENTORY, 0),
    ]
    member_data = b.add_blob(b"".join(MEMBER_DATA.pack(ref_offset(inv), slot) for _, inv, slot in placements))
    b.add_component(
        "game.inventory.v0.MemberComponent",
        8,
        [struct.pack("<Q", member_data + MEMBER_DATA.size * i) for i in range(len(placements))],
        owners=[item for item, _, _ in placements],
    )
    b.add_component(
        "game.inventory.v1.IsOwnedComponent",
        8,
        [ref(PLAYER), ref(BAG), ref(CHEST)],
        owners=[INVENTORY, BAG_INVENTORY, CHEST_INVENTORY],
    )
    b.add_component("game.inventory.v0.WieldingComponent", 8, [ref(PLAYER)], owners=[SWORD])

    return b.build()


def build_save() -> Save:
    return Save(
        newage=NewAge(build_blob()),
        items=ITEMS,
        members=(SaveInfoMember("Tav", 34359),),
        difficulty="Balanced",
        location="SCL_Main_A",
    )


def write_save_dir(path: Path) -> Path:
    """Write the sample save as an extracted save directory (Globals.lsx only)."""
    items = "".join(
        f'<node id="Creator"><attribute id="Entity" value="{from_larian_bytes(guid(entity))}" /></node>'
        f'<node id="Item"><attribute id="Stats" value="{info.stats_name}" />'
        + (f'<attribute id="CurrentTemplate" value="{info.template}" />' if info.template else "")
        + "</node>"
        for entity, info in ITEMS.items()
    )
    blob = base64.b64encode(build_blob()).decode()
    path.mkdir(parents=True, exist_ok=True)
    (path / "Globals.lsx").write_text(
        f'<save><region id="NewAge"><node id="NewAge"><attribute id="NewAge" value="{blob}" /></node></region>'
        f'<region id="Items"><node id="Items"><children>{items}</children></node></region></save>'
    )
    return path


def write_game_data_dir(path: Path, chest_templates: tuple[str, ...] = (CHEST_TEMPLATE,)) -> Path:
    """Write a minimal extracted Shared.pak holding only CampChestTemplates.lsx."""
    lists = path / "Public/Shared/Lists"
    lists.mkdir(parents=True, exist_ok=True)
    nodes = "".join(
        f'<node id="CampChestTemplate"><attribute id="TemplateId" value="{t}" /></node>' for t in chest_templates
    )
    (lists / "CampChestTemplates.lsx").write_text(
        f'<save><region><node id="root"><children>{nodes}</children></node></region></save>'
    )
    return path
