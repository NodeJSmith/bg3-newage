from bg3_newage.camp import CampState, Waypoint, read_camp
from tests.cli_runner import run_cli
from tests.sample_save import build_save, write_save_dir


def test_camp_state():
    assert read_camp(build_save().newage) == CampState(
        days_passed=43,
        supplies=581,
        recipes=("ALCH_Potion_Healing_RoguesMorsel",),
        waypoints=(Waypoint("SHA_Temple", "SCL_Main_A"),),
    )


def test_camp_command_text(tmp_path, capsys):
    code, out, _ = run_cli(["camp", str(write_save_dir(tmp_path / "save"))], capsys)

    assert code == 0
    assert out == (
        "Days passed: 43\n"
        "Camp supplies: 581\n"
        "Recipes (1): ALCH_Potion_Healing_RoguesMorsel\n"
        "Waypoints (1):\n"
        "   SHA_Temple  [SCL_Main_A]\n"
    )


def test_party_command_lists_camp_companion_after_party(tmp_path, capsys):
    code, out, _ = run_cli(["party", str(write_save_dir(tmp_path / "save"))], capsys)

    assert code == 0
    assert "--- At camp ---\n\n== Wyll  (XP 34359, HP 40/71, approval 42)\n" in out
