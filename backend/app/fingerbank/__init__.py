"""Device intelligence: what Fingerbank says each device on the network is.

Fingerbank fingerprints devices. Asked about a hardware (MAC) address it answers with the make and
model it most likely belongs to, the operating system and how sure it is. What it says is kept with
the device (``DeviceIdentity``), so every later connection from the same hardware address carries
it without asking again, and a device is only asked about again when what is kept has gone stale.

The owner's own devices are asked about first, the newest on the network first. Devices in
incidents and threats are asked about too, when the owner has allowed it. Only the hardware address
is ever sent, and never one that the device made up for itself, which says nothing of what it is.
"""
