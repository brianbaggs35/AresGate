"""Test harness for the Playwright end-to-end tests.

Only the e2e image (the Dockerfile's ``e2e`` target) and CI's run on the runner contain this
package; the production image never does, because it can erase the database. See
frontend/e2e/README.md.
"""
