"""Spells and tadpole powers, read straight from string views in the blob.

Unlike class and feat references, spell and power names are stored as text, so
no game data is needed to read them.
"""

import struct

from bg3_newage.lsmf import RANGE, NewAge

# Every character has these actions; listing them adds nothing
BASIC_ACTIONS = frozenset(
    {
        "Projectile_Jump",
        "Target_Dip",
        "Shout_Hide",
        "Target_Shove",
        "Throw_Throw",
        "Throw_ImprovisedWeapon",
        "Shout_Dash",
        "Target_Help",
        "Shout_Disengage",
        "Target_MainHandAttack",
        "Projectile_MainHandAttack",
        "Target_OffhandAttack",
        "Projectile_OffhandAttack",
    }
)
# game.spell.v0.SpellBookPrepares (80 bytes) starts with the [start, end) range of prepared spells; rest unknown
PREPARED_RANGE = struct.Struct("<QQ64x")
# One prepared spell: name string view (pointer, u32 length), 12 unknown bytes
PREPARED_SPELL = struct.Struct("<QI12x")
# game.tadpole_tree.v0.PowerContainerComponent is a [start, end) range of name string views: pointer, u64 length.
# Same layout as RANGE, different meaning. (Prepared spells above store a u32 length instead.)
STRING_VIEW = RANGE


def prepared_spells(blob: NewAge, entity: int) -> tuple[str, ...]:
    """Spells and actions the character can use right now: prepared spells, class actions, and item-granted spells.

    The full spell book (``game.spell.v3.SpellBookComponent``) also lists every
    upcast variant and, for prepared casters, the whole class list, so the
    prepared list is the useful one.
    """
    raw = blob.by_entity("game.spell.v0.SpellBookPrepares").get(entity)
    if raw is None:
        return ()
    start, end = PREPARED_RANGE.unpack(raw)
    names = (blob.read_string(ptr, length) for ptr, length in blob.read_range(start, end, PREPARED_SPELL))
    return tuple(name for name in names if name not in BASIC_ACTIONS)


def tadpole_powers(blob: NewAge, entity: int) -> tuple[str, ...]:
    raw = blob.by_entity("game.tadpole_tree.v0.PowerContainerComponent").get(entity)
    if raw is None:
        return ()
    start, end = RANGE.unpack(raw)
    return tuple(blob.read_string(ptr, length) for ptr, length in blob.read_range(start, end, STRING_VIEW))
