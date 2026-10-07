# Asset Inventory Reconciler

Compare two CSV inventory snapshots and produce a searchable HTML dashboard, machine-readable JSON, and spreadsheet reports. Identify assignment changes, missing records, identity mismatches, and maintenance review items before accepting a new inventory baseline.

**A local Python automation project with fictional sample records.** No agents, credentials, external packages, or live-system changes. This tool reconciles exported records; it does not discover endpoints.

## See it first

Download the repository, then open `examples/sample-report/report.html` in a browser. Each finding includes its recorded assignee, site, and serial, with the source snapshot clearly labeled. Search filters both report tables, including this context for assets whose fields did not change. Reset restores all rows. Print / save PDF clears the filter to print the complete report. The HTML is self-contained and makes no network requests.

## Run it

Python 3.10 or newer. In the project folder:

```sh
python reconcile.py examples/baseline.csv examples/current.csv --as-of 2026-09-07 --output output/demo
python -m unittest discover -s tests -v
```

On Windows, use `py` instead of `python` if needed. Each output directory must be new. No installation step is required.

The sample intentionally returns **exit code 1** because it contains findings. This is expected, not a crash.

| Exit | Meaning |
| --- | --- |
| 0 | Reports created; no review findings |
| 1 | Reports created; review findings present |
| 2 | Invalid input, arguments, or file operation; inspect the error |

## Sample result

Six assets in each snapshot, one added asset, one missing asset, four changed assets, five changed fields, and nine findings. Equal inventory totals can conceal a missing device and a new device.

| Asset | Review findings |
| --- | --- |
| LT-102 | Active without an assignee; warranty due |
| LT-103 | Missing from current export |
| LT-104 | Stale last-seen date; expired recorded warranty |
| LT-105 | Serial changed under the same asset tag |
| LT-106 | Retired but still assigned |
| LT-107 | Missing last-seen date and warranty date |

## Input contract

Both files require exactly these headers, in any order:

```csv
asset_tag,serial,assigned_to,site,status,last_seen,warranty_end
```

- Asset tag, serial, and site are required. Assignee and dates may be empty; empty values are reviewed where applicable.
- Status is `active`, `spare`, `repair`, or `retired`.
- Dates use YYYY-MM-DD. Last-seen dates cannot be after the supplied planning date.
- Asset tags and serials are normalized to uppercase. Surrounding whitespace is trimmed. Duplicate tags or serials in either export reject the run; identity ambiguity is not silently resolved.
- Other text changes, including assignee/site capitalization, remain visible.
- Limits: 5 MiB per export, 10,000 records, 250 characters per cell. Control characters and malformed row widths are rejected. Header-only files are supported and may represent an empty inventory.

Match by asset tag. If a tag is renamed, it appears as a missing asset plus an added asset, even if its serial is unchanged. A serial change under a retained tag generates an identity review.

## Maintenance policy

Default stale threshold: **strictly more than 30 days** since last seen. Default warranty window: **0 through 60 days inclusive** from the planning date. Earlier warranty dates are expired. Retired assets skip last-seen and warranty checks but still flag retained assignment.

```sh
python reconcile.py examples/baseline.csv examples/current.csv --as-of 2026-09-07 --stale-days 14 --warranty-days 90 --output output/custom
```

All dates are calendar dates, not timestamps. Policies are review settings, not vendor or compliance requirements.

## Outputs and automation

- `report.html`: searchable dashboard with reset and print buttons; responsive summary cards and horizontally scrollable tables.
- `summary.json`: structured counts, changes, findings, policy, and SHA-256 hashes of original input bytes.
- `changes.csv`: one row per changed field or added/missing asset.
- `findings.csv`: one row per review finding, including source snapshot, serial, assignee, and site for follow-up.

Finding context comes from the current snapshot when the asset is present. For a missing asset, it comes from the baseline and is explicitly labeled `baseline`; this is last recorded information, not a claim about the asset's current assignment or location. Empty current assignees remain empty in JSON/CSV and appear as “Unassigned” in the dashboard.

The report uses `schema_version: 2`. JSON findings add `context_source`, `serial`, `assigned_to`, and `site`; `findings.csv` appends those four columns after the existing `asset_tag,code,detail` columns. Consumers that enforce version 1 or a fixed column count must accept this updated schema. Reconciliation policies, counts, change records, input columns, and CLI exit codes are unchanged.

The CLI can be invoked by an existing job scheduler after exports arrive. Supply the planning date explicitly and use a unique output folder for each run. Handle exit 1 as “review required,” not a runtime failure. Scheduling and inventory collection are not installed by this project. Baselines are never automatically overwritten.

## Engineering choices

Validation precedes report creation. Output directories cannot be overwritten. Report text is HTML-escaped, and exported CSV cells with spreadsheet formula prefixes are prefixed with an apostrophe. JSON preserves values. Results are sorted by normalized asset tag for reproducibility; SHA-256 fingerprints provide byte-level input traceability, not signatures or proof of authenticity.

The 31-test suite covers policy boundaries, input rejection, unchanged source data, determinism, HTML escaping, spreadsheet formula handling, report output, and CLI exit behavior. It also verifies current versus baseline finding context, unassigned assets, searchable unchanged-asset context, and safe context exports. Local tests passed; the included GitHub workflow tests Python 3.10 and 3.13 on Ubuntu and Windows after upload. Browser interactions have not been verified by an automated browser test.

## Interpret with care

A missing record may reflect export scope, and a stale date may reflect collector coverage. Expired warranty does not establish hardware failure or replacement need. Findings require an owner to validate the underlying records. Public examples use fictional people and devices; employer exports should stay in an appropriate private environment.

See [DEMO_GUIDE.md](DEMO_GUIDE.md) and [GITHUB_SETUP.md](GITHUB_SETUP.md).
