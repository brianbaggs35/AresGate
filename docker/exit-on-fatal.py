#!/usr/bin/env python3
"""supervisord event listener: if any program gives up restarting (FATAL), stop the whole
container so Docker's restart policy brings it back cleanly instead of limping along."""

import os
import signal
import sys


def main() -> None:
    while True:
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        fields = (token.partition(":") for token in sys.stdin.readline().split())
        header = {key: value for key, _, value in fields}
        payload = sys.stdin.read(int(header["len"]))
        sys.stderr.write(f"exit-on-fatal: {header['eventname']} {payload}\n")
        sys.stderr.flush()
        os.kill(1, signal.SIGTERM)
        sys.stdout.write("RESULT 2\nOK")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
