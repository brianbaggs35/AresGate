#!/usr/bin/env bash
# Explains a failed Trivy scan: puts each finding in the error message and in the job summary,
# so the reason is on the failed run's page and not only in the log of an earlier step.
# Usage: trivy-report.sh <scan name> <outcome of the scan step> <SARIF file>
# Exits 0 when the scan passed and 1 when it didn't.
set -euo pipefail

name="$1"
outcome="$2"
sarif="$3"

if [[ "$outcome" == "success" ]]; then
  exit 0
fi

findings=""
if [[ -s "$sarif" ]]; then
  findings="$(jq -r '
    .runs[]?.results[]? |
    "\(.ruleId // "unknown")  \(.locations[0].physicalLocation.artifactLocation.uri // "")  \((.message.text // "") | gsub("\n"; "; "))"
  ' "$sarif")"
fi

if [[ -z "$findings" ]]; then
  message="The $name scan failed without a report. The error is in the log of the $name scan step."
else
  message="High or critical findings in the $name scan:"$'\n'"$findings"
fi

# An annotation is one line, so the message's own line breaks are escaped.
annotation="${message//'%'/%25}"
annotation="${annotation//$'\r'/%0D}"
annotation="${annotation//$'\n'/%0A}"
echo "::error title=Trivy $name scan::$annotation"

{
  echo "### Trivy $name scan"
  echo
  if [[ -z "$findings" ]]; then
    echo "$message"
  else
    echo "High or critical findings:"
    echo
    echo '```'
    echo "$findings"
    echo '```'
  fi
} >>"${GITHUB_STEP_SUMMARY:-/dev/null}"

exit 1
