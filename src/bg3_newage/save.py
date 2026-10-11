"""Load the pieces of an extracted save that the reports need.

Input is a save that LSLib has already unpacked (the ``.lsv`` extracted and
``Globals.lsf`` converted to ``Globals.lsx``). The NewAge blob is base64 inside
Globals.lsx, alongside item stats names and character templates; SaveInfo.json
and StorySave.bin sit beside it.
"""

import base64
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from bg3_newage.guids import to_larian_bytes
from bg3_newage.lsmf import NewAge
from bg3_newage.osiris import read_story_names


@dataclass(frozen=True)
class SaveInfoMember:
    origin: str
    total_xp: int


@dataclass(frozen=True)
class ItemInfo:
    stats_name: str  # e.g. WPN_Longsword_1
    template: str | None  # current template GUID, lowercase
    # Name of a save-local template, e.g. S_MOO_NightsongLetter for a note whose stats name is just OBJ_Scroll
    template_name: str | None = None


@dataclass(frozen=True)
class Save:
    newage: NewAge
    items: dict[int, ItemInfo]
    members: tuple[SaveInfoMember, ...]
    difficulty: str
    location: str
    # entity -> name from the story database, for characters whose template the story scripts name
    character_names: dict[int, str]


def load_save(save_dir: Path) -> Save:
    globals_path = save_dir / "Globals.lsx"
    if not globals_path.is_file():
        raise FileNotFoundError(f"{globals_path} not found; convert Globals.lsf to .lsx with LSLib first")
    root = ET.parse(globals_path).getroot()
    newage = NewAge(base64.b64decode(region_attribute(root, "NewAge", "NewAge")))
    info_path = save_dir / "SaveInfo.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.is_file() else {}
    story_names = read_story_names(save_dir / "StorySave.bin")
    character_names = {
        entity: story_names[template]
        for entity, template in read_character_templates(root, newage).items()
        if template in story_names
    }
    return Save(
        newage=newage,
        items=read_items(root, newage, read_cached_template_names(root)),
        members=tuple(
            SaveInfoMember(c.get("Origin", "?"), int(c.get("Experience Points (Total)", -1)))
            for c in info.get("Active Party", {}).get("Characters", [])
        ),
        difficulty=" / ".join(info.get("Difficulty", [])),
        location=info.get("Current Level", ""),
        character_names=character_names,
    )


def region_attribute(root: ET.Element, region_id: str, attribute_id: str) -> str:
    region = find_region(root, region_id)
    attr = region.find(f".//attribute[@id='{attribute_id}']") if region is not None else None
    if attr is not None and attr.get("value"):
        return attr.get("value", "")
    raise ValueError(f"Globals.lsx has no {region_id}/{attribute_id} attribute")


def find_region(root: ET.Element, region_id: str) -> ET.Element | None:
    return next((r for r in root.iter("region") if r.get("id") == region_id), None)


def read_cached_template_names(root: ET.Element) -> dict[str, str]:
    """Map lowercase template GUID -> template name for the save-local templates in ``CacheTemplates``.

    Story items (notes, keys, quest objects) get a template of their own here,
    and its ``Name`` says far more than the generic stats name they share.
    """
    region = find_region(root, "CacheTemplates")
    if region is None:
        return {}
    names = {}
    for node in region.iter("node"):
        if node.get("id") != "Template":
            continue
        key, name = attribute_value(node, "MapKey"), attribute_value(node, "Name")
        if key and name:
            names[key.lower()] = name
    return names


def read_character_templates(root: ET.Element, newage: NewAge) -> dict[int, str]:
    """Map entity index -> lowercase root template GUID, from the ``Characters`` region's Creator nodes."""
    region = find_region(root, "Characters")
    if region is None:
        return {}
    templates = {}
    for node in region.iter("node"):
        entity_guid, template = attribute_value(node, "Entity"), attribute_value(node, "TemplateID")
        if node.get("id") != "Creator" or not entity_guid or not template:
            continue
        index = newage.entity_by_guid.get(to_larian_bytes(entity_guid))
        if index is not None:
            templates[index] = template.lower()
    return templates


def read_items(root: ET.Element, newage: NewAge, template_names: dict[str, str]) -> dict[int, ItemInfo]:
    """Map entity index -> item stats name and template.

    The Items region lists Creator nodes (entity GUIDs) and Item nodes (stats
    names, templates) in matching order. Templates are lowercased so they
    compare equal to GUIDs read from game data.
    """
    items: dict[int, ItemInfo] = {}
    region = find_region(root, "Items")
    if region is None:
        return items
    creators = [n for n in region.iter("node") if n.get("id") == "Creator"]
    item_nodes = [n for n in region.iter("node") if n.get("id") == "Item"]
    if len(creators) != len(item_nodes):
        raise ValueError(f"Items region has {len(creators)} Creator nodes but {len(item_nodes)} Item nodes")
    for creator, item in zip(creators, item_nodes, strict=True):
        entity_guid = attribute_value(creator, "Entity")
        stats_name = attribute_value(item, "Stats")
        if not entity_guid or stats_name is None:
            continue
        index = newage.entity_by_guid.get(to_larian_bytes(entity_guid))
        if index is not None:
            template = (attribute_value(item, "CurrentTemplate") or "").lower() or None
            items[index] = ItemInfo(stats_name, template, template_names.get(template) if template else None)
    return items


def attribute_value(node: ET.Element, attribute_id: str) -> str | None:
    attr = node.find(f"attribute[@id='{attribute_id}']")
    return attr.get("value") if attr is not None else None
