# Do the tests notice when a defense is removed?

LocalPDF Hub runs a server on the user's computer, and any page open in the browser can send it requests. [`docs/security-defenses.md`](../docs/security-defenses.md) lists each defense and the test that watches it. A test named after a defense can pass without it: another check may refuse the request first, or the test may assert something else. Each mutant in [`mutants.json`](mutants.json) removes one defense from a copy of the code. A defense counts as watched only if some test fails without it.

## Run it yourself

From the repository root, with the dev requirements installed (`python -m pip install -r requirements.txt -r requirements-dev.txt`):

```
python security/mutate.py
```

It copies `HEAD` with `git archive` into a temporary folder, so uncommitted changes are not measured and the working tree is not touched. It takes about 40 seconds per mutant. Logs and `summary.json` go to `security/results/`, which git ignores. `--only L02,LC` runs some mutants; `--check` validates `mutants.json`.

## Rules

- One mutant per defense: an exact text replacement that removes it. A control, `LC`, changes only a log message. If a test catches the control, the run is not valid.
- Two scopes: `tests/test_security.py` alone, and the full suite.
- Every defense counts, first layer or second. No mutant turned out to be equivalent.
- L03, the constant-time token comparison, has no mutant. The inventory gives the reason.

## Results

| Run | `tests/test_security.py` | Full suite |
|---|---|---|
| First, at [`43677d3`](https://github.com/alaancuevas/LocalPDF-Hub/commit/43677d3), 32 defenses | [3/32](runs/43677d3.json) | [10/32](runs/43677d3.json) |
| Five request guard checks, at [`d677be2`](https://github.com/alaancuevas/LocalPDF-Hub/commit/d677be2), before their tests | [0/5](runs/d677be2.json) | [0/5](runs/d677be2.json) |
| Final, at [`7014c77`](https://github.com/alaancuevas/LocalPDF-Hub/commit/7014c77), 38 defenses | [31/38](runs/7014c77.json) | [38/38](runs/7014c77.json) |

The control survived every run. The final run was made with `security/mutate.py` on a clean clone.

Every mutant that survived a first run was a defense that worked and had no test. Each one got a test that fails with its mutant and passes without it, in its own commit: [21 commits](https://github.com/alaancuevas/LocalPDF-Hub/compare/43677d3...a4cc9e3) after the first run and [6 commits](https://github.com/alaancuevas/LocalPDF-Hub/compare/d677be2...b319174) after the guard run. The [7 defenses](runs/7014c77.json) that `tests/test_security.py` alone still misses (L11, L31, L32, L33, L36, L37, L38) are caught by tests in `test_api.py`, `test_images_pdf.py` and `test_compress.py`.

The review of the new tests found one defense missing. A 500 answer for an unhandled error went out without the CSP and `nosniff` headers, because Starlette builds it outside every middleware added with `add_middleware()`. [`d677be2`](https://github.com/alaancuevas/LocalPDF-Hub/commit/d677be2) fixes it with a test, and L39 now watches it.

| Id | Defense | `tests/test_security.py` | Full suite |
|---|---|---|---|
| L01 | Host must be a loopback name or the LAN IP | missed → **caught** | missed → **caught** |
| L02 | Launch token required on unsafe requests | caught | caught |
| L04 | Origin, when sent, must be this server | missed → **caught** | missed → **caught** |
| L05 | Sec-Fetch-Site, when sent, must be same-origin or none | missed → **caught** | missed → **caught** |
| L06 | Only GET and HEAD skip the token check | caught | caught |
| L07 | Declared Content-Length over the limit gets 413 | missed → **caught** | missed → **caught** |
| L08 | A chunked body is cut at the upload limit | missed → **caught** | missed → **caught** |
| L09 | Draining a refused body stops at the upload limit | missed → **caught** | missed → **caught** |
| L10 | A refused oversized body is not read | caught | caught |
| L11 | CSP default-src 'self' | missed | caught |
| L12 | CSP frame-ancestors 'none' | missed → **caught** | caught |
| L13 | CSP object-src 'none' | missed → **caught** | missed → **caught** |
| L14 | CSP base-uri 'none' | missed → **caught** | missed → **caught** |
| L15 | CSP form-action 'self' | missed → **caught** | missed → **caught** |
| L16 | X-Content-Type-Options: nosniff | missed → **caught** | missed → **caught** |
| L17 | Referrer-Policy: no-referrer | missed → **caught** | missed → **caught** |
| L18 | Security headers also cover the guard's own answers | missed → **caught** | missed → **caught** |
| L19 | No CORS approval for other origins | missed → **caught** | missed → **caught** |
| L20 | Launch token is random on every start | missed → **caught** | missed → **caught** |
| L21 | Interactive API docs and OpenAPI map not served | missed → **caught** | missed → **caught** |
| L22 | Unreadable PDF answered with a fixed message | missed → **caught** | missed → **caught** |
| L23 | Unexpected errors answered without details | missed → **caught** | missed → **caught** |
| L24 | Upload name reduced to its last path component | missed → **caught** | missed → **caught** |
| L25 | Unsafe characters in upload names replaced | missed → **caught** | missed → **caught** |
| L26 | Each job gets its own folder | missed → **caught** | missed → **caught** |
| L27 | Job folder removed after the answer | missed → **caught** | missed → **caught** |
| L28 | Job folder removed when the tool fails | missed → **caught** | missed → **caught** |
| L29 | Stale job folders swept | missed → **caught** | missed → **caught** |
| L30 | Server listens on loopback unless LAN is asked for | missed → **caught** | missed → **caught** |
| L31 | Page limit per job | missed | caught |
| L32 | Image count limit per job | missed | caught |
| L33 | Result size limit | missed | caught |
| L34 | Job deadline | missed → **caught** | missed → **caught** |
| L35 | Job gate caps concurrent heavy work | missed → **caught** | missed → **caught** |
| L36 | Image pixel cap read from the header | missed | caught |
| L37 | Compress pixel budget | missed | missed → **caught** |
| L38 | Compress work cap on the object walk | missed | caught |
| L39 | Security headers also cover 500 answers for unhandled errors | caught (added with the fix) | caught (added with the fix) |

## Limits

- The mutants were chosen by reading the code. The rate counts known defenses that have a test, not unknown vulnerabilities.
- One mutant per defense. A test that catches a removal can miss a subtler weakening. The reviews widened several tests for that reason; others may still miss one.
- The frontend is not measured.
- The mutants ran on macOS with Python 3.12. CI runs the suite on Windows as well, but not the mutants.

## How this was done

An AI agent environment that the maintainer directs wrote the mutants and the tests and ran the measurement. The maintainer decided what to measure, what to fix and what to publish, and reviewed the result. A separate agent reviewed each new test, given the test and the criterion but not the reasoning behind it.
