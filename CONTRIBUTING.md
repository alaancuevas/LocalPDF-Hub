# Contributing

Thanks for wanting to help. LocalPDF Hub is maintained by one person in
their spare time, so please open an issue before a large change, to agree
on it first.

## Setup

```sh
npm ci && npm run build
python -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=src python -m localpdf_hub
```

## Before opening a pull request

```sh
python -m pytest -q
ruff check src tests && ruff format --check src tests
mypy src
```

- Keep changes small and focused, with a test for every fix.
- The server's contract is [docs/api.md](docs/api.md); the interface
  follows [docs/DESIGN.md](docs/DESIGN.md).
- Code, comments and commit messages are in English. Commit messages use
  [Conventional Commits](https://www.conventionalcommits.org/), for
  example `fix: keep the page order when splitting`.
- UI text lives in `frontend/js/locales/` (English and Spanish); add both.

Security problems go through [SECURITY.md](SECURITY.md), not issues.
