"""What a conversation was for, in a few plain words.

An alert says what a rule thought of a flow, and the page lists the two ends and the port. Neither
says what the traffic was *for*, which is what tells a person whether it is worth worrying about:
a name being looked up is not a login being guessed. This puts it in words from what is known of
the flow: the application a program recognised, the port, and what the traffic asked for. It never
reads or guesses at what was inside, and says nothing where it can't tell.
"""

from typing import Final

_PORTS: Final[dict[int, str]] = {
    20: "Moving a file (FTP)",
    21: "Moving a file (FTP)",
    22: "Logging in to a computer (SSH)",
    23: "Logging in to a computer (Telnet, which is not encrypted)",
    25: "Sending email (SMTP)",
    53: "Looking up a name (DNS)",
    80: "Browsing a website (HTTP, not encrypted)",
    110: "Reading email (POP3)",
    123: "Setting a clock (NTP)",
    143: "Reading email (IMAP)",
    161: "Asking a device about itself (SNMP)",
    389: "Looking up accounts (LDAP)",
    443: "Browsing a website or using a service (HTTPS, encrypted)",
    445: "Sharing files (SMB)",
    465: "Sending email (SMTP, encrypted)",
    587: "Sending email (SMTP, encrypted)",
    993: "Reading email (IMAP, encrypted)",
    1433: "Using a database (SQL Server)",
    1883: "Talking to a smart device (MQTT)",
    1900: "Finding devices on the network (UPnP)",
    3306: "Using a database (MySQL)",
    3389: "Using a computer's screen from afar (Remote Desktop)",
    5060: "Setting up a phone call (SIP)",
    5353: "Finding devices on the network (mDNS)",
    5432: "Using a database (PostgreSQL)",
    5900: "Using a computer's screen from afar (VNC)",
    8080: "Browsing a website (alternate port)",
    8443: "Browsing a website or using a service (alternate port, encrypted)",
}
# What a program calls the application, where that is clearer than the port.
_APPS: Final[dict[str, str]] = {
    "dns": _PORTS[53],
    "http": _PORTS[80],
    "tls": _PORTS[443],
    "ssl": _PORTS[443],
    "quic": _PORTS[443],
    "ssh": _PORTS[22],
    "smb": _PORTS[445],
    "ntp": _PORTS[123],
    "rdp": _PORTS[3389],
    "smtp": _PORTS[25],
    "ftp": _PORTS[21],
    "mqtt": _PORTS[1883],
}


def of(
    *, app: str | None, port: int | None, protocol: str | None, asked_for: str | None = None
) -> str | None:
    """What the traffic was for, or None where nothing says. ``asked_for`` is the name it asked
    for (a site, a name looked up), where a program read one."""
    found = _APPS.get((app or "").lower()) or (_PORTS.get(port) if port is not None else None)
    if found is None:
        found = (
            "Pinging a device (ICMP)" if (protocol or "").lower() in ("icmp", "icmpv6") else None
        )
    if found is None:
        return None
    return f"{found}: {asked_for}" if asked_for else found
