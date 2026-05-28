"""scenarios/murderer.py — The Murderer scenario (v9)."""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Optional
from scenarios.base import (Scenario, Character, Clue, DialogueOption, ScenarioResult,
                             Secret, CaseType, RelKind, Relationship,
                             ConfrontationState, ConfrontationClue, Lead)

SERIAL=CaseType.SERIAL; PASSION=CaseType.PASSION
CONSPIRACY=CaseType.CONSPIRACY; FRAME=CaseType.FRAME
LOVER=RelKind.LOVER; RIVAL=RelKind.RIVAL; DEBTOR=RelKind.DEBTOR

"""
state.py — MurdererState dataclass and game constants.

MurdererState: full serializable game state
DIFFICULTY_TABLE: parameters per difficulty level
WEAPON_BY_OCCUPATION: murder weapon per killer occupation
Helper functions: timing, formatting, difficulty scaling
"""

@dataclass
class MurdererState:
    killer_id: str
    killer_occupation: str
    killer_district: str
    killer_trait: str
    killer_motive: str
    killer_method: str
    victims: list[str] = field(default_factory=list)
    clues_found: list[str] = field(default_factory=list)
    hour: float = 6.0
    day: int = 1
    next_strike_hour: float = 36.0
    accusation_count: int = 0
    max_victims: int = 3
    player_location: str = "market"
    accused_wrong: list[str] = field(default_factory=list)
    protected_this_period: Optional[str] = None
    protected_history: list[str] = field(default_factory=list)
    crime_scenes: list[str] = field(default_factory=list)
    scene_examined: list[str] = field(default_factory=list)
    gossip: dict = field(default_factory=dict)
    gossip_updated_hour: float = -1.0
    money: float = 100.0
    secrets_known: list[str] = field(default_factory=list)
    questions_asked_this_period: dict = field(default_factory=dict)
    questions_period_start: float = 6.0
    lies_planted: list[str] = field(default_factory=list)
    difficulty: int = 5
    action_log: list[dict] = field(default_factory=list)
    leads: list[dict] = field(default_factory=list)
    known_chars: list[str] = field(default_factory=list)
    weapon_found: str = ""
    weapon_locations: dict = field(default_factory=dict)
    conversation_count: dict = field(default_factory=dict)
    killer_agenda: list[dict] = field(default_factory=list)
    agenda_revealed: list[int] = field(default_factory=list)
    district_closed: dict = field(default_factory=dict)
    accused_wrong_reaction: dict = field(default_factory=dict)
    world_reactions: list[str] = field(default_factory=list)
    seed_used: int = 0
    follow_results: dict = field(default_factory=dict)
    alibi_checks: dict = field(default_factory=dict)
    searched_locations: list[str] = field(default_factory=list)
    case_type: str = "serial"
    accomplice_id: Optional[str] = None
    framed_id: Optional[str] = None
    accomplice_found: bool = False
    killer_fleeing: bool = False
    flee_hour: float = 999.0
    killer_heat: float = 0.0
    heat_actions: list[str] = field(default_factory=list)
    corrupted_clues: list[str] = field(default_factory=list)
    pending_heat_actions: list[str] = field(default_factory=list)
    next_period_hour: float = 8.0

DIFFICULTY_TABLE = {
    range(1,  5):  (12, 8, 150, 4, 0, 0.0),
    range(5,  9):  (10, 6, 100, 3, 0, 0.1),
    range(9,  13): ( 8, 5,  70, 3, 1, 0.2),
    range(13, 17): ( 7, 4,  40, 2, 2, 0.4),
    range(17, 21): ( 6, 3,  20, 2, 3, 0.6),
}

def _difficulty_params(level: int) -> tuple:
    for r, params in DIFFICULTY_TABLE.items():
        if level in r:
            return params
    return (10, 6, 100, 3, 0, 0.1)

SECRET_TEMPLATES = [
    ("{a} is having an affair with {b}.",         "affair",    "{a} is hiding a relationship with {b}."),
    ("{a} owes {b} a significant gambling debt.", "debt",      "{a} is indebted to {b} and desperate."),
    ("{a} was stealing from {b}'s store.",        "theft",     "{a} was caught stealing from {b}."),
    ("{a} forged documents for {b}.",             "forgery",   "{a} provided false papers to {b}."),
    ("{a} witnessed {b} commit a minor crime.",   "witness",   "{a} knows something damaging about {b}."),
    ("{a} was bribing {b} for favors.",           "bribery",   "{a} paid {b} to look the other way."),
]

LYING_CLUE_OVERRIDES = {
    "district_seen":   "{killer_district} becomes a neighboring district",
    "occupation_direct": "occupation becomes a common wrong one",
}

CONCRETE_CLUES = {
    "district_seen": (
        "district",
        "A neighbor reported seeing a figure leave {district} district "
        "in the early hours. They were heading away from the scene.",
    ),
    "occupation_direct": (
        "occupation",
        "Marks on the body are consistent with someone who handles "
        "{occupation} tools daily. The coroner was specific about this.",
    ),
    "trait_behavior": (
        "trait",
        "Three people who saw the killer briefly describe the same thing: "
        "{trait_desc}. Ask around — someone matches that description.",
    ),
    "alibi_break": (
        "occupation",
        "The {occupation}'s guild has a log. Someone with that trade "
        "cannot account for two hours the night of the murder.",
    ),
    "district_seen2": (
        "district",
        "The victim was last seen alive walking toward {district} district. "
        "Whoever met them there knew the area.",
    ),
    "victim_connection": (
        "district",
        "Records show the victim filed a complaint against someone in "
        "{district} district six weeks ago. It was never resolved.",
    ),
    "method_occ": (
        "occupation",
        "The method used requires strength and familiarity with blunt "
        "objects — or a blade, or poison. Someone with {occupation} "
        "training would know exactly how.",
    ),
}

TRAIT_DESCRIPTIONS = {
    "aggressive":   "aggressive, forceful — someone who doesn't hold back",
    "selfish":      "cold, calculating, indifferent to anyone watching",
    "cautious":     "methodical, unhurried — left almost nothing behind",
    "innovative":   "something about the scene felt staged, almost theatrical",
    "loyal":        "acted like someone who knew the victim personally",
    "charismatic":  "confident enough that the victim apparently trusted them",
}

FEAR_RESPONSES = {
    "aggressive": [
        "Whoever did this better hope the town finds them before I do.",
        "I'm not scared. I'm angry. There's a difference.",
        "I've started keeping my door locked and a tool nearby. Just in case.",
        "People keep asking me if I'm worried. No. I'm watching.",
    ],
    "selfish": [
        "I'm making sure my own doors are locked. Beyond that, not my concern.",
        "I keep my head down. This doesn't have to touch me if I'm careful.",
        "Tragic, yes. But I have my own situation to worry about.",
        "I'm not going to pretend I knew them well. I didn't. I'm fine.",
    ],
    "cautious": [
        "I've changed my routine. Different times, different paths. Safer that way.",
        "I observe a lot more than people realize. I've been paying attention.",
        "There's a pattern here. I feel it. I just can't quite name it yet.",
        "I don't go out after dark anymore. Neither should you.",
    ],
    "loyal": [
        "I'm more worried for my neighbors than myself. We have to watch each other.",
        "This community is shaken. We need to stay together or it gets worse.",
        "I've been checking on people. Making sure no one's alone at night.",
        "Someone in this town knows something and is staying quiet. That bothers me.",
    ],
    "charismatic": [
        "I've been talking to people. Everyone's scared but nobody's sharing.",
        "There are rumors. I hear things. People come to me.",
        "The mood has shifted completely. You can feel it the moment you walk in.",
        "Nobody wants to say it out loud but everyone's looking at everyone differently.",
    ],
    "innovative": [
        "I've been thinking about the timing, the location, the pattern. Something's off.",
        "If I were the killer, I'd be watching the investigation right now.",
        "The obvious answer is rarely the right one. I'd look harder at the details.",
        "There's something deliberate about how this is unfolding. Too clean.",
    ],
    "default": [
        "People are scared. You can feel it everywhere.",
        "I keep to myself. I don't know what else to do.",
        "It's the uncertainty that gets you. Not knowing who, not knowing why.",
        "I've been sleeping badly. I think most people have.",
    ],
}

GENERAL_RESPONSES = {
    "aggressive": [
        "I notice everything. People come to me when they want the truth.",
        "I don't look away from things that make others uncomfortable.",
        "I've been watching who's been acting differently. Several people.",
    ],
    "selfish": [
        "I only know what directly affects me. And this is starting to.",
        "I make it a point not to get involved in other people's business.",
        "I've heard things. Whether they're relevant to you is another matter.",
    ],
    "cautious": [
        "I've been keeping notes. Dates, times, who I saw where.",
        "I observe before I speak. There's a difference between guessing and knowing.",
        "Give me a moment. I want to tell you exactly what I saw, not approximately.",
    ],
    "loyal": [
        "I know almost everyone in this town. I've been watching for changes.",
        "People confide in me. I won't share everything, but I'll tell you what I can.",
        "There's a thread connecting things here. I can feel it even if I can't name it.",
    ],
    "charismatic": [
        "People tell me things they wouldn't tell others. Comes with the territory.",
        "I've been quietly listening to everyone. You'd be surprised what comes out.",
        "There are at least three people in this town with something to hide.",
    ],
    "innovative": [
        "I've been drawing a map of who interacted with the victim in the last week.",
        "I'm looking at this differently than most. The answer isn't where people think.",
        "What if the obvious suspect is meant to be obvious?",
    ],
    "default": [
        "I keep to myself mostly. But I notice things.",
        "I don't have much to add, but I'll tell you what I know.",
        "I've been trying to make sense of it. I haven't gotten far.",
    ],
}

VICTIM_RESPONSES = {
    "aggressive": [
        "{victim} didn't deserve it, but they weren't careful. That's the honest truth.",
        "I knew {victim} well enough. They had enemies. You should dig there.",
        "{victim} was involved in things. I don't know how deep.",
    ],
    "selfish": [
        "{victim} wasn't someone I knew well. Our paths crossed occasionally.",
        "Sad, yes. But I don't know enough about {victim} to be useful to you.",
        "{victim} kept to themselves mostly. I can't tell you much.",
    ],
    "cautious": [
        "{victim} was methodical, careful. Whoever got to them had to plan ahead.",
        "I think about {victim} differently since this happened. Trying to see what I missed.",
        "I saw {victim} the day before. Nothing unusual. That's what makes it hard.",
    ],
    "loyal": [
        "{victim} was part of this community. They mattered to people here.",
        "I've been thinking about {victim} every day. They had people who cared about them.",
        "{victim} trusted people easily. Maybe too easily.",
    ],
    "charismatic": [
        "I knew {victim} — not deeply, but enough. They had a life here, connections.",
        "Something about {victim} drew people in. That may be relevant.",
        "{victim} knew things about people in this town. Whether that matters, I don't know.",
    ],
    "innovative": [
        "The choice of {victim} was not random. That's what I keep thinking.",
        "{victim} had something — information, access, a relationship — that made them a target.",
        "Why {victim}? That's the question. The answer leads somewhere interesting.",
    ],
    "default": [
        "{victim} seemed fine. Nobody expected this.",
        "I didn't know {victim} that well. I wish I did.",
        "{victim} was just a person trying to get by. Like all of us.",
    ],
}

GOSSIP_BY_CONTEXT = {
    "morning": [
        "I couldn't sleep. I heard things outside that probably were nothing.",
        "People are gathering in small groups and going quiet when you approach.",
        "Someone knocked on my door before dawn. Wrong house, they said. Felt strange.",
    ],
    "afternoon": [
        "Three separate people asked me if I'd locked my doors last night.",
        "The market is quieter than usual. People aren't stopping to talk.",
        "I overheard two people arguing about who they think did it. Both wrong, probably.",
    ],
    "evening": [
        "People are going home earlier. The streets empty faster than before.",
        "Someone told me to stay inside tonight. They wouldn't say why.",
        "The tavern is quieter than it should be. People are drinking but not talking.",
    ],
    "night": [
        "I saw a light in a window that's usually dark. Late. Very late.",
        "There are sounds at night now that I didn't notice before. Or I wasn't listening.",
        "Someone is moving around after dark. I can't say who. I can't see well enough.",
    ],
    "second_victim": [
        "Two now. Everyone's running through the list of who they think is next.",
        "People are pairing up, not walking alone. Even in daylight.",
        "After the second one, people stopped saying it might be an accident.",
    ],
    "district_neighbor": [
        "I've lived here long enough to know when something's off. Something's off.",
        "There's someone in this district I've been watching. Different since it happened.",
        "I don't want to say a name without proof. But there's a name I keep coming back to.",
    ],
}

CASE_OPENERS = {
    "serial": [
        "You arrive in {town} to find it holding its breath.",
        "The town of {town} sent for you after the first murder.",
        "A letter reached you three days ago. {town} needed someone from outside.",
        "{town} hired you. The locals are too close to it. Too scared.",
        "You've worked cases like this before. {town} is hoping you'll recognize the pattern.",
    ],
    "passion": [
        "A body, a clear motive, a suspect who hasn't run — yet.",
        "{town} had one murder. But the killer is still here, for now.",
        "One crime. One night. The question is whether you find them before they leave.",
        "They said it looked personal. You're inclined to agree.",
        "The violence was specific. Targeted. This was about something.",
    ],
    "conspiracy": [
        "The murder was too clean for one person. Someone helped.",
        "{town} has a problem: two people are responsible and only one has been seen.",
        "Every witness says the same thing slightly differently. That's not coincidence.",
        "There's a pattern here that suggests coordination. Find both of them.",
        "One person killed. Another enabled it. {town} needs you to find both.",
    ],
    "frame": [
        "The evidence pointed somewhere so clearly it made you suspicious.",
        "{town} has an obvious suspect and an obvious answer. You're here to check if it's right.",
        "Someone's been set up. You don't know who yet. But the evidence feels arranged.",
        "The scene was too neat. The real work hasn't started yet.",
        "You've seen planted evidence before. Something here feels familiar.",
    ],
}

ACTION_HOURS = {
    "talk_question": 1.0,
    "move":          0.5,
    "examine_scene": 1.5,
    "protect":       3.0,
    "blackmail":     1.0,
    "accuse":        0.0,
}

QUESTION_PERIOD = 8.0

def _strike_hours(difficulty: int) -> float:
    if difficulty <= 4:  return 72.0
    if difficulty <= 8:  return 54.0
    if difficulty <= 12: return 42.0
    if difficulty <= 16: return 30.0
    return 20.0

def _questions_per_period(difficulty: int) -> int:
    if difficulty <= 4:  return 3
    if difficulty <= 8:  return 2
    if difficulty <= 14: return 2
    return 1

def _questions_per_day(difficulty: int) -> int:
    return _questions_per_period(difficulty)

def _payment_cost(difficulty: int) -> int:
    if difficulty <= 4:  return 10
    if difficulty <= 8:  return 15
    if difficulty <= 12: return 20
    if difficulty <= 16: return 30
    return 40

def rng_choice_seed(pool: list, seed: int):
    """Deterministic choice from a pool using a seed."""
    return pool[abs(seed) % len(pool)] if pool else ""

def _format_time(hour: float) -> str:
    """Format a float hour as Day N HH:MM."""
    day  = int(hour // 24) + 1
    h    = int(hour % 24)
    m    = int((hour % 1) * 60)
    return f"Day {day}  {h:02d}:{m:02d}"

def _is_night(hour: float) -> bool:
    h = hour % 24
    return h >= 21 or h < 5

WEAPON_BY_OCCUPATION = {
    "miner":    ("pickaxe",      "A heavy pickaxe head with an unusually sharp edge, found under loose floorboards."),
    "farmer":   ("scythe blade", "A curved scythe blade, recently cleaned but still faintly stained."),
    "merchant": ("ledger spike",  "A heavy iron spike used to pin invoices, missing from one shop."),
    "craftsman":("chisel",        "A woodworking chisel, wrapped in cloth, hidden beneath a workbench."),
    "healer":   ("lancet",        "A surgical lancet, ground to a finer edge than any medical use requires."),
    "priest":   ("candlestick",   "A heavy brass candlestick, its base reshaped into something more purposeful."),
    "soldier":  ("knife",         "A military knife, its serial filed off, wrapped in oilcloth."),
    "scholar":  ("letter opener", "A brass letter opener sharpened on both edges, found in a hidden compartment."),
    "teacher":  ("ruler",         "A metal ruler with one edge honed to a blade, hidden in a stack of papers."),
    "guard":    ("baton",         "A weighted lead baton, not standard issue, wrapped in leather."),
}
DEFAULT_WEAPON = ("blunt object", "An improvised weapon — heavy and common, left where it might not be noticed.")

"""text_pools.py — Static text data for The Murderer scenario."""

FIRST_NAMES = [
    "Aldric","Brynn","Cara","Dante","Elena","Finn","Gemma","Hadwin","Iris","Jasper",
    "Kira","Leon","Mira","Nolan","Opal","Pierce","Quinn","Rosa","Silas","Tara",
    "Una","Victor","Wren","Asha","Brennan","Cleo","Elio","Fiona","Gareth","Hana",
    "Ivan","Jade","Luna","Marc","Nadia","Owen","Petra","Remy","Sage","Theo",
]
LAST_NAMES = [
    "Ashford","Blackwood","Crane","Dusk","Ember","Frost","Gale","Hawke","Irwin",
    "Jarrow","Kael","Lorne","Merrow","Nash","Oldham","Pike","Quill","Raven","Stone","Thorn","Vale",
]
OCCUPATIONS = ["miner","craftsman","merchant","soldier","doctor","teacher","farmer","priest"]
DISTRICTS    = ["farming","market","civic","military","healing","slums"]
TRAITS       = ["aggressive","selfish","cautious","innovative","loyal","charismatic"]
MOTIVES      = ["jealousy","revenge","greed","fear","obsession","desperation"]
METHODS      = ["blunt_force","sharp_blade","poison","strangulation"]

METHOD_DESC = {
    "blunt_force":   "blunt force trauma",
    "sharp_blade":   "a sharp instrument",
    "poison":        "an unknown substance",
    "strangulation": "strangulation",
}
METHOD_CLUE = {
    "blunt_force":   ["miner","craftsman","soldier","farmer"],
    "sharp_blade":   ["soldier","craftsman","doctor","merchant"],
    "poison":        ["doctor","farmer","priest"],
    "strangulation": ["soldier","craftsman","miner"],
}
TRAIT_CLUE = {
    "aggressive":  "witnesses describe an intense, forceful presence",
    "selfish":     "the killings seem calculated, removing personal obstacles",
    "cautious":    "the killer leaves almost no trace — methodical and careful",
    "innovative":  "each crime scene has something unusual about it",
    "loyal":       "the pattern suggests the killer only targets outsiders to a group",
    "charismatic": "victims apparently trusted whoever approached them",
}
MOTIVE_CLUE = {
    "jealousy":     "victims share something enviable — wealth, status, or affection",
    "revenge":      "the victims are connected by a past event",
    "greed":        "each victim had something of value that later disappeared",
    "fear":         "the victims seem to have known something dangerous",
    "obsession":    "the killer returns to the scene — something personal drives them",
    "desperation":  "the crimes escalate in frequency — someone running out of time",
}

TRAIT_RESPONSES = {
    "aggressive": {
        "fear":    "Whoever's behind this better hope the town finds them before I do.",
        "general": "I don't have time for fear. I'm watching my own back.",
        "victim":  "They were weak. This town rewards weakness with death. Ugly truth.",
    },
    "selfish": {
        "fear":    "I'm making sure my doors are locked. Beyond that, not my problem.",
        "general": "I keep my head down. This doesn't have to touch me if I'm careful.",
        "victim":  "Sad, yes. But they weren't careful. I'm being careful.",
    },
    "cautious": {
        "fear":    "I've changed my routine. Different times, different routes. Can't be too safe.",
        "general": "I observe a lot. More than people realize.",
        "victim":  "I noticed things about them. Patterns. I should have said something sooner.",
    },
    "loyal": {
        "fear":    "I'm worried for my neighbors more than myself. We have to look out for each other.",
        "general": "This community is shaken. We need to stay together.",
        "victim":  "They were part of this town. One of us. We owe them the truth.",
    },
    "charismatic": {
        "fear":    "I've been talking to people. Everyone's scared but nobody's sharing what they know.",
        "general": "There are rumors. I hear things. People talk to me.",
        "victim":  "I knew them. Not well, but well enough. This hits differently when it's someone you've spoken to.",
    },
    "innovative": {
        "fear":    "I've been thinking about patterns. The timing. The locations. Something doesn't add up.",
        "general": "If I were investigating this, I'd look at who benefits from the fear itself.",
        "victim":  "There was something specific about who was chosen. This wasn't random.",
    },
    "default": {
        "fear":    "People are scared. You can feel it.",
        "general": "I keep to myself these days.",
        "victim":  "They didn't deserve it. Nobody does.",
    },
}

SCENE_VARIANTS = {
    "blunt_force": [
        "The force used was extraordinary. Someone strong, or desperate.",
        "Whoever did this wasn't subtle. The violence was personal.",
        "Tool marks on the surface. Whoever held it knew how to swing it.",
    ],
    "sharp_blade": [
        "A single precise cut. This person knew what they were doing.",
        "Clean work. Too clean. This wasn't a fight — it was an execution.",
        "The angle suggests someone taller, or someone who struck from above.",
    ],
    "poison": [
        "No struggle. The victim never knew. Something in what they ate or drank.",
        "Whoever did this had access and patience. Poison takes planning.",
        "The symptoms suggest something botanical. Someone with knowledge of plants or medicines.",
    ],
    "strangulation": [
        "A struggle, but brief. The killer was stronger or caught them off guard.",
        "Face to face. This was intimate. Personal. The killer wanted to be there.",
        "The victim fought back — there may be marks on whoever did this.",
    ],
}

PREMISE_OPENERS = [
    "You arrive in {town} by the last coach of the evening.",
    "A letter found you three days ago. You came to {town} as fast as you could.",
    "The town of {town} is not on any map you own. But someone needed help.",
    "You were passing through {town} when the second body was found.",
    "{town} hired you. They call it an investigation. It feels more like a last hope.",
]

AGENDA_SIGNALS = {
    "visit_accomplice": [
        "Someone was seen meeting briefly with a figure near {district} district around {time}.",
        "A light was on in {district} district well past when it should have been.",
        "Two people were seen talking quietly near {district} at around {time}. One left quickly.",
    ],
    "silence_witness": [
        "A witness who spoke earlier today seems... different now. More closed off.",
        "Someone in {district} has stopped talking about what they saw.",
        "{name} mentioned they were approached by someone asking what they'd told investigators.",
    ],
    "leave_town": [
        "Word is someone was seen loading bags at the edge of town around {time}.",
        "A figure was seen moving toward the town road in the early {time}.",
    ],
    "visit_scene": [
        "Someone was spotted near where {victim} was found. Late. Alone.",
        "Fresh marks near the scene. Someone came back.",
    ],
}

AGENDA_INTERCEPT_SUCCESS = [
    "You arrive in time. {name} is here — caught in the act of {action_desc}.",
    "You find {name} in {district} district. They stop when they see you.",
    "You've intercepted something. {name} was not expecting you here.",
]
AGENDA_INTERCEPT_LATE = [
    "You arrive too late. Signs of recent activity, but {name} is gone.",
    "Someone was here. The {district} district shows it — but you missed them.",
    "You find traces of what happened. {name} was here, and now they're not.",
]

WRONG_ACCUSATION_REACTIONS = {
    "aggressive": [
        "Don't come back. We have nothing more to say.",
        "You accused me. You were wrong. Now leave me alone.",
    ],
    "selfish": [
        "I'm not obligated to help you after what you did.",
        "You wanted to pin this on me. I remember that.",
    ],
    "cautious": [
        "I'll speak to you again. But understand — I'm watching how you handle information.",
        "You were wrong about me. I hope you're being more careful now.",
    ],
    "loyal": [
        "You hurt me. I'll still help if I can, but you should know that.",
        "I understand mistakes happen. I just need a moment.",
    ],
    "charismatic": [
        "That was clumsy. But I've seen worse. Let's move past it.",
        "You owe me. And now I'll tell you something I wasn't going to.",
    ],
    "innovative": [
        "Interesting. You came to the wrong answer through right reasoning. Let me show you why.",
        "You accused me because the logic pointed here. I respect that, and here's why you were wrong.",
    ],
    "default": [
        "I don't have anything more to say to you.",
        "That was wrong. I hope you find who actually did it.",
    ],
}

DISTRICT_CLOSING = {
    "aggressive": "People here are done talking. Word got out that you're snooping around.",
    "selfish":    "The {district} district has gone quiet. No one wants to be the next person questioned.",
    "cautious":   "People in {district} are being more careful about what they say.",
    "default":    "Something has shifted in {district} district. Fewer people are willing to speak.",
}

CONSPIRACY_SIGNALS = [
    "The victim didn't seem afraid of one person. More like they were avoiding a situation.",
    "I saw two people talking the night before. Hushed. Urgent. I didn't think much of it then.",
    "Whatever happened was coordinated. You don't pull that off alone.",
    "Someone kept watch while someone else acted. I'm almost certain of it.",
]
CONSPIRACY_ACCOMPLICE_HINTS = [
    "There was a second person involved. I don't know who, but I heard two voices.",
    "The killer had help. Someone created a distraction, I think.",
    "Two people left separately but from the same direction. One I know. One I don't.",
]
FRAME_SIGNALS = [
    "The evidence showed up very quickly, didn't it? Almost like someone knew where to point.",
    "I've seen someone set up before. This has that feeling.",
    "The obvious answer is there for a reason. Someone put it there.",
    "I wouldn't rush to the easy conclusion. Something about this feels arranged.",
]
ACCOMPLICE_OPENING = {
    "first":  "I don't know what you've been told, but I want you to hear my side.",
    "guilty": "So. You found me. I wondered how long it would take.",
    "deny":   "Whatever you think I did — you're wrong about the extent of it.",
}
ACCOMPLICE_PRESSURE = {
    "low":      "I was there. But not in the way you think.",
    "mid":      "I knew what was happening. I didn't stop it. That's different from doing it.",
    "high":     "I helped. I'm not proud of it. But I didn't think it would go this far.",
    "breaking": "Yes. I was part of it. I told them where the victim would be. That's all I did.",
}
FRAMED_PERSON_ACCUSATION = [
    "This is exactly what they wanted. Someone set me up — can't you see that?",
    "Think about how fast that evidence appeared. Who benefits from you looking at me?",
    "The real killer is watching you accuse the wrong person right now.",
    "I didn't do this. And the fact that it looks so clear is exactly the problem.",
]
KILLER_STEERING = {
    "frame": [
        "Have you looked at {framed}? I hear there's something suspicious there.",
        "Someone told me {framed} was seen near the scene. I don't know what to make of it.",
        "If I were investigating this, I'd start with {framed}. Just a feeling.",
    ],
}

FIRST_MEETING = {
    "aggressive": "First time we've spoken. I'll keep it brief.",
    "selfish":    "I don't make a habit of talking to strangers.",
    "cautious":   "I don't know you. I'll be careful about what I say.",
    "loyal":      "You're new here, or at least new to me.",
    "charismatic":"Welcome. I don't think we've been introduced.",
    "innovative": "Ah. I've been wondering when someone would come to me.",
    "default":    "I haven't spoken to you before.",
}
SECOND_MEETING = {
    "aggressive": "You again. Ask what you came to ask.",
    "selfish":    "Back already. I told you what I know.",
    "cautious":   "You returned. I've been thinking about what we discussed.",
    "loyal":      "I've thought about what I said last time. I stand by it.",
    "charismatic":"I was wondering if you'd come back. I've thought of more.",
    "innovative": "Good. I hoped you'd return. I have a different angle now.",
    "default":    "Back again. I'll try to help if I can.",
}
THIRD_MEETING = {
    "aggressive": "Third time. You're persistent. I respect that, barely.",
    "selfish":    "You keep coming to me. I'm not sure what else I can offer.",
    "cautious":   "I've shared more with you than I planned to. You're thorough.",
    "loyal":      "I trust you now, more than when we started. What do you need?",
    "charismatic":"You've worn me down in the best way. Ask me anything.",
    "innovative": "By now I think you understand more than you let on.",
    "default":    "You've spoken to me more than most. I'll be open.",
}
AFTER_PROTECTION = {
    "any": [
        "You stayed close yesterday. I noticed. Thank you.",
        "I slept better knowing you were watching. That counts for something.",
        "I owe you one. I'll tell you what I know.",
    ],
}
AFTER_WITNESS_DEATH = {
    "any": [
        "Did you hear? Another one. I'm frightened.",
        "Two people now. I don't feel safe saying too much.",
        "After what happened to {last_victim}, I'm keeping my head down.",
    ],
}

SEARCH_RESULTS = {
    "scene": {
        "found": [
            "You examine the area carefully. {clue_text}",
            "Between the shadows and the dust: {clue_text}",
            "It takes time, but you find something. {clue_text}",
        ],
        "nothing": [
            "You search thoroughly. Nothing that wasn't already known.",
            "The scene has been disturbed. Whatever was here is gone.",
            "Footprints, marks, nothing clear enough to be useful.",
        ],
    },
    "district": {
        "found": [
            "Asking around the {district} district turns up something. {detail}",
            "Someone in {district} mentions something in passing: {detail}",
        ],
        "nothing": [
            "The {district} district offers nothing new today.",
            "People in {district} aren't talking. You come away empty-handed.",
        ],
    },
}

FOLLOW_RESULTS = {
    "killer_to_scene": "You tail {name} at a distance. They pass near where {victim} was found — not hurrying, but deliberate.",
    "killer_at_home":  "You follow {name} for several hours. They go home, stay there. But you notice they check the street twice before going in.",
    "killer_contact":  "You watch {name} meet briefly with someone in the {district} district. The exchange lasts under a minute.",
    "innocent_routine":"You follow {name} through their usual movements. Nothing unusual.",
    "innocent_nervous": "You follow {name}. They seem uneasy — looking over their shoulder. Aware of being watched, or afraid of something else?",
}

ALIBI_RESULTS = {
    "holds":   "{name}'s alibi checks out. {corroboration}",
    "breaks":  "{name}'s alibi doesn't hold. {gap}",
    "partial": "{name}'s alibi is partially confirmed. The timeline has gaps.",
}
ALIBI_CORROBORATIONS = [
    "Two people confirm they were together.",
    "Guild records show they were logged in that evening.",
    "A shopkeeper remembers the visit clearly.",
]
ALIBI_GAPS = [
    "The person they claim to have been with can't confirm the time.",
    "Records show a two-hour gap they haven't explained.",
    "Their account changed slightly when pressed on the details.",
]

CONFRONTATION_OPENING = {
    "aggressive": [
        "You're accusing *me*? Do you have any idea what you're implying?",
        "Say that again. I dare you to say that to my face.",
        "You'd better have something solid. I don't take this lightly.",
    ],
    "selfish": [
        "This is a misunderstanding. I can explain everything.",
        "You're wasting both our time. I had nothing to do with this.",
        "Whatever you think you know, you're wrong. Let's get that clear first.",
    ],
    "cautious": [
        "I expected this. People always look for the simplest answer.",
        "I won't say anything until I understand what you have.",
        "I'm not going to panic. If you had evidence, you'd have used it already.",
    ],
    "loyal": [
        "This is a mistake. I've lived here my whole life. I would never.",
        "Whatever you've been told, someone is lying to you.",
        "I'll hear you out. But you're wrong, and I'll prove it.",
    ],
    "charismatic": [
        "Interesting. You've worked your way to me. Let's talk this through.",
        "I knew someone would come eventually. I've been preparing for this conversation.",
        "You have my full attention. Show me what you've got.",
    ],
    "innovative": [
        "You've been thorough. I'll give you that. But you're missing something.",
        "Whoever told you to look here was counting on you making this mistake.",
        "Walk me through your reasoning. I want to hear how you got here.",
    ],
    "default": [
        "You can't be serious.",
        "I didn't do anything. You have the wrong person.",
        "What exactly do you think you know?",
    ],
}

CONFRONTATION_PRESSURE = {
    "low": {
        "aggressive": "Is that all you have? I've heard stronger gossip.",
        "selfish":    "That's not evidence. That's a story.",
        "cautious":   "I can explain that easily. Is that really the best you have?",
        "loyal":      "That doesn't prove anything. Anyone could say that.",
        "charismatic":"Interesting, but not damning. Keep going.",
        "innovative": "You're building a case on assumptions. This doesn't hold.",
        "default":    "That doesn't mean what you think it means.",
    },
    "mid": {
        "aggressive": "You're putting things together that don't belong together.",
        "selfish":    "I need a moment. This is getting... complicated.",
        "cautious":   "I see where you're going. You're not entirely wrong about some of it.",
        "loyal":      "I... that's not how it happened. Not exactly.",
        "charismatic":"You're good at this. But you're still missing the context.",
        "innovative": "Your logic is sound but incomplete. There's a piece you don't have.",
        "default":    "Stop. Just — stop for a moment.",
    },
    "high": {
        "aggressive": "You don't understand what was happening. You never could.",
        "selfish":    "Fine. Yes. Some of that is true. But it's not what you think.",
        "cautious":   "I was careful. I was so careful. How did you find all of this?",
        "loyal":      "I didn't want any of this. You have to believe that.",
        "charismatic":"You've done something remarkable. And I'm cornered. I can feel it.",
        "innovative": "Everything you've said is correct. The conclusion you're drawing, though—",
        "default":    "I can't — I didn't want this to happen.",
    },
    "breaking": {
        "aggressive": "I did what had to be done. They would have ruined everything.",
        "selfish":    "It wasn't supposed to go this far. None of it was.",
        "cautious":   "You're the first person to actually piece it together. I'm... impressed.",
        "loyal":      "I was protecting someone. That's all I ever wanted to do.",
        "charismatic":"You've earned this. Yes. It was me. I'll tell you everything.",
        "innovative": "The ending I planned was different. Not this one. But here we are.",
        "default":    "Alright. You want the truth? Here it is.",
    },
}

INNOCENT_RESPONSES = {
    "low":      "I can account for that. Ask anyone.",
    "mid":      "That's concerning. Someone has gone to a lot of trouble to point at me.",
    "high":     "This is wrong. All of it. Someone is using me.",
    "breaking": "I didn't do this. I swear on everything — I did not do this.",
}

CLUE_REBUTTAL = {
    "lie": [
        "That's not right. Whoever told you that was either mistaken or lying.",
        "I can disprove that. Ask {source}. They were with me.",
        "That's fabricated. That is not what happened.",
    ],
    "irrelevant": [
        "That applies to half the people in this town.",
        "You're reaching. That doesn't point specifically at me.",
        "I don't know what you're trying to say with that.",
    ],
}

class MurdererScenario(Scenario):
    """The Murderer — find the killer before they strike again."""
    name        = "The Murderer"
    description = "Find the killer before they strike again."
    actions     = ["talk","accuse","search","follow","status","nearby","go",
                   "clues","surrender","restart","save","load","help"]

    def __init__(self, seed: int = 42, difficulty: int = 5):
        super().__init__()
        self.seed        = seed
        self.difficulty  = max(1, min(20, difficulty))
        self.state:         MurdererState
        self.characters:    dict[str, Character] = {}
        self.clues:         dict[str, Clue]      = {}
        self.relationships: dict[str, Relationship] = {}
        self.secrets:       dict[str, Secret]    = {}
        self.clue_holders:  dict[str, list[str]] = {}
        self.town_name:     str                  = ""
        self.premise:       str                  = ""
        self.events: list[str] = []
        self._setup(seed)

    """Mixin: Setup and initialization — population, clues, case types, premise."""

    def _setup(self, seed: int):
        rng = random.Random(seed)
        self.town_name = rng.choice([
            "Coldwater","Ashbridge","Millhaven","Dunmere","Vanthorpe",
            "Greywood","Ironholt","Saltwick","Crestfall","Moorfield",
        ])

        pop, strikes, money, max_victims, lie_count, payment_pct = _difficulty_params(self.difficulty)

        all_occupations = rng.choices(OCCUPATIONS, k=pop)
        all_districts   = rng.choices(DISTRICTS,   k=pop)
        all_traits      = rng.choices(TRAITS,      k=pop)

        chars = []
        for i in range(pop):
            fn = rng.choice(FIRST_NAMES)
            ln = rng.choice(LAST_NAMES)
            c = Character(
                id=f"c{i}",
                name=f"{fn} {ln}",
                occupation=all_occupations[i],
                district=all_districts[i],
                trait=all_traits[i],
                portrait=rng.choice(["◈","◉","◎","◍","◌","◐","◑","◒","◓"]),
            )
            chars.append(c)
            self.characters[c.id] = c

        killer_idx = rng.randint(0, pop-1)
        killer = chars[killer_idx]
        killer.is_killer = True

        method = rng.choice(METHODS)
        motive = rng.choice(MOTIVES)

        non_killers = [c for c in chars if not c.is_killer]
        first_victim = rng.choice(non_killers)
        first_victim.alive = False

        self.first_victim_name = first_victim.name
        first_strike = _strike_hours(self.difficulty) + rng.uniform(-4, 4)
        self.state = MurdererState(
            killer_id=killer.id,
            killer_occupation=killer.occupation,
            killer_district=killer.district,
            killer_trait=killer.trait,
            killer_motive=motive,
            killer_method=method,
            victims=[first_victim.id],
            next_strike_hour=first_strike,
            max_victims=max_victims,
            money=money,
            difficulty=self.difficulty,
            player_location=first_victim.district,
            seed_used=seed,
        )
        occ = killer.occupation
        self._weapon_name, self._weapon_desc = WEAPON_BY_OCCUPATION.get(occ, DEFAULT_WEAPON)
        weapon_districts = [c.district for c in self.characters.values() if c.district]
        self._weapon_district = rng.choice(weapon_districts)
        self.state.weapon_locations = {self._weapon_district: self._weapon_desc}

        self._generate_clues(rng, killer, first_victim, method, motive)
        case_type = self._pick_case_type(rng, self.difficulty)
        self.state.case_type = case_type.value
        self._setup_case_type(rng, case_type, killer, first_victim)

        self._generate_relationships(rng)

        self._generate_killer_agenda(rng)

        self._generate_secrets(rng)
        if lie_count > 0:
            self._inject_lies(rng, lie_count, payment_pct)
        else:
            self._mark_payment_required(rng, payment_pct)
        self.premise = self._generate_premise(rng, killer, first_victim, method, motive)
        self.events.append(
            f"{first_victim.name} was found dead. The town is in shock."
        )

    def _pick_case_type(self, rng, difficulty: int) -> CaseType:
        """Higher difficulty enables rarer case types."""
        if difficulty <= 4:
            return CaseType.SERIAL
        pool = [CaseType.SERIAL, CaseType.SERIAL, CaseType.PASSION]
        if difficulty >= 8:
            pool.append(CaseType.FRAME)
        if difficulty >= 12:
            pool.append(CaseType.CONSPIRACY)
        return rng.choice(pool)

    def _setup_case_type(self, rng, case_type: CaseType,
                         killer: Character, victim: Character) -> None:
        s = self.state
        alive_non_killer = [c for c in self.characters.values()
                            if c.alive and not c.is_killer]

        if case_type == CaseType.PASSION:
            s.max_victims      = 1
            s.flee_hour        = s.hour + 48 + rng.uniform(-6, 6)
            s.next_strike_hour = 9999.0
            self.events.append(
                "This appears to be a single, deliberate murder. "
                "The killer may try to leave town within two days."
            )

        elif case_type == CaseType.CONSPIRACY:
            if len(alive_non_killer) >= 2:
                accomplice = rng.choice(alive_non_killer)
                s.accomplice_id = accomplice.id

                ac1 = Clue(
                    id="accomplice_presence",
                    attribute="district", value=accomplice.district,
                    text=f"A second figure was seen near {accomplice.district} district "
                         f"before the murder — possibly acting as lookout.",
                    day_available=1, narrows_suspects=True,
                )
                ac2 = Clue(
                    id="accomplice_occupation",
                    attribute="occupation", value=accomplice.occupation,
                    text=f"Whoever helped the killer had knowledge of "
                         f"{accomplice.occupation} work — the approach suggests it.",
                    day_available=2, narrows_suspects=True,
                )
                ac3 = Clue(
                    id="accomplice_direct",
                    attribute="district", value=accomplice.district,
                    text=f"A reliable witness saw two people leaving together "
                         f"from the {accomplice.district} district that night.",
                    day_available=1, narrows_suspects=True,
                )
                for clue in [ac1, ac2, ac3]:
                    self.clues[clue.id] = clue

                witnesses = [c for c in alive_non_killer
                             if c.id != accomplice.id and c.district == accomplice.district]
                other_witnesses = [c for c in alive_non_killer
                                   if c.id != accomplice.id and c.district != accomplice.district]
                if witnesses:
                    self.clue_holders.setdefault(rng.choice(witnesses).id, []).append(ac1.id)
                if other_witnesses:
                    self.clue_holders.setdefault(rng.choice(other_witnesses).id, []).append(ac2.id)
                if witnesses:
                    self.clue_holders.setdefault(rng.choice(witnesses).id, []).append(ac3.id)

            self.events.append(rng.choice(CONSPIRACY_SIGNALS))

        elif case_type == CaseType.FRAME:
            if len(alive_non_killer) >= 2:
                framed = rng.choice(alive_non_killer)
                s.framed_id = framed.id

                frame_clue = Clue(
                    id="frame_evidence",
                    attribute="district", value=framed.district,
                    text=f"Something belonging to {framed.name} was found near the scene. "
                         f"It may have been placed there deliberately.",
                    day_available=0, narrows_suspects=True, is_lie=True,
                )
                self.clues[frame_clue.id] = frame_clue
                s.lies_planted.append(frame_clue.id)

                counter = Clue(
                    id="frame_counter",
                    attribute="district", value=killer.district,
                    text=f"The item found near the scene was reported stolen from "
                         f"{framed.name} two days before the murder. "
                         f"Someone took it specifically to use it.",
                    day_available=0, narrows_suspects=True,
                )
                self.clues[counter.id] = counter
                holders = [c for c in alive_non_killer
                           if c.id not in {killer.id, framed.id}]
                if holders:
                    h = rng.choice(holders)
                    self.clue_holders.setdefault(h.id, []).append(counter.id)
                    self.clues[counter.id].day_available = 0

                timeline = Clue(
                    id="frame_timeline",
                    attribute="trait", value=killer.trait,
                    text=f"The timing of when the 'evidence' was placed doesn't match "
                         f"{framed.name}'s verified movements. Someone else put it there.",
                    day_available=2, narrows_suspects=True,
                )
                self.clues[timeline.id] = timeline
                if holders:
                    self.clue_holders.setdefault(rng.choice(holders).id, []).append(timeline.id)

            self.events.append(rng.choice(FRAME_SIGNALS))

    def _generate_relationships(self, rng) -> None:
        """Build a web of relationships between characters."""
        chars = list(self.characters.values())
        if len(chars) < 3:
            return
        kinds = list(RelKind)
        used_pairs: set[frozenset] = set()
        n_rels = max(3, len(chars) // 2)
        for i in range(n_rels):
            attempts = 0
            while attempts < 10:
                a, b = rng.sample(chars, 2)
                pair = frozenset({a.id, b.id})
                if pair not in used_pairs:
                    used_pairs.add(pair)
                    break
                attempts += 1
            else:
                continue
            kind = rng.choice(kinds)
            rel = Relationship(
                id=f"rel_{i}",
                person_a_id=a.id, person_a_name=a.name,
                person_b_id=b.id, person_b_name=b.name,
                kind=kind,
                known_to=[rng.choice([c.id for c in chars if c.id not in {a.id, b.id}])]
                         if len(chars) > 2 else [],
            )
            self.relationships[rel.id] = rel
            if kind in (RelKind.LOVER, RelKind.RIVAL, RelKind.DEBTOR):
                desc = {
                    RelKind.LOVER:  f"{a.name} and {b.name} are secretly involved.",
                    RelKind.RIVAL:  f"{a.name} and {b.name} have a bitter rivalry.",
                    RelKind.DEBTOR: f"{a.name} owes {b.name} a significant debt.",
                }[kind]
                lever = {
                    RelKind.LOVER:  f"{a.name} is hiding a relationship with {b.name}.",
                    RelKind.RIVAL:  f"{a.name} and {b.name} have unresolved conflict.",
                    RelKind.DEBTOR: f"{a.name} is financially beholden to {b.name}.",
                }[kind]
                s = Secret(
                    id=f"rel_secret_{i}",
                    holder_id=rel.known_to[0] if rel.known_to else a.id,
                    about_id=a.id, about_name=a.name,
                    description=desc, leverage=lever,
                )
                self.secrets[s.id] = s

    def _generate_secrets(self, rng) -> None:
        """Generate minor crimes / secrets between citizens that can be used for blackmail."""
        alive = [c for c in self.characters.values() if c.alive]
        if len(alive) < 2:
            return
        n_secrets = max(2, self.difficulty // 3)
        for i in range(min(n_secrets, len(SECRET_TEMPLATES))):
            tmpl_desc, tmpl_kind, tmpl_leverage = SECRET_TEMPLATES[i % len(SECRET_TEMPLATES)]
            pair = rng.sample(alive, 2)
            a, b = pair[0], pair[1]
            desc      = tmpl_desc.replace("{a}", a.name).replace("{b}", b.name)
            leverage  = tmpl_leverage.replace("{a}", a.name).replace("{b}", b.name)
            s = Secret(
                id=f"secret_{i}",
                holder_id=rng.choice([c.id for c in alive if c.id not in {a.id, b.id}] or [alive[0].id]),
                about_id=a.id,
                about_name=a.name,
                description=desc,
                leverage=leverage,
            )
            self.secrets[s.id] = s

    def _mark_payment_required(self, rng, payment_pct: float) -> None:
        """At higher difficulties, some clue-bearing witnesses demand payment."""
        if payment_pct <= 0:
            return
        all_holders = list(self.clue_holders.keys())
        rng.shuffle(all_holders)
        n = max(1, int(len(all_holders) * payment_pct))
        for holder_id in all_holders[:n]:
            char = self.characters.get(holder_id)
            if char and char.trait in ("selfish", "aggressive"):
                char._requires_payment = True

    def _inject_lies(self, rng, lie_count: int, payment_pct: float) -> None:
        """At high difficulty, plant false clues that point away from the killer."""
        self._mark_payment_required(rng, payment_pct)
        injectable = [
            cid for cid in ("district_seen", "occupation_direct")
            if cid in self.clues
        ]
        rng.shuffle(injectable)
        districts = [d for d in ("market","civic","healing","military","slums")
                     if d != self.state.killer_district]
        occupations = [o for o in ("merchant","teacher","doctor","priest","soldier","farmer")
                       if o != self.state.killer_occupation]
        for i, cid in enumerate(injectable[:lie_count]):
            clue = self.clues[cid]
            if cid == "district_seen":
                wrong = rng.choice(districts)
                clue.text = clue.text.replace(
                    self.state.killer_district, wrong
                )
                clue.value = wrong
                clue.is_lie = True
            elif cid == "occupation_direct":
                wrong = rng.choice(occupations)
                clue.text = clue.text.replace(
                    self.state.killer_occupation, wrong
                )
                clue.value = wrong
                clue.is_lie = True
            self.state.lies_planted.append(cid)

    def _generate_clues(self, rng, killer: Character, victim: Character, method: str, motive: str):
        """Generate concrete, falseable clues about the killer."""
        non_killers = [c for c in self.characters.values() if c.id != killer.id and c.alive]
        rn = lambda: rng.choice(non_killers).name

        trait_desc = TRAIT_DESCRIPTIONS.get(killer.trait, killer.trait)
        occ_suspects = METHOD_CLUE[method]

        def make(cid: str, attr: str, value: str, text: str,
                 day: int = 0, scene: bool = False, narrows: bool = True) -> Clue:
            return Clue(id=cid, attribute=attr, value=value, text=text,
                        source_name=rn(), day_available=day,
                        scene_only=scene, narrows_suspects=narrows)

        pool = [
            make("district_seen",
                 "district", killer.district,
                 f"A neighbor reported seeing a figure leave the {killer.district} district "
                 f"in the early hours the night {victim.name} was killed.",
                 day=0),

            make("occupation_direct",
                 "occupation", killer.occupation,
                 f"The coroner noted the wounds are consistent with someone "
                 f"who handles {killer.occupation} tools regularly.",
                 day=0),

            make("trait_behavior",
                 "trait", killer.trait,
                 f"Multiple people who glimpsed the killer describe them as {trait_desc}. "
                 f"That narrows it to someone with that specific manner.",
                 day=1),

            make("alibi_break",
                 "occupation", killer.occupation,
                 f"The {killer.occupation} guild register shows one member "
                 f"with an unexplained gap the evening of the murder. "
                 f"Two hours unaccounted for.",
                 day=1),

            make("victim_connection",
                 "district", killer.district,
                 f"{victim.name} filed a complaint against a resident of "
                 f"the {killer.district} district six weeks before the murder. "
                 f"The case was closed without resolution.",
                 day=2),

            make("motive_pattern",
                 "district", killer.district,
                 f"Talking to those who knew {victim.name}: "
                 f"{MOTIVE_CLUE.get(self.state.killer_motive, 'something drove this')}. "
                 f"The {killer.district} district keeps coming up.",
                 day=2, narrows=False),

            make("scene_physical",
                 "occupation", killer.occupation,
                 f"At the scene: tool marks, a partial footprint, "
                 f"and a residue that a {killer.occupation} would recognize immediately. "
                 f"This was not a random act.",
                 day=0, scene=True),
        ]

        pool.append(make(
            "method_occ", "occupation", "|".join(occ_suspects),
            f"The method — {METHOD_DESC[method]} — suggests physical familiarity. "
            f"Cross-reference with {', '.join(occ_suspects[:-1])} or {occ_suspects[-1]}.",
            day=0, narrows=False,
        ))

        rng.shuffle(pool)
        for clue in pool:
            self.clues[clue.id] = clue

        non_killer_ids = [c.id for c in self.characters.values()
                          if not c.is_killer and c.alive]
        rng.shuffle(non_killer_ids)
        for i, clue in enumerate(c for c in pool if not c.scene_only):
            holder = non_killer_ids[i % len(non_killer_ids)]
            if holder not in self.clue_holders:
                self.clue_holders[holder] = []
            self.clue_holders[holder].append(clue.id)

        if killer.id not in self.clue_holders:
            self.clue_holders[killer.id] = []
        self.clue_holders[killer.id].append("victim_connection")

        self.state.crime_scenes.append(victim.id)

    def _generate_premise(self, rng, killer, victim, method, motive) -> str:
        ct_key = self.state.case_type if self.state.case_type in CASE_OPENERS else "serial"
        opener = rng.choice(CASE_OPENERS[ct_key]).replace("{town}", self.town_name)
        victim_intro = (f"\n\nA body has been found in the {victim.district} district. "
                        f"The victim is {victim.name}, a {victim.occupation}. "
                        f"You are standing at the scene. The {victim.district} district "
                        f"is where your investigation begins.")
        scene  = rng.choice(SCENE_VARIANTS[method])
        tone_lines = {
            "jealousy":     "The tension here predates the murder. Something has been building for a while.",
            "revenge":      "Whoever did this waited. This was not impulsive.",
            "greed":        "Money changes people. Follow what was taken.",
            "fear":         "Someone felt cornered. Dangerous people are cornered people.",
            "obsession":    "The killer will not stop on their own. They are driven.",
            "desperation":  "The killings are getting closer together. Time is short.",
        }
        return (
            opener + "\n\n"
            + f"{victim.name} was found dead, killed by {METHOD_DESC[method]}.\n"
            + f"{scene}\n\n"
            + tone_lines.get(motive, "Something dark is at work here.") + "\n\n"
            + "Talk to residents. Examine the scene. Accuse when you are certain.\n"
            + f"You have until the third victim to solve this."
        )

    def _generate_killer_agenda(self, rng) -> None:
        """Build the killer's schedule of actions with specific hours."""
        s = self.state
        killer = self.characters[s.killer_id]
        ct = CaseType(s.case_type)
        agenda = []

        if ct == CaseType.CONSPIRACY and s.accomplice_id:
            agenda.append({
                "hour": rng.uniform(14, 20),
                "action": "visit_accomplice",
                "target_id": s.accomplice_id,
                "district": self.characters[s.accomplice_id].district,
                "intercepted": False,
                "revealed": False,
                "action_desc": "coordinating with their accomplice",
                "signal": rng.choice(AGENDA_SIGNALS["visit_accomplice"]),
            })
        else:
            agenda.append({
                "hour": rng.uniform(16, 22),
                "action": "visit_scene",
                "target_id": s.victims[0] if s.victims else None,
                "district": killer.district,
                "intercepted": False,
                "revealed": False,
                "action_desc": "returning to the scene",
                "signal": rng.choice(AGENDA_SIGNALS["visit_scene"]).replace(
                    "{victim}", self.characters[s.victims[0]].name if s.victims else "the victim"
                ),
            })

        at_risk = [
            c for c in self.characters.values()
            if c.alive and not c.is_killer
            and self.clue_holders.get(c.id)
            and c.id not in s.victims
        ]
        if at_risk:
            target = rng.choice(at_risk)
            agenda.append({
                "hour": rng.uniform(20, 30),
                "action": "silence_witness",
                "target_id": target.id,
                "district": target.district,
                "intercepted": False,
                "revealed": False,
                "action_desc": f"pressuring {target.name} to stay quiet",
                "signal": rng.choice(AGENDA_SIGNALS["silence_witness"]).replace(
                    "{district}", target.district
                ).replace("{name}", target.name),
            })

        if ct == CaseType.PASSION:
            agenda.append({
                "hour": s.flee_hour,
                "action": "leave_town",
                "target_id": None,
                "district": "road",
                "intercepted": False,
                "revealed": False,
                "action_desc": "leaving town",
                "signal": rng.choice(AGENDA_SIGNALS["leave_town"]).replace(
                    "{time}", _format_time(s.flee_hour)
                ),
            })

        agenda.sort(key=lambda a: a["hour"])
        s.killer_agenda = agenda

    """Mixin: Time advancement, killer agency, agenda, gossip, end conditions."""

    def advance_time(self, hours: float) -> list[str]:
        """Advance the game clock by `hours`. Returns events that happened."""
        events: list[str] = []
        s = self.state
        old_hour = s.hour
        s.hour += hours
        s.day = int(s.hour // 24) + 1

        s.action_log.append({"hour": round(s.hour, 1), "hours_spent": round(hours, 1)})

        if s.hour - s.questions_period_start >= QUESTION_PERIOD:
            s.questions_asked_this_period = {}
            s.questions_period_start = s.hour
            s.protected_this_period = None

        if s.hour - s.gossip_updated_hour >= 8.0:
            self._generate_gossip()
            s.gossip_updated_hour = s.hour

        if s.hour >= s.next_strike_hour:
            protected = set(s.protected_history[-3:])
            in_player_district = {
                c.id for c in self.characters.values()
                if c.alive and c.district == s.player_location
            }
            protected = protected | in_player_district
            alive = [
                c for c in self.characters.values()
                if c.alive and not c.is_killer
                and c.id not in s.victims
                and c.id not in protected
            ]
            if not alive:
                alive = [c for c in self.characters.values()
                         if c.alive and not c.is_killer and c.id not in s.victims]
            if alive:
                killer = self.characters[s.killer_id]
                preferred = [c for c in alive
                             if c.district == killer.district or c.occupation == killer.occupation]
                victim = random.choice(preferred if preferred else alive)
                victim.alive = False
                s.victims.append(victim.id)
                s.crime_scenes.append(victim.id)

                interval = _strike_hours(s.difficulty) + random.uniform(-4, 6)
                s.next_strike_hour = s.hour + interval

                self._unlock_post_murder_clues(victim, s.hour)

                scene_clue = self.clues.get("scene_physical")
                if scene_clue and not scene_clue.found:
                    scene_clue.found = True
                    s.clues_found.append("scene_physical")

                player_protected = victim.district == s.player_location
                protect_note = " (you were there — your presence protected the area)" if player_protected else ""
                night_str = " under cover of darkness" if _is_night(s.next_strike_hour - interval) else ""
                msg = (f"[{_format_time(s.hour)}] Another victim: {victim.name} "
                       f"({victim.occupation}, {victim.district}){night_str}.{protect_note} "
                       f"Next strike expected around {_format_time(s.next_strike_hour)}.")
                events.append(msg)
                self.events.append(msg)

        self._update_killer_heat(hours)
        self._killer_agency()

        intercept_events = self._check_agenda_intercept(s.player_location)
        events.extend(intercept_events)
        missed_events = self._fire_missed_agenda()
        events.extend(missed_events)

        for district, until in list(s.district_closed.items()):
            if s.hour > until:
                del s.district_closed[district]

        if s.case_type == CaseType.PASSION.value and s.hour >= s.flee_hour and not s.killer_fleeing:
            s.killer_fleeing = True
            killer_char = self.characters[s.killer_id]
            msg = (f"[{_format_time(s.hour)}] Reports suggest someone matching "
                   f"a {killer_char.occupation} from {killer_char.district} district "
                   f"was seen loading belongings. They may be trying to leave {self.town_name}.")
            events.append(msg); self.events.append(msg)

        hours_to_strike = s.next_strike_hour - s.hour
        if 0 < hours_to_strike <= 4 and not any("WARNING" in e for e in self.events[-3:]):
            w = f"[{_format_time(s.hour)}] WARNING: The killer may strike within {round(hours_to_strike)}h."
            events.append(w)
            self.events.append(w)

        return events

    def step(self) -> list[str]:
        return self.advance_time(24.0)

    def _update_killer_heat(self, hours_passed: float) -> None:
        """Accumulate heat silently. Queue actions to fire at next period boundary."""
        s = self.state
        killer = self.characters[s.killer_id]

        if s.player_location == killer.district:
            s.killer_heat = min(1.0, s.killer_heat + 0.03 * hours_passed)
        else:
            s.killer_heat = max(0.0, s.killer_heat - 0.008 * hours_passed)

        s.killer_heat = min(1.0, s.killer_heat + 0.04 * len(s.clues_found) / max(1, len(self.clues)))

        if s.killer_heat >= 0.30 and "bribe" not in s.heat_actions and "bribe" not in s.pending_heat_actions:
            s.pending_heat_actions.append("bribe")
        if s.killer_heat >= 0.60 and "eliminate_witness" not in s.heat_actions and "eliminate_witness" not in s.pending_heat_actions:
            s.pending_heat_actions.append("eliminate_witness")
        if s.killer_heat >= 0.90 and "plant_evidence" not in s.heat_actions and "plant_evidence" not in s.pending_heat_actions:
            s.pending_heat_actions.append("plant_evidence")

        if s.hour >= s.next_period_hour and s.pending_heat_actions:
            s.next_period_hour = s.hour + 8.0
            self._killer_agency()

    def _killer_agency(self) -> None:
        """Execute queued killer actions at a period boundary — not immediately."""
        s = self.state
        if not self.characters.get(s.killer_id) or not self.characters[s.killer_id].alive:
            return
        alive_non_killer = [c for c in self.characters.values()
                            if c.alive and not c.is_killer and c.id not in s.victims]

        for action in list(s.pending_heat_actions):
            s.pending_heat_actions.remove(action)
            s.heat_actions.append(action)

            if action == "bribe":
                corruptible = [
                    cid for cid in s.clues_found
                    if cid in self.clues
                    and self.clues[cid].narrows_suspects
                    and not self.clues[cid].is_lie
                    and cid not in s.corrupted_clues
                    and self.clues[cid].attribute in ("district","occupation")
                ]
                if corruptible:
                    cid = random.choice(corruptible)
                    clue = self.clues[cid]
                    if clue.attribute == "district":
                        wrong = random.choice([d for d in
                            ("market","civic","healing","military","slums","farming")
                            if d != clue.value])
                        clue.value = wrong
                        clue.text  = (f"A witness has reconsidered their account. "
                                      f"They now place the figure in the {wrong} district "
                                      f"— not where they originally said.")
                    else:
                        wrong = random.choice([o for o in
                            ("merchant","farmer","teacher","soldier","doctor","priest")
                            if o != clue.value])
                        clue.value = wrong
                        clue.text  = (f"A witness revised their description: "
                                      f"they believe the person was a {wrong}. "
                                      f"Their earlier account may have been mistaken.")
                    clue.is_lie = True
                    s.corrupted_clues.append(cid)
                    msg = (f"[{_format_time(s.hour)}] A witness came forward to correct "
                           f"an earlier statement. One of your clues may no longer be accurate.")
                    self.events.append(msg)

            elif action == "eliminate_witness":
                witness_scores = {
                    cid: len([c for c in self.clue_holders.get(cid,[])
                               if c not in s.clues_found and c in self.clues
                               and self.clues[c].narrows_suspects])
                    for cid in self.clue_holders
                    if self.characters.get(cid) and self.characters[cid].alive
                    and not self.characters[cid].is_killer
                }
                witness_scores = {k:v for k,v in witness_scores.items() if v > 0}
                if witness_scores:
                    target_id = max(witness_scores, key=lambda k: witness_scores[k])
                    target = self.characters[target_id]
                    if target.id not in s.protected_history[-5:]:
                        target.alive = False
                        s.victims.append(target.id)
                        s.crime_scenes.append(target.id)
                        interval = _strike_hours(s.difficulty) * 0.7
                        s.next_strike_hour = s.hour + interval
                        msg = (f"[{_format_time(s.hour)}] {target.name} was found dead. "
                               f"Another victim — or a silenced witness.")
                        self.events.append(msg)

            elif action == "plant_evidence":
                non_killers = [c for c in alive_non_killer if c.id != s.framed_id]
                if non_killers:
                    scapegoat = random.choice(non_killers)
                    pid = f"killer_plant_{len(s.lies_planted)}"
                    plant = Clue(
                        id=pid, attribute="district", value=scapegoat.district,
                        text=(f"An item from {scapegoat.district} district turned up "
                              f"near the latest scene. The circumstances are unclear."),
                        day_available=int(s.hour), is_lie=True, narrows_suspects=True,
                    )
                    self.clues[plant.id] = plant
                    s.lies_planted.append(plant.id)
                    if non_killers:
                        w = random.choice(non_killers)
                        self.clue_holders.setdefault(w.id, []).append(plant.id)
                    msg = (f"[{_format_time(s.hour)}] New evidence has come to light "
                           f"near the latest scene. Its origins are unclear.")
                    self.events.append(msg)

    def _check_agenda_intercept(self, location: str) -> list[str]:
        """Check if player is present for a scheduled killer action. Returns events."""
        s = self.state
        events = []
        killer = self.characters[s.killer_id]

        for item in s.killer_agenda:
            if item["intercepted"] or item["hour"] > s.hour + 0.5:
                continue
            if abs(item["hour"] - s.hour) > 2.0:
                continue
            if item["district"] != location:
                continue
            item["intercepted"] = True
            target = self.characters.get(item["target_id"]) if item.get("target_id") else None
            msg = rng_choice_seed(AGENDA_INTERCEPT_SUCCESS, hash(item["hour"])).replace(
                "{name}", killer.name
            ).replace(
                "{district}", item["district"]
            ).replace(
                "{action_desc}", item["action_desc"]
            )
            events.append(f"[{_format_time(s.hour)}] INTERCEPT: {msg}")
            self.events.append(events[-1])

            undiscovered = [
                cid for cid in self.clues
                if cid not in s.clues_found
                and self.clues[cid].day_available <= int(s.hour / 24)
                and self.clues[cid].narrows_suspects
                and not self.clues[cid].scene_only
            ]
            if undiscovered:
                reveal_id = undiscovered[0]
                self.clues[reveal_id].found = True
                s.clues_found.append(reveal_id)
                events.append(
                    f"From intercepting this moment: {self.clues[reveal_id].text}"
                )

        return events

    def _fire_missed_agenda(self) -> list[str]:
        """Process agenda items the player missed (hour has passed, not intercepted)."""
        s = self.state
        events = []
        killer = self.characters[s.killer_id]

        for item in s.killer_agenda:
            if item["intercepted"] or item["hour"] > s.hour:
                continue
            if s.hour - item["hour"] > 4.0:
                continue
            if item.get("fired"):
                continue
            item["fired"] = True

            action = item["action"]
            target = self.characters.get(item["target_id"]) if item.get("target_id") else None

            if action == "silence_witness" and target and target.alive:
                s.district_closed[target.district] = s.hour + 8.0
                msg = item["signal"]
                events.append(f"[{_format_time(s.hour)}] {msg}")
                self.events.append(events[-1])
                s.world_reactions.append(
                    f"{target.name} was approached by someone. They're less willing to talk."
                )

            elif action in ("visit_scene", "visit_accomplice"):
                msg = rng_choice_seed(AGENDA_SIGNALS[action], hash(item["hour"]))[0] if AGENDA_SIGNALS.get(action) else ""
                if msg:
                    events.append(f"[{_format_time(s.hour)}] {msg}")
                    self.events.append(events[-1])

        return events

    def agenda_signals_available(self) -> list[str]:
        """Return signals the player can learn about upcoming killer actions."""
        s = self.state
        signals = []
        now = s.hour
        for item in s.killer_agenda:
            if item["intercepted"] or item.get("fired"):
                continue
            hours_away = item["hour"] - now
            if 0 < hours_away <= 8 and not item.get("revealed"):
                item["revealed"] = True
                signals.append(
                    f"Signal (in ~{round(hours_away)}h): {item['signal']}"
                )
        return signals

    def _generate_gossip(self) -> None:
        """Refresh gossip — what citizens have observed recently."""
        s = self.state
        killer = self.characters[s.killer_id]
        alive_ids = [c.id for c in self.characters.values()
                     if c.alive and not c.is_killer]
        if not alive_ids:
            return
        for cid in random.sample(alive_ids, min(3, len(alive_ids))):
            char = self.characters[cid]
            options = []
            if char.district == killer.district:
                options.append(
                    f"I've noticed someone in {killer.district} district "
                    f"coming and going at odd hours since the murder."
                )
            if char.occupation == killer.occupation:
                options.append(
                    f"In our trade you notice things. The injuries described "
                    f"— I know exactly what made those marks."
                )
            if len(s.victims) >= 2:
                options.append(
                    f"Both victims — there's a pattern. Same kind of person, "
                    f"same part of town. This is not random."
                )
            h = self.state.hour % 24
            if 5 <= h < 12:   ctx_key = "morning"
            elif 12 <= h < 18: ctx_key = "afternoon"
            elif 18 <= h < 21: ctx_key = "evening"
            else:              ctx_key = "night"
            if len(self.state.victims) >= 2:
                options.extend(GOSSIP_BY_CONTEXT["second_victim"])
            options.extend(GOSSIP_BY_CONTEXT[ctx_key])
            if char.district == killer.district:
                options.extend(GOSSIP_BY_CONTEXT["district_neighbor"])
            for sec in self.secrets.values():
                if sec.holder_id == cid and sec.id not in s.secrets_known:
                    if random.random() < 0.20:
                        s.secrets_known.append(sec.id)
                        options.append(f"(Overheard: {sec.description})")
            s.gossip[cid] = random.choice(options)

    def _unlock_post_murder_clues(self, victim: Character, day: int) -> None:
        """After a second+ murder, new clues may become available."""
        if len(self.state.victims) < 2:
            return
        killer = self.characters[self.state.killer_id]
        victims_objs = [self.characters[v] for v in self.state.victims if v in self.characters]
        same_district = sum(1 for v in victims_objs if v.district == killer.district)
        if same_district >= 2 and "pattern_district" not in self.clues:
            clue = Clue(
                id="pattern_district",
                text=f"Both victims lived or worked in or near the {killer.district} district. "
                     f"The killer knows that area well.",
                attribute="district", value=killer.district,
                day_available=day, found=False,
            )
            self.clues["pattern_district"] = clue
            witnesses = [c for c in self.characters.values()
                        if c.alive and not c.is_killer
                        and c.district == killer.district]
            if witnesses:
                holder = random.choice(witnesses)
                if holder.id not in self.clue_holders:
                    self.clue_holders[holder.id] = []
                self.clue_holders[holder.id].append("pattern_district")

    def check_end(self) -> Optional[ScenarioResult]:
        s = self.state
        killer = self.characters[s.killer_id]

        if len(s.victims) >= s.max_victims:
            return ScenarioResult(
                won=False,
                message=(f"Too many lives lost. The killer — {killer.name}, "
                         f"a {killer.occupation} from {killer.district} district — "
                         f"was never brought to justice. {self.town_name} lives in fear."),
                days=s.day,
            )

        if s.case_type == CaseType.PASSION.value and s.killer_fleeing:
            if s.hour >= s.flee_hour + 6:
                return ScenarioResult(
                    won=False,
                    message=(f"The killer — {killer.name} — slipped out of {self.town_name} "
                             f"before you could act. The case goes cold."),
                    days=s.day,
                )
        return None

    def auto_text(self, char_id: str) -> str:
        """Immediate flavor text — varies by conversation count."""
        char = self.characters.get(char_id)
        if not char or not char.alive:
            return ""
        s = self.state
        if char_id not in s.known_chars:
            s.known_chars.append(char_id)
        count = s.conversation_count.get(char_id, 0)
        t = char.trait if char.trait in FIRST_MEETING else "default"
        s.conversation_count[char_id] = count + 1
        if count == 0:   greeting = FIRST_MEETING[t]
        elif count == 1: greeting = SECOND_MEETING[t]
        else:            greeting = THIRD_MEETING[t]

        TRAIT_VIBES = {
            "aggressive":  "direct, no patience for vagueness",
            "cautious":    "measured, chooses every word carefully",
            "loyal":       "steady, protective of those they trust",
            "charismatic": "warm, at ease with strangers",
            "innovative":  "methodical, sees patterns others miss",
            "selfish":     "evasive, hard to read",
        }
        if count == 1 and char.trait in TRAIT_VIBES:
            greeting += f" [You get a sense of them: {TRAIT_VIBES[char.trait]}.]"
        context = ""
        if char_id in s.protected_history[-5:]:
            context = " " + random.choice(AFTER_PROTECTION["any"])
        elif len(s.victims) >= 2:
            last = self.characters.get(s.victims[-1])
            if last:
                ctx = random.choice(AFTER_WITNESS_DEATH["any"])
                context = " " + ctx.replace("{last_victim}", last.name)
        return char.name + " (" + char.occupation + "): \"" + greeting + context + "\""

    def get_dialogue(self, char_id: str) -> list[DialogueOption]:
        """Returns investigative questions only — filler shown via auto_text."""
        char = self.characters.get(char_id)
        if not char or not char.alive:
            return []

        day      = self.state.day
        diff     = self.state.difficulty
        max_q    = _questions_per_day(diff)
        used_today = self.state.questions_asked_this_period.get(char.id, 0)
        base_cost  = _payment_cost(diff) if getattr(char, '_requires_payment', False) else 0

        victim_names = [self.characters[vid].name for vid in self.state.victims
                        if vid in self.characters]
        victim_str = victim_names[-1] if victim_names else "the victim"
        killer = self.characters[self.state.killer_id]
        is_neighbor = (char.district == killer.district)

        if char.is_killer:
            victim_hint = "I don't know who would do this."
        elif is_neighbor:
            victim_hint = "Someone in our district has been different lately. I can't say more without proof."
        else:
            victim_hint = "Whoever it is, they knew what they were doing."

        motive_hint = MOTIVE_CLUE.get(self.state.killer_motive, "Hard to say.")
        options: list[DialogueOption] = []
        char_clues = self.clue_holders.get(char.id, [])

        available_clues = [
            cid for cid in char_clues
            if cid in self.clues
            and not self.clues[cid].scene_only
            and self.clues[cid].day_available <= day
            and cid not in self.state.clues_found
        ]

        if victim_names:
            options.append(DialogueOption(
                key="vic_q",
                question=f"What was your relationship with {victim_str}?",
                response=victim_hint,
                cost=base_cost,
                requires_bond=0.0,
                value_tier=1,
            ))

        q_variants = [
            "Did you see anything unusual near the scene?",
            "Is there something you haven't told anyone?",
            "You seem like you know more than you're letting on.",
            "What have people been saying among themselves?",
        ]
        for i, clue_id in enumerate(available_clues):
            clue = self.clues[clue_id]
            bond_needed = 0.0 if i == 0 else 0.3 + (i - 1) * 0.15
            this_cost   = base_cost if char.bond >= bond_needed else 0
            if char.bond >= bond_needed:
                response      = clue.text
                cid_to_reveal = clue_id
            else:
                response      = "I'm not sure I should say. Come back when I know you better."
                cid_to_reveal = None
                this_cost     = 0
            options.append(DialogueOption(
                key=f"clue_{clue_id}",
                question=q_variants[i % len(q_variants)],
                response=response,
                clue_id=cid_to_reveal,
                requires_bond=bond_needed,
                cost=this_cost,
                value_tier=3 if cid_to_reveal else 2,
            ))

        if day >= 2 and (is_neighbor or char.occupation == killer.occupation) and not char.is_killer:
            hint_q = "Have you noticed anyone unusual around here lately?" if is_neighbor \
                     else "In your line of work, could someone do this unnoticed?"
            t2 = char.trait if char.trait in TRAIT_RESPONSES else "default"
            options.append(DialogueOption(
                key="local_hint",
                question=hint_q,
                response=random.Random(hash(char.id)).choice(GENERAL_RESPONSES.get(t2, GENERAL_RESPONSES["default"])),
                cost=0, requires_bond=0.0, value_tier=2,
            ))

        if len(self.state.victims) >= 2 and not char.is_killer:
            options.append(DialogueOption(
                key="pattern_q",
                question="Do you see a pattern in who is being targeted?",
                response=motive_hint,
                cost=base_cost // 2, requires_bond=0.2, value_tier=2,
            ))

        if char.id in self.state.protected_history[-5:]:
            unshared = [cid for cid in char_clues
                        if cid not in self.state.clues_found and cid in self.clues
                        and not self.clues[cid].scene_only and self.clues[cid].day_available <= day]
            if unshared:
                clue = self.clues[unshared[0]]
                options.append(DialogueOption(
                    key="protected_bonus",
                    question="You protected me. Is there something you can tell me?",
                    response=clue.text, clue_id=unshared[0],
                    cost=0, requires_bond=0.0, value_tier=3,
                ))

        if char.id in self.state.gossip:
            options.append(DialogueOption(
                key="gossip_today",
                question="Heard anything new today?",
                response=self.state.gossip[char.id],
                cost=0, requires_bond=0.0, value_tier=1,
            ))

        dist_closed_until = self.state.district_closed.get(char.district, 0)
        if self.state.hour < dist_closed_until and not char.is_killer:
            trait = char.trait if char.trait in DISTRICT_CLOSING else 'default'
            return [DialogueOption(
                key='guarded',
                question='Can we talk?',
                response=DISTRICT_CLOSING[trait].replace('{district}', char.district),
                cost=0, requires_bond=0.0,
            )]

        accused_until = self.state.accused_wrong_reaction.get(char.id, 0)
        if self.state.hour < accused_until and not char.is_killer:
            t2 = char.trait if char.trait in WRONG_ACCUSATION_REACTIONS else 'default'
            reaction = random.Random(hash(char.id) ^ int(self.state.hour)).choice(WRONG_ACCUSATION_REACTIONS[t2])
            return [DialogueOption(
                key='accusation_reaction',
                question='I need to speak with you.',
                response=reaction,
                cost=0, requires_bond=0.0,
            )]

        flavor_qs = [
            ("How are you holding up?", random.Random(hash(char.id)).choice(FEAR_RESPONSES.get(char.trait, FEAR_RESPONSES["default"]))),
            ("What do people around here say about all this?",
             random.Random(hash(char.id)+1).choice(GENERAL_RESPONSES.get(char.trait, GENERAL_RESPONSES["default"]))),
        ]
        for fq, fr in flavor_qs[:1]:
            options.append(DialogueOption(
                key=f"flavor_{fq[:8].replace(' ','_')}",
                question=fq, response=fr,
                cost=0, requires_bond=0.0, value_tier=0,
            ))

        rels = self._rels_for(char.id)
        for rel in rels[:2]:
            other = self._other_in_rel(rel, char.id)
            if rel.kind == RelKind.RIVAL:
                options.append(DialogueOption(
                    key=f"rel_rival_{rel.id}",
                    question=f"I heard you and {other} don't get along.",
                    response=f"Old business. But since you ask — I would not put anything past {other}.",
                    cost=0, requires_bond=0.2, value_tier=1,
                ))
            elif rel.kind == RelKind.DEBTOR and char.id == rel.person_a_id:
                options.append(DialogueOption(
                    key=f"rel_debt_{rel.id}",
                    question=f"Is it true you owe {other} money?",
                    response=f"That is a private matter. There is a debt. It has been stressful.",
                    cost=0, requires_bond=0.3, value_tier=1,
                ))
            elif rel.kind == RelKind.LOVER:
                options.append(DialogueOption(
                    key=f"rel_lover_{rel.id}",
                    question=f"Are you close with {other}?",
                    response=f"We are... friends. Why do you ask?",
                    cost=0, requires_bond=0.0,
                ))

        ct = CaseType(self.state.case_type)
        if ct == CaseType.CONSPIRACY and self.state.accomplice_id and not char.is_killer:
            accomplice = self.characters.get(self.state.accomplice_id)
            if accomplice and char.district == accomplice.district and char.bond >= 0.4:
                hint = random.Random(hash(char.id)+2).choice(CONSPIRACY_ACCOMPLICE_HINTS)
                ac_clue_id = next(
                    (cid for cid in self.clue_holders.get(char.id, [])
                     if cid.startswith("accomplice_") and cid not in self.state.clues_found),
                    None
                )
                options.append(DialogueOption(
                    key="conspiracy_hint",
                    question="Did you notice anything about who else might have been involved?",
                    response=hint,
                    clue_id=ac_clue_id,
                    cost=0, requires_bond=0.4, value_tier=3,
                ))

        if ct == CaseType.FRAME and char.is_killer and self.state.framed_id:
            framed = self.characters.get(self.state.framed_id)
            if framed:
                steer = random.Random(hash(char.id)+3).choice(KILLER_STEERING["frame"]).replace("{framed}", framed.name)
                options.append(DialogueOption(
                    key="frame_steer",
                    question="Do you have any idea who might be responsible?",
                    response=steer,
                    cost=0, requires_bond=0.0,
                ))

        if ct == CaseType.FRAME and self.state.framed_id == char.id:
            framed_rng = random.Random(hash(char.id) ^ 999)
            framed_response = framed_rng.choice(FRAMED_PERSON_ACCUSATION)
            options.append(DialogueOption(
                key="frame_innocent",
                question="Evidence points toward you. What do you say to that?",
                response=framed_response,
                cost=0, requires_bond=0.0,
            ))

        time_ctx = self._time_context()
        case_note = {
            "serial": "with another strike possible",
            "passion": "knowing the killer may flee",
            "conspiracy": "knowing more than one person was involved",
            "frame": "knowing someone may have been set up",
        }.get(self.state.case_type, "")
        suffix = (" " + case_note) if case_note else ""
        options.append(DialogueOption(
            key="time_q",
            question=f"What are people saying {time_ctx}{suffix}?",
            response=self.state.gossip.get(char.id,
                     random.Random(hash(char.id)).choice(FEAR_RESPONSES.get(char.trait, FEAR_RESPONSES["default"]))),
            cost=0, requires_bond=0.0,
            value_tier=1 if suffix else 0,
        ))

        return options

    def _rels_for(self, char_id: str) -> list:
        return [r for r in self.relationships.values()
                if r.person_a_id == char_id or r.person_b_id == char_id]

    def _other_in_rel(self, rel, char_id: str) -> str:
        return rel.person_b_name if rel.person_a_id == char_id else rel.person_a_name

    def _time_context(self) -> str:
        h = self.state.hour % 24
        if 5 <= h < 9:   return "early morning"
        if 9 <= h < 12:  return "this morning"
        if 12 <= h < 14: return "at midday"
        if 14 <= h < 18: return "this afternoon"
        if 18 <= h < 21: return "this evening"
        return "tonight"

    def detect_leads(self, speaker_id: str, category: str, response: str) -> list[dict]:
        """
        Scan a response for mentions of other characters.
        Returns list of leads (dicts) to create.
        Category determines what kind of lead to generate.
        """
        speaker = self.characters.get(speaker_id)
        if not speaker:
            return []
        new_leads = []
        existing_lead_keys = {(l["target_id"], l["source_id"]) for l in self.state.leads}

        for char in self.characters.values():
            if char.id == speaker_id or not char.alive:
                continue
            first = char.name.split()[0]
            if first.lower() not in response.lower() and char.name.lower() not in response.lower():
                continue
            if (char.id, speaker_id) in existing_lead_keys:
                continue

            if category == "alibi":
                question = f"{speaker.name} says they were with you that evening — is that true?"
                ctx = f"{speaker.name} mentioned you when asked about their alibi."
            elif category == "time":
                question = f"{speaker.name} says they saw something near you that night — what do you know about that?"
                ctx = f"{speaker.name} mentioned you when describing the night of the murder."
            elif category == "strangers":
                question = f"{speaker.name} mentioned you when describing unusual activity — can you explain?"
                ctx = f"{speaker.name} referred to you when asked about strangers."
            elif category == "victim":
                question = f"{speaker.name} mentioned you knew the victim — can you tell me more?"
                ctx = f"{speaker.name} connected you to the victim."
            else:
                question = f"{speaker.name} mentioned your name — what can you tell me about that?"
                ctx = f"{speaker.name} brought up your name."

            lead = {
                "id": f"lead_{speaker_id}_{char.id}_{category}",
                "target_id": char.id,
                "target_name": char.name,
                "source_id": speaker_id,
                "source_name": speaker.name,
                "question": question,
                "context": ctx,
                "category": category,
                "asked": False,
            }
            new_leads.append(lead)
            self.state.leads.append(lead)
            existing_lead_keys.add((char.id, speaker_id))

        return new_leads

    def get_leads_for(self, char_id: str) -> list[dict]:
        """Return unanswered leads targeting this character."""
        return [l for l in self.state.leads
                if l["target_id"] == char_id and not l["asked"]]

    def answer_lead(self, lead: dict, char) -> str:
        """Generate a response to a lead question."""
        lead["asked"] = True
        source = self.characters.get(lead["source_id"])
        s = self.state
        killer = self.characters[s.killer_id]
        rng = random.Random(hash(char.id) ^ hash(lead["id"]))

        cat = lead.get("category", "")
        source_is_killer = source and source.is_killer if source else False
        char_is_killer   = char.is_killer

        if cat == "alibi":
            shared_rel = next(
                (r for r in self.relationships.values()
                 if {r.person_a_id, r.person_b_id} == {char.id, lead["source_id"]}),
                None
            )
            if source_is_killer:
                return rng.choice([
                    f"With {source.name if source else 'them'}? No. We're barely acquainted.",
                    f"I wasn't with {source.name if source else 'anyone'} that evening. That's not right.",
                    f"I don't know why they'd say that. We didn't meet that night.",
                ])
            elif shared_rel:
                return rng.choice([
                    f"Yes, that's correct. We were together that evening.",
                    f"That's right. I can confirm that.",
                    f"We were together, yes. Is there something specific you need to know?",
                ])
            else:
                return rng.choice([
                    f"I don't recall being with {source.name if source else 'them'} that evening.",
                    f"We might have crossed paths briefly. I wouldn't call it 'together'.",
                    f"I'm not sure what {source.name if source else 'they'} means by that.",
                ])

        elif cat == "strangers":
            if source_is_killer:
                return rng.choice([
                    "I don't know why my name came up. I wasn't doing anything unusual.",
                    "I move around for my work. Someone might have noticed, but there's nothing to it.",
                    "I can explain my movements that night if needed.",
                ])
            else:
                return rng.choice([
                    "I was in the area, yes. For ordinary reasons.",
                    "If someone noticed me, they'd have seen nothing unusual.",
                    "I don't know what they saw, but it wasn't anything concerning.",
                ])

        t = char.trait if char else "default"
        fallbacks = {
            "aggressive": "I don't know what they're implying, but they'd better be careful.",
            "cautious":   "I'd rather know what exactly was said before I respond to it.",
            "loyal":      "If they mentioned me, there's probably a reason. I'll be honest with you.",
            "selfish":    "My name keeps coming up. I don't appreciate it.",
            "charismatic":"Interesting that they brought me up. Let me tell you my side.",
            "innovative": "The fact that my name appeared is itself significant. Think about why.",
        }
        return fallbacks.get(t, "I'm not sure what they meant by that.")

    """Mixin: Player actions — search, follow, blackmail, protect, reveal clues."""

    def search_location(self, location: str) -> tuple[bool, str]:
        """Search a district for physical evidence. Returns (found_something, narrative)."""
        s = self.state
        if location in s.weapon_locations and not s.weapon_found:
            wdesc = s.weapon_locations[location]
            wname = getattr(self, "_weapon_name", "weapon")
            s.weapon_found = wname
            s.action_log.append("Found weapon in " + location + ".")
            wmsg = "Searching carefully, you find something significant."
            return True, wmsg + chr(10) + wdesc + chr(10) + chr(10) + "Murder weapon identified: " + wname + "."
        killer = self.characters[s.killer_id]

        is_killer_district = (location == killer.district)
        has_scene = any(
            self.characters.get(vid) and
            (self.characters[vid].district == location or location in s.crime_scenes)
            for vid in self.victim_ids_in(location)
        )
        already_searched = location in s.searched_locations
        s.searched_locations.append(location)

        scene_victim = next(
            (self.characters[vid] for vid in s.crime_scenes
             if self.characters.get(vid) and self.characters[vid].district == location
             and vid not in s.scene_examined),
            None
        )

        if scene_victim:
            result = self.examine_scene(scene_victim.id)
            pool = SEARCH_RESULTS["scene"]
            found_clue = result and "Clue found:" in result
            template = random.choice(pool["found"] if found_clue else pool["nothing"])
            detail = result.split("Clue found:")[-1].strip() if found_clue else ""
            return found_clue, template.replace("{clue_text}", detail)

        if is_killer_district and not already_searched:
            details = [
                f"Someone matching a {killer.occupation}'s build was seen here recently.",
                f"A resident mentions unusual activity near the {killer.district} district edge.",
                f"You notice something left behind — consistent with a {killer.occupation}'s work.",
            ]
            detail = random.choice(details)
            if "alibi_break" not in s.clues_found and "alibi_break" in self.clues:
                self.clues["alibi_break"].found = True
                s.clues_found.append("alibi_break")
                detail += " " + self.clues["alibi_break"].text
            tmpl = random.choice(SEARCH_RESULTS["district"]["found"])
            return True, tmpl.replace("{district}", location).replace("{detail}", detail)

        tmpl = random.choice(SEARCH_RESULTS["district"]["nothing"])
        return False, tmpl.replace("{district}", location)

    def follow_character(self, char_id: str) -> str:
        """Tail a character for several hours. Returns narrative of what you observe."""
        char = self.characters.get(char_id)
        if not char or not char.alive:
            return "That person is not available."
        s = self.state
        killer = self.characters[s.killer_id]
        is_killer = char.is_killer

        if char_id in s.follow_results:
            return (f"You've already followed {char.name} recently. "
                    f"Previous observation: {s.follow_results[char_id]}")

        if is_killer:
            n_victims = len(s.victims)
            if n_victims >= 2:
                result = FOLLOW_RESULTS["killer_contact"].format(
                    name=char.name, district=killer.district)
            elif random.random() < 0.5:
                victim_name = self.characters[s.victims[0]].name if s.victims else "the victim"
                result = FOLLOW_RESULTS["killer_to_scene"].format(
                    name=char.name, victim=victim_name)
            else:
                result = FOLLOW_RESULTS["killer_at_home"].format(name=char.name)
            if "district_seen" not in s.clues_found and "district_seen" in self.clues:
                self.clues["district_seen"].found = True
                s.clues_found.append("district_seen")
                result += f" You note: {self.clues['district_seen'].text}"
        else:
            if char.trait in ("cautious", "innovative"):
                result = FOLLOW_RESULTS["innocent_nervous"].format(name=char.name)
            else:
                result = FOLLOW_RESULTS["innocent_routine"].format(name=char.name)

        s.follow_results[char_id] = result
        return result

    def blackmail(self, target_id: str, secret_id: str) -> tuple[bool, str]:
        """Use a known secret to extract a clue from the target."""
        if secret_id not in self.state.secrets_known:
            return False, "You don't have that information yet."
        secret = self.secrets.get(secret_id)
        if not secret:
            return False, "Unknown secret."
        if secret.about_id != target_id:
            return False, f"That secret is about {secret.about_name}, not them."
        target = self.characters.get(target_id)
        if not target or not target.alive:
            return False, "That person is not available."
        char_clues = self.clue_holders.get(target_id, [])
        unshared = [cid for cid in char_clues
                    if cid not in self.state.clues_found and cid in self.clues
                    and not self.clues[cid].scene_only and self.clues[cid].day_available <= self.state.day]
        narrative = f"{target.name} goes pale. You mention {secret.leverage}.\n"
        if unshared:
            clue = self.clues[unshared[0]]
            clue.found = True
            if clue.id not in self.state.clues_found:
                self.state.clues_found.append(clue.id)
            return True, narrative + f"They break. \"{clue.text}\""
        target.bond = max(0.0, target.bond - 0.3)
        return False, narrative + "They have nothing useful to give you."

    def secrets_about(self, target_id: str) -> list:
        return [s for s in self.secrets.values()
                if s.about_id == target_id and s.id in self.state.secrets_known]

    def examine_scene(self, victim_id: str) -> str:
        """Examine a crime scene to get physical clues."""
        if victim_id not in self.state.crime_scenes:
            return "There is no crime scene associated with that person."
        if victim_id in self.state.scene_examined:
            return "You have already examined this scene thoroughly."
        self.state.scene_examined.append(victim_id)
        victim = self.characters.get(victim_id)
        if not victim:
            return "Scene not found."

        scene_clues = [c for c in self.clues.values()
                       if c.scene_only and not c.found]
        results = []
        if scene_clues:
            clue = scene_clues[0]
            clue.found = True
            if clue.id not in self.state.clues_found:
                self.state.clues_found.append(clue.id)
            results.append(f"Clue found: {clue.text}")

        killer = self.characters[self.state.killer_id]
        physical = {
            "blunt_force":   "Heavy impact marks. Whoever did this had strength.",
            "sharp_blade":   "Clean cuts. Controlled. Someone who knows tools.",
            "poison":        "No signs of struggle. The victim trusted whoever gave it.",
            "strangulation": "Signs of a struggle. The killer was close, face to face.",
        }.get(self.state.killer_method, "The scene tells a story, but it's hard to read.")

        results.insert(0, f"You examine where {victim.name} was found.")
        results.append(physical)
        return "\n".join(results)

    def protect(self, char_id: str) -> tuple[bool, str]:
        """Protect one citizen today. Returns (success, message)."""
        if self.state.protected_this_period is not None:
            already = self.characters.get(self.state.protected_this_period)
            name = already.name if already else "someone"
            return False, f"You already protected {name} today. One person per day."
        char = self.characters.get(char_id)
        if not char or not char.alive:
            return False, "That person is not available."
        self.state.protected_this_period = char_id
        self.state.protected_history.append(char_id)
        char.bond = min(1.0, char.bond + 0.3)
        msg = char.name + " feels safer knowing you are watching. Bond strengthened. They may share more tomorrow."
        return True, msg

    def reveal_clue(self, clue_id: str) -> str:
        clue = self.clues.get(clue_id)
        if not clue or clue.found:
            return ""
        clue.found = True
        if clue_id not in self.state.clues_found:
            self.state.clues_found.append(clue_id)
        return clue.text

    def use_question(self, char_id: str, cost: int) -> tuple[bool, str]:
        """Spend a question slot (per 8h period) and optional money."""
        max_q = _questions_per_period(self.state.difficulty)
        used  = self.state.questions_asked_this_period.get(char_id, 0)
        if used >= max_q:
            word = "question" if max_q == 1 else f"{max_q} questions"
            hrs  = round(QUESTION_PERIOD - (self.state.hour - self.state.questions_period_start))
            return False, (f"You've asked your {word} for this period. "
                           f"Try again in ~{max(1,hrs)}h.")
        if cost > 0 and self.state.money < cost:
            return False, f"They want {cost}g. You have {round(self.state.money)}g."
        self.state.questions_asked_this_period[char_id] = used + 1
        if cost > 0:
            self.state.money -= cost
        return True, ""

    def victim_ids_in(self, district: str) -> list[str]:
        return [vid for vid in self.state.victims
                if self.characters.get(vid) and
                self.characters[vid].district == district]

    def _is_accomplice(self, char_id: str) -> bool:
        return self.state.accomplice_id == char_id

    def begin_confrontation(self, char_id: str) -> tuple:
        char = self.characters.get(char_id)
        if not char or not char.alive:
            return None, "That person is not here."
        if not self.state.weapon_found:
            return None, ("You need to identify the murder weapon first. Search the districts.")
        ct = CaseType(self.state.case_type)
        s = self.state

        if ct == CaseType.FRAME and s.framed_id == char_id and s.hour < 12.0 and len(s.clues_found) < 2:
            return None, (
                f"You move toward {char.name}, but something stops you. "
                f"The evidence is there — but it arrived very quickly. "
                f"Look deeper before committing."
            )

        min_clues = 1 if self._is_accomplice(char_id) else 2
        if len(s.clues_found) < min_clues:
            return None, (f"You need at least {min_clues} clue(s) before confronting. "
                          f"You have {len(s.clues_found)}.")
        s.accusation_count += 1
        return ConfrontationState(suspect_id=char_id), ""

    def confrontation_clues(self, char_id: str, conf) -> list:
        char = self.characters.get(char_id)
        is_killer = char and char.is_killer
        s = self.state
        result_clues = []
        for cid in s.clues_found:
            if cid in conf.clues_presented:
                continue
            clue = self.clues.get(cid)
            if not clue:
                continue
            char_val = getattr(char, clue.attribute, None)
            clue_vals = clue.value.split("|")
            matches_suspect = char_val in clue_vals
            is_lie = clue.is_lie or cid in s.corrupted_clues
            trait = char.trait if char and char.trait in CONFRONTATION_PRESSURE["high"] else "default"
            stage = ("breaking" if conf.pressure >= 0.6 else
                     "high"     if conf.pressure >= 0.3 else "mid")
            is_accomplice = self._is_accomplice(char_id)
            if (is_killer or is_accomplice) and not is_lie and matches_suspect:
                delta = random.uniform(0.22, 0.32) if is_accomplice else random.uniform(0.25, 0.35)
                if is_accomplice:
                    response = ACCOMPLICE_PRESSURE[stage]
                else:
                    response = CONFRONTATION_PRESSURE[stage][trait]
            elif is_lie and matches_suspect:
                delta = -0.10
                response = random.choice(CLUE_REBUTTAL["lie"])
            elif matches_suspect:
                delta = 0.08
                response = CONFRONTATION_PRESSURE["low"].get(trait, "That doesn't prove what you think.")
            else:
                delta = 0.04
                response = random.choice(CLUE_REBUTTAL["irrelevant"])
            if not is_killer and not self._is_accomplice(char_id):
                stage_key = ("breaking" if conf.pressure >= 0.6 else
                             "high"     if conf.pressure >= 0.3 else
                             "mid"      if conf.pressure >= 0.15 else "low")
                if self.state.framed_id == char_id:
                    response = random.choice(FRAMED_PERSON_ACCUSATION)
                else:
                    response = INNOCENT_RESPONSES[stage_key]
                delta = min(delta, 0.12)
            result_clues.append(ConfrontationClue(
                clue_id=cid, text=clue.text,
                attribute=clue.attribute, is_genuine=(not is_lie and matches_suspect),
                pressure_delta=delta, suspect_response=response,
            ))
        return result_clues

    def present_clue(self, conf, clue) -> tuple:
        char = self.characters.get(conf.suspect_id)
        s = self.state
        conf.clues_presented.append(clue.clue_id)
        conf.pressure = max(0.0, min(1.0, conf.pressure + clue.pressure_delta))
        is_killer = char and char.is_killer
        trait = char.trait if char else "default"
        if conf.pressure >= 0.80:
            conf.stage = "breaking"
        elif conf.pressure >= 0.60:
            conf.stage = "high"
        elif conf.pressure >= 0.30:
            conf.stage = "mid"
        else:
            conf.stage = "low"
        narrative = clue.suspect_response
        ct = CaseType(s.case_type)

        if conf.pressure >= 0.80:
            if is_killer:
                if ct == CaseType.CONSPIRACY and s.accomplice_id and not s.accomplice_found:
                    conf.resolved = True
                    conf.outcome = "confessed_partial"
                    break_line = CONFRONTATION_PRESSURE["breaking"].get(
                        trait, CONFRONTATION_PRESSURE["breaking"]["default"])
                    result = ScenarioResult(
                        won=False,
                        message=(char.name + " breaks.\n\"" + break_line + "\"\n\n"
                                 "They admit to the murder — but name an accomplice.\n"
                                 "The town holds " + char.name + ", but the accomplice is still free.\n"
                                 "Find them and confront them to close the case."),
                        days=s.day,
                    )
                    s.accomplice_found = False
                    return narrative, result

                conf.resolved = True
                conf.outcome = "confessed"
                break_line = CONFRONTATION_PRESSURE["breaking"].get(
                    trait, CONFRONTATION_PRESSURE["breaking"]["default"])
                result = ScenarioResult(
                    won=True,
                    message=(char.name + " breaks.\n\"" + break_line + "\"\n\n"
                             "The " + char.occupation + " from " + char.district + " district confesses.\n"
                             "Motive: " + s.killer_motive + ".\n\n"
                             + self.town_name + " can finally breathe again."),
                    days=s.day,
                )
                return narrative, result

            if self._is_accomplice(char.id):
                conf.resolved = True
                conf.outcome = "accomplice_confessed"
                s.accomplice_found = True
                result = ScenarioResult(
                    won=False,
                    message=(char.name + " admits to their part.\n\"" +
                             ACCOMPLICE_PRESSURE["breaking"] + "\"\n\n"
                             "They name the person who carried out the murder.\n"
                             "Now confront the killer directly to close the case."),
                    days=s.day,
                )
                return narrative, result

            if ct == CaseType.FRAME and s.framed_id == char.id:
                conf.resolved = True
                conf.outcome = "frame_collapsed"
                real_killer = self.characters[s.killer_id]
                result = ScenarioResult(
                    won=False,
                    message=(char.name + " breaks — but what they say doesn\'t add up.\n"
                             "\"I didn\'t do this. I couldn\'t have. Look at the dates.\"\n\n"
                             "They were framed. The real killer — " + real_killer.name + "\n"
                             "— planted the evidence. You pursued the wrong person.\n\n"
                             "Go back and look harder."),
                    days=s.day,
                )
                return narrative, result

            conf.resolved = True
            conf.outcome = "collapsed_innocent"
            real_killer = self.characters[s.killer_id]
            s.accused_wrong_reaction[char.id] = s.hour + 8.0
            if char.district not in s.district_closed:
                s.district_closed[char.district] = s.hour + 3.0
            s.killer_heat = min(1.0, s.killer_heat + 0.12)
            result = ScenarioResult(
                won=False,
                message=(char.name + " breaks under pressure.\n"
                         "They were innocent. The real killer — " + real_killer.name +
                         " — watches from the crowd.\n\n"
                         "The wrongly accused will refuse to speak for a while.\n"
                         "When they do — listen carefully. They may know who did this."),
                days=s.day,
            )
            return narrative, result

        return narrative, None

    def withdraw_confrontation(self, conf) -> str:
        self.state.accusation_count -= 1
        self.state.killer_heat = min(1.0, self.state.killer_heat + 0.10)
        conf.resolved = True
        conf.outcome = "withdrew"
        char = self.characters.get(conf.suspect_id)
        if char:
            return ("You step back.\n"
                    + char.name + " watches you go, expression unreadable.\n"
                    "You can return when you have more.")
        return "You step back."

    def opening_line(self, char_id: str) -> str:
        char = self.characters.get(char_id)
        if not char:
            return ""
        if self._is_accomplice(char_id):
            return random.Random(hash(char_id)).choice([
                ACCOMPLICE_OPENING["first"],
                ACCOMPLICE_OPENING["deny"],
            ])
        ct = CaseType(self.state.case_type)
        if ct == CaseType.FRAME and self.state.framed_id == char_id:
            return random.choice(FRAMED_PERSON_ACCUSATION)
        trait = char.trait if char.trait in CONFRONTATION_OPENING else "default"
        return random.Random(hash(char_id)).choice(CONFRONTATION_OPENING[trait])

    def snapshot(self) -> dict:
        s = self.state
        chars = []
        for c in self.characters.values():
            known = c.id in s.known_chars
            chars.append({
                "id": c.id,
                "name": c.name,
                "occupation": c.occupation if known else "?",
                "district": c.district,
                "trait": c.trait if known else "",
                "alive": c.alive, "bond": round(c.bond, 2),
                "portrait": c.portrait,
                "is_accused": c.id in s.accused_wrong,
                "known": known,
            })
        suspects = self._compute_suspects_snap()
        clues = [
            {"id": cl.id, "text": cl.text, "attribute": cl.attribute,
             "found": cl.found, "value": cl.value,
             "narrows_suspects": cl.narrows_suspects, "is_lie": cl.is_lie}
            for cl in self.clues.values()
        ]
        victim_names = [self.characters[v].name for v in s.victims
                        if v in self.characters]
        return {
            "scenario_type": "murderer",
            "scenario_name": f"The Murderer — {self.town_name}",
            "town_name": self.town_name,
            "day": s.day, "hour": round(s.hour, 1), "time_str": _format_time(s.hour),
            "victims": len(s.victims),
            "max_victims": s.max_victims,
            "victim_names": victim_names,
            "hours_to_strike": round(max(0, s.next_strike_hour - s.hour), 1),
            "clues_found": len(s.clues_found),
            "total_clues": len(self.clues),
            "accusation_count": s.accusation_count,
            "player_location": s.player_location,
            "characters": chars,
            "clues": clues,
            "suspects": suspects,
            "events": self.events[-20:],
            "pressure_pct": round(len(s.victims) / s.max_victims * 100),
            "case_type": s.case_type,
            "heat_actions_count": len(s.heat_actions),
            "killer_agenda_visible": self.agenda_signals_available(),
            "district_closed": {k: round(v,1) for k,v in s.district_closed.items()},
            "world_reactions": s.world_reactions[-5:],
            "accomplice_found": s.accomplice_found,
            "accomplice_suspects": (self._compute_accomplice_suspects()
                                    if s.case_type == "conspiracy" and not s.accomplice_found
                                    else []),
            "killer_fleeing": s.killer_fleeing,
            "relationships": [
                {"a": r.person_a_name, "b": r.person_b_name, "kind": r.kind.value}
                for r in self.relationships.values()
                if r.id in s.secrets_known or True
            ][:6],
            "money": round(s.money),
            "difficulty": s.difficulty,
            "secrets_known": len(s.secrets_known),
            "weapon_found": s.weapon_found,
            "weapon_name": getattr(self, "_weapon_name", ""),
            "weapon_district": getattr(self, "_weapon_district", ""),
            "questions_remaining": max(0, _questions_per_day(s.difficulty) -
                                       max(s.questions_asked_this_period.values() or [0])),
        }

    def _compute_suspects_snap(self) -> list[dict]:
        """Compute current suspect list from found genuine clues.

        Accomplice-specific clues (accomplice_*) are excluded from the main
        killer suspect pool — they narrow the accomplice separately.
        Lies and non-narrowing clues are also excluded.
        """
        found = [c for c in self.clues.values() if c.found]
        valid_attrs = {"occupation", "district", "trait"}
        chars = [c for c in self.characters.values() if c.alive]

        killer_clues = [
            cl for cl in found
            if cl.narrows_suspects
            and not cl.is_lie
            and not cl.id.startswith("accomplice_")
            and cl.attribute in valid_attrs
        ]

        for clue in killer_clues:
            vals = clue.value.split("|")
            chars = [c for c in chars if getattr(c, clue.attribute, None) in vals]

        return [{"name": c.name, "occupation": c.occupation, "district": c.district}
                for c in chars]

    def _compute_accomplice_suspects(self) -> list[dict]:
        """Compute suspects for the accomplice role (conspiracy cases only)."""
        found = [c for c in self.clues.values()
                 if c.found and c.id.startswith("accomplice_")
                 and not c.is_lie and c.narrows_suspects]
        valid_attrs = {"occupation", "district", "trait"}
        chars = [c for c in self.characters.values()
                 if c.alive and not c.is_killer]
        for clue in found:
            if clue.attribute in valid_attrs:
                vals = clue.value.split("|")
                chars = [c for c in chars
                         if getattr(c, clue.attribute, None) in vals]
        return [{"name": c.name, "occupation": c.occupation, "district": c.district}
                for c in chars]

    def status_lines(self) -> list[str]:
        s = self.state
        victims = len(s.victims)
        found   = len(s.clues_found)
        alive   = len([c for c in self.characters.values() if c.alive and not c.is_killer])
        hours_to_strike = max(0.0, s.next_strike_hour - s.hour)
        danger = "TONIGHT" if hours_to_strike < 6 else f"~{round(hours_to_strike)}h"
        q_max  = _questions_per_period(s.difficulty)
        q_used = max((s.questions_asked_this_period.get(c,0) for c in s.questions_asked_this_period), default=0)
        q_left = q_max - q_used
        lines = [
            f"Town: {self.town_name}  |  {_format_time(s.hour)}",
            f"Victims: {victims}/{s.max_victims}  |  Next strike: {danger}",
            f"Clues: {found}  |  Witnesses alive: {alive}  |  Money: {round(s.money)}g",
            f"Location: {s.player_location}  |  Questions left this period: {q_left}/{q_max}",
        ]
        agenda_signals = self.agenda_signals_available()
        for sig in agenda_signals:
            lines.append(f"⚠ {sig}")

        ct = CaseType(s.case_type)
        if ct == CaseType.CONSPIRACY and s.accomplice_id:
            acc = self.characters.get(s.accomplice_id)
            acc_status = "IDENTIFIED" if s.accomplice_found else "unknown"
            lines.append(f"Case type: CONSPIRACY | Accomplice: {acc_status}")
        elif ct == CaseType.FRAME and s.framed_id:
            framed = self.characters.get(s.framed_id)
            frame_status = "planted evidence found" if "frame_counter" in s.clues_found else "watch for planted evidence"
            lines.append(f"Case type: FRAME | {frame_status}")
        elif ct == CaseType.PASSION:
            hours_to_flee = max(0, s.flee_hour - s.hour)
            if hours_to_flee < 12:
                lines.append(f"Case type: PASSION | Killer may flee in ~{round(hours_to_flee)}h")
            else:
                lines.append(f"Case type: PASSION | Single murder — find them before they leave")
        if s.accused_wrong:
            wrong_names = [self.characters[i].name for i in s.accused_wrong if i in self.characters]
            lines.append(f"Wrong accusations: {', '.join(wrong_names)}")
        if s.secrets_known:
            lines.append(f"Secrets known: {len(s.secrets_known)}")
        return lines

    def nearby_chars(self, location: str) -> list[Character]:
        return [c for c in self.characters.values()
                if c.alive and c.district == location]

    def all_locations(self) -> list[str]:
        return list(set(c.district for c in self.characters.values()))
