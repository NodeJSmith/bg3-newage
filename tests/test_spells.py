import json

from bg3_newage.spells import prepared_spells
from tests.cli_runner import run_cli
from tests.sample_save import COMPANION, PLAYER, build_save, write_save_dir


def test_prepared_spells_skip_basic_actions():
    assert prepared_spells(build_save().newage, PLAYER) == ("Target_ViciousMockery",)


def test_no_spell_book_means_no_spells():
    assert prepared_spells(build_save().newage, COMPANION) == ()


def test_spells_command_json(tmp_path, capsys):
    code, out, _ = run_cli(["spells", str(write_save_dir(tmp_path / "save")), "--json"], capsys)

    assert code == 0
    assert json.loads(out) == [
        {"entity": PLAYER, "name": f"entity {PLAYER}", "spells": ["Target_ViciousMockery"]},
        {"entity": COMPANION, "name": "Wyll", "spells": []},
    ]
