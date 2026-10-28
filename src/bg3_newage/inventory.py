"""Who holds which items: equipped gear, carried items, and the camp's Traveller's Chest.

Every container (a character's pack, a bag, the camp chest) is an inventory
entity. ``IsOwnedComponent`` on the inventory references the entity that owns
it: a character, or the item a bag inventory belongs to. Each item's
``MemberComponent`` points at a ``MemberData`` record naming its inventory and
slot. An item whose ``WieldingComponent`` references a character is equipped.

Equipped items are still members of the character's own inventory; their
``MemberData`` slot is then the equipment slot (an index into
``EQUIPMENT_SLOTS``). For anything else the slot is just a position in the
container.
"""

import struct
from dataclasses import dataclass

from bg3_newage.gamedata import GameData
from bg3_newage.lsmf import NewAge, read_u64_field
from bg3_newage.save import ItemInfo, Save

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
# game.inventory.v0.MemberData: entity ref to the containing inventory, i16 slot, 6 unknown bytes
MEMBER_DATA = struct.Struct("<Qh6x")


@dataclass(frozen=True)
class Item:
    slot: int
    slot_name: str
    name: str


@dataclass(frozen=True)
class Holdings:
    """Equipped gear keeps its slot; carried items are just names, in container order."""

    equipped: tuple[Item, ...]
    carried: tuple[str, ...]


class Inventories:
    """Item placement for the whole save, indexed by the entity that owns each container."""

    def __init__(self, blob: NewAge, items: dict[int, ItemInfo], character_names: dict[int, str]) -> None:
        self.items = items
        self.character_names = character_names
        inventory_owner = {
            inv: blob.resolve_ref(read_u64_field(raw))
            for inv, raw in blob.by_entity("game.inventory.v1.IsOwnedComponent").items()
        }
        # item -> character equipping it
        self.wielder_of = {
            item: owner
            for item, raw in blob.by_entity("game.inventory.v0.WieldingComponent").items()
            if (owner := blob.resolve_ref(read_u64_field(raw))) is not None
        }
        # owner (character, bag item, chest item) -> [(member slot, item)] across all of its inventories
        self.members_by_owner: dict[int, list[tuple[int, int]]] = {}
        # item -> slot in its container; an equipment slot when the item is wielded
        self.member_slot: dict[int, int] = {}
        for item, raw in blob.by_entity("game.inventory.v0.MemberComponent").items():
            # MemberComponent holds a pointer to the item's MemberData record, not an entity reference
            inventory_ref, slot = blob.read_struct(MEMBER_DATA, read_u64_field(raw))
            self.member_slot[item] = slot
            inventory = blob.resolve_ref(inventory_ref)
            owner = inventory_owner.get(inventory) if inventory is not None else None
            if owner is not None:
                self.members_by_owner.setdefault(owner, []).append((slot, item))

    @classmethod
    def from_save(cls, save: Save) -> "Inventories":
        return cls(save.newage, save.items, save.character_names)

    def holdings(self, character: int) -> Holdings:
        # A wielded item with no MemberComponent has no slot to report, so it's left out
        equipped = sorted(
            (
                Item(self.member_slot[item], slot_name(self.member_slot[item]), self.name(item))
                for item, owner in self.wielder_of.items()
                if owner == character and item in self.member_slot
            ),
            key=lambda i: i.slot,
        )
        # Equipped gear is also an inventory member, so leave it out of carried to avoid listing it twice
        return Holdings(tuple(equipped), self.names_held_by(character, exclude_equipped=True))

    def names_held_by(self, owner: int, exclude_equipped: bool = False) -> tuple[str, ...]:
        """Names of everything in an owner's containers, depth-first: a bag's contents follow the bag."""
        names: list[str] = []
        # A valid save never nests a bag inside itself, but the blob isn't trusted: expand each container once
        expanded = {owner}

        def visit(container: int) -> None:
            for _, item in sorted(self.members_by_owner.get(container, [])):
                if exclude_equipped and item in self.wielder_of:
                    continue
                names.append(self.name(item))
                if item in self.members_by_owner and item not in expanded:
                    expanded.add(item)
                    visit(item)

        visit(owner)
        return tuple(names)

    def camp_chests(self, game: GameData) -> list[int]:
        """Items whose root template appears in the game's CampChestTemplates list."""
        return sorted(
            entity
            for entity, info in self.items.items()
            if info.template is not None and info.template in game.camp_chest_templates
        )

    def name(self, item: int) -> str:
        if char_name := self.character_names.get(item):
            return char_name
        info = self.items.get(item)
        if info is None:
            return f"entity {item}"
        return info.template_name or info.stats_name


def slot_name(slot: int) -> str:
    return EQUIPMENT_SLOTS[slot] if 0 <= slot < len(EQUIPMENT_SLOTS) else f"slot {slot}"
