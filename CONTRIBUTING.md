# Contributing

Thank you for improving UWC/SFCC Extractor. Contributions should preserve the
project's evidence-first and human-reviewed scientific boundary.

## Development setup

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The public repository discovers 180 tests, executes 158 synthetic and contract
tests, and skips 22 tests that require private recorded-paper fixtures.

## Pull requests

1. Open an issue for substantial behavior or schema changes.
2. Keep each pull request focused on one general failure mode.
3. Add a minimal synthetic regression test that fails before the change and
   passes afterward.
4. Run the public suite locally.
5. Explain any data-contract, schema, compatibility or readiness-gate impact.
6. Do not weaken a scientific gate merely to improve a pass rate.

Paper-specific corrections belong in the affected extraction package, not in
generic production logic. General algorithm changes require evidence that the
failure mode is reusable beyond one paper.

## Data hygiene

Do not commit PDFs, publisher figures, long source quotations, author emails,
local absolute paths, proprietary datasets, manually digitized workbooks or
`.internal` extraction packages. Follow [DATA_AND_COPYRIGHT.md](DATA_AND_COPYRIGHT.md).

## Style

- Preserve original source strings in evidence fields.
- Keep schema and vocabulary enums in stable English `lower_snake_case`.
- Keep production and benchmark behavior separate.
- Prefer deterministic helpers for repeated processing.
- Avoid unrelated formatting changes.

By contributing, you agree that your contribution is licensed under the MIT
License included in this repository.
