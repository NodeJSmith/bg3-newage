import json
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, NoReturn

from cyclopts import App, Parameter

from bg3_newage.camp import read_camp
from bg3_newage.gamedata import GameData, load_game_data
from bg3_newage.inventory import Inventories
from bg3_newage.levelup import class_summary
from bg3_newage.party import PartyMember, read_party
from bg3_newage.save import load_save

app = App(name="bg3-newage", help="Read party builds out of an extracted Baldur's Gate 3 save.")


@app.command
def party(
    save_dir: Path,
    *,
    game_data: Annotated[Path | None, Parameter(help="Extracted Shared.pak directory, for class/feat names.")] = None,
    as_json: Annotated[bool, Parameter(name="--json")] = False,
) -> None:
    """Show each party member's ability scores, level-up choices, and gear.

    SAVE_DIR is a save extracted with LSLib, with Globals.lsf converted to Globals.lsx.
    """
    with exit_on_bad_input():
        save = load_save(save_dir)
        members = read_party(save, load_game_data(game_data))
    if as_json:
        print(json.dumps([asdict(m) for m in members], indent=2))
        return
    print(f"{save.location}  ({save.difficulty})\n")
    for heading, group in (
        ("Party", [m for m in members if m.in_party]),
        ("At camp", [m for m in members if not m.in_party]),
    ):
        if group:
            print(f"--- {heading} ---\n")
            for member in group:
                print(format_member(member))


@app.command
def spells(
    save_dir: Path,
    *,
    as_json: Annotated[bool, Parameter(name="--json")] = False,
) -> None:
    """List what each party and camp member can cast or use: prepared spells, class actions, item spells.

    Actions every character has (jump, shove, dash, attacks) are left out.
    """
    with exit_on_bad_input():
        # Spell names are stored as text, so no class/feat game data is needed here
        members = read_party(load_save(save_dir), GameData())
    if as_json:
        spell_lists = [{"entity": m.entity, "name": m.name, "spells": m.prepared_spells} for m in members]
        print(json.dumps(spell_lists, indent=2))
        return
    for member in members:
        print(f"== {member.name} ({len(member.prepared_spells)})")
        print(f"   {', '.join(member.prepared_spells)}\n")


@app.command
def camp(
    save_dir: Path,
    *,
    as_json: Annotated[bool, Parameter(name="--json")] = False,
) -> None:
    """Show days passed, camp supplies, known alchemy recipes, and unlocked waypoints."""
    with exit_on_bad_input():
        state = read_camp(load_save(save_dir).newage)
    if as_json:
        print(json.dumps(asdict(state), indent=2))
        return
    print(f"Days passed: {or_unknown(state.days_passed)}")
    print(f"Camp supplies: {or_unknown(state.supplies)}")
    print(f"Recipes ({len(state.recipes)}): {', '.join(state.recipes)}")
    print(f"Waypoints ({len(state.waypoints)}):")
    for waypoint in state.waypoints:
        print(f"   {waypoint.name}  [{waypoint.level}]")


@app.command
def camp_chest(
    save_dir: Path,
    *,
    game_data: Annotated[Path, Parameter(help="Extracted Shared.pak directory; identifies the chest.")],
    as_json: Annotated[bool, Parameter(name="--json")] = False,
) -> None:
    """List everything in the camp's Traveller's Chest, including the contents of bags inside it.

    The chest is recognised by its root template, so this needs the game's CampChestTemplates list.
    """
    with exit_on_bad_input():
        save = load_save(save_dir)
        game = load_game_data(game_data)
    if not game.camp_chest_templates:
        fail(f"no Public/*/Lists/CampChestTemplates.lsx under {game_data}; pass an extracted Shared.pak")
    inventories = Inventories.from_save(save)
    chests = inventories.camp_chests(game)
    if not chests:
        fail("no item in this save uses a camp chest template")
    contents = [name for chest in chests for name in inventories.names_held_by(chest)]
    counted = count_in_order(contents)
    if as_json:
        print(json.dumps([{"name": name, "count": n} for name, n in counted], indent=2))
        return
    print(f"Traveller's Chest: {len(contents)} item{'' if len(contents) == 1 else 's'}")
    for name, n in counted:
        print(f"   {with_count(name, n)}")


@app.command
def components(save_dir: Path, *, grep: str = "") -> None:
    """List every component in the NewAge blob: index, element size, count, and whether it's per-entity."""
    with exit_on_bad_input():
        blob = load_save(save_dir).newage
    for comp in blob.components.values():
        if grep.lower() in comp.name.lower():
            kind = "entity" if comp.owners is not None else "table"
            print(f"{comp.index:4d}  {comp.element_size:5d} x {comp.element_count:<6d} {kind:6s}  {comp.name}")


@contextmanager
def exit_on_bad_input() -> Iterator[None]:
    """Report unreadable or malformed input as a one-line error instead of a traceback."""
    try:
        yield
    # LsmfError is a ValueError; struct.error means a component element was shorter than its known layout
    except (OSError, ValueError, ET.ParseError, struct.error) as exc:
        fail(str(exc))


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def count_in_order(names: Iterable[str]) -> list[tuple[str, int]]:
    """Collapse duplicate names to counts, keeping first-seen (in-game container) order."""
    return list(Counter(names).items())


def with_count(name: str, n: int) -> str:
    return name if n == 1 else f"{name} x{n}"


def or_unknown(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def format_member(member: PartyMember) -> str:
    details = []
    if member.total_xp is not None:
        details.append(f"XP {member.total_xp}")
    if member.max_hp is not None:
        details.append(f"HP {member.hp}/{member.max_hp}")
    if member.approval is not None:
        details.append(f"approval {member.approval}")
    lines = [f"== {member.name}  ({', '.join(details)})" if details else f"== {member.name}"]
    if member.abilities:
        scores = "  ".join(f"{k} {v}" for k, v in member.abilities.items())
        lines.append(f"   {scores}  prof +{member.proficiency}")
    if member.point_buy:
        lines.append(f"   point buy: {'  '.join(f'{k} {v}' for k, v in member.point_buy.items())}")
    # Only levels where a choice was made; plain class levels are covered by the classes line
    for lu in member.level_ups:
        if lu.subclass or lu.feat or lu.choices or lu.level == 1:
            picks = [("subclass", lu.subclass), ("feat", lu.feat)]
            picks += [(kind, ", ".join(values)) for kind, values in lu.choices.items()]
            extra = "".join(f"  {label}: {value}" for label, value in picks if value)
            lines.append(f"   L{lu.level} {lu.class_name or '?'}{extra}")
    lines.append(f"   classes: {class_summary(member.level_ups)}")
    if member.tadpole_powers:
        lines.append(f"   tadpole powers: {', '.join(member.tadpole_powers)}")
    for item in member.equipped:
        lines.append(f"   [{item.slot_name}] {item.name}")
    if member.carried:
        listed = ", ".join(with_count(name, n) for name, n in count_in_order(member.carried))
        lines.append(f"   carrying {len(member.carried)}: {listed}")
    return "\n".join(lines) + "\n"
