from enum import Enum
from typing import Dict, List, Tuple, Type
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
    poison_used: bool = False

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

ROLE_REGISTRY: Dict[RoleType, Type[Role]] = {
    RoleType.WEREWOLF: Werewolf,
    RoleType.WITCH: Witch,
    RoleType.SEER: Seer,
    RoleType.HUNTER: Hunter,
    RoleType.VILLAGER: Villager,
}

def register_role(role_type: RoleType, role_class: Type[Role]) -> None:
    ROLE_REGISTRY[role_type] = role_class

def create_roles_from_counts(role_counts: Dict[str, int]) -> Tuple[List[Role], List[str]]:
    roles: List[Role] = []
    unknown_roles: List[str] = []
    for role_key, count in role_counts.items():
        if count <= 0:
            continue
        try:
            role_type = RoleType(role_key)
        except ValueError:
            unknown_roles.append(role_key)
            continue
        role_class = ROLE_REGISTRY.get(role_type)
        if not role_class:
            unknown_roles.append(role_key)
            continue
        roles.extend(role_class() for _ in range(count))
    return roles, unknown_roles
