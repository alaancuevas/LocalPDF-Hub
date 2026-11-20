# Do the tests notice when a defense is removed?

A green test named after a defense does not prove the defense works: another check may reject the request first, or the test may assert something else. This folder measures it. Each mutant in [`mutants.json`](mutants.json) removes one defense listed in [`docs/security-defenses.md`](../docs/security-defenses.md); the tests run against each mutant, and a defense counts as watched only if some test fails without it.

## Run it yourself

From the repository root, with the dev requirements installed (`python -m pip install -r requirements.txt -r requirements-dev.txt`):

```
python security/mutate.py
```

It copies `HEAD` with `git archive` into a temporary folder, so uncommitted changes are not measured and the working tree is never touched. It takes about 40 seconds per mutant. Logs and `summary.json` go to `security/results/` (ignored by git). Options: `--only L02,LC` to run some mutants, `--check` to validate `mutants.json`.

## Rules

- **One mutant per defense**, an exact text replacement that removes it, plus a **control** (`LC`) that only changes a log message. If the control is caught, the run is not valid.
- **Two scopes:** `tests/test_security.py` alone, and the full suite.
- **Every defense counts**, first layer or second. An equivalent mutant (one that changes no behaviour) would be left out with its reason; there are none.
- Not every defense has a mutant yet: five request guard checks (L01, L04, L05, L08, L09) are not measured, and L03 (constant-time comparison) cannot be measured by a test. See the inventory.

## Results

32 defenses, measured before (`43677d3`) and after the tests added in `7a5a06b`…`a4cc9e3`, one commit per defense. Python 3.12, macOS.

| | `tests/test_security.py` | Full suite |
|---|---|---|
| Before | 3/32 | 10/32 |
| After | 24/32 | 31/32 |

Still missed: **L20**: no test fails if the launch token stops being random on every start.

| Id | Defense | `tests/test_security.py` | Full suite |
|---|---|---|---|
| L02 | Launch token required on unsafe requests | caught | caught |
| L06 | Only GET and HEAD skip the token check | caught | caught |
| L07 | Declared Content-Length over the limit gets 413 | missed → **caught** | missed → **caught** |
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
| L20 | Launch token is random on every start | missed | missed |
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

## Limits

- The mutants were chosen by reading the code: the rate counts known defenses that have a test, not unknown vulnerabilities.
- One mutant per defense. A test can catch the removal of a defense and still miss a subtler weakening of it.
- The frontend (`frontend/`) is not measured.
- The runs were on macOS. CI also runs the suite on Windows, but the mutants were not run there.
