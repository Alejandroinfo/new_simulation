from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DialogueOption:
    key: str
    question: str
    response: str
    clue_id: Optional[str] = None
    requires_bond: float = 0.0
    cost: int = 0
    asked: bool = False
    value_tier: int = 0   


from enum import Enum

class CaseType(Enum):
    SERIAL      = "serial"       # killer strikes repeatedly on a timer
    PASSION     = "passion"      # single murder, no more strikes; find killer before they flee
    CONSPIRACY  = "conspiracy"   # two people involved; both must be identified
    FRAME       = "frame"        # killer framed an innocent; must expose both

class RelKind(Enum):
    ALLY        = "ally"
    RIVAL       = "rival"
    DEBTOR      = "debtor"       # a owes b money
    LOVER       = "lover"
    FAMILY      = "family"
    COLLEAGUE   = "colleague"

@dataclass
class Relationship:
    id: str
    person_a_id: str
    person_a_name: str
    person_b_id: str
    person_b_name: str
    kind: RelKind
    known_to: list[str] = field(default_factory=list)  # who knows about this

@dataclass
class Secret:
    id: str
    holder_id: str
    about_id: str
    about_name: str
    description: str
    leverage: str

@dataclass
class Clue:
    id: str
    text: str
    attribute: str
    value: str
    found: bool = False
    source_name: str = ""
    day_available: int = 0
    scene_only: bool = False
    narrows_suspects: bool = True
    is_lie: bool = False


@dataclass
class Character:
    id: str
    name: str
    occupation: str
    district: str
    trait: str
    alive: bool = True
    bond: float = 0.0
    is_killer: bool = False
    is_accused: bool = False
    portrait: str = ""
    _requires_payment: bool = False

    def bond_label(self) -> str:
        if self.bond < 0.2: return "stranger"
        if self.bond < 0.5: return "acquaintance"
        if self.bond < 0.8: return "trusted"
        return "close ally"


@dataclass
class ScenarioResult:
    won: bool
    message: str
    days: int


@dataclass
class Lead:
    """A specific follow-up question unlocked by something someone said."""
    id: str
    target_id: str       
    source_id: str        
    source_name: str
    question: str       
    context: str          
    asked: bool = False

@dataclass
class ConfrontationClue:
    clue_id: str
    text: str
    attribute: str
    is_genuine: bool          
    pressure_delta: float     
    suspect_response: str     

@dataclass
class ConfrontationState:
    suspect_id: str
    pressure: float = 0.0      
    clues_presented: list[str] = field(default_factory=list)
    stage: str = "opening"      
    resolved: bool = False
    outcome: str = ""           

class Scenario:
    name: str = "Base"
    premise: str = ""
    actions: list[str] = []

    def step(self) -> list[str]:
        return []

    def check_end(self) -> Optional[ScenarioResult]:
        return None

    def get_dialogue(self, char_id: str) -> list[DialogueOption]:
        return []

    def handle_action(self, action: str, args: list[str]) -> str:
        return ""

    def status_lines(self) -> list[str]:
        return []

    def nearby_chars(self, location: str) -> list[Character]:
        return []
