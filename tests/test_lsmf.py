import pytest

from bg3_newage.guids import from_larian_bytes, swap_tail, to_larian_bytes
from bg3_newage.lsmf import ENTITY_ID_COMPONENT, LsmfError, NewAge
from tests.builder import BlobBuilder


def test_larian_guid_encoding_matches_real_save_bytes():
    # The one real-save fixture: an entity GUID as printed in Globals.lsx and the bytes stored for it
    # in the NewAge blob. It's an engine entity ID, not personal data.
    text = "e3c5f9c9-40c1-c67d-e89a-706431974622"
    raw = bytes.fromhex("c9f9c5e3c1407dc69ae8647097312246")
    assert to_larian_bytes(text) == raw
    assert from_larian_bytes(raw) == text
    assert swap_tail(swap_tail(raw)) == raw


def test_components_and_owner_maps():
    b = BlobBuilder(entity_count=3)
    b.add_component("game.test.v0.PerEntity", 4, [b"\x01\0\0\0", b"\x02\0\0\0"], owners=[2, 0])
    b.add_component("game.test.v0.SideTable", 2, [b"ab", b"cd", b"ef"])
    blob = NewAge(b.build())

    assert len(blob.entities) == 3
    assert blob.components["game.test.v0.PerEntity"].owners == (2, 0)
    assert blob.components["game.test.v0.SideTable"].owners is None
    assert blob.by_entity("game.test.v0.PerEntity") == {2: b"\x01\0\0\0", 0: b"\x02\0\0\0"}
    assert [raw for _, raw in blob.elements("game.test.v0.SideTable")] == [b"ab", b"cd", b"ef"]
    assert blob.elements("game.missing.v0.Nothing") == []


def test_resolve_ref_points_into_entity_id_table():
    b = BlobBuilder(entity_count=3)
    table = b.add_component(ENTITY_ID_COMPONENT, 16, [b.entities[2], b.entities[0]])
    blob = NewAge(b.build())

    assert blob.resolve_ref(table) == 2
    assert blob.resolve_ref(table + 16) == 0
    assert blob.resolve_ref(table + 32) is None
    assert blob.resolve_ref(0xFFFFFF) is None


def test_rejects_non_lsmf_data():
    with pytest.raises(LsmfError):
        NewAge(b"XXXX" + bytes(60))


def test_out_of_bounds_read_raises():
    blob = NewAge(BlobBuilder(entity_count=1).build())
    with pytest.raises(LsmfError):
        blob.read(len(blob.data), 16)


def test_owner_map_length_must_match_element_count():
    b = BlobBuilder(entity_count=2)
    b.add_component("game.test.v0.PerEntity", 1, [b"a", b"b"], owners=[0])
    with pytest.raises(LsmfError, match="owner map has 1 entries for 2 elements"):
        NewAge(b.build())


def test_by_entity_rejects_multiple_elements_per_entity():
    b = BlobBuilder(entity_count=1)
    b.add_component("game.test.v0.Many", 1, [b"a", b"b"], owners=[0, 0])
    blob = NewAge(b.build())
    assert len(blob.elements("game.test.v0.Many")) == 2
    with pytest.raises(LsmfError, match="more than one element"):
        blob.by_entity("game.test.v0.Many")


def test_build_is_repeatable():
    b = BlobBuilder(entity_count=2)
    b.add_component("game.test.v0.X", 1, [b"a"], owners=[1])
    assert b.build() == b.build()


def test_empty_owner_map_with_sentinel_offset():
    b = BlobBuilder(entity_count=1)
    b.add_component("game.test.v0.Empty", 4, [], owners=[])
    blob = NewAge(b.build())
    assert blob.components["game.test.v0.Empty"].owners == ()
    assert blob.by_entity("game.test.v0.Empty") == {}
