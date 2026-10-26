#!/usr/bin/env bash
# Fails when a script ends a pipeline in a command that stops reading early: grep --quiet (or -q,
# or --max-count) stops at the first match, and head stops after its lines. Whatever feeds it can
# then die of a broken pipe if it is still writing, and these scripts run under pipefail, which
# makes that the whole pipeline's failure. It happens only now and then, depending on timing, so
# a check that is right still fails once in a while. Read the output into a variable first and
# give grep that (grep --quiet pattern <<<"$output"). Pass the scripts to check.
set -euo pipefail

if (($# == 0)); then
    echo "Usage: $0 SCRIPT..." >&2
    exit 2
fi

status=0
for script in "$@"; do
    # A pipeline carried over to the next line is joined to it, and what is quoted is blanked, so
    # a | or a flag inside a string does not count.
    found="$(awk '
        {
            line = $0
            gsub(/"[^"]*"/, "\"\"", line)
            gsub(/'"'"'[^'"'"']*'"'"'/, "'"''"'", line)
            sub(/(^|[[:space:]])#.*$/, "", line)
            if (joined == "") first = NR
            joined = joined " " line
            if (line ~ /(\||\\)[[:space:]]*$/) next
            command = joined
            joined = ""
            gsub(/\|\|/, ";", command)
            if (command ~ /\|[[:space:]]*grep[^;&]*[[:space:]](--quiet|--max-count|-[A-Za-z]*[qm])/ ||
                command ~ /\|[[:space:]]*head([[:space:]]|$)/) {
                print first
            }
        }' "$script")"
    for number in $found; do
        echo "::error file=$script,line=$number::A pipeline ends in a command that stops reading early (grep --quiet, grep --max-count, head). Read the output into a variable first and use <<<." >&2
        status=1
    done
done
exit "$status"
