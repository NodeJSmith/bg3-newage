from bg3_newage.osiris import SCRAMBLE_KEY, read_story_names

GUID = "c7c13742-bacd-460a-8f65-f864fe41f255"


def test_story_names_are_unscrambled_and_prefixes_stripped(tmp_path):
    story = f"\x00CHARACTERGUID_S_Player_Astarion_{GUID}\x00S_GLO_Hirelings_Barbarian_{GUID.replace('c7', 'd8')}\x00"
    path = tmp_path / "StorySave.bin"
    path.write_bytes(bytes(c ^ SCRAMBLE_KEY for c in story.encode()))

    assert read_story_names(path) == {GUID: "Astarion", GUID.replace("c7", "d8"): "Hirelings_Barbarian"}


def test_missing_story_file_gives_no_names(tmp_path):
    assert read_story_names(tmp_path / "StorySave.bin") == {}
