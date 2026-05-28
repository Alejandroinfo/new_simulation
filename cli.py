import cmd, sys, argparse, platform, random, json
import server as _ws_server

_COMPLETER = "none"
readline = None

if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7
        )
    except Exception:
        pass
    try:
        import colorama
        colorama.init(autoreset=False, strip=False, convert=True)
    except ImportError:
        pass
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer as PTCompleter, Completion
        _COMPLETER = "prompt_toolkit"
    except ImportError:
        try:
            from pyreadline3 import Readline as _PyRL3
            _rl3 = _PyRL3()
            class _ReadlineShim:
                def set_completer(self, fn):        _rl3.set_completer(fn)
                def set_completer_delims(self, s):  _rl3.set_completer_delims(s)
                def parse_and_bind(self, s):        _rl3.parse_and_bind(s)
                def get_line_buffer(self):          return _rl3.get_line_buffer()
            readline = _ReadlineShim()
            _COMPLETER = "pyreadline3"
        except Exception:
            _COMPLETER = "none"
else:
    try:
        import readline
        _COMPLETER = "readline"
    except ImportError:
        _COMPLETER = "none"

from scenarios.base import DialogueOption, ScenarioResult
from scenarios.murderer import MurdererScenario

class C:
    R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"
    CY="\033[96m"; DIM="\033[90m"; BLD="\033[1m"; RST="\033[0m"

def col(c, t):  return c + t + C.RST
def bold(t):    return C.BLD + t + C.RST
def ok(t):      return col(C.G, t)
def err(t):     return col(C.R, t)
def warn(t):    return col(C.Y, t)
def info(t):    return col(C.CY, t)
def dim(t):     return col(C.DIM, t)


SCENARIOS = {
    "1": ("The Murderer", "Find the killer before they strike again.", MurdererScenario),
}


def pick_scenario(seed) -> object:
    if seed is None:
        try:
            raw = input(dim("  Seed (blank=random): ")).strip()
            seed = int(raw) if raw else random.randint(1, 99999)
        except (ValueError, EOFError):
            seed = random.randint(1, 99999)
        print(dim(f"  Using seed: {seed}"))
    print()
    print(col(C.Y, "=" * 54))
    print("  " + bold("TOWN SIMULATION") + " — Choose a scenario")
    print(col(C.Y, "=" * 54))
    print()
    for key, (name, desc, _) in SCENARIOS.items():
        print(f"  {info(key)}.  {bold(name)}")
        print(f"       {dim(desc)}")
        print()
    choice = input(info("  Pick (1/2/3): ")).strip()

    name, desc, cls = SCENARIOS[choice]
    print()
    print(info(f"  Loading '{name}'..."))
    print()

    kwargs = {"seed": seed}
    if cls == MurdererScenario:
        print(dim("  Difficulty 1-20  (1=novice · 5=investigator · 10=detective · 15=inspector · 20=mastermind)"))
        raw = input(dim("  Difficulty [5]: ")).strip() or "5"
        try:
            diff = max(1, min(20, int(raw)))
        except ValueError:
            diff = 5
        kwargs["difficulty"] = diff
    return cls(**kwargs)


def _make_pt_session(cli_instance):
    """Build a prompt_toolkit PromptSession with dynamic completion."""
    if _COMPLETER != "prompt_toolkit":
        return None
    try:
        class _DynamicCompleter(PTCompleter):
            def get_completions(self, document, complete_event):
                text  = document.text_before_cursor
                word  = document.get_word_before_cursor()
                parts = text.strip().split()
                cmd_name = ""
                if len(parts) > 1 or (parts and text.endswith(" ")):
                    cmd_name = parts[0].lower()
                if cmd_name == "go":
                    if hasattr(cli_instance.scenario, "go"):
                        pool = ["north","south","east","west"]
                    else:
                        pool = sorted(set(
                            c.district for c in cli_instance.scenario.characters.values()
                            if c.alive
                        ))
                    for w in pool:
                        if w.startswith(word.lower()):
                            yield Completion(w, -len(word))
                elif cmd_name == "load":
                    import glob
                    saves = sorted(set(glob.glob("save_*.json") + glob.glob("*.json")))
                    for s in saves:
                        if s.startswith(word.lower()): yield Completion(s, -len(word))
                elif cmd_name in {"talk","protect","accuse","examine"}:
                    chars = [c for c in cli_instance.scenario.characters.values() if c.alive]
                    seen = set()
                    for c in chars:
                        fn = c.name.split()[0].lower()
                        if fn not in seen and fn.startswith(word.lower()):
                            seen.add(fn); yield Completion(fn, -len(word))
                        fl = c.name.lower()
                        if fl not in seen and fl.startswith(word.lower()):
                            seen.add(fl); yield Completion(fl, -len(word))
                elif not cmd_name:
                    for a in cli_instance.scenario.actions:
                        if a.startswith(word.lower()):
                            yield Completion(a, -len(word))
        from prompt_toolkit.formatted_text import HTML
        return PromptSession(
            completer=_DynamicCompleter(),
            complete_while_typing=False,
            message=HTML('<ansicyan>[&gt;] </ansicyan>'),
        )
    except Exception:
        return None


def _wrap(text: str, width: int = 72, indent: str = "  ") -> list[str]:
    """Wrap text to terminal width, respecting existing newlines."""
    import textwrap
    result = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            result.append("")
        else:
            wrapped = textwrap.fill(paragraph, width=width,
                                    subsequent_indent=indent)
            result.extend(wrapped.split("\n"))
    return result
class GameCLI(cmd.Cmd):
    prompt = info("[>] ")
    intro  = ""

    def __init__(self, scenario):
        super().__init__()
        self.scenario = scenario
        self.talk_state: dict = {}
        self._pending_events: list[str] = []
        self._conversation_log: list[dict] = []
        self._active_char_id = None
        if _COMPLETER == "prompt_toolkit":
            self._pt_session = _make_pt_session(self)
        elif readline is not None:
            try:
                readline.set_completer(self._complete)
                readline.set_completer_delims(" \t\n")
                if platform.system() == "Darwin":
                    readline.parse_and_bind("bind ^I rl_complete")
                else:
                    readline.parse_and_bind("tab: complete")
            except Exception:
                pass
        else:
            self._pt_session = None

    def _complete(self, text, state):
        if state == 0:
            self._tab_opts = self._build_opts(text)
        try:
            return self._tab_opts[state]
        except IndexError:
            return None

    def _build_opts(self, text):
        tl = text.lower()
        all_actions = self.scenario.actions
        try:
            line = readline.get_line_buffer() if readline else ""
        except Exception:
            line = ""
        parts = line.strip().split()
        cmd = parts[0].lower() if parts and (len(parts) > 1 or line.endswith(" ")) else ""

        if cmd == "load":
            import glob
            saves = sorted(set(glob.glob("save_*.json") + glob.glob("*.json")))
            return [s for s in saves if s.startswith(tl)]
        if cmd == "go":
            if hasattr(self.scenario, "go"):
                pool = ["north","south","east","west"]
            else:
                pool = sorted(set(
                    c.district for c in self.scenario.characters.values() if c.alive
                ))
            return [o for o in pool if o.startswith(tl)]

        cmd_opts = [a for a in all_actions if a.startswith(tl)]
        if cmd_opts:
            return cmd_opts
        loc = (getattr(self.scenario.state, "player_location", None)
               or getattr(self.scenario.state, "player_room", ""))
        here = self.scenario.nearby_chars(loc)
        if cmd in {"talk", "protect"}:
            pool = here  
        else:
            here_ids = {c.id for c in here}
            rest = [c for c in self.scenario.characters.values()
                    if c.alive and c.id not in here_ids]
            pool = list(here) + rest

        seen: set = set()
        result = []
        for c in pool:
            if not c.alive: continue
            for n in [c.name.split()[0].lower(), c.name.lower()]:
                if n not in seen and n.startswith(tl):
                    seen.add(n); result.append(n)
        return result

    def _print_scenario_events(self):
        for ev in self._pending_events:
            print()
            print("  " + col(C.Y, "! ") + ev)
        self._pending_events.clear()

    def _resolve_char(self, query: str):
        if not query:
            return None, "Provide a name."
        ql = query.lower()
        matches = [c for c in self.scenario.characters.values()
                   if ql in c.name.lower() and c.alive]
        if not matches:
            return None, f"No one named '{query}'."
        if len(matches) == 1:
            return matches[0], None
        print(warn(f"  Multiple matches for '{query}':"))
        for i, c in enumerate(matches[:6], 1):
            print(f"    {i}. {c.name} ({c.occupation})")
        try:
            idx = 0  
            if 0 <= idx < len(matches):
                return matches[idx], None
        except (ValueError, KeyboardInterrupt, EOFError):
            pass
        return None, "Selection cancelled."

    def _show_banner(self):
        self._export()
        s = self.scenario
        print()
        print(col(C.Y, "=" * 56))
        print("  " + bold(s.name.upper()))
        print(col(C.Y, "=" * 56))
        print()
        ct_val = getattr(getattr(s,'state',None),'case_type','')
        if ct_val:
            ct_labels = {'serial':'[SERIAL]','passion':'[PASSION]',
                         'conspiracy':'[CONSPIRACY]','frame':'[FRAME]'}
            ct_colors = {'serial':C.R,'passion':C.Y,'conspiracy':C.CY,'frame':C.Y}
            label = col(ct_colors.get(ct_val, C.RST), ct_labels.get(ct_val,ct_val.upper()))
            print('  ' + label + dim('  — case type'))
            print()
        for line in s.premise.split("\n"):
            print("  " + line)
        print()
        if hasattr(s, "events") and s.events:
            print("  " + col(C.R, "» ") + s.events[0])
        print()
        print(dim("  Type 'help' for available actions."))
        print(dim("  Type 'status' to see the current situation."))
        print()

    def _advance(self, days: int = 1):
        """Legacy: advance N days. Prefer _spend_time for murderer."""
        return self._spend_time(days * 24.0)

    def _spend_time(self, hours: float) -> bool:
        """Advance the clock by hours, print time and events, check end."""
        s = getattr(self.scenario, "state", None)
        if s is None:
            return False

        if hasattr(self.scenario, "advance_time"):
            events = self.scenario.advance_time(hours)
        else:
            events = self.scenario.step()
        self._pending_events.extend(events)

        if hasattr(s, "hour"):
            from scenarios.murderer import _format_time
            print(dim(f"  [{_format_time(s.hour)}]  (+{hours:.0f}h)"))
        elif hasattr(s, "day"):
            print(dim(f"  [Day {s.day}]"))

        result = self.scenario.check_end()
        if result:
            self._end_game(result)
            return True
        self._export()
        return False

    def _end_game(self, result: ScenarioResult):
        print()
        border = col(C.G if result.won else C.R, "=" * 56)
        print(border)
        if result.won:
            print("  " + bold("VICTORY"))
        else:
            print("  " + bold("DEFEAT"))
        print(border)
        print()
        for line in result.message.split("\n"):
            print("  " + line)
        print()
        import time; time.sleep(1.5)  
        sys.exit(0)

    def _export(self, active_char_id=None):
        import sys
        try:
            if not hasattr(self.scenario, 'snapshot'):
                return
            data = self.scenario.snapshot()
            data['conversation_log'] = self._conversation_log[-30:]
            data['active_char_id'] = active_char_id or self._active_char_id
            _ws_server.push_state(data)
            sys.stderr.write('[ws] exported: ' + str(data.get('scenario_type')) + chr(10))
        except Exception as _e:
            import traceback
            sys.stderr.write('[ws] export error: ' + str(_e) + chr(10))
            traceback.print_exc(file=sys.stderr)

    def do_status(self, arg):
        print()
        for line in self.scenario.status_lines():
            print("  " + info("│ ") + line)
        self._print_scenario_events()
        print()

    def do_nearby(self, arg):
        location = getattr(self.scenario.state, "player_location",
                           getattr(self.scenario.state, "player_room", "?"))
        chars = self.scenario.nearby_chars(location)
        known = getattr(self.scenario.state, "known_chars", [])
        print()
        print("  " + bold(f"You are in: {location} district"))
        if not chars:
            print("  " + dim("Nobody else here."))
        else:
            print("  " + bold("People here:"))
            for c in chars:
                if c.id in known:
                    print(f"    {c.portrait} {c.name} ({c.occupation})")
                else:
                    print(f"    {c.portrait} {c.name} {dim('— talk to learn more')} ")
        print()

    def _current_location(self) -> str:
        s = self.scenario.state
        return getattr(s, "player_location", getattr(s, "player_room", ""))

    def _resolve_char_here(self, query: str):
        """Resolve a character name restricted to the player's current location."""
        location = self._current_location()
        here = set(c.id for c in self.scenario.nearby_chars(location))
        if not query:
            return None, "Provide a name."
        ql = query.lower()
        matches = [
            c for c in self.scenario.characters.values()
            if ql in c.name.lower() and c.alive and c.id in here
        ]
        if not matches:
            elsewhere = [
                c for c in self.scenario.characters.values()
                if ql in c.name.lower() and c.alive and c.id not in here
            ]
            if elsewhere:
                e = elsewhere[0]
                return None, (
                    f"{e.name} is not here — they are in the {e.district} district. "
                    f"Use 'go {e.district}' to find them, or 'nearby' to see who is here."
                )
            return None, f"No one named '{query}' is here. Use 'nearby' to see who is around."
        if len(matches) == 1:
            return matches[0], None
        print(warn(f"  Multiple matches for '{query}':"))
        for i, c in enumerate(matches[:6], 1):
            print(f"    {i}. {c.name} ({c.occupation})")
        try:
            idx = 0  
            if 0 <= idx < len(matches):
                return matches[idx], None
        except (ValueError, KeyboardInterrupt, EOFError):
            pass
        return None, "Selection cancelled."

    def do_talk(self, arg):
        if not arg.strip():
            print(err("  Usage: talk <name>"))
            self.do_nearby("")
            return
        char, errmsg = self._resolve_char_here(arg.strip())
        if not char:
            print(err("  " + errmsg))
            return
        is_murderer = hasattr(self.scenario, "begin_confrontation")
        char.bond = min(1.0, char.bond + 0.1)
        self._active_char_id = char.id
        self._export(active_char_id=char.id)
        if hasattr(self.scenario, "auto_text"):
            at = self.scenario.auto_text(char.id)
            if at:
                print()
                for atl in _wrap(at, width=70, indent="    "):
                    print("  " + dim("~ ") + atl)
        if not is_murderer:
            self._do_talk_legacy(char)
        else:
            self._do_talk_categories(char)
        self._active_char_id = None
        self._export()
        try:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getwch()
        except ImportError:
            import termios, sys
            try:
                termios.tcflush(sys.stdin, termios.TCIFLUSH)
            except Exception:
                pass
        if self._spend_time(1.0):
            return
        self._print_scenario_events()

    def _do_talk_legacy(self, char):
        options = self.scenario.get_dialogue(char.id)
        if not options:
            print(err(f"  {char.name} has nothing to say."))
            return
        while True:
            print()
            print("  " + bold(f"Speaking with {char.name}") + dim(f"  ({char.occupation})"))
            print()
            available = []
            for opt in options:
                if opt.asked:
                    continue
                if char.bond < opt.requires_bond:
                    print(dim(f"    [needs more trust] {opt.question}"))
                    continue
                available.append(opt)
            if not available:
                print(dim("  Nothing more to ask."))
                print()
                break
            for i, opt in enumerate(available, 1):
                cost_tag = warn(f" [{opt.cost}g]") if opt.cost > 0 else ""
                print(f"  {info(str(i) + '.')} {opt.question}{cost_tag}")
            print(f"  {info('0.')} Leave")
            print()
            try:
                choice = self._read_input("  > ")
            except (EOFError, KeyboardInterrupt):
                break
            if choice == "0" or choice.lower() in ("leave", "exit", "back"):
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(available):
                    chosen = available[idx]
                    chosen.asked = True
                    print()
                    for line in chosen.response.split("\n"):
                        print("  " + col(C.CY, "| ") + line)
                    print()
            except ValueError:
                pass

    def _cat_response(self, cat, char) -> str:
        """
        Generate a response based on trait, knowledge, and relationships.
        The killer gets NO special responses — they answer like anyone else
        would given what they know. The player must deduce from clue consistency.
        """
        import random as _rng
        s  = self.scenario.state
        killer = self.scenario.characters[s.killer_id]
        rng = _rng.Random(hash(char.id) ^ hash(cat) ^ s.day)

        victim = self.scenario.characters.get(s.victims[-1]) if s.victims else None
        vname  = victim.name if victim else "the victim"
        t      = char.trait
        near_scene = char.district == killer.district
        same_trade = char.occupation == killer.occupation
        rels = [r for r in self.scenario.relationships.values()
                if r.person_a_id == char.id or r.person_b_id == char.id]
        rel_others = [
            (r.person_b_name if r.person_a_id == char.id else r.person_a_name,
             r.kind.value)
            for r in rels
        ]

        has_secret = any(
            s_obj.about_id == char.id or s_obj.holder_id == char.id
            for s_obj in self.scenario.secrets.values()
            if s_obj.id in s.secrets_known
        )
        evasive = has_secret or t in ("selfish",) or rng.random() < 0.15
        if cat == "location":
            if near_scene:
                responses = {
                    "aggressive": [
                        f"Something changed in {killer.district} after it happened. I notice things.",
                        f"The {killer.district} district isn't what it was. There's someone there I've been watching.",
                        f"I've lived in {killer.district} long enough to know when something's off.",
                    ],
                    "cautious": [
                        f"I've been paying close attention to {killer.district} district. More than usual.",
                        f"There's been unusual movement in {killer.district}. I wrote down what I saw.",
                        f"I keep to myself but I notice. {killer.district} district has been tense.",
                    ],
                    "loyal": [
                        f"I know {killer.district} well. And something has been wrong there since the murder.",
                        f"I've lived near {killer.district} for years. The feel of the place is different now.",
                        f"Someone in {killer.district} district has not been themselves since it happened.",
                    ],
                    "charismatic": [
                        f"People tell me things. From {killer.district}, I've been hearing things that trouble me.",
                        f"Word from {killer.district} district is that someone has been on edge.",
                        f"I've talked to enough people in {killer.district} to know something is off.",
                    ],
                    "innovative": [
                        f"The pattern points back to {killer.district}. I've been thinking through it.",
                        f"Whoever did this has ties to {killer.district}. The evidence, when you look at it right, is clear.",
                        f"I've mapped out the movements I've observed. {killer.district} district is the center.",
                    ],
                    "selfish": [
                        f"I'm in {killer.district} district and I want nothing to do with any of this.",
                        f"Something happened in {killer.district}. I saw enough to know that much.",
                        f"I mind my own affairs. But yes, something is wrong in {killer.district}.",
                    ],
                }
                pool = responses.get(t, responses["loyal"])
                return rng.choice(pool)
            elif same_trade:
                return rng.choice([
                    f"In our trade you notice things. Someone with {char.occupation} skills has been somewhere they shouldn't.",
                    f"The {char.occupation} community is small. Someone has been unaccounted for.",
                    f"I can't name a district, but whoever did this knew the work I know. I can feel it in how it was done.",
                ])
            else:
                if evasive:
                    return rng.choice([
                        "I keep to my own district. I wouldn't know.",
                        "I don't involve myself in other people's neighborhoods.",
                        "Can't help you with that. I have my own concerns.",
                    ])
                return rng.choice([
                    "I don't have much reason to move between districts.",
                    "I'm not the right person to ask about other parts of town.",
                    "I hear things, but nothing I could point to on a map.",
                ])

        elif cat == "time":
            if near_scene or same_trade:
                responses = {
                    "aggressive": [
                        "I was out that night. Not hiding it. I saw movement that I thought nothing of at the time.",
                        "Late movements near the district. I didn't think it was my business then.",
                        "Someone was out past when they should have been. I saw a shadow.",
                    ],
                    "cautious": [
                        "I noted the time specifically. There was unusual activity between the tenth and twelfth hour.",
                        "I keep a kind of log in my head. That night was not normal.",
                        "I observed something I've been reluctant to share. A figure, moving with purpose.",
                    ],
                    "loyal": [
                        "I was up late. And I heard something I can't explain away.",
                        "I saw someone that night that I haven't told anyone about yet. I wasn't sure it mattered.",
                        "The timing matters. I know that now. At the time I thought it was nothing.",
                    ],
                    "charismatic": [
                        "People were talking that night. Things I heard don't add up now that I think on it.",
                        "I was at the tavern. Heard someone mention the district late. Didn't place it then.",
                        "I keep good hours. That night, someone didn't.",
                    ],
                    "innovative": [
                        "The time of death and the movements I observed that evening are not coincidental.",
                        "If you reconstruct the timeline, something becomes very clear. I've done it.",
                        "I've been through that night hour by hour in my mind. There's a gap that shouldn't be.",
                    ],
                    "selfish": [
                        "I was doing my own business that night. What I saw isn't relevant to you.",
                        "Late hours. I saw things I'd rather not have seen.",
                        "I keep odd hours sometimes. For my own reasons. I noticed someone else did too.",
                    ],
                }
                pool = responses.get(t, responses["loyal"])
                return rng.choice(pool)
            else:
                if evasive:
                    return rng.choice([
                        "I was home that night. That's all I'll say.",
                        "My whereabouts are my own business.",
                        "I don't keep track of the hours. I was where I was.",
                    ])
                return rng.choice([
                    "I was home. Unremarkable evening for me.",
                    "I turned in early. Nothing to report.",
                    "I wasn't paying attention to the hour. Normal night for me.",
                ])

        elif cat == "victim":
            victim_rels = [
                (other, kind) for other, kind in rel_others
                if victim and other == victim.name
            ]
            if victim_rels:
                other_name, kind = victim_rels[0]
                rel_responses = {
                    "lover":    f"We were close. More than people knew. This has hit me harder than I show.",
                    "rival":    f"We didn't get along. I want to be honest about that. But I had nothing to do with this.",
                    "debtor":   f"I owed {vname} something. A debt. This complicates things for me.",
                    "ally":     f"{vname} and I worked well together. Losing them is a real loss.",
                    "family":   f"{vname} was family to me. Whatever you need to find who did this, I'll give it.",
                    "colleague":f"We worked in the same trade. Knew each other through that. Good person.",
                }
                return rel_responses.get(kind, f"I knew {vname}. Better than most here.")

            responses = {
                "aggressive": [
                    f"{vname} was decent enough. Didn't have enemies that I knew of. Someone wanted something.",
                    f"Whoever did this to {vname} had a reason. Crimes like this aren't random.",
                    f"I didn't know {vname} well, but this makes me angry. Someone has to answer for it.",
                ],
                "cautious": [
                    f"I observed {vname} occasionally. Quiet person. Kept their business private.",
                    f"{vname} was careful about who they trusted. I respected that.",
                    f"I can't say I knew {vname} well, but nothing I saw suggested they had enemies.",
                ],
                "loyal": [
                    f"{vname} was part of this town. Someone we'll miss.",
                    f"I liked {vname}. This doesn't sit right with me at all.",
                    f"Good person. I can't understand why anyone would do this.",
                ],
                "charismatic": [
                    f"{vname} was well-regarded. People spoke well of them to me.",
                    f"I heard things about {vname} — all good, mostly. Someone must have had a private grievance.",
                    f"Word is {vname} had some dealings that not everyone knew about. Make of that what you will.",
                ],
                "innovative": [
                    f"The choice of {vname} was not accidental. There is a reason they were targeted specifically.",
                    f"{vname} had something — information, a connection — that made them dangerous to someone.",
                    f"I've been thinking about why {vname}. The answer to your case is in that question.",
                ],
                "selfish": [
                    f"I knew {vname} to nod at. Nothing more.",
                    f"Sad news. But I don't have information that would help you.",
                    f"{vname} kept to themselves. So do I. We weren't close.",
                ],
            }
            pool = responses.get(t, responses["loyal"])
            return rng.choice(pool)

        elif cat == "strangers":
            killer = self.scenario.characters[self.scenario.state.killer_id]
            killer_dist = killer.district
            killer_trait = killer.trait
            TRAIT_DESC = {
                "aggressive":  "blunt and forceful, someone who doesn't hide what they want",
                "cautious":    "deliberate, careful with words, never says more than needed",
                "loyal":       "steady and principled, the kind who protects their own circle",
                "charismatic": "warm, draws people in, socially comfortable in any company",
                "innovative":  "methodical, unusual way of thinking, notices things others miss",
                "selfish":     "calculating, self-interested, hard to read what they actually want",
            }
            trait_words = TRAIT_DESC.get(killer_trait, "difficult to describe precisely")

            if near_scene:
                desc_responses = [
                    f"No strangers. But there is someone here I've been watching. {trait_words.capitalize()}. You'd know them if you paid attention.",
                    f"Someone in {killer_dist} has been on my mind. Hard to explain — it's their manner. {trait_words.capitalize()}.",
                    f"I haven't seen outsiders. But one person here has been different lately. The kind that is {trait_words}.",
                ]
                vague_responses = [
                    f"Someone who lives here. {trait_words.capitalize()}. They've been drawing attention without meaning to.",
                    f"No strangers. But someone in {killer_dist} — {trait_words}. That's the best I can say.",
                    f"It's not a stranger you're looking for. Someone already here. {trait_words.capitalize()}.",
                ]
                pool = desc_responses if t in ("cautious","innovative","loyal") else vague_responses
                return rng.choice(pool)
            elif same_trade:
                return rng.choice([
                    f"In our trade you notice behavior. Someone with our skills has been acting {trait_words.split(',')[0]}.",
                    f"I've worked beside all kinds. Someone {trait_words} — that can go wrong under pressure.",
                    f"The killer's manner, from what I hear — {trait_words}. I may know who that points to.",
                ])
            else:
                if evasive:
                    return rng.choice([
                        "I don't pay attention to people I don't know.",
                        "Strangers aren't my concern unless they're in my way.",
                        "I can't help you there.",
                    ])
                return rng.choice([
                    "Nothing unusual where I am. Normal faces, normal days.",
                    "Nobody stood out to me. I would tell you if they had.",
                    "I'm not the most observant person. I can't give you what I don't have.",
                ])

        elif cat == "motive":
            motive_knowledge = {
                "revenge":   "This looks like it was about settling something old. A grudge that was never resolved.",
                "greed":     "Someone needed something that person had. A debt, an inheritance, something owed.",
                "fear":      "Whoever did this was protecting themselves. The victim knew something.",
                "obsession": "This was personal in a way that goes beyond reason. Someone couldn't let something go.",
                "jealousy":  "Envy. Someone wanted what that person had and couldn't stand not having it.",
            }
            trait_preambles = {
                "aggressive": "My guess, and I'll say it straight:",
                "cautious":   "I've thought carefully about this before saying it:",
                "loyal":      "I hate speculating, but if you're asking:",
                "charismatic":"People have been talking about this. The consensus is:",
                "innovative": "Looking at the pattern of it, I'd say:",
                "selfish":    "Not really my area, but:",
            }
            preamble = trait_preambles.get(t, "I think:")
            motive_hint = motive_knowledge.get(s.killer_motive,
                "Hard to say. Could be any number of reasons.")
            if evasive:
                return rng.choice([
                    "I don't like to speculate about these things.",
                    "I have my guesses. I'd rather keep them to myself.",
                    "Could be a lot of things. I'm not comfortable pointing at anything specific.",
                ])
            return f"{preamble} {motive_hint}"
        elif cat == "alibi":
            if evasive:
                evasive_responses = {
                    "aggressive": [
                        "That's not your business.",
                        "I was doing what I do. I don't answer to investigations.",
                        "I have people who can account for me. I'd rather not drag them into this.",
                    ],
                    "selfish": [
                        "My time is my own. I don't report to anyone.",
                        "I was occupied. With private matters.",
                        "I'd rather not say. It has nothing to do with this.",
                    ],
                    "cautious": [
                        "I was somewhere I'd prefer to keep quiet. Unrelated to all this.",
                        "I can account for myself, but not without explaining other things I'd rather not.",
                        "Let me say I was occupied, and leave it there for now.",
                    ],
                }
                pool = evasive_responses.get(t, [
                    "I'd rather not say where I was.",
                    "Private matter. Nothing to do with this.",
                    "I was occupied. That's all.",
                ])
                return rng.choice(pool)
            cooperative = {
                "loyal": [
                    "I was home. My neighbor's light was on — they'd have heard me.",
                    "I can give you three names who saw me that evening.",
                    "I was at the community hall until late. Ask anyone.",
                ],
                "charismatic": [
                    "Half the district saw me that night. I was at the gathering.",
                    "I was with people. Several of them. I can introduce you.",
                    "I went home after the market closed. My landlord was there.",
                ],
                "aggressive": [
                    "I was working. You can check with my client.",
                    "I don't need an alibi. But I have one. Ask the guildmaster.",
                    "Home, then the tavern, then home. Several witnesses.",
                ],
                "innovative": [
                    "I was at the archive that evening, crosschecking records. The archivist can confirm.",
                    "I was working through a problem at home. Alone, but I have written notes with timestamps.",
                    "I was observed by two people that evening. I'll give you their names.",
                ],
            }
            pool = cooperative.get(t, [
                "I was home. Nothing unusual.",
                "You can ask around — people saw me.",
                "I was where I always am at that hour.",
            ])
            return rng.choice(pool)

        return "I don't have much to say about that."


    def _ws_parse(self, cmd: dict) -> str | None:
        """Convert a WS command dict to a string the conversation loop understands."""
        if not isinstance(cmd, dict): return None
        action = cmd.get("action", "")
        if action == "talk_cat": return cmd.get("cat", "")
        if action == "leave":    return "0"
        if action == "go":       return cmd.get("district", "")
        if action == "command":  return cmd.get("value", "")
        return None

    def _read_input(self, prompt: str = "  > ") -> str:
        """
        Read from WS queue OR keyboard.
        Uses one stdin thread at a time (semaphore prevents accumulation).
        The prompt_toolkit thread is paused via _in_command while we run here,
        so we safely own stdin.
        """
        import queue as _q, threading as _th
        cmd = _ws_server.read_command(timeout=0.0)
        if cmd:
            val = self._ws_parse(cmd)
            if val is not None: return val

        sys.stdout.write(info(prompt))
        sys.stdout.flush()
        if not hasattr(self, "_stdin_sem"):
            self._stdin_sem = _th.Semaphore(1)

        stdin_q  = _q.Queue()
        acquired = self._stdin_sem.acquire(blocking=False)
        if acquired:
            def _read():
                try:
                    line = sys.stdin.readline().rstrip("\n").strip()
                    stdin_q.put(line)
                except Exception:
                    stdin_q.put("")
                finally:
                    self._stdin_sem.release()
            _th.Thread(target=_read, daemon=True).start()

        while True:
            cmd = _ws_server.read_command(timeout=0.0)
            if cmd:
                val = self._ws_parse(cmd)
                if val is not None:
                    sys.stdout.write("\r" + info(prompt) + dim(val) + "\n")
                    sys.stdout.flush()
                    return val
            try:
                return stdin_q.get(timeout=0.05)
            except _q.Empty:
                continue

    def _do_talk_categories(self, char):
        from scenarios.murderer import _questions_per_period

        s     = self.scenario.state
        max_q = _questions_per_period(s.difficulty)

        CATS = {
            "location":  ["location","district","place","zone","where","area"],
            "time":      ["time","night","when","evening","late","hour","schedule"],
            "victim":    ["victim","dead","killed","knew","murder","deceased"],
            "strangers": ["strangers","stranger","suspicious","unusual","odd","outsider"],
            "motive":    ["motive","why","reason","because","drove","cause"],
            "alibi":     ["alibi","proof","witness","whereabouts","account"],
        }
        CAT_LABELS = {
            "location":"location","time":"time","victim":"victim",
            "strangers":"strangers","motive":"motive","alibi":"alibi",
        }
        QUESTIONS = {
            "location":  "What have you noticed about the different districts?",
            "time":      "What were you doing the night it happened?",
            "victim":    "How well did you know the victim?",
            "strangers": "Have you seen anyone acting unusual or out of place?",
            "motive":    "What do you think drove someone to do this?",
            "alibi":     "Can you account for your whereabouts that evening?",
        }
        ATTR_TO_CAT = {
            "district":"location","occupation":"time","trait":"strangers",
        }

        def match(raw):
            raw = raw.lower().strip()
            for cat, kws in CATS.items():
                if raw == cat or raw in kws:
                    return cat
            words = raw.split()
            for word in words:
                if len(word) < 4: continue
                for cat, kws in CATS.items():
                    for kw in kws:
                        if len(kw) >= 4:
                            d = sum(1 for a,b in zip(word,kw) if a!=b) + abs(len(word)-len(kw))
                            if d <= 2: return cat
            return None

        char_clues = self.scenario.clue_holders.get(char.id, [])
        available_clues = [
            cid for cid in char_clues
            if cid in self.scenario.clues
            and not self.scenario.clues[cid].scene_only
            and self.scenario.clues[cid].day_available <= s.day
            and cid not in s.clues_found
        ]
        asked_cats: set = set()

        while True:
            rem = max_q - s.questions_asked_this_period.get(char.id, 0)
            print()
            print("  " + bold(char.name) +
                  dim(f"  ({char.occupation}, {char.district})") +
                  dim(f"  [{rem}q left]"))
            print()
            print(bold(f"  What do you want to ask {char.name.split()[0]}?"))
            print()
            for i_q, (cat_q, label_q) in enumerate(CAT_LABELS.items(), 1):
                q_q = QUESTIONS[cat_q]
                if cat_q in asked_cats:
                    print(f"  {dim(str(i_q) + '.')} {dim('['+label_q+']')} {dim(q_q)}")
                else:
                    print(f"  {info(str(i_q) + '.')} {col(C.CY, '['+label_q+']')} {q_q}")

            if available_clues:
                print(f"  {col(C.Y, '*')} This person has information about the case")
            char_leads = (self.scenario.get_leads_for(char.id)
                          if hasattr(self.scenario, "get_leads_for") else [])
            if char_leads:
                print()
                print(dim("  Leads from other conversations:"))
                for li_i, lead_i in enumerate(char_leads):
                    if li_i >= len("abcdefghij"): break
                    ltr = "abcdefghij"[li_i]
                    src = lead_i.get("source_name", "?")
                    print(f"  {warn(ltr + chr(46))} {dim(chr(91)+src+chr(93))} {lead_i[chr(113)+chr(117)+chr(101)+chr(115)+chr(116)+chr(105)+chr(111)+chr(110)][:65]}")
                    src = lead_i.get("source_name", "?")
                    print(f"  {warn(str(li_i) + '.')} {dim('['+src+']')} {lead_i['question'][:65]}")
            bl_secrets = (self.scenario.secrets_about(char.id)
                          if hasattr(self.scenario, "secrets_about") else [])
            if bl_secrets:
                print(f"  {warn('s.')} Use a secret against them")
            print(f"  {info('0.')} Leave")
            print()

            try:
                raw = self._read_input("  > ")
            except (EOFError, KeyboardInterrupt):
                break

            if not raw or raw == "0" or raw.lower() in ("leave","exit","back"):
                break

            if len(raw)==1 and raw.lower() in "abcdefghij" and char_leads:
                try:
                    li_num = "abcdefghij".index(raw.lower())
                    if 0 <= li_num < len(char_leads):
                        chosen_lead = char_leads[li_num]
                        print()
                        print(f"  {dim('You:')} {chosen_lead['question']}")
                        print()
                        lr = (self.scenario.answer_lead(chosen_lead, char)
                              if hasattr(self.scenario, "answer_lead")
                              else "I am not sure what you mean.")
                        for line in _wrap(lr, width=70, indent="    "):
                            print(f"  {col(C.CY, '| ')} {line}")
                        print()
                        self._conversation_log.append({
                            "who": char.name,
                            "q":   f"[lead] {chosen_lead['question'][:50]}",
                            "a":   lr[:120], "clue": False,
                        })
                        self._export(active_char_id=char.id)
                        continue
                except (ValueError, IndexError):
                    pass
            if raw.lower() == "s" and bl_secrets and hasattr(self.scenario, "blackmail"):
                print()
                for i_s, sec in enumerate(bl_secrets, 1):
                    print(f"  {warn(str(i_s) + '.')} {sec.description}")
                print(f"  {info('0.')} Cancel"); print()
                try:
                    sidx = int(self._read_input("  > ")) - 1
                    if 0 <= sidx < len(bl_secrets):
                        ok_bl, msg_bl = self.scenario.blackmail(char.id, bl_secrets[sidx].id)
                        print()
                        for line in msg_bl.split("\n"):
                            print("  " + (ok("- ") if ok_bl else warn("- ")) + line)
                        print(); self._export(active_char_id=char.id)
                except (ValueError, KeyboardInterrupt, EOFError):
                    pass
                continue

            if rem <= 0:
                print(warn("  No questions left this period. Come back in a few hours."))
                continue

            cat_list = list(CAT_LABELS.keys())
            cat_match = None
            try:
                num = int(raw) - 1
                if 0 <= num < len(cat_list):
                    cat_match = cat_list[num]
            except ValueError:
                cat_match = match(raw)

            if not cat_match:
                print(warn(f"  Not recognized. Try a number 1-6 or: {', '.join(CATS.keys())}"))
                continue

            ok_q, err_q = self.scenario.use_question(char.id, 0)
            if not ok_q:
                print(warn(f"  {err_q}")); continue

            asked_cats.add(cat_match)
            q_display = QUESTIONS.get(cat_match, cat_match)
            print()
            print(f"  {dim('You:')} {col(C.CY, '['+cat_match+']')} {q_display}")
            response = self._cat_response(cat_match, char)
            clue_id = None
            attr_map = {
                "location":"district","time":"occupation","strangers":"trait",
                "victim":"district","alibi":"occupation","motive":"district",
            }
            target_attr = attr_map.get(cat_match)
            killer = self.scenario.characters[self.scenario.state.killer_id]
            near_scene = char.district == killer.district
            same_trade = char.occupation == killer.occupation
            can_reveal = near_scene or same_trade or cat_match in ("victim",)
            if can_reveal:
                for cid in list(available_clues):
                    if self.scenario.clues[cid].attribute == target_attr:
                        clue_id = cid; break

            resp_col = C.Y if clue_id else C.CY
            for line in _wrap(response, width=70, indent="    "):
                print(f"  {col(resp_col, '| ')} {line}")

            if clue_id:
                clue = self.scenario.clues[clue_id]
                print()
                print(f"  {col(C.Y, '* ')} {clue.text}")
                self.scenario.reveal_clue(clue_id)
                available_clues.remove(clue_id)
            print()
            if hasattr(self.scenario, "detect_leads"):
                new_leads = self.scenario.detect_leads(char.id, cat_match, response)
                for lead in new_leads:
                    print(f"  {col(C.Y, '->')} {dim('Lead: ask')} "
                          f"{info(lead['target_name'])} {dim('—')} {lead['question'][:60]}")
                if new_leads: print()

            self._conversation_log.append({
                "who": char.name,
                "q":   f"[{cat_match}]",
                "a":   response[:120],
                "clue": clue_id is not None,
            })
            self._export(active_char_id=char.id)

    def do_blackmail(self, arg):
        if not hasattr(self.scenario, "blackmail"):
            print(err("  This action is not available in this scenario."))
            return
        if not arg.strip():
            print()
            if not self.scenario.state.secrets_known:
                print(dim("  You don't know any secrets yet. Keep talking to people."))
            else:
                print(bold("  Secrets you know:"))
                for sid in self.scenario.state.secrets_known:
                    s = self.scenario.secrets.get(sid)
                    if s:
                        print(f"    {col(C.Y, '◈')} [{s.about_name}] {s.description}")
                print()
                print(dim("  Usage: blackmail <target>"))
            print()
            return
        char, errmsg = self._resolve_char(arg.strip())
        if not char:
            print(err("  " + errmsg))
            return
        secrets = self.scenario.secrets_about(char.id)
        if not secrets:
            known_about = [
                s for s in self.scenario.secrets.values()
                if s.id in self.scenario.state.secrets_known
            ]
            if not known_about:
                print(err("  You don't know any secrets yet."))
            else:
                print(err(f"  You don't know any secrets about {char.name}."))
            return

        print()
        print(bold(f"  Secrets you know about {char.name}:"))
        for i, s in enumerate(secrets, 1):
            print(f"    {info(str(i) + '.')} {s.description}")
        print(f"    {info('0.')} Cancel")
        print()

        try:
            choice = self._read_input("  Use which? > ")
            if choice == "0":
                return
            idx = int(choice) - 1
            if 0 <= idx < len(secrets):
                secret = secrets[idx]
                ok, msg = self.scenario.blackmail(char.id, secret.id)
                print()
                color = ok if False else (ok and C.G or C.Y)
                for line in msg.split("\n"):
                    print("  " + (ok("› ") if ok else warn("› ")) + line)
                print()
                if self._spend_time(3.0):
                    return
                self._print_scenario_events()
            else:
                print(warn("  Invalid choice."))
        except (ValueError, KeyboardInterrupt, EOFError):
            print(dim("  Cancelled."))

    def do_clues(self, arg):
        print()
        if not hasattr(self.scenario, "clues"):
            print(dim("  No clues in this scenario."))
            return
        found  = [(cid, c) for cid, c in self.scenario.clues.items() if c.found]
        hidden = [c for c in self.scenario.clues.values() if not c.found]

        if not found:
            print(dim("  No clues found yet. Talk to witnesses, search districts."))
        else:
            print(bold(f"  Evidence ({len(found)} clue{'s' if len(found)!=1 else ''} found):"))
            print()
            for cid, clue in found:
                if clue.is_lie:
                    prefix = warn("  ⚠ ")
                    note   = dim("  [account revised — treat with caution]")
                elif clue.narrows_suspects:
                    prefix = col(C.Y, "  ★ ")
                    note   = ""
                else:
                    prefix = col(C.CY, "  · ")
                    note   = ""
                ac_tag = col(C.CY, " [accomplice clue]") if cid.startswith("accomplice_") else ""
                attr_tag = info(f"[{clue.attribute}]")
                print(f"{prefix}{attr_tag} {clue.text}{ac_tag}{note}")
            print()

        if hasattr(self.scenario.state, "weapon_found"):
            w = self.scenario.state.weapon_found
            if w:
                print(f"  {ok(chr(10003))} Murder weapon: {bold(w)}")
            else:
                print(f"  {warn('!')} Murder weapon not yet found — search the districts")

        if hidden:
            print()
            print(dim(f"  {len(hidden)} clue(s) still undiscovered."))

        print()
        print(dim("  Use the deduction grid in the dashboard to cross-reference clues with suspects."))
        print()
        return
    def _compute_suspects(self):
        if not hasattr(self.scenario, "clues"):
            return []
        found = [c for c in self.scenario.clues.values() if c.found]
        chars = [c for c in self.scenario.characters.values() if c.alive]
        for clue in found:
            if "|" in clue.value:
                valid_vals = clue.value.split("|")
            else:
                valid_vals = [clue.value]
            chars = [c for c in chars if getattr(c, clue.attribute, None) in valid_vals]
        return chars

    def do_accuse(self, arg):
        if not arg.strip():
            print(err("  Usage: accuse <name>"))
            return
        if not hasattr(self.scenario, "begin_confrontation"):
            print(err("  Accusation not available in this scenario."))
            return

        char, errmsg = self._resolve_char(arg.strip())
        if not char:
            print(err("  " + errmsg))
            return

        conf, err_msg = self.scenario.begin_confrontation(char.id)
        if conf is None:
            print(err("  " + err_msg))
            return

        print()
        print(col(C.Y, "=" * 56))
        print("  " + bold(f"CONFRONTING: {char.name}"))
        print(col(C.Y, "=" * 56))
        print()
        opening = self.scenario.opening_line(char.id)
        print("  " + col(C.CY, f"{char.name}: ") + f'"{opening}"')
        print()

        while not conf.resolved:
            pct   = int(conf.pressure * 20)
            bar   = col(C.R, "█" * pct) + col(C.DIM, "░" * (20 - pct))
            plbl  = warn("BREAKING") if conf.pressure >= 0.8 else \
                    warn("HIGH")     if conf.pressure >= 0.6 else \
                    dim("MID")       if conf.pressure >= 0.3 else dim("LOW")
            print(f"  Pressure: [{bar}] {plbl}")
            print()
            avail = self.scenario.confrontation_clues(char.id, conf)
            if not avail:
                print(dim("  You have no more clues to present."))
                print()
                r = self.scenario.withdraw_confrontation(conf)
                print()
                for line in r.split("\n"):
                    print("  " + dim("│ ") + line)
                print()
                break

            print(bold("  Present evidence:"))
            for i, cc in enumerate(avail, 1):
                genuine_mark = ok(" ✓") if cc.is_genuine else ""
                lie_mark     = err(" ✗") if not cc.is_genuine and cc.pressure_delta < 0 else ""
                print(f"  {info(str(i) + '.')} [{cc.attribute}] {cc.text[:70]}"
                      f"{'...' if len(cc.text) > 70 else ''}{genuine_mark}{lie_mark}")
            print(f"  {info('0.')} {dim('Withdraw — step back without penalty')}")
            print()

            try:
                choice = self._read_input("  > ")
            except (EOFError, KeyboardInterrupt):
                break

            if choice == "0" or choice.lower() in ("withdraw","back","leave","w"):
                r = self.scenario.withdraw_confrontation(conf)
                print()
                for line in r.split("\n"):
                    print("  " + dim("│ ") + line)
                print()
                break

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(avail):
                    chosen = avail[idx]
                    narrative, result = self.scenario.present_clue(conf, chosen)
                    print()
                    delta_str = (ok(f"+{int(chosen.pressure_delta*100)}%") if chosen.pressure_delta > 0
                                 else err(f"{int(chosen.pressure_delta*100)}%"))
                    print(f"  {col(C.CY, char.name + ': ')}\"{narrative}\"")
                    print(f"  {dim('Pressure: ')} {delta_str}")
                    print()
                    if result:
                        self._end_game(result)
                        return
                else:
                    print(warn("  Invalid choice."))
            except ValueError:
                print(warn("  Enter a number."))

        if self._spend_time(0.0):
            return
        self._print_scenario_events()

    def do_present(self, arg):
        if not hasattr(self.scenario, "present_case"):
            print(err("  This action is not available here."))
            return
        verdict_word = arg.strip().lower()
        if verdict_word not in ("guilty","innocent"):
            print(err("  Usage: present guilty  OR  present innocent"))
            return
        verdict = verdict_word == "guilty"
        print()

    def do_go(self, arg):
        if not arg.strip():
            if hasattr(self.scenario, "go"):
                room_id = getattr(self.scenario.state, "player_room", None)
                if room_id and room_id in self.scenario.rooms:
                    exits = list(self.scenario.rooms[room_id].connections.keys())
                    print(err("  Usage: go <direction>   available: " +
                              (", ".join(exits) if exits else "none")))
                else:
                    print(err("  Usage: go <direction>   (north/south/east/west)"))
            else:
                locs = sorted(set(
                    c.district for c in self.scenario.characters.values()
                    if c.alive
                ))
                current = getattr(self.scenario.state, "player_location", "?")
                print()
                print(bold("  Locations:"))
                for loc in locs:
                    people = self.scenario.nearby_chars(loc)
                    mark = info(" ← you") if loc == current else ""
                    count = f"  ({len(people)} people)" if people else "  (empty)"
                    print(f"    {info(loc)}{mark}{dim(count)}")
                print()
                print(dim("  go <location>  to move there"))
                print()
            return

        dest = arg.strip().lower()

        if hasattr(self.scenario, "go"):
            result = self.scenario.go(dest)
            print()
            for line in result.split("\n"):
                print("  " + line)
            print()
            end = self.scenario.check_end()
            if end:
                self._end_game(end)
                return
        else:
            valid = sorted(set(
                c.district for c in self.scenario.characters.values()
                if c.alive
            ))
            if dest not in valid:
                matches = [v for v in valid if v.startswith(dest)]
                if len(matches) == 1:
                    dest = matches[0]
                elif len(matches) > 1:
                    print(err(f"  Ambiguous: {', '.join(matches)}"))
                    return
                else:
                    print(err(f"  Unknown location '{dest}'. Available: {', '.join(valid)}"))
                    return
            current = getattr(self.scenario.state, "player_location", "")
            if dest == current:
                print(dim(f"  You are already in the {dest} district."))
                return
            self.scenario.state.player_location = dest
            people = self.scenario.nearby_chars(dest)
            print()
            print(info(f"  You move to the {dest} district."))
            if people:
                names = ", ".join(c.name.split()[0] for c in people[:4])
                print(dim(f"  People here: {names}"))
            print()

        if self._spend_time(0.5):
            return
        self._print_scenario_events()

    def do_rest(self, arg):
        if hasattr(self.scenario, "rest"):
            result = self.scenario.rest()
            print()
            print("  " + ok("›") + " " + result)
            print()
        else:
            print(dim("  You take a moment to collect your thoughts."))
        if self._spend_time(8.0):
            return
        self._print_scenario_events()

    def do_map(self, arg):
        if hasattr(self.scenario, "show_map"):
            print()
            print(self.scenario.show_map())
            print()
        else:
            if hasattr(self.scenario, "all_locations"):
                locs = self.scenario.all_locations()
                print()
                print(bold("  Known locations:"))
                for l in sorted(set(locs)):
                    print(f"    • {l}")
                print()

    def do_items(self, arg):
        if hasattr(self.scenario.state, "items"):
            items = self.scenario.state.items
            print()
            print(bold("  Items:") + (" " + ", ".join(items) if items else dim("  none")))
            print()
        else:
            print(dim("  No item system in this scenario."))

    def do_search(self, arg):
        """search <district>  (1.5h) — Physically search a district for evidence.
        Most useful after 'follow' reveals a person was in an area, or after
        conversations hint that something happened in a specific location."""
        if not hasattr(self.scenario, "search_location"):
            self.do_search(arg)
            return
        if not arg.strip():
            # Show searchable locations
            loc = self._current_location()
            locs = sorted(set(
                c.district for c in self.scenario.characters.values() if c.alive
            ))
            print()
            print(bold("  Searchable locations:"))
            for l in locs:
                already = l in (getattr(self.scenario.state, "searched_locations", []))
                tag = dim(" [searched]") if already else ""
                mark = ok("  you") if l == loc else "     "
                print(f"  {mark} {info(l)}{tag}")
            print()
            print(dim("  Usage: search <location>"))
            print()
            return
        location = arg.strip().lower()
        found, narrative = self.scenario.search_location(location)
        print()
        icon = ok("★") if found else dim("·")
        for line in narrative.split("\n"):
            print(f"  {icon} {line}")
        print()
        if self._spend_time(1.5):
            return
        self._print_scenario_events()

    def do_follow(self, arg):
        """follow <name>  (3h) — Tail someone to learn their movements.
        If the subject visits a district where clue evidence exists, you find a lead.
        Then use 'search <district>' in that area to find physical evidence."""
        if not hasattr(self.scenario, "follow_character"):
            print(err("  Not available in this scenario."))
            return
        if not arg.strip():
            print(err("  Usage: follow <name>"))
            return
        char, errmsg = self._resolve_char(arg.strip())
        if not char:
            print(err("  " + errmsg))
            return
        print()
        print(dim(f"  You tail {char.name} for several hours..."))
        print()
        result = self.scenario.follow_character(char.id)
        for line in result.split("\n"):
            print("  " + col(C.DIM, "│ ") + line)
        print()
        if self._spend_time(3.0):
            return
        self._print_scenario_events()



    def do_help(self, arg):
        s = self.scenario
        print()
        print(bold("  == Actions =="))
        action_help = {
            "talk":      "talk <name>      Talk to someone here. Limited questions per day.",
            "search":    "search <location>  Search a district for physical evidence  (1.5h)",
            "follow":    "follow <name>      Tail someone for several hours  (3h)",
            "examine":   "examine [item]   Inspect a piece of evidence or the room.",
            "search":    "search           Search your current location.",
            "blackmail": "blackmail <name>  Use a known secret to extract info.",
            "accuse":    "accuse <name>    Accuse someone of the crime.",
            "challenge": "challenge <witness> <evidence>  Confront a witness with evidence.",
            "present":   "present guilty/innocent  Present your final case.",
            "protect":   "protect <name>  Warn a citizen to be careful.",
            "clues":     "clues            Review clues found and current suspects.",
            "evidence":  "evidence         List all evidence items.",
            "restart":   "restart          Replay this seed from the beginning.",
            "save":      "save [file]       Save game to JSON file.",
            "load":      "load <file>       Load a saved game.",
            "surrender": "surrender         Give up and see solution walkthrough.",
            "go":        "go <direction>   Move to a new location (north/south/east/west).",
            "rest":      "rest             Recover stamina.",
            "map":       "map              Show known locations or rooms.",
            "items":     "items            Show items in your possession.",
            "nearby":    "nearby           See who is at your current location.",
            "status":    "status           Show situation overview.",
            "help":      "help             This menu.",
        }
        for action in s.actions:
            if action in action_help:
                print("  " + info(action_help[action].split("  ")[0].ljust(28)) +
                      dim("  " + action_help[action].split("  ", 1)[1]))
        print()

    def do_quit(self, arg):
        print(dim("  Goodbye."))
        return True
    do_exit = do_quit

    def do_save(self, arg):
        if not hasattr(self.scenario, "state") or not hasattr(self.scenario.state, "seed_used"):
            print(err("  Save only available in murderer scenario."))
            return
        try:
            import saveload
            path_arg = arg.strip() or None
            path = saveload.save_game(self.scenario, path_arg, self._conversation_log)
            print()
            print(ok(f"  Game saved: {path}"))
            print()
        except Exception as e:
            print(err(f"  Save failed: {e}"))

    def do_load(self, arg):
        if not arg.strip():
            import glob, os
            saves = sorted(glob.glob("save_*.json"), key=os.path.getmtime, reverse=True)
            print()
            if not saves:
                print(dim("  No save files found in current directory."))
                print(dim("  Usage: load <filename>"))
            else:
                print(bold("  Available saves:"))
                for s in saves[:8]:
                    print(f"    {info(s)}")
                print()
                print(dim("  Usage: load <filename>"))
            print()
            return
        try:
            import saveload
            scenario, conv_log = saveload.load_game(arg.strip())
            self.scenario = scenario
            self._conversation_log = conv_log
            self._export()
            print()
            print(ok(f"  Loaded: {arg.strip()}"))
            self._show_banner()
            self.do_status("")
        except Exception as e:
            print(err(f"  Load failed: {e}"))

    def do_restart(self, arg):
        """Restart the current scenario from the beginning with the same seed."""
        if not hasattr(self.scenario.state, "seed_used"):
            print(err("  Restart only available in murderer scenario."))
            return
        print()
        if arg.strip().lower() not in ("yes","y"):
            print(warn("  Type 'restart yes' to replay from the beginning."))
            return
        confirm = "yes"
        diff = self.scenario.state.difficulty
        print(info(f"  Restarting seed {seed} at difficulty {diff}..."))
        new_scenario = MurdererScenario(seed=seed, difficulty=diff)
        self.scenario = new_scenario
        self._conversation_log = []
        self._export()
        self._show_banner()
        print(ok("  Restarted. You know the town now — use what you learned."))
        print()

    def do_surrender(self, arg):
        if not hasattr(self.scenario, "state") or not hasattr(self.scenario.state, "killer_id"):
            print(err("  Surrender only available in murderer scenario."))
            return
        if arg.strip().lower() not in ("yes", "y"):
            print()
            print(warn("  Type surrender yes to give up and reveal the truth."))
            print(dim("  This will end the game."))
            return
        from scenarios.base import ScenarioResult
        s      = self.scenario.state
        killer = self.scenario.characters[s.killer_id]
        seed_val = getattr(s, "seed_used", "?")

        print()
        print(col(C.Y, "=" * 56))
        print("  " + bold("CASE CLOSED — SURRENDER"))
        print(col(C.Y, "=" * 56))
        print()
        print(f"  The killer was {bold(killer.name)}")
        print(f"  {killer.occupation} — {killer.district} district — {killer.trait}")
        print(f"  Motive: {s.killer_motive}")
        weapon = getattr(s, "weapon_found", "") or getattr(self.scenario, "_weapon_name", "unknown")
        print(f"  Weapon: {weapon}")
        print()

        if hasattr(self.scenario, "clues") and self.scenario.clues:
            found    = [c for c in self.scenario.clues.values() if c.found]
            not_found = [c for c in self.scenario.clues.values() if not c.found]

            if found:
                print(bold(f"  Clues you found ({len(found)}):"))
                for c in found:
                    lie_tag  = warn(" [planted lie]") if c.is_lie else ""
                    narr_tag = col(C.Y, " [narrows]") if c.narrows_suspects else ""
                    print(f"    {ok(chr(10003))} [{c.attribute}] {c.text}{lie_tag}{narr_tag}")
                print()

            if not_found:
                print(bold(f"  Clues you missed ({len(not_found)}):"))
                for c in not_found:
                    holder = next(
                        (self.scenario.characters[cid].name
                         for cid, ids in self.scenario.clue_holders.items()
                         if c.id in ids),
                        "scene"
                    )
                    narr_tag = col(C.Y, " [narrows]") if c.narrows_suspects else ""
                    print(f"    {dim(chr(45))} [{c.attribute}] {c.text}{narr_tag}")
                    print(f"         {dim(chr(40)+holder+chr(41))}")
                print()

        print(bold("  How you could have deduced it:"))
        killer_clues = [c for c in self.scenario.clues.values()
                        if c.narrows_suspects and not c.is_lie]
        for c in killer_clues:
            print(f"    {col(C.CY, chr(46))} [{c.attribute} = {c.value}]  {c.text[:70]}")
        print()

        print(dim(f"  Seed: {seed_val}  Difficulty: {s.difficulty}/20"))
        print(dim("  Use restart to replay this case with what you now know."))
        print()
        print(col(C.Y, "=" * 56))
        print()

        result = ScenarioResult(won=False, message="", days=s.day)
        self._end_game(result)

    def cmdloop(self, intro=None):
        if _COMPLETER != "prompt_toolkit" or not hasattr(self, "_pt_session") or self._pt_session is None:
            return self._cmdloop_with_ws()
        import threading, queue as _queue
        prompt_q = _queue.Queue()   
        prompt_stop = threading.Event()

        self._in_command = threading.Event()
        self._in_command.set()  

        def _prompt_thread():
            while not prompt_stop.is_set():
                self._in_command.wait()  
                if prompt_stop.is_set(): break
                try:
                    line = self._pt_session.prompt()
                    self._in_command.clear()  
                    prompt_q.put(("line", line))
                except KeyboardInterrupt:
                    self._in_command.clear()
                    prompt_q.put(("ctrl_c", ""))
                except EOFError:
                    prompt_q.put(("eof", ""))
                    break

        t = threading.Thread(target=_prompt_thread, daemon=True)
        t.start()

        if intro:
            print(intro)
        try:
            while True:
                ws_cmd = _ws_server.read_command(timeout=0.0)
                if ws_cmd:
                    line = self._ws_cmd_to_line(ws_cmd)
                    if line:
                        sys.stdout.write("\n" + info("[html] ") + dim(line) + "\n")
                        sys.stdout.flush()
                        if self.onecmd(line):
                            prompt_stop.set(); return
                    import time; time.sleep(0.05)
                    continue
                try:
                    kind, val = prompt_q.get(timeout=0.1)
                except _queue.Empty:
                    continue

                if kind == "ctrl_c":
                    self._in_command.set(); print(); continue
                if kind == "eof":
                    break
                line = val.strip()
                if not line:
                    self._in_command.set(); continue
                if self.onecmd(line):
                    break
                self._in_command.set()  
        finally:
            prompt_stop.set()

    def _cmdloop_with_ws(self):
        """Standard cmdloop with WS command injection support."""
        import time
        while True:
            ws_cmd = _ws_server.read_command(timeout=0.0)
            if ws_cmd:
                line = self._ws_cmd_to_line(ws_cmd)
                if line and self.onecmd(line):
                    return
                continue
            try:
                sys.stdout.write(self.prompt)
                sys.stdout.flush()
                line = input()
            except EOFError:
                break
            except KeyboardInterrupt:
                print()
                continue
            if self.onecmd(line.strip()):
                break

    def _ws_cmd_to_line(self, cmd: dict) -> str:
        """Convert a WS command dict to a CLI command string."""
        action = cmd.get("action", "")
        if action == "go":
            return f"go {cmd.get('district', '')}"
        if action == "clues":
            return "clues"
        if action == "status":
            return "status"
        if action == "talk":
            return f"talk {cmd.get('char_name', '')}"
        if action == "leave":
            return ""   
        return ""

    def default(self, line):
        print(err(f"  Unknown command '{line.split()[0]}'. Type 'help'."))


def main():
    parser = argparse.ArgumentParser(description="Town Simulation")
    parser.add_argument("--seed",     type=int, default=None)
    parser.add_argument("--scenario", type=str, default=None,
                        choices=["murderer"])
    args = parser.parse_args()

    print(f"\n  System: {platform.system()} | Python {sys.version.split()[0]}")
    print(f"\n  System: {platform.system()} | Python {sys.version.split()[0]}")
    print(f"  Autocomplete: {_COMPLETER}")
    ws_ok = _ws_server.start(port=8765)
    if ws_ok:
        print(f"  Dashboard:    run 'python -m http.server 8080' then open localhost:8080/scenarios/murderer/dashboard/")

    if args.scenario == "murderer":
        scenario = MurdererScenario(seed=args.seed)
    else:
        scenario = pick_scenario(args.seed)

    cli = GameCLI(scenario)
    cli._show_banner()
    cli._export()   
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print(dim("\n\n  Interrupted.\n"))


if __name__ == "__main__":
    main()
