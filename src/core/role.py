from enum import Enum
from pydantic import BaseModel

class RoleType(str, Enum):
    WEREWOLF = "werewolf"
    WITCH = "witch"
    SEER = "seer"
    HUNTER = "hunter"
    VILLAGER = "villager"

class Faction(str, Enum):
    GOOD = "good"
    WEREWOLF = "werewolf"

class Role(BaseModel):
    name: str
    type: RoleType
    faction: Faction

class Werewolf(Role):
    name: str = "狼人"
    type: RoleType = RoleType.WEREWOLF
    faction: Faction = Faction.WEREWOLF

class Witch(Role):
    name: str = "女巫"
    type: RoleType = RoleType.WITCH
    faction: Faction = Faction.GOOD
    has_antidote: bool = True
    has_poison: bool = True

class Seer(Role):
    name: str = "预言家"
    type: RoleType = RoleType.SEER
    faction: Faction = Faction.GOOD

class Hunter(Role):
    name: str = "猎人"
    type: RoleType = RoleType.HUNTER
    faction: Faction = Faction.GOOD
    can_shoot: bool = True

class Villager(Role):
    name: str = "平民"
    type: RoleType = RoleType.VILLAGER
    faction: Faction = Faction.GOOD
