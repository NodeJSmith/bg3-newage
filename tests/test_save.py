import base64
import json
import uuid

import pytest

from bg3_newage.cli import app
from bg3_newage.gamedata import load_game_data
from bg3_newage.guids import to_larian_bytes
from bg3_newage.save import load_save
from tests.builder import BlobBuilder, guid

GLOBALS = """<?xml version="1.0" encoding="utf-8"?>
<save>
  <region id="NewAge"><node id="NewAge">
    <attribute id="NewAge" type="ScratchBuffer" value="{blob}" />
  </node></region>
  <region id="Items"><node id="Items"><children>
    <node id="Creator"><attribute id="Entity" type="guid" value="{item_guid}" /></node>
    <node id="Item"><attribute id="Stats" type="FixedString" value="WPN_Longsword_1" /></node>
  </children></node></region>
</save>
"""


def test_load_save_reads_blob_items_and_save_info(tmp_path):
    builder = BlobBuilder(entity_count=2)
    blob = builder.build()
    item_guid = str(uuid.UUID(int=2))  # entity 1's GUID, as LSX would print it
    assert to_larian_bytes(item_guid) == guid(1)
    (tmp_path / "Globals.lsx").write_text(GLOBALS.format(blob=base64.b64encode(blob).decode(), item_guid=item_guid))
    (tmp_path / "SaveInfo.json").write_text(
        json.dumps(
            {
                "Current Level": "SCL_Main_A",
                "Difficulty": ["DifficultyMedium", "RulesetLarian"],
                "Active Party": {"Characters": [{"Origin": "Shadowheart", "Experience Points (Total)": 34074}]},
            }
        )
    )

    save = load_save(tmp_path)

    assert save.item_stats == {1: "WPN_Longsword_1"}
    assert save.members[0].origin == "Shadowheart"
    assert save.members[0].total_xp == 34074
    assert save.location == "SCL_Main_A"
    assert save.difficulty == "DifficultyMedium / RulesetLarian"


def test_missing_globals_explains_conversion(tmp_path):
    with pytest.raises(FileNotFoundError, match="Globals.lsf to .lsx"):
        load_save(tmp_path)


def test_load_game_data_reads_feats_and_classes(tmp_path):
    feats = tmp_path / "Public/Shared/Feats"
    feats.mkdir(parents=True)
    (feats / "Feats.lsx").write_text(
        '<save><node id="Feat"><attribute id="Name" value="Lucky" />'
        '<attribute id="UUID" value="D84C7F36-8C5B-4B17-B95A-E1DA20F79004" /></node></save>'
    )

    game = load_game_data(tmp_path)

    assert game.feats == {"d84c7f36-8c5b-4b17-b95a-e1da20f79004": "Lucky"}
    assert game.classes == {}


def test_mismatched_items_region_fails_loudly(tmp_path):
    blob = base64.b64encode(BlobBuilder(entity_count=1).build()).decode()
    xml = GLOBALS.format(blob=blob, item_guid=str(uuid.UUID(int=1))).replace(
        '<node id="Item">', '<node id="Item"><attribute id="Stats" value="X" /></node><node id="Item">'
    )
    (tmp_path / "Globals.lsx").write_text(xml)
    with pytest.raises(ValueError, match="1 Creator nodes but 2 Item nodes"):
        load_save(tmp_path)


def test_cli_reports_malformed_globals_without_traceback(tmp_path, capsys):
    (tmp_path / "Globals.lsx").write_text("<save><region")
    with pytest.raises(SystemExit) as exit_info:
        app(["party", str(tmp_path)], exit_on_error=False)
    assert exit_info.value.code == 1
    assert capsys.readouterr().err.startswith("error: ")
