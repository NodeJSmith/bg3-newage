"""Character names from the save's Osiris story database (StorySave.bin).

The NewAge blob has no character names, but the story scripts refer to
characters by constants like ``S_Player_Astarion_c7c13742-bacd-...``: a name
followed by the character's root template GUID. StorySave.bin stores its
strings XOR-scrambled with 0xAD, so unscrambling the whole file and searching it
recovers a template GUID -> name table without parsing the Osiris format.
"""

import re
from pathlib import Path

SCRAMBLE_KEY = 0xAD
UNSCRAMBLE = bytes(b ^ SCRAMBLE_KEY for b in range(256))
NAMED_GUID = re.compile(rb"([A-Za-z0-9_]+?)_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
# Story constants carry a type tag and a scope prefix that aren't part of the name
NAME_PREFIX = re.compile(r"^(?:[A-Z]+GUID_)?S_(?:Player_|GLO_)?")


def read_story_names(path: Path) -> dict[str, str]:
    """Map lowercase root template GUID -> readable name, e.g. ``Astarion`` or ``GOB_DrowCommander``."""
    if not path.is_file():
        return {}
    text = path.read_bytes().translate(UNSCRAMBLE)
    names: dict[str, str] = {}
    for raw_name, guid in NAMED_GUID.findall(text):
        name = NAME_PREFIX.sub("", raw_name.decode("ascii"))
        names.setdefault(guid.decode("ascii"), name)
    return names
