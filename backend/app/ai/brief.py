"""What every AI analyst of AresGate is told before it is asked anything: how to tell a threat
from the noise of the internet, and what the owner has said of their network.

It is the same for every question about a threat (a reading of one incident, a judgement of a
whole family of them), and it comes first, ahead of what makes each question its own, so a
provider that caches the start of a prompt keeps all of it and charges a tenth for it every time
after the first. It is also long enough to be cached at all: OpenAI's GPT-6 models don't cache
less than 1,024 tokens. Nothing in it changes from one question to the next except when the owner
changes their settings, and nothing in it is a date, a count or an id, which would make it new
each time.
"""

from typing import Final

from app.ai.redaction import Redactor
from app.threats.settings import Tuning, describe

PLAYBOOK: Final = """\
How to tell a real threat from the noise of the internet:

Background noise. Scanners sweep the whole internet all day: research projects, security \
companies, and botnets looking for open ports and weak passwords. One of them can raise \
thousands of alerts against a home network and none of it is aimed at the owner. A scan, a probe \
or a rejected login from an address that has no other business with this network is noise or a \
probe, however many alerts it raised, and alerts that say the traffic was blocked or dropped \
mean the defences worked. Judge the kind of thing, not how many times it happened: ten thousand \
copies of one scan are one scan.

What changes the picture. Something got through and answered. An exploit aimed at a service that \
really is reachable from the internet (the owner's setup below says which). A scan followed by an \
exploit from the same address. A device on the home network talking out to a known-bad host or a \
command server, or malware, ransomware, a web shell or a backdoor being named. A login that \
succeeded after many failures. Independent programs agreeing about the same device. These are \
attacks or compromises, and a compromise is the most serious: it means the network is already \
being used.

Direction matters. Traffic from the internet in is what the network is for being exposed to. \
Traffic from a device on the home network out to the internet is the network doing something, \
so the same words are more serious. Alerts between two devices on the home network are usually \
discovery, backups, printers, media servers and misconfigured rules, and are noise unless they \
name malware or an exploit.

Be honest about what you can't see. Alerts rarely say whether an attack worked. Give a high \
confidence only when the evidence is plain, say "unclear" when it is too thin to tell, and never \
invent a product, a vulnerability or an address that the evidence doesn't show. Keep "threat" \
and a high confidence for what the owner should be woken for: alarms must stay rare.\
"""


def setup(redactor: Redactor, tuning: Tuning) -> str:
    """What the owner has told AresGate about their network, for the analyst: what is reachable
    from the internet and whatever else they wrote, through the redactor."""
    lines = ["What the owner has told AresGate about this network:", describe(tuning)]
    if tuning.notes:
        lines.append(f"In their own words: {redactor.text(tuning.notes, 600)}")
    return "\n".join(lines)


def start(redactor: Redactor, tuning: Tuning) -> str:
    """The start of the prompt that is the same for every question about threats."""
    return f"{PLAYBOOK}\n\n{setup(redactor, tuning)}"
