# Three-minute demonstration

1. Open `examples/sample-report/report.html`. Point out that both inventories contain six assets, but one asset disappeared and another appeared.
2. Search for `LT-105`. Its serial changed under an unchanged asset tag. Explain why matching identifiers needs validation before accepting a record as the same device.
3. Reset, then search for `LT-102`. Show the removed assignee and warranty review. Distinguish a changed field from a finding: multiple findings can apply to one device.
4. Search for an assignee, site, or serial displayed in the findings table. Findings retain that context even when those fields did not change. Search `LT-103` to see that a missing asset's assignment and site are explicitly labeled as baseline information.
5. Reset and use Print / save PDF if you want a shareable report. The print button clears filters to include all rows.
6. Run the CLI example from README, then run `python -m unittest discover -s tests -v`.

## Questions to practice answering

- Why match on asset tag? It is the declared inventory key; serial mismatches are flagged, and tag renames remain missing/added pairs.
- Why not automatically delete missing records? Export filters or collection failures can hide existing equipment.
- What makes this repeatable? Explicit planning date, fixed thresholds, stable sorting, unchanged input files, and source hashes.
- How would this connect to real operations? A separate authorized collector exports inventory; a scheduled job invokes this CLI; an owner reviews the findings before a new baseline is accepted.
- What is deliberately outside scope? Endpoint discovery, ticket submission, vendor warranty verification, notifications, and automatic remediation.

Describe actual behavior and show the tests. Do not claim production deployment or measured time savings without evidence.
