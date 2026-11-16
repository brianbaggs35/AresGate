"""What is normal on this network, learned from what AresGate has already stored, and what is not.

No AI provider is involved and nothing is sent anywhere: a baseline is a few plain statistics that
can be explained in a sentence. A deviation is stored as an event of the kind ``alert`` from the
source ``baseline``, with a low severity and a confidence in its record, so the incident engine
files it with whatever else is known of the same device, and the owner's verdicts apply to it as
they do to any alert (one called not suspicious stops it filing again).
"""

from typing import Final

# Whose events these are, as the incident engine and the pages name them.
SOURCE: Final = "baseline"
CONNECTION: Final = "learned"
NAME: Final = "Learned baselines"
KIND: Final = "alert"
