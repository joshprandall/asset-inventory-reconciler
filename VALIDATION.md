# Validation record

25 unit/integration tests passed locally with Python 3.12.13 on Linux.
Command: `python -m unittest discover -s tests -v`.
The sample CLI returned expected exit code 1 and produced four output files.
Expected counts: 6 baseline, 6 current, 1 added, 1 missing, 4 changed assets, 5 field changes, 9 findings.
Remote GitHub workflow results remain to be checked after upload. Interactive browser controls were not exercised in an automated browser.
