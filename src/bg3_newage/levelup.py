"""Level-up history: class, subclass, and feat per level, plus every choice made along the way.

Each ``LevelUpComponentData`` record points at a ``LevelUpComponentSelectors``
record: one range of selector pointers per kind of choice (``SELECTOR_KINDS``).
Each selector record holds its own range of picks:

- abilities and skills: a pointer to an element of an enum table
  (``EAbility``/``ESkill``) whose i64 value is the game's ability or skill ID
- spells, passives (fighting styles, Elemental Adept's element), equipment:
  a string view with the name

Point-buy base scores, set at character creation, live in
``CharacterCreationStatsComponent`` and are read here too because they are the
starting point the level-up choices build on.
"""

import struct
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from bg3_newage.gamedata import GameData
from bg3_newage.lsmf import EMPTY_RANGE, I32, I64, RANGE, U64, NewAge

# Game ability IDs, in the order the game lists them; 0 means "none"
ABILITY_IDS = {1: "STR", 2: "DEX", 3: "CON", 4: "INT", 5: "WIS", 6: "CHA"}
ABILITIES = tuple(ABILITY_IDS.values())
# Game skill IDs: a skill's position in this tuple is its ID
SKILL_IDS = (
    "Deception",
    "Intimidation",
    "Performance",
    "Persuasion",
    "Acrobatics",
    "SleightOfHand",
    "Stealth",
    "Arcana",
    "History",
    "Investigation",
    "Nature",
    "Religion",
    "Athletics",
    "AnimalHandling",
    "Insight",
    "Medicine",
    "Perception",
    "Survival",
)

# game.character_creation.v3.LevelUpComponentData: class, subclass, feat GUIDs (null when not chosen),
# 16 unknown bytes, u64 pointer to a 16-byte ability record (all zero in practice), u64 pointer to the level's
# LevelUpComponentSelectors (all ones when there is none), an unknown range
LEVEL_UP_RECORD = struct.Struct("<16s16s16s16xQQ16x")
# Every selector record starts with: u64 metadata pointer, 16-byte list GUID, [start, end) range of picks
SELECTOR = struct.Struct("<Q16xQQ")
# AbilityBonusSelector is a SELECTOR followed by a [start, end) range of i32 amounts, one per pick
BONUS_SELECTOR = struct.Struct(SELECTOR.format + "QQ")
# game.character_creation.v1.StringViewAddSlot: name pointer, u32 length, 4 unknown bytes.
# (Prepared spells in spells.py use the same pointer + u32 length view with different padding.)
NAME_SLOT = struct.Struct("<QI4x")
# game.character_creation.v1.CharacterCreationStatsComponent: 72 unknown bytes, then a [start, end) range of i32
# point-buy increments, indexed by ability ID (index 0 unused). A score is POINT_BUY_FLOOR plus its increment.
CREATION_STATS = struct.Struct("<72xQQ")
POINT_BUY_FLOOR = 8


@dataclass(frozen=True)
class LevelUp:
    level: int
    class_name: str | None
    subclass: str | None
    feat: str | None
    # Choice kind (a SELECTOR_KINDS label) -> picks, for the kinds chosen at this level
    choices: dict[str, tuple[str, ...]]


def read_level_ups(blob: NewAge, entity: int, game: GameData) -> tuple[LevelUp, ...]:
    raw = blob.by_entity("game.progression.v3.LevelUpComponent").get(entity)
    if raw is None:
        return ()
    start, end = RANGE.unpack(raw)
    level_ups = []
    for level, (record_offset,) in enumerate(blob.read_range(start, end, U64), start=1):
        class_guid, subclass_guid, feat_guid, _, selectors = blob.read_struct(LEVEL_UP_RECORD, record_offset)
        level_ups.append(
            LevelUp(
                level,
                game.class_name(class_guid),
                game.class_name(subclass_guid),
                game.feat_name(feat_guid),
                read_choices(blob, selectors),
            )
        )
    return tuple(level_ups)


def read_choices(blob: NewAge, selectors_offset: int) -> dict[str, tuple[str, ...]]:
    if selectors_offset == EMPTY_RANGE:
        return {}
    ranges = RANGE.iter_unpack(blob.read(selectors_offset, RANGE.size * len(SELECTOR_KINDS)))
    choices = {}
    for (label, read_picks), (start, end) in zip(SELECTOR_KINDS, ranges, strict=True):
        picks = tuple(pick for (selector,) in blob.read_range(start, end, U64) for pick in read_picks(blob, selector))
        if picks:
            choices[label] = picks
    return choices


def read_names(blob: NewAge, selector: int) -> list[str]:
    _, start, end = blob.read_struct(SELECTOR, selector)
    return [blob.read_string(ptr, length) for ptr, length in blob.read_range(start, end, NAME_SLOT)]


def read_enum_values(blob: NewAge, start: int, end: int) -> list[int]:
    """Picks stored as pointers into an enum table; the table element holds the game's ID."""
    return [blob.read_struct(I64, slot)[0] for (slot,) in blob.read_range(start, end, U64)]


def read_skills(blob: NewAge, selector: int) -> list[str]:
    _, start, end = blob.read_struct(SELECTOR, selector)
    return [SKILL_IDS[v] if 0 <= v < len(SKILL_IDS) else f"skill {v}" for v in read_enum_values(blob, start, end)]


def read_ability_points(blob: NewAge, selector: int) -> list[str]:
    """Feat/ASI points: each pick is +1, so two picks of one ability show as +2."""
    _, start, end = blob.read_struct(SELECTOR, selector)
    abilities = [ability_name(v) for v in read_enum_values(blob, start, end)]
    return format_bonuses(abilities, [1] * len(abilities))


def read_racial_bonus(blob: NewAge, selector: int) -> list[str]:
    _, start, end, amounts_start, amounts_end = blob.read_struct(BONUS_SELECTOR, selector)
    abilities = [ability_name(v) for v in read_enum_values(blob, start, end)]
    amounts = [n for (n,) in blob.read_range(amounts_start, amounts_end, I32)]
    if len(amounts) != len(abilities):
        raise ValueError(f"racial bonus selector at {selector:#x}: {len(abilities)} picks but {len(amounts)} amounts")
    return format_bonuses(abilities, amounts)


def ability_name(value: int) -> str:
    return ABILITY_IDS.get(value, f"ability {value}")


def format_bonuses(abilities: list[str], amounts: list[int]) -> list[str]:
    totals: Counter[str] = Counter()
    for ability, amount in zip(abilities, amounts, strict=True):
        totals[ability] += amount
    return [f"{ability} {amount:+d}" for ability, amount in totals.items()]


# The ranges of LevelUpComponentSelectors, in stored order: the label each kind's picks are reported under,
# and how its selector records store them
SELECTOR_KINDS: tuple[tuple[str, Callable[[NewAge, int], list[str]]], ...] = (
    ("ability increase", read_ability_points),  # AbilitySelector
    ("racial bonus", read_racial_bonus),  # AbilityBonusSelector
    ("skills", read_skills),  # SkillSelector
    ("expertise", read_skills),  # SkillExpertiseSelector
    ("spells", read_names),  # SpellSelector
    ("passives", read_names),  # PassiveSelector
    ("equipment", read_names),  # EquipmentSelector
)


def read_point_buy(blob: NewAge, entity: int) -> dict[str, int]:
    """Ability scores as bought at character creation, before racial bonuses and feats."""
    raw = blob.by_entity("game.character_creation.v1.CharacterCreationStatsComponent").get(entity)
    if raw is None:
        return {}
    start, end = CREATION_STATS.unpack(raw)
    increments = [n for (n,) in blob.read_range(start, end, I32)]
    if len(increments) <= max(ABILITY_IDS):
        raise ValueError(
            f"point buy for entity {entity} has {len(increments)} entries, expected {max(ABILITY_IDS) + 1}"
        )
    return {name: POINT_BUY_FLOOR + increments[i] for i, name in ABILITY_IDS.items()}


def class_summary(level_ups: tuple[LevelUp, ...]) -> str:
    counts = Counter(lu.class_name or "no class" for lu in level_ups)
    return " / ".join(f"{name} {n}" for name, n in counts.items())
