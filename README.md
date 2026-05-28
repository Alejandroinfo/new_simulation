# Town Simulation — Scenarios

A narrative investigation game played in the terminal. Each scenario drops you into a situation with a clear objective, limited time, and people who may or may not tell you the truth. You talk, observe, and decide — the outcome depends on what you choose to ask and when.
## Setup
```bash
pip install colorama          
pip install pyreadline3       
uv add colorama pyreadline3

## Visual dashboard
Open the first terminal and run uv run cli.py
Open a second terminal and run a local server:
python -m http.server 8080
```

Then open `http://localhost:8080/dashboard.html` in a browser. It updates every 2 seconds as you play and shows scenario-appropriate information.

---

## Scenarios

### The Murderer

A killer is loose in a small town. You arrive to find one person already dead. Find the killer before they strike again.

**How it works:**
- The killer has four hidden attributes: occupation, district, trait, and motive
- Clues are distributed among the townspeople — each narrows the field
- New information emerges each day as people process what they've seen
- The killer strikes every few days; protected citizens are safer

**You lose if:** Three people die before you identify the killer  
**You win if:** You accuse the correct person with at least 3 clues

**Key commands:**
```
talk <name>           Start a conversation — choose what to ask
examine               List crime scenes to examine
examine <victim>      Examine the scene where someone died (reveals physical clues)
protect <name>        Stay close to someone — they gain trust and may share more
protect               Show who might be at risk based on the killer's pattern
clues                 Review what you've found and current suspects
accuse <name>         Accuse someone — wrong accusations make things worse
status                See day, victim count, next strike estimate
nearby                See who is in your current location
go <district>         Move to a different part of town
```

## How conversations work

When you `talk <name>`, a menu of questions appears. You choose what to ask. The other person's response depends on:

- **Bond level** — higher trust unlocks deeper questions
- **Day** — people notice more and share more as time passes
- **Trait** — an aggressive person responds differently than a cautious one
- **What happened** — after a murder or protection, new dialogue options appear

Bond increases each time you talk to someone (+0.15) and when you protect them (+0.3). Some questions are locked until bond reaches a threshold — you'll see them grayed out with `[needs more trust]`.

## File structure
```
main.py                  Entry point
cli.py                   Terminal interface and game loop
dashboard.html           Visual dashboard (served via HTTP)
scenarios/
  base.py                Base classes: Scenario, Character, Clue, DialogueOption
  murderer.py            The Murderer scenario
  trial.py               The Trial scenario
  labyrinth.py           The Labyrinth scenario
```

