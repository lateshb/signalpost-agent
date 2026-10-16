#!/usr/bin/env sh
# Signalpost agent - one-command runner for macOS and Linux (also Git Bash). Needs only Python 3.11+.
#   ./run.sh                   research the 11 demo companies, then open the results page
#   ./run.sh my-companies.txt  research the organisation numbers in that file (one per line)
#   ./run.sh FILE --previous out/old-envelopes.jsonl   any extra options go straight to the agent
set -e
cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is needed: https://www.python.org/downloads/"; exit 1
fi

venv_python() {
  if [ -x .venv-local/bin/python ]; then echo .venv-local/bin/python; else echo .venv-local/Scripts/python.exe; fi
}
if [ ! -x "$(venv_python)" ]; then
  echo "First run: setting up a local Python environment ..."
  "$PY" -m venv .venv-local
fi
VPY="$(venv_python)"
if [ ! -f .venv-local/installed.txt ]; then
  echo "First run: installing dependencies, about a minute ..."
  "$VPY" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  echo ok > .venv-local/installed.txt
fi

INPUT="${1:-demo/demo-companies.txt}"
[ $# -gt 0 ] && shift
echo "Researching the companies in $INPUT ..."
set +e
"$VPY" scripts/run_competition_batch.py "$INPUT" "$@"
CODE=$?
echo
echo "Results: out/envelopes.jsonl, out/report.json and out/report.html"
if [ -z "${SIGNALPOST_NO_OPEN:-}" ] && [ -f out/report.html ]; then
  (command -v open >/dev/null 2>&1 && open out/report.html) || (command -v xdg-open >/dev/null 2>&1 && xdg-open out/report.html >/dev/null 2>&1) || true
fi
exit $CODE
