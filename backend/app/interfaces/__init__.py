"""The owner's own names for the parts of the network, and which data belongs to each.

Every program calls its ports something different (OPNsense ``igc0``, ntopng ``eno1``). An
*interface* here is what the owner calls a part of the network (Internet, Home, Guests, IoT); a
*feed* is one integration's view of one port, found from the names its data carries; and the
owner places each feed on an interface or sets it aside. Data keeps the name its source gave it
and is read through the placing, so placing a feed again relabels what was stored before."""
