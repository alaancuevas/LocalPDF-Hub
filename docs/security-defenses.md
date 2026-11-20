# Security defenses

Every control in LocalPDF Hub that keeps another site, another program or a hostile file from misusing the app, with the test that watches it. A test "watches" a defense only if it fails when that defense is removed; [`security/`](../security/) has the mutants that check this and the results.

Line numbers match the code as of the last change to this file.

**Status:** *tested* = a test fails without it · *not measured* = no mutant yet · *open* = known to have no test · *not mutated* = see the note.

## Request guard and launch token

| Id | Defense | Where | What it prevents | Test that watches it | Status |
|---|---|---|---|---|---|
| L01 | `Host` must be a loopback name (or the LAN IP when LAN access is on) | `src/localpdf_hub/security.py:119` | DNS rebinding: a hostile domain resolved to 127.0.0.1 reading `index.html` and its token | none | not measured |
| L02 | Unsafe requests must carry the launch token | `security.py:173-175` | Another page in the browser triggering a tool (CSRF) | `tests/test_api.py::test_requests_without_the_token_are_refused` | tested |
| L03 | The token is compared in constant time (`hmac.compare_digest`) | `security.py:174` | Guessing the token from how long the comparison takes | none | not mutated: a timing difference has no reliable unit test |
| L04 | `Origin`, when sent, must be this server | `security.py:176-178` | A request from another site that somehow carries the token | none | not measured |
| L05 | `Sec-Fetch-Site`, when sent, must be `same-origin` or `none` | `security.py:179-180` | Cross-site requests, as marked by the browser | none | not measured |
| L06 | Only GET and HEAD skip the token check | `security.py:26`, `127` | CSRF through POST, which every tool uses, or any other method | `tests/test_api.py::test_requests_without_the_token_are_refused` | tested |
| L07 | A declared `Content-Length` over the limit gets 413 without being read, token or not | `security.py:135-137` | Filling disk or memory with one request | `tests/test_security.py::test_an_upload_with_the_token_over_the_limit_is_also_refused_unread` | tested |
| L08 | A chunked body is counted while parsed and cut at the limit | `security.py:148-160` | The same, with no `Content-Length` to check | none | not measured |
| L09 | Draining a refused body stops at the limit | `security.py:89` | A request without token keeping the server reading forever | none | not measured |
| L10 | A refused body over the limit is not read at all | `security.py:128` | Reading attacker data that will be thrown away | `tests/test_security.py::test_an_upload_over_the_limit_is_refused_unread` | tested |
| L19 | No CORS approval for other origins | `src/localpdf_hub/app.py:120-121` | A foreign page reading `index.html`, and with it the token | `tests/test_security.py::test_another_origin_gets_no_cors_approval` | tested |
| L20 | The token is random on every start | `app.py:117` | A token that could be predicted or reused | none | open |
| L21 | No interactive docs or OpenAPI map | `app.py:118-119` | Publishing a map of every endpoint to any local page | `tests/test_security.py::test_the_api_map_is_not_published` | tested |
| L30 | The server listens on loopback unless `LOCALPDF_LAN` is set | `src/localpdf_hub/settings.py:25-26` | Exposing the tools to the network by default | `tests/test_security.py::test_the_server_listens_only_on_this_computer_by_default` | tested |

## Browser hardening headers

| Id | Defense | Where | What it prevents | Test that watches it | Status |
|---|---|---|---|---|---|
| L11 | CSP `default-src 'self'` | `security.py:45` | Running injected or third-party scripts | `tests/test_api.py::test_every_response_carries_a_strict_content_security_policy` | tested |
| L12 | CSP `frame-ancestors 'none'` | `security.py:51` | Clickjacking: the app framed by another page | same | tested |
| L13 | CSP `object-src 'none'` | `security.py:48` | Plugins and embedded objects | `tests/test_security.py::test_the_policy_blocks_plugins` | tested |
| L14 | CSP `base-uri 'none'` | `security.py:49` | An injected `<base>` sending relative requests elsewhere | `tests/test_security.py::test_the_policy_fixes_the_base_url` | tested |
| L15 | CSP `form-action 'self'` | `security.py:50` | Injected forms posting data to another site | `tests/test_security.py::test_the_policy_keeps_forms_on_this_server` | tested |
| L16 | `X-Content-Type-Options: nosniff` | `security.py:72` | The browser running a file as a type it was not served as | `tests/test_security.py::test_responses_are_not_sniffed` | tested |
| L17 | `Referrer-Policy: no-referrer` | `security.py:73` | Leaking local URLs to other sites | `tests/test_security.py::test_responses_send_no_referrer` | tested |
| L18 | The headers also cover the guard's own 400, 403 and 413 | `app.py:100-109` | Guard answers served without the policy | `tests/test_security.py::test_the_guards_own_refusals_carry_the_security_headers` | tested |
| L39 | The headers also cover the 500 answered for an unhandled error | `app.py:100-109` (wraps Starlette's own error middleware) | An error answer served without the policy | `tests/test_security.py::test_an_unexpected_error_carries_the_security_headers` | tested |

## Error answers

| Id | Defense | Where | What it prevents | Test that watches it | Status |
|---|---|---|---|---|---|
| L22 | An unreadable PDF gets a fixed message | `app.py:135-140` | Echoing parser details about the file | `tests/test_security.py::test_an_unreadable_pdf_gets_a_fixed_message` | tested |
| L23 | Unexpected errors get a fixed message | `app.py:161-164` | Leaking paths or internals in a 500 | `tests/test_security.py::test_an_unexpected_error_is_answered_without_its_details` | tested |

## Job folders

| Id | Defense | Where | What it prevents | Test that watches it | Status |
|---|---|---|---|---|---|
| L24 | An upload name keeps only its last path component | `src/localpdf_hub/workspace.py:25` | Path traversal (`../../x`) out of the job folder | `tests/test_security.py::test_an_upload_name_keeps_only_its_last_part` | tested |
| L25 | Characters outside letters, digits, `.`, `-`, `_` and space are replaced | `workspace.py:26` | Names some systems refuse; a second layer against traversal | `tests/test_security.py::test_an_upload_name_loses_characters_some_systems_refuse` | tested |
| L26 | Each job gets its own folder | `workspace.py:18-20` | Two jobs reading or overwriting each other's files | `tests/test_security.py::test_each_job_gets_its_own_folder` | tested |
| L27 | The job folder is removed after the answer | `src/localpdf_hub/api.py:67` | User files left on disk | `tests/test_security.py::test_a_job_folder_is_removed_after_the_answer` | tested |
| L28 | The job folder is removed when the tool fails | `api.py:60-62` | The same, after an error | `tests/test_security.py::test_a_job_folder_is_removed_when_the_tool_fails` | tested |
| L29 | Folders older than an hour are swept | `workspace.py:50-67` | Files left by a crash or a closed tab | `tests/test_security.py::test_stale_job_folders_are_swept_and_recent_ones_kept` | tested |

## Limits on work

| Id | Defense | Where | What it prevents | Test that watches it | Status |
|---|---|---|---|---|---|
| L31 | Page limit per job | `src/localpdf_hub/limits.py:110-115` | Thousands of tiny pages exhausting CPU and memory | `tests/test_api.py::test_page_limit_answers_413` and others | tested |
| L32 | Image count limit per job | `limits.py:94-99` | The same with images | `tests/test_images_pdf.py::test_two_hundred_images_pass_and_one_more_does_not` | tested |
| L33 | Result size limit | `limits.py:102-107` | A result too large for memory | `tests/test_api.py::test_to_images_stops_at_the_result_limit` and others | tested |
| L34 | Job deadline | `limits.py:56-59` | A job that never ends | `tests/test_security.py::test_a_job_past_its_deadline_is_stopped` | tested |
| L35 | Job gate: heavy jobs wait for room | `limits.py:30-41` | Several heavy jobs at once running out of memory | `tests/test_security.py::test_the_job_gate_holds_a_job_that_does_not_fit` | tested |
| L36 | Image size checked from the header before decoding | `src/localpdf_hub/tools/images_pdf.py:174` | Decompression bombs | `tests/test_images_pdf.py::test_too_many_pixels_is_refused_from_the_header` | tested (Pillow's own bomb check, `images_pdf.py:169`, covers the larger case) |
| L37 | Compress stops recompressing at its pixel budget | `src/localpdf_hub/tools/compress.py:359` | A PDF full of images taking minutes of CPU | `tests/test_compress.py::test_the_pixel_budget_stops_recompressing` | tested |
| L38 | Compress caps the work of its object walk | `compress.py:202` | A crafted PDF with a huge object graph | `tests/test_compress.py::test_work_cap_falls_back_to_lossless` | tested |

## Known gaps

- **L20** has no test yet: nothing fails if the token becomes a fixed string.
- **L01, L04, L05, L08, L09** have no mutant yet, so whether a test watches them is not measured.
