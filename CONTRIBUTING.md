# Contributing to AresGate

Thank you for helping. AresGate is in early development, so please open an issue to talk about a
change before you spend time on a large one.

1. Set up with `make install`. [DOCS/development.md](DOCS/development.md) explains the layout, the
   checks and how to run the app while you work.
2. Every change has a ticket key like `AR-12`; open an issue and a maintainer will make the
   ticket. Branch from `master`, named `AR-<number>-short-name` after it, and start every
   commit message and the pull request's title with the same `AR-<number>`. Mention only that
   ticket's key; to refer to another, write "ticket 12".
3. Run `make lint` and `make test` (and `make e2e` for anything you can see in the browser). Add
   tests for what you add: the target is 100% coverage for pytest, Vitest and Playwright, and the
   build fails below 95%.
4. Open a pull request with the template filled in. CI must be green, including SonarQube Cloud
   with no open issues. Keep your branch linear by rebasing, not merging `master` into it. A
   maintainer merges by rebasing.

Report a security problem privately, as [SECURITY.md](SECURITY.md) describes, not in an issue.
