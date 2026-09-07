# GitHub upload

1. Create a public repository named `asset-inventory-reconciler`. Leave automatic README, license, and gitignore creation off.
2. Extract the download and open the inner project folder containing `reconcile.py`.
3. Upload the contents of that folder, keeping `examples` and `tests` as subfolders. Commit with `Add asset inventory reconciler`.
4. Confirm `.github/workflows/test.yml` exists. If browser upload omitted it, choose Add file → Create new file and enter that exact full path, then paste the workflow below.
5. Open Actions and inspect Python tests. Four jobs should run. A green workflow verifies the tests, not production suitability.

Repository description:

`Python inventory reconciliation with change tracking, maintenance findings, searchable HTML reports, and automated tests.`

## Complete test workflow

```yaml
name: Python tests
on:
  push:
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ['3.10', '3.13']
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: ${{ matrix.python-version }}
      - name: Run tests
        run: python -m unittest discover -s tests -v
```

Official action references: https://github.com/actions/checkout and https://github.com/actions/setup-python
