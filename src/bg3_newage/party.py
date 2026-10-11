"""Decode party members' builds from a parsed save.

Component layouts below were reversed against a Patch 8 save. Only the fields
this module reads are known; the rest of each record is still unidentified.
"""

import struct
from collections import Counter
from dataclasses import dataclass

from bg3_newage.gamedata import GameData
from bg3_newage.lsmf import NewAge, read_u64_field
from bg3_newage.save import Save, SaveInfoMember

ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
EQUIPMENT_SLOTS = (
    "Helmet",
    "Body",
    "Cloak",
    "Melee main hand",
    "Melee off hand",
    "Ranged main hand",
    "Ranged off hand",
    "Ring 1",
    "Underwear",
    "Boots",
    "Gloves",
    "Amulet",
    "Ring 2",
    "Wings",
    "Horns",
    "Overhead",
    "Instrument",
    "Camp body",
    "Camp shoes",
)
# game.stats.v3.StatsComponent: 8 unknown bytes, six i32 ability scores, i32 proficiency bonus
STATS = struct.Struct("<8x6ii")
# game.experience.v0.ExperienceComponent: i32 total XP (repeated), 4 unknown bytes
EXPERIENCE = struct.Struct("<i8x")
# game.inventory.v0.MemberData: entity ref to the containing inventory, i16 slot, 6 unknown bytes
MEMBER_DATA = struct.Struct("<Qh6x")
# game.progression.v3.LevelUpComponent: [start, end) range of u64 pointers, one per character level
LEVEL_UP_RANGE = struct.Struct("<QQ")
# game.character_creation.v3.LevelUpComponentData: class, subclass, feat GUIDs (null when not chosen), 48 unknown
LEVEL_UP_RECORD = struct.Struct("<16s16s16s48x")


@dataclass(frozen=True)
class LevelUp:
    level: int
    class_name: str | None
    subclass: str | None
    feat: str | None


@dataclass(frozen=True)
class Item:
    slot: int
    slot_name: str
    stats: str


@dataclass(frozen=True)
class PartyMember:
    entity: int
    name: str
    total_xp: int | None
    abilities: dict[str, int]
    proficiency: int | None
    level_ups: tuple[LevelUp, ...]
    equipped: tuple[Item, ...]
    carried: tuple[str, ...]


def read_party(save: Save, game: GameData) -> list[PartyMember]:
    blob = save.newage
    stats = blob.by_entity("game.stats.v3.StatsComponent")
    xp = blob.by_entity("game.experience.v0.ExperienceComponent")
    inventory = read_inventory(blob, save.item_stats)
    members = []
    for entity in sorted(blob.by_entity("game.v0.PlayerComponent")):
        total_xp = EXPERIENCE.unpack(xp[entity])[0] if entity in xp else None
        scores, proficiency = decode_stats(stats.get(entity))
        equipped, carried = inventory.get(entity, ((), ()))
        members.append(
            PartyMember(
                entity=entity,
                name=name_from_save_info(save.members, total_xp) or f"entity {entity}",
                total_xp=total_xp,
                abilities=scores,
                proficiency=proficiency,
                level_ups=read_level_ups(blob, entity, game),
                equipped=equipped,
                carried=carried,
            )
        )
    return members


def name_from_save_info(members: tuple[SaveInfoMember, ...], total_xp: int | None) -> str | None:
    """SaveInfo.json names the party by origin but has no entity link, so total XP is the join key.

    Returns None when the XP is missing or shared by several members, rather than guessing.
    """
    if total_xp is None:
        return None
    matches = [m.origin for m in members if m.total_xp == total_xp]
    return matches[0] if len(matches) == 1 else None


def decode_stats(raw: bytes | None) -> tuple[dict[str, int], int | None]:
    if raw is None or len(raw) < STATS.size:
        return {}, None
    *scores, proficiency = STATS.unpack_from(raw)
    return dict(zip(ABILITIES, scores, strict=True)), proficiency


def read_level_ups(blob: NewAge, entity: int, game: GameData) -> tuple[LevelUp, ...]:
    raw = blob.by_entity("game.progression.v3.LevelUpComponent").get(entity)
    if raw is None:
        return ()
    start, end = LEVEL_UP_RANGE.unpack(raw)
    level_ups = []
    for level, pointer_offset in enumerate(range(start, end, 8), start=1):
        record_offset = blob.read_u64(pointer_offset)
        class_guid, subclass_guid, feat_guid = blob.read_struct(LEVEL_UP_RECORD, record_offset)
        level_ups.append(
            LevelUp(level, game.class_name(class_guid), game.class_name(subclass_guid), game.feat_name(feat_guid))
        )
    return tuple(level_ups)


def read_inventory(blob: NewAge, item_stats: dict[int, str]) -> dict[int, tuple[tuple[Item, ...], tuple[str, ...]]]:
    """Group items by character.

    An item is equipped when its WieldingComponent references the character;
    its MemberData slot is then the equipment slot. Other items count as
    carried when they sit in an inventory whose IsOwnedComponent references the
    character. Items inside bags are not followed.
    """
    inventory_owner = {
        inv: blob.resolve_ref(read_u64_field(raw))
        for inv, raw in blob.by_entity("game.inventory.v1.IsOwnedComponent").items()
    }
    wielder = {
        item: blob.resolve_ref(read_u64_field(raw))
        for item, raw in blob.by_entity("game.inventory.v0.WieldingComponent").items()
    }
    equipped: dict[int, list[Item]] = {}
    carried: dict[int, list[tuple[int, str]]] = {}
    for item, raw in blob.by_entity("game.inventory.v0.MemberComponent").items():
        # MemberComponent holds a pointer to the item's MemberData record, not an entity reference
        inventory_ref, slot = blob.read_struct(MEMBER_DATA, read_u64_field(raw))
        name = item_stats.get(item, f"entity {item}")
        inventory = blob.resolve_ref(inventory_ref)
        if (owner := wielder.get(item)) is not None:
            equipped.setdefault(owner, []).append(Item(slot, slot_name(slot), name))
        elif inventory is not None and (owner := inventory_owner.get(inventory)) is not None:
            carried.setdefault(owner, []).append((slot, name))
    return {
        owner: (
            tuple(sorted(equipped.get(owner, []), key=lambda i: i.slot)),
            tuple(name for _, name in sorted(carried.get(owner, []))),
        )
        for owner in equipped.keys() | carried.keys()
    }


def slot_name(slot: int) -> str:
    return EQUIPMENT_SLOTS[slot] if 0 <= slot < len(EQUIPMENT_SLOTS) else f"slot {slot}"


def class_summary(member: PartyMember) -> str:
    counts = Counter(lu.class_name or "no class" for lu in member.level_ups)
    return " / ".join(f"{name} {n}" for name, n in counts.items())
