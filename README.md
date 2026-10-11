# bg3-newage

Read a Baldur's Gate 3 party straight out of a save file: builds (ability scores, point-buy base scores, and every level-up choice: feats, racial bonuses, skills, expertise, spells learned, fighting styles and other passive picks), HP, approval, tadpole powers, prepared spells, equipped gear and carried items, for the party and for companions waiting at camp. Also the Traveller's Chest and camp state (days passed, supplies, recipes, waypoints).

Since Patch 4, most character state lives in the ECS "NewAge" blob inside `Globals.lsf`. LSLib can extract the blob but can't interpret it. This project decodes the parts needed for a party report and writes down what's been learned about the format, extending [Norbyte/lslib#127](https://github.com/Norbyte/lslib/issues/127).

It's read-only and was tested against a single Patch 8 (Hotfix 10) save. Expect field layouts to drift between patches.

```
$ bg3-newage party data/QuickSave_128 --game-data data/shared
SCL_Main_A  (DifficultyMedium / RulesetLarian)

--- Party ---
...
== Shadowheart  (XP 34074, HP 59/59, approval 94)
   STR 11  DEX 14  CON 14  INT 8  WIS 18  CHA 12  prof +3
   point buy: STR 10  DEX 14  CON 13  INT 8  WIS 15  CHA 12
   L1 Cleric  subclass: TempestDomain  racial bonus: WIS +2, STR +1  skills: Medicine, History  spells: ...
   L4 Cleric  feat: AbilityScoreIncrease  ability increase: WIS +1, CON +1  spells: Target_BurstingSinew
   L8 Cleric  feat: ElementalAdept  passives: ElementalAdept_Thunder
   classes: Cleric 8
   tadpole powers: TAD_IllithidPersuasion, TAD_PeaceBreaker, TAD_LuckOfTheFarRealms
   [Helmet] UNI_DarkJusticiar_Helmet
   [Body] UNI_DarkJusticiarArmor_HalfPlate
   ...
   carrying 33: ClericEquipmentAct2_Staff_of_Resurrection, UND_Wand_Fireballs_Crooked, ...
```

## Usage

You need Python 3.12+ with [uv](https://docs.astral.sh/uv/), and the .NET 8 SDK for the LSLib wrapper. Put every save and extracted file under `data/`, which is gitignored.

1. **Build the LSLib wrapper.** Download an [LSLib release](https://github.com/Norbyte/lslib/releases) (ExportTool) and unzip it into `vendor/ExportTool/`, so that `vendor/ExportTool/Packed/Tools/LSLib.dll` exists. Alternatively, point `-p:LSLibDir=` at any directory holding `LSLib.dll`. Then run:

   ```sh
   dotnet build tools/lsltool -c Release
   ```

   The wrapper exists because Divine's CLI rejects absolute paths on Linux.

2. **Extract a save and convert `Globals.lsf`.** Saves live under `.../Larian Studios/Baldur's Gate 3/PlayerProfiles/Public/Savegames/Story/`; on a Steam Deck that's in `~/.local/share/`.

   ```sh
   LSL=tools/lsltool/bin/Release/net8.0/lsltool.dll
   dotnet $LSL extract AutoSave_86.lsv data/AutoSave_86
   dotnet $LSL lsf2lsx data/AutoSave_86/Globals.lsf data/AutoSave_86/Globals.lsx
   ```

3. **Extract the game's own `Data/Shared.pak`** the same way. `party` uses it for class and feat names (without it they show as GUID prefixes), and `camp-chest` needs it to recognise the chest. `spells` and `camp` don't need it.

   ```sh
   dotnet $LSL extract "<game>/Data/Shared.pak" data/shared
   ```

4. **Run the tool.**

   ```sh
   uv tool install -e .
   bg3-newage party data/AutoSave_86 --game-data data/shared [--json]
   bg3-newage camp-chest data/AutoSave_86 --game-data data/shared [--json]   # Traveller's Chest contents
   bg3-newage spells data/AutoSave_86 [--json]       # prepared spells, class actions, item spells
   bg3-newage camp data/AutoSave_86 [--json]         # days passed, supplies, recipes, waypoints
   bg3-newage components data/AutoSave_86 --grep inventory   # explore the blob
   ```

Party members get their names by matching total XP against the save's `SaveInfo.json`, because the blob has no direct link between the two. Anyone that doesn't match (camp companions, or two members with the same XP) is named from the story database in `StorySave.bin` instead: its strings are XOR-scrambled with `0xAD`, and story constants such as `S_Player_Astarion_<guid>` pair a name with the character's root template, which the `Characters` region of `Globals.lsx` links to the entity. Characters with no story name (a custom Tav) are labelled `entity N`.

The repo contains no save or game data. The tests build synthetic blobs instead (`tests/builder.py`). To run them: `uv sync && uv run pytest`.

## Format notes

All offsets are relative to the end of the 48-byte LSMF header (`BASE_OFFSET`).

**Header and component table.** The header holds `magic "LSMF", u32 version, u64 hash, u64 blockOffset, u64 blockSize, u32 nameBlockSize, u16 componentCount, u16, u64`. Component names are a packed string block at `blockOffset`. The table that follows it has one 48-byte entry per component: `u64 nameOffset, u64 nameSize, u64 hash, u32 elementSize, u32 version, u64 elementCount, u64 dataOffset`. This matches [LennardF1989/BG3-ImHex-Patterns](https://github.com/LennardF1989/BG3-ImHex-Patterns).

**Entities and owner maps.** Component 0, `core.v0.Level`, is `u64 entitiesStart, entitiesEnd, ownerMapsStart, ownerMapsEnd`. Entities are 16-byte GUIDs. Each owner map is `u64 indicesStart, indicesEnd, componentIndex, count`, pointing at `u32` entity indices (an empty map stores `0xFFFFFFFFFFFFFFFF` as its offset): element `k` of that component belongs to entity `indices[k]`. Components without an owner map are side tables that other components point into.

**Entity references.** Cross-entity references (inventory → owner, item → wielder, and so on) are `u64` offsets into the element array of `core.v0.EntityId`. Its elements are entity GUIDs, so you resolve a reference by reading 16 bytes at that offset and looking the GUID up in the Level's entity list.

**GUID encoding.** The first 8 bytes use the Microsoft/`uuid.bytes_le` layout, where the first three groups are byte-reversed. The last 8 bytes are swapped pairwise. For example, `e3c5f9c9-40c1-c67d-e89a-706431974622` is stored as `c9f9c5e3 c140 7dc6 9ae8 6470 9731 2246`. This holds for entity IDs as well as class, feat, and origin references. With that encoding, Creator `Entity` GUIDs in `Globals.lsx` match the blob byte for byte (see `guids.py`).

**Decoded components:**

| Component | Size | Layout |
|---|---|---|
| `game.stats.v3.StatsComponent` | 36 | 8 unknown bytes, `i32` STR DEX CON INT WIS CHA, `i32` proficiency bonus |
| `game.experience.v0.ExperienceComponent` | 12 | `i32` total XP (twice), 4 unknown bytes. Matches `SaveInfo.json`, which is how party members get names |
| `game.progression.v3.LevelUpComponent` | 16 | `u64 start, end`: a range of `u64` pointers, one per character level, each to a 96-byte `LevelUpComponentData` record |
| `game.character_creation.v3.LevelUpComponentData` | 96 | class GUID, subclass GUID (null unless chosen at that level), feat GUID (null unless chosen), 16 unknown bytes, `u64` pointer to a 16-byte abilities record (all zero in practice), `u64` pointer to a `LevelUpComponentSelectors` record (all ones if none), an unknown range |
| `game.character_creation.v2.LevelUpComponentSelectors` | 112 | seven `u64 start, end` ranges of selector pointers, in order: ability increase (`AbilitySelector`), racial bonus (`AbilityBonusSelector`), skills (`SkillSelector`), expertise (`SkillExpertiseSelector`), spells (`SpellSelector`), passives (`PassiveSelector`), equipment (`EquipmentSelector`) |
| `game.character_creation.v2.*Selector` | 40–56 | each starts `u64` metadata pointer, 16-byte list GUID, `u64 start, end` of picks. `AbilityBonusSelector` adds a range of `i32` amounts (+2, +1), one per pick. `SpellSelector` and `PassiveSelector` add a range that is usually empty (for spells, probably replaced spells; not decoded). `SkillExpertiseSelector` adds 8 unknown bytes |
| `AbilityAddSlot`, `SkillAddSlot` | 8 | pointer to an element of the `EAbility`/`ESkill` enum table, whose `i64` is the game's ID (abilities 1–6 = STR…CHA; skills 0 Deception … 17 Survival) |
| `StringViewAddSlot` | 16 | name string view (pointer, `u32` length), 4 unknown bytes: spell, passive (e.g. `ElementalAdept_Thunder`, `FightingStyle_Protection`) or equipment names |
| `game.character_creation.v1.CharacterCreationStatsComponent` | 88 | 72 unknown bytes (starting with two GUIDs), then `u64 start, end` of `i32` point-buy increments over 8, indexed by ability ID (index 0 unused) |
| `game.passives.v0.ToggledPassivesComponent` | 32 | not shown by the tool: a range of passive name string views and a range of matching `u8` on/off flags. Only switchable passives (Non-Lethal Attacks, Uncanny Dodge) appear; passives a character simply has aren't stored |
| `game.inventory.v0.MemberComponent` | 8 | pointer to a 16-byte `MemberData`: entity ref to the containing inventory, `i16` slot, 6 unknown bytes |
| `game.inventory.v0.WieldingComponent` | 8 | entity ref to the character wielding (equipping) the item. The `MemberData` slot is then the equipment slot: 0 helmet, 1 body, 2 cloak, 3/4 melee main/off hand, 5/6 ranged main/off hand, 7 ring, 8 underwear, 9 boots, 10 gloves, 11 amulet, 12 ring 2, 13 wings, 14 horns, 15 overhead, 16 instrument, 17/18 camp clothes |
| `game.inventory.v1.IsOwnedComponent` | 8 | on an inventory entity: entity ref to its owner |
| `game.v0.PlayerComponent` | 1 | marks the active party |
| `game.camp.v1.PresenceComponent` | 1 | marks characters at camp, camp NPCs included |
| `game.recruit.v0.RecruitedByComponent` | 8 | entity ref to the recruiter; present at camp and recruited = a companion waiting there |
| `game.avatar.v0.AvatarComponent` | 16 | marks the player's own character (contents unread) |
| `game.stats.v0.HealthComponent` | 32 | `i32` current HP, `i32` max HP, 24 unknown bytes |
| `game.approval.v0.Ratings` | 48 | on a companion: `u64 start, end` of entity refs, `u64 start, end` of matching `i32` ratings (the companion's approval of each), then a range of 16-byte GUIDs (unidentified). The report shows the rating of the avatar |
| `game.spell.v0.SpellBookPrepares` | 80 | `u64 start, end` of 24-byte prepared spells (name string view, 12 unknown bytes), 64 unknown bytes |
| `game.tadpole_tree.v0.PowerContainerComponent` | 16 | `u64 start, end` of 16-byte power name string views |
| `game.calendar.v0.DaysPassedComponent`, `game.camp.v0.TotalSuppliesComponent` | 4 | singletons: `i32` |
| `game.party.v1.RecipesComponent` | 16 | `u64 start, end` of 24-byte recipes: name string view, 8 unknown bytes |
| `game.party.v0.WaypointsComponent` | 16 | `u64 start, end` of 48-byte waypoints: name string view, GUID, level name string view |

**Strings.** Spell, power, recipe, and waypoint names are stored as text, not GUIDs: a string view is a `u64` pointer into a shared string block plus a length (`u32` or `u64`, depending on the record). An empty range stores `0xFFFFFFFFFFFFFFFF` as its start, like an empty owner map.

Item stats names (for example `WPN_Longsword_1`) and current templates come from the `Items` region of `Globals.lsx`, whose `Creator`/`Item` nodes pair entity GUIDs with `Stats` and `CurrentTemplate` in matching order. Story items (letters, keys, quest objects) share generic stats names like `OBJ_Scroll` or `PUZ_Key`, but their `CurrentTemplate` is a save-local template in the `CacheTemplates` region whose `Name` (such as `S_MOO_NightsongLetter`) is shown instead.

**Bags and the camp chest.** A bag works like any other container: its inventory's `IsOwnedComponent` references the bag item, so following owners recursively reaches bag contents. The Traveller's Chest is the item whose `CurrentTemplate` is listed in `Public/Shared*/Lists/CampChestTemplates.lsx`. In the save, its stats name is just `OBJ_ImmutableContainer`.

**Not decoded yet:** the full spell book (`game.spell.v3.SpellBookComponent`, 72-byte records whose first field points at a spell-name record), spells replaced at level-up (the extra range in `SpellSelector`), and the unknown bytes listed above. `StatsComponent` scores seem to include item bonuses: on the reference save, point buy plus racial bonus plus ASI matches every character except one whose Strength is 2 higher, most likely from gear (unconfirmed).
