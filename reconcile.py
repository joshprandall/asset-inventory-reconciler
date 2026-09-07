#!/usr/bin/env python3
"""Compare declared inventory snapshots. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse
import csv
from datetime import date
import hashlib
import html
import io
import json
from pathlib import Path
import shutil
import sys

FIELDS = ('asset_tag', 'serial', 'assigned_to', 'site', 'status', 'last_seen', 'warranty_end')
STATUSES = {'active', 'spare', 'repair', 'retired'}
MAX_BYTES = 5 * 1024 * 1024


def iso_date(value: str) -> date:
    if len(value) != 10:
        raise ValueError(f'Expected YYYY-MM-DD date: {value!r}')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f'Expected YYYY-MM-DD date: {value!r}')
    return parsed


def read_inventory(path: Path, as_of: date) -> tuple[dict[str, dict], str]:
    """Normalize whitespace; compare asset tags and serials case-insensitively."""
    with path.open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Inventory exceeds the 5 MiB limit.')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    if reader.fieldnames is None or len(reader.fieldnames) != len(FIELDS) or set(reader.fieldnames) != set(FIELDS):
        raise ValueError('CSV must contain each required column exactly once: ' + ', '.join(FIELDS))
    records: dict[str, dict] = {}
    serials: set[str] = set()
    for row in reader:
        if len(records) >= 10000:
            raise ValueError('Inventory exceeds 10,000 records.')
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'Malformed row ending at line {reader.line_num}.')
        row = {k: v.strip() for k, v in row.items()}
        if any(len(v) > 250 or any(ord(c) < 32 for c in v) for v in row.values()):
            raise ValueError(f'Invalid field length or control character at line {reader.line_num}.')
        if not row['asset_tag'] or not row['serial'] or not row['site']:
            raise ValueError(f'Asset tag, serial, and site are required at line {reader.line_num}.')
        row['asset_tag'] = row['asset_tag'].upper()
        row['serial'] = row['serial'].upper()
        row['status'] = row['status'].lower()
        if row['status'] not in STATUSES:
            raise ValueError(f'Unknown status at line {reader.line_num}.')
        if row['asset_tag'] in records or row['serial'] in serials:
            raise ValueError(f'Duplicate asset tag or serial at line {reader.line_num}.')
        if row['last_seen']:
            if iso_date(row['last_seen']) > as_of:
                raise ValueError(f'Last-seen date is in the future at line {reader.line_num}.')
        if row['warranty_end']:
            iso_date(row['warranty_end'])
        records[row['asset_tag']] = row
        serials.add(row['serial'])
    return records, hashlib.sha256(raw).hexdigest()


def analyze(baseline: dict, current: dict, as_of: date, stale_days: int = 30, warranty_days: int = 60) -> dict:
    if stale_days < 0 or warranty_days < 0:
        raise ValueError('Day thresholds must be nonnegative.')
    findings, changes = [], []
    def finding(tag, code, detail):
        findings.append({'asset_tag': tag, 'code': code, 'detail': detail})
    for tag in sorted(baseline.keys() | current.keys()):
        before, after = baseline.get(tag), current.get(tag)
        if before is None:
            changes.append({'asset_tag': tag, 'kind': 'added', 'field': '', 'before': '', 'after': 'Present in current export'})
        elif after is None:
            changes.append({'asset_tag': tag, 'kind': 'missing', 'field': '', 'before': 'Present in baseline', 'after': ''})
            finding(tag, 'MISSING_FROM_EXPORT', 'Absent from current export; confirm export scope before treating this as a lost device.')
            continue
        else:
            for field in FIELDS[1:]:
                if before[field] != after[field]:
                    changes.append({'asset_tag': tag, 'kind': 'changed', 'field': field, 'before': before[field], 'after': after[field]})
            if before['serial'] != after['serial']:
                finding(tag, 'IDENTITY_REVIEW', 'Serial changed under the same asset tag; validate identity before accepting other changes.')
        if after['status'] == 'retired':
            if after['assigned_to']:
                finding(tag, 'RETIRED_ASSIGNED', 'Retired asset still has an assignee; reconcile return or assignment records.')
            continue
        if after['status'] == 'active' and not after['assigned_to']:
            finding(tag, 'MISSING_ASSIGNEE', 'Active asset has no recorded assignee.')
        if not after['last_seen']:
            finding(tag, 'LAST_SEEN_UNKNOWN', 'No last-seen date recorded.')
        elif (as_of - iso_date(after['last_seen'])).days > stale_days:
            finding(tag, 'STALE_RECORD', f'Last seen more than {stale_days} days before the planning date; verify collection coverage.')
        if not after['warranty_end']:
            finding(tag, 'WARRANTY_UNKNOWN', 'Warranty end date is not recorded.')
        else:
            remaining = (iso_date(after['warranty_end']) - as_of).days
            if remaining < 0:
                finding(tag, 'WARRANTY_EXPIRED', 'Recorded warranty end date is before the planning date.')
            elif remaining <= warranty_days:
                finding(tag, 'WARRANTY_DUE', f'Recorded warranty ends within {warranty_days} days, including today.')
    return {
        'schema_version': 1, 'as_of': as_of.isoformat(),
        'policy': {'stale_days': stale_days, 'warranty_days': warranty_days},
        'counts': {'baseline_assets': len(baseline), 'current_assets': len(current),
                   'added_assets': len(current.keys() - baseline.keys()),
                   'missing_assets': len(baseline.keys() - current.keys()),
                   'changed_assets': len({c['asset_tag'] for c in changes if c['kind'] == 'changed'}),
                   'field_changes': sum(c['kind'] == 'changed' for c in changes),
                   'findings': len(findings)},
        'changes': changes, 'findings': findings,
    }


def csv_safe(value: object) -> str:
    """Neutralize spreadsheet formula prefixes in exported cells."""
    text = str(value)
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text


def render_html(report: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    cards = ''.join(f'<article><strong>{esc(v)}</strong><span>{esc(k.replace("_", " "))}</span></article>' for k, v in report['counts'].items())
    findings = ''.join(f'<tr><td>{esc(f["asset_tag"])}</td><td><span class="tag">{esc(f["code"])}</span></td><td>{esc(f["detail"])}</td></tr>' for f in report['findings'])
    changes = ''.join('<tr>' + ''.join(f'<td>{esc(c[k])}</td>' for k in ('asset_tag', 'kind', 'field', 'before', 'after')) + '</tr>' for c in report['changes'])
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Asset Inventory Reconciliation</title><style>
:root{color-scheme:dark;font:16px/1.55 system-ui,sans-serif;background:#0b1220;color:#e7eef9}*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:32px 20px}header{border-bottom:1px solid #30415b;padding-bottom:24px}h1{font-size:clamp(2rem,5vw,3rem);line-height:1.1;margin:12px 0}h2{font-size:1.4rem}.eyebrow{color:#6ee7d0;letter-spacing:.14em;font-size:.8rem}p{color:#bac8db}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:12px;margin:24px 0}article{background:#152237;border:1px solid #30415b;border-radius:12px;padding:18px}strong{display:block;font-size:2rem;color:#6ee7d0}span{display:block}.tag{font-size:.75rem;color:#fcd58b}input,button{font:inherit;padding:10px 14px;background:#152237;border:1px solid #59708e;border-radius:8px;color:inherit}input{width:min(100%,460px)}button{cursor:pointer}button:hover{background:#25415b}:focus-visible{outline:3px solid #6ee7d0;outline-offset:3px}.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.scroll{overflow-x:auto;border:1px solid #30415b;border-radius:10px}table{border-collapse:collapse;width:100%;min-width:640px}th,td{text-align:left;vertical-align:top;padding:13px;border-bottom:1px solid #30415b;overflow-wrap:anywhere}th{background:#152237}td{font-size:.9rem}details{margin:24px 0}summary{cursor:pointer;font-weight:600}footer{margin-top:36px;font-size:.85rem;color:#bac8db}@media print{:root{color-scheme:light;background:white;color:black}.controls{display:none}.scroll{overflow:visible}table{min-width:0}article,th{background:white}p,footer,.tag,strong{color:black}main{padding:0}details{display:block}}
</style><main><header><div class="eyebrow">OPERATIONS / ASSET VISIBILITY</div><h1>Inventory, reconciled.</h1><p>A comparison of declared exports. Findings are review prompts, not proof of loss, compromise, or replacement need.</p><p>Planning date: ''' + esc(report['as_of']) + '''</p></header><section class="cards" aria-label="Summary">''' + cards + '''</section>
<div class="controls"><label for="search">Filter both tables</label><input id="search" type="search" placeholder="Asset tag, finding, owner, or site"><button id="reset">Reset filter</button><button id="print">Print / save PDF</button></div><p id="count" role="status" aria-live="polite"></p>
<h2>Review findings</h2><div class="scroll" tabindex="0" aria-label="Findings table"><table><thead><tr><th>Asset</th><th>Finding</th><th>Follow-up</th></tr></thead><tbody>''' + findings + '''</tbody></table></div>
<h2>Snapshot changes</h2><div class="scroll" tabindex="0" aria-label="Changes table"><table><thead><tr><th>Asset</th><th>Change</th><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>''' + changes + '''</tbody></table></div>
<details><summary>How to interpret this report</summary><p>Match key: asset tag, case-insensitive. A changed serial requires identity review. Missing devices may reflect export filters. Retired records skip stale/warranty checks. Stale means strictly older than the threshold; warranty due includes the threshold day. Counts remain inventory-wide while filtering.</p></details><footer>Generated locally by Asset Inventory Reconciler. No live systems were queried or modified.</footer></main>
<script>const search=document.querySelector('#search');const rows=[...document.querySelectorAll('tbody tr')];function filter(){let shown=0;const query=search.value.toLowerCase();for(const row of rows){row.hidden=!row.textContent.toLowerCase().includes(query);if(!row.hidden)shown++;}document.querySelector('#count').textContent=`Showing ${shown} of ${rows.length} report rows.`;}search.addEventListener('input',filter);document.querySelector('#reset').addEventListener('click',()=>{search.value='';filter();search.focus();});document.querySelector('#print').addEventListener('click',()=>{search.value='';filter();window.print();});filter();</script></html>'''


def write_reports(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    try:
        (output / 'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (output / 'report.html').write_text(render_html(report), encoding='utf-8')
        for name, keys in (('changes', ('asset_tag', 'kind', 'field', 'before', 'after')), ('findings', ('asset_tag', 'code', 'detail'))):
            with (output / f'{name}.csv').open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(keys)
                writer.writerows([csv_safe(row[k]) for k in keys] for row in report[name])
    except BaseException:
        shutil.rmtree(output)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('current', type=Path)
    parser.add_argument('--as-of', required=True, type=iso_date)
    parser.add_argument('--stale-days', type=int, default=30)
    parser.add_argument('--warranty-days', type=int, default=60)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        baseline, before_hash = read_inventory(args.baseline, args.as_of)
        current, after_hash = read_inventory(args.current, args.as_of)
        report = analyze(baseline, current, args.as_of, args.stale_days, args.warranty_days)
        report['source_sha256'] = {'baseline': before_hash, 'current': after_hash}
        write_reports(report, args.output)
    except (ValueError, OSError, UnicodeError, csv.Error, OverflowError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2
    print(json.dumps(report['counts'], indent=2))
    print(f'Report: {args.output / "report.html"}')
    return 1 if report['findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
