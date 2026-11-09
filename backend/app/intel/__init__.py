"""Threat intelligence: what outside services say about the internet addresses that an incident
involves.

A service is asked about one address at a time, within the limits its access level allows, and
what it says is kept (``store``). The AI reads that as part of an incident, and a read-only tool
lets it ask about one address. Only addresses on the internet are ever sent: an address on the
home network is never shown to a service, and neither is the home's own address on the internet.
"""
