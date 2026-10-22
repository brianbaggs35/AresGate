# Security policy

AresGate holds the credentials for your firewall and monitoring tools and reads your network's
logs, so a security problem here matters. Thank you for reporting one privately.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private report instead:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Describe what you found, how to reproduce it, and which version you ran.

The maintainer will reply as soon as they can. Please give a reasonable time to fix the problem
before you share it publicly.

## Supported versions

Only the latest release is supported. Fixes land in a new release, so update to the newest
image after reading its release notes.

## What is in scope

- The AresGate application, its container image and its default configuration.
- How credentials, sessions and the setup code are stored and protected.

Problems in OPNsense, ntopng, Wazuh or another tool AresGate connects to belong with that
project.

## Checks on every change

Every pull request is checked by CodeQL, SonarQube, Trivy, pip-audit, npm audit, bandit and an
audit of the workflow files, and Dependabot keeps dependencies current.
