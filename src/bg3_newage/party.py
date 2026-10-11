"""Decode the builds of the party and of recruited companions waiting at camp.

Component layouts below were reversed against a Patch 8 save. Only the fields
this module reads are known; the rest of each record is still unidentified.
"""

import struct
from dataclasses import dataclass

from bg3_newage.gamedata import GameData
from bg3_newage.inventory import Inventories, Item
from bg3_newage.levelup import ABILITIES, LevelUp, read_level_ups, read_point_buy
from bg3_newage.lsmf import I32, U64, NewAge
from bg3_newage.save import Save, SaveInfoMember
from bg3_newage.spells import prepared_spells, tadpole_powers

# game.stats.v3.StatsComponent: 8 unknown bytes, six i32 ability scores (STR..CHA), i32 proficiency bonus
STATS = struct.Struct("<8x6ii")
# game.experience.v0.ExperienceComponent: i32 total XP (repeated), 4 unknown bytes
EXPERIENCE = struct.Struct("<i8x")
# game.stats.v0.HealthComponent: i32 current HP, i32 max HP, 24 unknown bytes
HEALTH = struct.Struct("<ii24x")
# game.approval.v0.Ratings: [start, end) of u64 entity refs (whose approval), [start, end) of matching i32 ratings,
# then a [start, end) range of 16-byte GUIDs, unidentified
APPROVAL = struct.Struct("<QQQQ16x")


@dataclass(frozen=True)
class PartyMember:
    """A character on the roster: someone in the active party, or a recruited companion waiting at camp."""

    entity: int
    name: str
    in_party: bool  # False for a recruited companion waiting at camp
    total_xp: int | None
    hp: int | None
    max_hp: int | None
    approval: int | None  # of the player's avatar; None for the avatar itself
    abilities: dict[str, int]
    point_buy: dict[str, int]  # base scores bought at character creation
    proficiency: int | None
    level_ups: tuple[LevelUp, ...]
    equipped: tuple[Item, ...]
    carried: tuple[str, ...]
    tadpole_powers: tuple[str, ...]
    prepared_spells: tuple[str, ...]


def read_party(save: Save, game: GameData) -> list[PartyMember]:
    """The active party, then recruited companions who are at camp."""
    blob = save.newage
    inventories = Inventories.from_save(save)
    stats = blob.by_entity("game.stats.v3.StatsComponent")
    xp = blob.by_entity("game.experience.v0.ExperienceComponent")
    health = blob.by_entity("game.stats.v0.HealthComponent")
    approvals = read_approvals(blob)
    party = sorted(blob.by_entity("game.v0.PlayerComponent"))
    members = []
    for entity in party + camp_companions(blob, party):
        total_xp = EXPERIENCE.unpack(xp[entity])[0] if entity in xp else None
        scores, proficiency = decode_stats(stats.get(entity))
        hp, max_hp = HEALTH.unpack(health[entity]) if entity in health else (None, None)
        holdings = inventories.holdings(entity)
        in_party = entity in party
        # SaveInfo.json lists only the active party, so its XP join must not name anyone at camp
        save_info_name = name_from_save_info(save.members, total_xp) if in_party else None
        members.append(
            PartyMember(
                entity=entity,
                name=save_info_name or save.character_names.get(entity) or f"entity {entity}",
                in_party=in_party,
                total_xp=total_xp,
                hp=hp,
                max_hp=max_hp,
                approval=approvals.get(entity),
                abilities=scores,
                point_buy=read_point_buy(blob, entity),
                proficiency=proficiency,
                level_ups=read_level_ups(blob, entity, game),
                equipped=holdings.equipped,
                carried=holdings.carried,
                tadpole_powers=tadpole_powers(blob, entity),
                prepared_spells=prepared_spells(blob, entity),
            )
        )
    return members


def camp_companions(blob: NewAge, party: list[int]) -> list[int]:
    """Recruited characters present at camp but not in the party.

    Camp presence alone also matches camp NPCs (Withers, the dog), so the
    character must also have been recruited.
    """
    at_camp = blob.by_entity("game.camp.v1.PresenceComponent").keys()
    recruited = blob.by_entity("game.recruit.v0.RecruitedByComponent").keys()
    return sorted((at_camp & recruited) - set(party))


def read_approvals(blob: NewAge) -> dict[int, int]:
    """Companion entity -> approval of the player's avatar. Companions who have left have no ratings."""
    avatars = blob.by_entity("game.avatar.v0.AvatarComponent").keys()
    approvals = {}
    for companion, raw in blob.by_entity("game.approval.v0.Ratings").items():
        refs_start, refs_end, ratings_start, ratings_end = APPROVAL.unpack(raw)
        refs = blob.read_range(refs_start, refs_end, U64)
        ratings = blob.read_range(ratings_start, ratings_end, I32)
        for (ref,), (rating,) in zip(refs, ratings, strict=True):
            if blob.resolve_ref(ref) in avatars:
                approvals[companion] = rating
                break
    return approvals


def name_from_save_info(members: tuple[SaveInfoMember, ...], total_xp: int | None) -> str | None:
    """SaveInfo.json names the party by origin but has no entity link, so total XP is the join key.

    Returns None when the XP is missing or shared by several members, rather than guessing.
    """
    if total_xp is None:
        return None
    matches = [m.origin for m in members if m.total_xp == total_xp]
    return matches[0] if len(matches) == 1 else None


def decode_stats(raw: bytes | None) -> tuple[dict[str, int], int | None]:
    if raw is None or len(raw) < STATS.size:
        return {}, None
    *scores, proficiency = STATS.unpack_from(raw)
    return dict(zip(ABILITIES, scores, strict=True)), proficiency
