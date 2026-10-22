#!/usr/bin/env python3
"""Container healthcheck: GET /api/health through nginx on the TLS port.

It connects to this container's own nginx, but checks the certificate the way a browser
does, for the name people browse to: one from a certificate authority, such as Let's
Encrypt, or the self-signed one AresGate makes when there isn't one. So an expired
certificate, or one for another name, makes the container unhealthy too.
"""

import http.client
import json
import os
import socket
import ssl
import sys

PORT = 8443
# The certificate nginx is serving, copied here by entrypoint.sh.
CERTIFICATE = "/run/aresgate/tls/cert.pem"


class LoopbackConnection(http.client.HTTPSConnection):
    """HTTPS to 127.0.0.1 that asks for, and verifies, the server's name."""

    def __init__(self, server_name: str, context: ssl.SSLContext) -> None:
        super().__init__(server_name, PORT, timeout=4, context=context)
        self.tls = context

    def connect(self) -> None:
        connection = socket.create_connection(("127.0.0.1", PORT), self.timeout)
        self.sock = self.tls.wrap_socket(connection, server_hostname=self.host)


def healthy() -> bool:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(cafile=CERTIFICATE)
    connection = LoopbackConnection(os.environ.get("ARESGATE_SERVER_NAME") or "localhost", context)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        return response.status == 200 and json.load(response).get("status") == "ok"
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        sys.exit(0 if healthy() else 1)
    except Exception as error:
        print(f"unhealthy: {error}", file=sys.stderr)
        sys.exit(1)
