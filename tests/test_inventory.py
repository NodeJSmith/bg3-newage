import json
import struct
from dataclasses import replace

from bg3_newage.cli import app
from bg3_newage.inventory import MEMBER_DATA, Inventories, Item
from bg3_newage.lsmf import ENTITY_ID_COMPONENT, GUID_SIZE, NewAge
from bg3_newage.save import ItemInfo, Save
from tests.builder import BlobBuilder
from tests.sample_save import (
    CHEST,
    GAME,
    NO_GAME_DATA,
    PLAYER,
    build_save,
    write_game_data_dir,
    write_save_dir,
)


def test_equipped_items_come_from_wielding():
    holdings = Inventories.from_save(build_save()).holdings(PLAYER)

    assert holdings.equipped == (Item(3, "Melee main hand", "WPN_Longsword_1"),)


def test_carried_items_list_bag_contents_right_after_the_bag():
    holdings = Inventories.from_save(build_save()).holdings(PLAYER)

    assert holdings.carried == ("OBJ_Potion_Healing", "OBJ_Bag_AlchemyPouch", "OBJ_Agate")


def test_camp_chest_found_by_template():
    inventories = Inventories.from_save(build_save())

    assert inventories.camp_chests(GAME) == [CHEST]
    assert inventories.names_held_by(CHEST) == ("ARM_Helmet_1",)


def test_no_camp_chest_without_templates():
    assert Inventories.from_save(build_save()).camp_chests(NO_GAME_DATA) == []


def test_no_camp_chest_when_save_lacks_template_info():
    save = build_save()
    untemplated = replace(save, items={e: replace(i, template=None) for e, i in save.items.items()})

    assert Inventories.from_save(untemplated).camp_chests(GAME) == []


def test_bag_inside_itself_is_listed_once():
    # Corrupt case: a bag whose own inventory contains the bag
    bag, bag_inventory = 0, 1
    b = BlobBuilder(entity_count=2)
    ids = b.add_component(ENTITY_ID_COMPONENT, GUID_SIZE, list(b.entities))
    member_data = b.add_blob(MEMBER_DATA.pack(ids + GUID_SIZE * bag_inventory, 0))
    b.add_component("game.inventory.v0.MemberComponent", 8, [struct.pack("<Q", member_data)], owners=[bag])
    b.add_component(
        "game.inventory.v1.IsOwnedComponent", 8, [struct.pack("<Q", ids + GUID_SIZE * bag)], owners=[bag_inventory]
    )
    save = Save(NewAge(b.build()), {bag: ItemInfo("OBJ_Bag", None)}, (), "", "")

    assert Inventories.from_save(save).names_held_by(bag) == ("OBJ_Bag",)


def run_cli(args: list[str], capsys) -> tuple[int, str, str]:
    try:
        app(args, exit_on_error=False)
        code = 0
    except SystemExit as exc:
        code = int(exc.code or 0)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_camp_chest_command_text_and_json(tmp_path, capsys):
    save_dir = write_save_dir(tmp_path / "save")
    game_dir = write_game_data_dir(tmp_path / "shared")

    code, out, _ = run_cli(["camp-chest", str(save_dir), "--game-data", str(game_dir)], capsys)
    assert code == 0
    assert out == "Traveller's Chest: 1 item\n   ARM_Helmet_1\n"

    code, out, _ = run_cli(["camp-chest", str(save_dir), "--game-data", str(game_dir), "--json"], capsys)
    assert code == 0
    assert json.loads(out) == [{"name": "ARM_Helmet_1", "count": 1}]


def test_camp_chest_command_explains_missing_template_list(tmp_path, capsys):
    save_dir = write_save_dir(tmp_path / "save")

    code, _, err = run_cli(["camp-chest", str(save_dir), "--game-data", str(tmp_path / "empty")], capsys)

    assert code == 1
    assert "CampChestTemplates.lsx" in err


def test_camp_chest_command_explains_no_chest_in_save(tmp_path, capsys):
    save_dir = write_save_dir(tmp_path / "save")
    game_dir = write_game_data_dir(tmp_path / "shared", chest_templates=("00000000-0000-0000-0000-00000000abcd",))

    code, _, err = run_cli(["camp-chest", str(save_dir), "--game-data", str(game_dir)], capsys)

    assert code == 1
    assert "no item in this save uses a camp chest template" in err
