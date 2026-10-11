"""Load the pieces of an extracted save that the party report needs.

Input is a save that LSLib has already unpacked (the ``.lsv`` extracted and
``Globals.lsf`` converted to ``Globals.lsx``). The NewAge blob is base64 inside
Globals.lsx; item stats names and SaveInfo.json sit beside it.
"""

import base64
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from bg3_newage.guids import to_larian_bytes
from bg3_newage.lsmf import NewAge


@dataclass(frozen=True)
class SaveInfoMember:
    origin: str
    total_xp: int


@dataclass(frozen=True)
class Save:
    newage: NewAge
    item_stats: dict[int, str]
    members: tuple[SaveInfoMember, ...]
    difficulty: str
    location: str


def load_save(save_dir: Path) -> Save:
    globals_path = save_dir / "Globals.lsx"
    if not globals_path.is_file():
        raise FileNotFoundError(f"{globals_path} not found; convert Globals.lsf to .lsx with LSLib first")
    root = ET.parse(globals_path).getroot()
    newage = NewAge(base64.b64decode(region_attribute(root, "NewAge", "NewAge")))
    info_path = save_dir / "SaveInfo.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.is_file() else {}
    return Save(
        newage=newage,
        item_stats=read_item_stats(root, newage),
        members=tuple(
            SaveInfoMember(c.get("Origin", "?"), int(c.get("Experience Points (Total)", -1)))
            for c in info.get("Active Party", {}).get("Characters", [])
        ),
        difficulty=" / ".join(info.get("Difficulty", [])),
        location=info.get("Current Level", ""),
    )


def region_attribute(root: ET.Element, region_id: str, attribute_id: str) -> str:
    for region in root.iter("region"):
        if region.get("id") == region_id:
            attr = region.find(f".//attribute[@id='{attribute_id}']")
            if attr is not None and attr.get("value"):
                return attr.get("value", "")
    raise ValueError(f"Globals.lsx has no {region_id}/{attribute_id} attribute")


def read_item_stats(root: ET.Element, newage: NewAge) -> dict[int, str]:
    """Map entity index -> item stats name (e.g. WPN_Longsword_1).

    The Items region lists Creator nodes (entity GUIDs) and Item nodes (stats
    names) in matching order.
    """
    stats: dict[int, str] = {}
    region = next((r for r in root.iter("region") if r.get("id") == "Items"), None)
    if region is None:
        return stats
    creators = [n for n in region.iter("node") if n.get("id") == "Creator"]
    items = [n for n in region.iter("node") if n.get("id") == "Item"]
    if len(creators) != len(items):
        raise ValueError(f"Items region has {len(creators)} Creator nodes but {len(items)} Item nodes")
    for creator, item in zip(creators, items, strict=True):
        entity_attr = creator.find("attribute[@id='Entity']")
        stats_attr = item.find("attribute[@id='Stats']")
        if entity_attr is None or stats_attr is None or not entity_attr.get("value"):
            continue
        index = newage.entity_by_guid.get(to_larian_bytes(entity_attr.get("value", "")))
        if index is not None:
            stats[index] = stats_attr.get("value", "")
    return stats
