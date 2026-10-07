# Validation record

31 unit/integration tests passed locally with Python 3.12.14 on Linux on October 7, 2026.
Command: `python -m unittest discover -s tests -v`.
The original 25 tests passed before the change. Six additional tests failed against the old implementation and passed after adding finding context. They cover current assignment/site/serial, baseline context for missing records, empty current assignees, searchable context for unchanged assets, HTML escaping, JSON preservation, and spreadsheet formula handling in the new CSV columns.
The sample CLI returned expected exit code 1 and produced four output files.
Expected counts: 6 baseline, 6 current, 1 added, 1 missing, 4 changed assets, 5 field changes, 9 findings.
Remote GitHub workflow results remain to be checked after upload. Interactive browser controls were not exercised in an automated browser.
