import os

TEST_DATABASE_URL = os.environ.get("ARESGATE_TEST_DATABASE_URL", "")
SERVER_NAME = "aresgate.test"
ORIGIN = f"https://{SERVER_NAME}"
