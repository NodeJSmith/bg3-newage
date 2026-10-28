"""Build synthetic LSMF blobs so tests never need a real save.

The builder lays components out in a body buffer, then appends the Level
record (entities + owner maps), the name block, and the component table, and
prefixes the header. Offsets it returns are body-relative, which is exactly
what stored offsets in a real blob are.
"""

import struct
import uuid
from dataclasses import dataclass

from bg3_newage.guids import to_larian_bytes
from bg3_newage.lsmf import (
    EMPTY_RANGE,
    GUID_SIZE,
    HEADER,
    LEVEL_COMPONENT,
    LEVEL_RECORD,
    MAGIC,
    OWNER_MAP_ENTRY,
    TABLE_ENTRY,
)

UNKNOWN_HASH = 0
FORMAT_VERSION = 1
COMPONENT_VERSION = 0


def guid(n: int) -> bytes:
    """Stored bytes of a distinct GUID per n (+1 keeps n=0 from being the null GUID)."""
    return to_larian_bytes(str(uuid.UUID(int=n + 1)))


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    element_size: int
    element_count: int
    data_offset: int
    owners: list[int] | None


class BlobBuilder:
    def __init__(self, entity_count: int) -> None:
        self.entities = [guid(i) for i in range(entity_count)]
        self.body = bytearray()
        self.components: list[ComponentSpec] = []

    def add_blob(self, data: bytes) -> int:
        offset = len(self.body)
        self.body += data
        return offset

    def add_component(self, name: str, size: int, elements: list[bytes], owners: list[int] | None = None) -> int:
        assert all(len(e) == size for e in elements)
        offset = self.add_blob(b"".join(elements))
        self.components.append(ComponentSpec(name, size, len(elements), offset, owners))
        return offset

    def build(self) -> bytes:
        body = bytearray(self.body)

        def append(data: bytes) -> int:
            offset = len(body)
            body.extend(data)
            return offset

        entities_offset = append(b"".join(self.entities))
        owner_maps = b""
        # Table index 0 is the Level component itself, so added components start at 1
        for table_index, spec in enumerate(self.components, start=1):
            if spec.owners is not None:
                # Real blobs store an all-ones sentinel offset for empty owner maps
                indices = append(struct.pack(f"<{len(spec.owners)}I", *spec.owners)) if spec.owners else EMPTY_RANGE
                owner_maps += OWNER_MAP_ENTRY.pack(
                    indices, indices + 4 * len(spec.owners), table_index, len(spec.owners)
                )
        maps_offset = append(owner_maps)
        level_offset = append(
            LEVEL_RECORD.pack(
                entities_offset,
                entities_offset + GUID_SIZE * len(self.entities),
                maps_offset,
                maps_offset + len(owner_maps),
            )
        )

        level = ComponentSpec(LEVEL_COMPONENT, LEVEL_RECORD.size, 1, level_offset, None)
        block_offset = len(body)
        names = b""
        table = b""
        for spec in [level, *self.components]:
            encoded = spec.name.encode()
            table += TABLE_ENTRY.pack(
                len(names),
                len(encoded),
                0,
                UNKNOWN_HASH,
                spec.element_size,
                COMPONENT_VERSION,
                spec.element_count,
                spec.data_offset,
            )
            names += encoded
        body += names + table
        header = HEADER.pack(
            MAGIC,
            FORMAT_VERSION,
            UNKNOWN_HASH,
            block_offset,
            len(names) + len(table),
            len(names),
            1 + len(self.components),
            0,
            0,
        )
        return header + bytes(body)
