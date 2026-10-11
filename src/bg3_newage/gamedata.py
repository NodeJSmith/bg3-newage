"""Name lookups from the game's own data files.

Class and feat references in the save are bare GUIDs. Their names live in
``Shared.pak`` (``Public/Shared*/ClassDescriptions/ClassDescriptions.lsx`` and
``Public/Shared*/Feats/Feats.lsx``), which this tool reads from the user's own
extracted copy rather than shipping. Subclasses are ClassDescriptions entries
too. ``Public/Shared*/Lists/CampChestTemplates.lsx`` lists the root templates
of the camp's Traveller's Chest. Anything added by later patches or living in
``Gustav.pak`` shows as an unknown GUID.
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from bg3_newage.guids import NULL_GUID, from_larian_bytes

UNKNOWN_PREFIX = "unknown:"


@dataclass(frozen=True)
class GameData:
    classes: dict[str, str] = field(default_factory=dict)
    feats: dict[str, str] = field(default_factory=dict)
    camp_chest_templates: frozenset[str] = frozenset()

    def class_name(self, raw: bytes) -> str | None:
        return lookup(self.classes, raw)

    def feat_name(self, raw: bytes) -> str | None:
        return lookup(self.feats, raw)


def lookup(table: dict[str, str], raw: bytes) -> str | None:
    """None for a null GUID (nothing chosen), the name if known, else ``unknown:<guid prefix>``."""
    if raw == NULL_GUID:
        return None
    guid = from_larian_bytes(raw)
    return table.get(guid, f"{UNKNOWN_PREFIX}{guid[:8]}")


def load_game_data(shared_dir: Path | None) -> GameData:
    if shared_dir is None:
        return GameData()
    return GameData(
        classes=read_name_table(shared_dir.glob("Public/*/ClassDescriptions/ClassDescriptions.lsx")),
        feats=read_name_table(shared_dir.glob("Public/*/Feats/Feats.lsx")),
        camp_chest_templates=read_camp_chest_templates(shared_dir.glob("Public/*/Lists/CampChestTemplates.lsx")),
    )


def read_name_table(paths: Iterable[Path]) -> dict[str, str]:
    names: dict[str, str] = {}
    for path in paths:
        for node in ET.parse(path).getroot().iter("node"):
            attrs = {a.get("id"): a.get("value", "") for a in node.findall("attribute")}
            if attrs.get("UUID") and attrs.get("Name"):
                names[attrs["UUID"].lower()] = attrs["Name"]
    return names


def read_camp_chest_templates(paths: Iterable[Path]) -> frozenset[str]:
    """Root template GUIDs of camp chests.

    The file is a list of ``<node id="CampChestTemplate">`` entries, each with a
    ``TemplateId`` attribute (the chest's root template) and its own ``UUID``.
    """
    templates = set()
    for path in paths:
        for node in ET.parse(path).getroot().iter("node"):
            if node.get("id") != "CampChestTemplate":
                continue
            attr = node.find("attribute[@id='TemplateId']")
            if attr is not None and (value := attr.get("value")):
                templates.add(value.lower())
    return frozenset(templates)
