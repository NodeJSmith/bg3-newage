"""Larian's on-disk GUID encoding.

The first 8 bytes use ``uuid.UUID.bytes_le`` layout (the first three groups
byte-reversed). The last 8 bytes, which ``bytes_le`` leaves as written, are
additionally swapped pairwise. For example, the GUID
``e3c5f9c9-40c1-c67d-e89a-706431974622`` is stored as
``c9f9c5e3 c140 7dc6 9ae8 6470 9731 2246``.

Every GUID-typed field seen so far (entity IDs, class/feat/origin references)
uses this encoding, and the textual GUIDs in LSX files and game data decode
from it.
"""

import uuid

NULL_GUID = bytes(16)


def swap_tail(raw: bytes) -> bytes:
    """Swap the last 8 bytes pairwise (ab cd ef .. -> ba dc fe ..). The operation is its own inverse."""
    return raw[:8] + bytes(raw[8 + (i ^ 1)] for i in range(8))


def to_larian_bytes(text: str) -> bytes:
    return swap_tail(uuid.UUID(text).bytes_le)


def from_larian_bytes(raw: bytes) -> str:
    return str(uuid.UUID(bytes_le=swap_tail(raw)))
