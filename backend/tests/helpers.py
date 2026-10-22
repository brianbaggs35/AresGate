import os
import secrets

TEST_DATABASE_URL = os.environ.get("ARESGATE_TEST_DATABASE_URL", "")
SERVER_NAME = "aresgate.test"
ORIGIN = f"https://{SERVER_NAME}"
# A fresh key for each test run: nothing here is worth keeping.
TEST_SECRET_KEY = secrets.token_urlsafe(32)

ACCOUNT_USERNAME = "brian"
ACCOUNT_PASSWORD = "a sentence nobody would guess"
OTHER_ORIGIN = "https://evil.example"
