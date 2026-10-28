"""A small synthetic save.

One Bard in the party with an equipped sword, a potion, and a bag holding a gem
and a story note; a companion waiting at camp; a camp chest; and party-wide
camp state.
"""

import base64
import struct
from pathlib import Path

from bg3_newage.gamedata import GameData
from bg3_newage.guids import from_larian_bytes
from bg3_newage.inventory import MEMBER_DATA
from bg3_newage.levelup import LEVEL_UP_RECORD, SELECTOR_ID_OFFSET, SELECTOR_KINDS
from bg3_newage.lsmf import EMPTY_RANGE, ENTITY_ID_COMPONENT, GUID_SIZE, NewAge
from bg3_newage.osiris import SCRAMBLE_KEY
from bg3_newage.save import ItemInfo, Save, SaveInfoMember
from tests.builder import BlobBuilder, guid

ENTITIES = (
    PLAYER,
    INVENTORY,
    SWORD,
    POTION,
    BAG,
    BAG_INVENTORY,
    GEM,
    CHEST,
    CHEST_INVENTORY,
    HELM,
    COMPANION,
    NOTE,
    PARTY_STATE,
    CAMP_NPC,
) = range(14)
BARD, SWORDS, DUAL_WIELDER = guid(100), guid(101), guid(102)
CHEST_TEMPLATE = "96eab9d1-74b1-42f7-b1ad-061a9fcea8c4"
NOTE_TEMPLATE = "06332bc8-19b5-4f9c-9013-6d433abd78a0"
COMPANION_TEMPLATE = "c774d764-4a17-48dc-b470-32ace9ce447d"

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
    NOTE: ItemInfo("OBJ_Scroll", NOTE_TEMPLATE, "S_MOO_NightsongLetter"),
}


def build_blob() -> bytes:
    b = BlobBuilder(entity_count=len(ENTITIES))
    ids = b.add_component(ENTITY_ID_COMPONENT, GUID_SIZE, list(b.entities))

    def ref_offset(entity: int) -> int:
        """An entity reference is the offset of that entity's GUID in the EntityId table."""
        return ids + GUID_SIZE * entity

    def ref(entity: int) -> bytes:
        return struct.pack("<Q", ref_offset(entity))

    def text(value: str) -> tuple[int, int]:
        """Store a string and return its (pointer, length) view."""
        return b.add_blob(value.encode()), len(value)

    def stored_range(data: bytes) -> bytes:
        """Store records and return the [start, end) range pointing at them."""
        start = b.add_blob(data)
        return struct.pack("<QQ", start, start + len(data))

    b.add_component("game.v0.PlayerComponent", 1, [b"\x01"], owners=[PLAYER])
    b.add_component("game.avatar.v0.AvatarComponent", 16, [bytes(16)], owners=[PLAYER])
    # The camp NPC is at camp but was never recruited, so it isn't a companion
    b.add_component("game.camp.v1.PresenceComponent", 1, [b"\x01"] * 3, owners=[PLAYER, COMPANION, CAMP_NPC])
    b.add_component("game.recruit.v0.RecruitedByComponent", 8, [ref(PLAYER)], owners=[COMPANION])
    b.add_component(
        "game.stats.v0.HealthComponent",
        32,
        [struct.pack("<ii24x", 59, 59), struct.pack("<ii24x", 40, 71)],
        owners=[PLAYER, COMPANION],
    )
    approval = (
        stored_range(ref(PLAYER)) + stored_range(struct.pack("<i", 42)) + struct.pack("<QQ", EMPTY_RANGE, EMPTY_RANGE)
    )
    b.add_component("game.approval.v0.Ratings", 48, [approval], owners=[COMPANION])
    b.add_component(
        "game.tadpole_tree.v0.PowerContainerComponent",
        16,
        [stored_range(struct.pack("<QQ", *text("TAD_Charm")))],
        owners=[PLAYER],
    )
    prepared = b"".join(struct.pack("<QI12x", *text(name)) for name in ("Shout_Dash", "Target_ViciousMockery"))
    b.add_component("game.spell.v0.SpellBookPrepares", 80, [stored_range(prepared) + bytes(64)], owners=[PLAYER])
    b.add_component("game.calendar.v0.DaysPassedComponent", 4, [struct.pack("<i", 43)], owners=[PARTY_STATE])
    b.add_component("game.camp.v0.TotalSuppliesComponent", 4, [struct.pack("<i", 581)], owners=[PARTY_STATE])
    recipe = struct.pack("<QQ8x", *text("ALCH_Potion_Healing_RoguesMorsel"))
    b.add_component("game.party.v1.RecipesComponent", 16, [stored_range(recipe)], owners=[PARTY_STATE])
    waypoint = struct.pack("<QQ16xQQ", *text("WAYP_SHA_Temple"), *text("SCL_Main_A"))
    b.add_component("game.party.v0.WaypointsComponent", 16, [stored_range(waypoint)], owners=[PARTY_STATE])
    b.add_component(
        "game.stats.v3.StatsComponent", 36, [struct.pack("<8x6ii", 8, 15, 14, 12, 10, 18, 3)], owners=[PLAYER]
    )
    # The companion's XP equals the player's, as shared party XP usually does
    b.add_component(
        "game.experience.v0.ExperienceComponent",
        12,
        [struct.pack("<3i", 34359, 34359, 0)] * 2,
        owners=[PLAYER, COMPANION],
    )

    # Point buy: increments over 8 indexed by ability ID, index 0 unused (DEX 15, CHA 15, the rest 8)
    increments = stored_range(struct.pack("<7i", 0, 0, 7, 0, 0, 0, 7))
    b.add_component(
        "game.character_creation.v1.CharacterCreationStatsComponent", 88, [bytes(72) + increments], owners=[PLAYER]
    )

    # Ability and skill picks point at elements of enum tables holding the game's IDs
    abilities = b.add_component("game.character_creation.v1.EAbility", 8, [struct.pack("<q", 2), struct.pack("<q", 6)])
    dex, cha = abilities, abilities + 8
    performance = b.add_component("game.character_creation.v1.ESkill", 8, [struct.pack("<q", 2)])

    empty_range = struct.pack("<QQ", EMPTY_RANGE, EMPTY_RANGE)

    def selector(picks: bytes, extra: bytes = b"", selector_id: str = "") -> int:
        """A selector record: info pointer, list GUID, range of picks, then any kind-specific fields."""
        # The info record: a base-Selector pointer, index and unknown bytes the decoder skips, then the SelectorId
        info = b.add_blob(bytes(SELECTOR_ID_OFFSET) + struct.pack("<QI4x", *text(selector_id)))
        return b.add_blob(struct.pack("<Q16x", info) + stored_range(picks) + extra)

    def names(*values: str) -> bytes:
        return b"".join(struct.pack("<QI4x", *text(v)) for v in values)

    def swap(old: str, new: str) -> bytes:
        """One swap record: the pick given up, then its replacement; ("", "") is a swap offered and declined."""
        return names(old, new)

    def selectors(by_kind: dict[str, int]) -> int:
        """LevelUpComponentSelectors: one range of selector pointers per kind, in SELECTOR_KINDS order."""
        labels = [label for label, _, _ in SELECTOR_KINDS]
        assert set(by_kind) <= set(labels)
        return b.add_blob(
            b"".join(stored_range(struct.pack("<Q", by_kind[k])) if k in by_kind else empty_range for k in labels)
        )

    level1_choices = selectors(
        {
            "racial bonus": selector(
                struct.pack("<QQ", dex, cha), stored_range(struct.pack("<2i", 2, 1)), selector_id="AbilityBonus"
            ),
            "skills": selector(struct.pack("<Q", performance)),
            # Real saves store some generic selector IDs as a lone space
            "spells": selector(names("Target_ViciousMockery"), empty_range, selector_id=" "),
            "equipment": selector(names("ARM_Instrument_Drum"), selector_id="BardInstrument"),
        }
    )
    level2_choices = selectors(
        {
            "ability increase": selector(struct.pack("<QQ", dex, dex), selector_id="FeatASI"),
            "expertise": selector(struct.pack("<Q", performance)),
            "passives": selector(names("FightingStyle_TwoWeaponFighting"), empty_range, selector_id="FightingStyle"),
            # Swapped Vicious Mockery for Thunderwave; the empty pair is a swap offered and declined
            "spells": selector(b"", stored_range(swap("Target_ViciousMockery", "Target_Thunderwave") + swap("", ""))),
        }
    )

    def level_up(class_guid: bytes, subclass: bytes, feat: bytes, choices: int) -> bytes:
        abilities = 0  # LevelUpComponentAbilities pointer, unread
        return LEVEL_UP_RECORD.pack(class_guid, subclass, feat, abilities, choices)

    level1 = level_up(BARD, bytes(16), bytes(16), level1_choices)
    level2 = level_up(BARD, SWORDS, DUAL_WIELDER, level2_choices)
    records = b.add_blob(level1 + level2)
    pointers = b.add_blob(struct.pack("<QQ", records, records + LEVEL_UP_RECORD.size))
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
        (NOTE, BAG_INVENTORY, 1),
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
        character_names={COMPANION: "Wyll"},
    )


def write_save_dir(path: Path) -> Path:
    """Write the sample save as an extracted save directory: Globals.lsx and a minimal StorySave.bin."""
    items = "".join(
        f'<node id="Creator"><attribute id="Entity" value="{from_larian_bytes(guid(entity))}" /></node>'
        f'<node id="Item"><attribute id="Stats" value="{info.stats_name}" />'
        + (f'<attribute id="CurrentTemplate" value="{info.template}" />' if info.template else "")
        + "</node>"
        for entity, info in ITEMS.items()
    )
    cache = (
        f'<node id="Template"><attribute id="MapKey" value="{NOTE_TEMPLATE}" />'
        '<attribute id="Name" value="S_MOO_NightsongLetter" /></node>'
    )
    characters = (
        f'<node id="Creator"><attribute id="Entity" value="{from_larian_bytes(guid(COMPANION))}" />'
        f'<attribute id="TemplateID" value="{COMPANION_TEMPLATE}" /></node>'
    )
    blob = base64.b64encode(build_blob()).decode()
    path.mkdir(parents=True, exist_ok=True)
    (path / "Globals.lsx").write_text(
        f'<save><region id="NewAge"><node id="NewAge"><attribute id="NewAge" value="{blob}" /></node></region>'
        f'<region id="CacheTemplates"><node id="Templates"><children>{cache}</children></node></region>'
        f'<region id="Characters"><node id="Characters"><children>{characters}</children></node></region>'
        f'<region id="Items"><node id="Items"><children>{items}</children></node></region></save>'
    )
    story = b"\x00junk\x00CHARACTERGUID_S_Player_Wyll_" + COMPANION_TEMPLATE.encode() + b"\x00"
    (path / "StorySave.bin").write_bytes(bytes(c ^ SCRAMBLE_KEY for c in story))
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
