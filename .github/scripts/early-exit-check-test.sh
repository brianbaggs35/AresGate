#!/usr/bin/env bash
# Tests early-exit-check.sh against scripts that have the mistake in each way it can be written,
# and ones that are fine. Needs nothing but bash and awk, so run it from anywhere.
set -euo pipefail

check="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/early-exit-check.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail() {
    echo "::error::$1" >&2
    exit 1
}

# expect_flagged WHAT LINE: a script that is just LINE is refused, and the refusal names line 2.
expect_flagged() {
    local what="$1" line="$2" script="$work/flagged.sh" status=0 output
    printf '#!/usr/bin/env bash\n%s\n' "$line" >"$script"
    output="$("$check" "$script" 2>&1)" || status=$?
    [[ "$status" = 1 ]] || fail "$what: expected it to be refused, but the exit code was $status"
    grep --quiet --fixed-strings "line=2::" <<<"$output" || fail "$what: the refusal doesn't name line 2: $output"
}

expect_fine() {
    local what="$1" line="$2" script="$work/fine.sh" output
    printf '#!/usr/bin/env bash\n%s\n' "$line" >"$script"
    output="$("$check" "$script" 2>&1)" || fail "$what: expected it to pass, but it said: $output"
}

expect_flagged "grep --quiet after a pipe" 'docker logs aresgate | grep --quiet ready'
expect_flagged "grep -q after a pipe" 'docker logs aresgate | grep -q ready'
expect_flagged "grep with combined flags" 'docker logs aresgate | grep -iq ready'
expect_flagged "grep --max-count" 'docker logs aresgate | grep --max-count=1 ready'
expect_flagged "head" 'docker logs aresgate | head -n 1'
expect_flagged "grep on the next line" $'docker logs aresgate |\n    grep --quiet ready'
expect_flagged "grep on the next line after a backslash" $'docker logs aresgate \\\n    | grep --quiet ready'
expect_flagged "grep after a longer pipeline" 'docker logs aresgate | tr a-z A-Z | grep --quiet READY'

expect_fine "grep --quiet on a here-string" 'grep --quiet ready <<<"some logs"'
expect_fine "grep --quiet on a file" 'grep --quiet ready file.txt'
expect_fine "a pipeline that grep reads to the end" 'docker logs aresgate | grep ready >/dev/null'
expect_fine "grep with --quiet after ||" 'false || grep --quiet ready file.txt'
expect_fine "a | inside a string" 'echo "a | grep --quiet b"'
expect_fine "a | inside a pattern" "grep --quiet 'a|b' file.txt"
expect_fine "a comment" '# docker logs | grep --quiet ready'
expect_fine "a pipeline that ends in something else" 'docker logs aresgate | wc -l'

status=0
"$check" >/dev/null 2>&1 || status=$?
[[ "$status" = 2 ]] || fail "with no scripts it should say how to use it (exit 2), but the exit code was $status"

echo "early-exit-check.sh passed"
