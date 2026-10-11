"""Party-wide state: days passed, camp supplies, known recipes, and unlocked waypoints.

These live on singleton entities rather than on characters.
"""

import struct
from dataclasses import dataclass

from bg3_newage.lsmf import RANGE, NewAge, read_i32_field

# game.party.v0.RecipeData: name string view (pointer, u64 length), 8 unknown bytes
RECIPE = struct.Struct("<QQ8x")
# game.party.v0.WaypointsComponent points at 48-byte entries: name string view, 16-byte GUID, level name string view
WAYPOINT = struct.Struct("<QQ16xQQ")
WAYPOINT_PREFIX = "WAYP_"


@dataclass(frozen=True)
class Waypoint:
    name: str
    level: str


@dataclass(frozen=True)
class CampState:
    days_passed: int | None
    supplies: int | None
    recipes: tuple[str, ...]
    waypoints: tuple[Waypoint, ...]


def read_camp(blob: NewAge) -> CampState:
    return CampState(
        days_passed=read_i32_field(blob.single("game.calendar.v0.DaysPassedComponent")),
        supplies=read_i32_field(blob.single("game.camp.v0.TotalSuppliesComponent")),
        recipes=read_recipes(blob),
        waypoints=read_waypoints(blob),
    )


def read_recipes(blob: NewAge) -> tuple[str, ...]:
    raw = blob.single("game.party.v1.RecipesComponent")
    if raw is None:
        return ()
    start, end = RANGE.unpack(raw)
    return tuple(blob.read_string(ptr, n) for ptr, n in blob.read_range(start, end, RECIPE))


def read_waypoints(blob: NewAge) -> tuple[Waypoint, ...]:
    raw = blob.single("game.party.v0.WaypointsComponent")
    if raw is None:
        return ()
    start, end = RANGE.unpack(raw)
    return tuple(
        Waypoint(blob.read_string(ptr, n).removeprefix(WAYPOINT_PREFIX), blob.read_string(level_ptr, level_n))
        for ptr, n, level_ptr, level_n in blob.read_range(start, end, WAYPOINT)
    )
