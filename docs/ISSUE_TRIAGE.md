# Post-Release Issue Triage

This document converts post-v0.3.0 feedback and validation tracking into
actionable v0.3.1 planning.

It is maintained as a living document. Update the inventory and
recommendations as validation results arrive and new issues are filed.

---

## Purpose

After v0.3.0 was published, five validation tracking issues were opened
(#32–#36). Recorded validation evidence now includes:

- #36 sample-mode Prometheus export: **pass**
- #36 live-mode Prometheus evidence: **recorded via cross-link to #34 full Linux Docker validation (Goal 17.2)**
- #35 Chromium sample UI browser smoke workflow: **pass**
- #34 Linux Docker Engine validation attempt in Claude Code: **partial pass / live Docker unable to run**
- #34 GitHub Actions Docker live preflight: **pass**
- #34 full Linux Docker Engine validation (Goal 17.2, run ID 26423354910): **pass**

The #34 run found a package version mismatch. That mismatch was fixed in PR
#44. PR #46 added a manual Docker live preflight workflow. PR #48 added the
full Linux Docker Engine validation workflow. The manual run confirmed a full
pass across all nine validation steps, including live Prometheus validation.
That live-mode evidence was subsequently recorded in Issue #36 via a
cross-link comment (Goal 17.3). No confirmed runtime bug, traceback leak,
redaction failure, broken sample mode report, or broken package-data issue was
found. Issues #34 and #36 are closed/completed.

This triage document:

1. Inventories all known open issues and their current classification.
2. Defines what qualifies for v0.3.1 vs what should be deferred.
3. Proposes an ordered list of next actions.
4. Establishes how new issues should be processed as validation results arrive.

---

## Issue inventory (as of Issue #36 closure, 2026-05-25)

#34 and #36 are closed/completed. The remaining three issues are open
validation tracking issues. No confirmed runtime bugs, traceback leaks, or
redaction failures are open.

| # | Title | Classification | Priority | Recommended action | v0.3.1 candidate? |
|---|---|---|---|---|---|
| #32 | Validation: Docker Desktop on macOS | validation tracking | high | Keep open; record results when available | Only if a bug is found |
| #33 | Validation: Docker Desktop on Windows / WSL2 | validation tracking | medium | Keep open; record results when available | Only if a bug is found |
| #34 | Validation: Linux Docker Engine | closed / completed | — | Closed after Goal 17.2 validation pass; no further action required | None |
| #35 | Validation: Browser UI across Chrome, Safari, Firefox | validation tracking | medium | Keep open; Chromium smoke pass recorded; Safari/Firefox remain | No current v0.3.1 impact |
| #36 | Validation: Prometheus export in sample and live modes | closed / completed | — | Closed after sample-mode pass and live-mode evidence via #34 cross-link | None |

**Current status:** Issues #34 and #36 are closed/completed. No confirmed
runtime bug, traceback leak, redaction failure, broken sample mode, or
package-data issue was found. #35 has a Chromium smoke pass; Safari and
Firefox remain open. #32 and #33 have no recorded validation results yet. No
open validation result currently requires v0.3.1.

---

## Classification definitions

| Classification | Meaning | Default action |
|---|---|---|
| **validation tracking** | Open issue collecting real-world validation run results | Keep open until sufficient results are recorded |
| **bug** | Confirmed reproducible failure — wrong behavior with steps to reproduce | Prioritize for v0.3.1 if it affects core functionality |
| **platform-specific caveat** | Expected difference from the primary Linux target | Document in `docs/VALIDATION.md`; close or downgrade the issue |
| **documentation gap** | Existing docs are unclear, incomplete, or wrong | Fix in a docs-only PR; does not require a runtime change |
| **enhancement** | The feature works but could be improved | Defer unless directly tied to a confirmed bug or validation gap |
| **release/process** | CI, release scripts, package metadata | Triage separately; do not block runtime releases |
| **deferred** | Not actionable now; revisit after more validation data | Leave open with a `deferred` note; do not close prematurely |

---

## Validation tracking issues: current classification

### #32 — Validation: Docker Desktop on macOS

- **Classification:** validation tracking
- **Priority:** high (common developer environment)
- **Current state:** no results recorded
- **Expected platform-specific caveats to watch for:**
  - `blockReadBytes` and `blockWriteBytes` consistently 0 (cgroups v1 limitation)
  - Bind mount paths under `/Users/` classified as `sourceCategory: "home"` — verify
  - SSE EventSource behavior in Safari on macOS
- **Action when results arrive:**
  - Pass → add a "Validated on macOS Docker Desktop vX.X" note to `docs/VALIDATION.md`
  - Caveat → add a Known caveat entry to `docs/VALIDATION.md`; close or downgrade when fully covered
  - Bug → open a new bug report issue and evaluate for v0.3.1 if it affects core functionality

### #33 — Validation: Docker Desktop on Windows / WSL2

- **Classification:** validation tracking
- **Priority:** medium
- **Current state:** no results recorded
- **Expected platform-specific caveats to watch for:**
  - Windows-style path separators in bind mount sources
  - WSL2 path format (`/mnt/c/...`) vs native Windows format
  - `sourceCategory` classification for non-Linux paths
- **Action when results arrive:** same pattern as #32

### #34 — Validation: Linux Docker Engine

- **Classification:** closed / completed
- **Priority:** high (closest to production Docker behavior)
- **Current state:** closed after Goal 17.2 full Linux Docker Engine validation pass.
- **Recorded partial result from Claude Code environment (earlier run):**
  - install/package smoke: pass
  - sample mode: pass
  - sample server API checks: pass
  - sample SSE metrics/diagnostics: pass
  - sample diagnostics: pass
  - sample Prometheus export: pass
  - host path redaction: pass
  - offline D3 route: pass
  - CORS/default bind checks: pass
  - live Docker scan/events/cgroups v2 metrics: unable to run because Docker daemon was unavailable
- **Resolved follow-up:** package version mismatch found during this run was fixed by PR #44.
- **Goal 17.1 preflight result:** PR #46 confirmed GitHub-hosted `ubuntu-latest` runners support Docker-daemon-based validation.
- **Goal 17.2 full validation result (run ID 26423354910):** Linux Docker Engine validation workflow passed on GitHub-hosted `ubuntu-latest`. All nine steps completed: environment/Docker preflight, install/compile/unit-tests/doctor, disposable topology creation, live scan, diagnostics, metrics and Prometheus, SSE/event validation, cleanup, and summary artifact upload. No runtime bug, traceback leak, redaction failure, broken sample mode, or package-data issue was found.
- **v0.3.1 impact:** none. No release-blocking issues were found.
- **Status:** closed/completed. No further action required unless the project intentionally adds additional Linux host variants (e.g., RHEL, arm64).
- **Diagnostics false-positive recording:** any `exposed-port`, `no-network`, or `exited-container` finding that fires for an intentional configuration in a future run should be filed as a new issue and fed into `docs/DIAGNOSTICS_TUNING.md`.

### #35 — Validation: Browser UI across Chrome, Safari, Firefox

- **Classification:** validation tracking
- **Priority:** Chrome high; Safari and Firefox medium
- **Current state:** Chromium sample UI browser smoke workflow recorded as **pass**; Safari and Firefox not yet recorded
- **Recorded Chromium result:**
  - manual Browser Smoke workflow completed successfully in GitHub Actions
  - optional `browser-test` extra and Playwright Chromium installed successfully
  - compile check passed
  - unit tests passed
  - `scripts/browser_smoke.py` passed
  - screenshot artifact upload step completed
  - no v0.3.1 impact from this result
- **Remaining validation:**
  - Safari manual/browser validation
  - Firefox manual/browser validation
  - broader EventSource reconnect behavior after server restart
- **Action when remaining results arrive:** same pattern as #32; browser-specific rendering bugs go to a new bug report issue

### #36 — Validation: Prometheus export in sample and live modes

- **Classification:** closed / completed
- **Priority:** medium
- **Current state:** closed after both sample-mode and live-mode Prometheus evidence were recorded.
- **Recorded sample-mode result:**
  - `--prometheus` enabled → `/metrics` returned HTTP 200
  - Prometheus text output contained `# HELP`, `# TYPE`, summary metrics, and per-container metrics
  - labels were limited to `container_id`, `container_name`, and `status`
  - no Docker labels, environment variables, or host paths appeared in the output
  - `/metrics` returned HTTP 404 when `--prometheus` was not used
  - `/api/metrics` remained JSON when `--prometheus` was enabled
  - no traceback was observed
- **Non-blocking caveat:** `HEAD /metrics` returned HTTP 501 in the sample validation environment. Prometheus scrapes with `GET`, so this is not a release blocker.
- **Live-mode evidence (Goal 17.3):** live-mode Prometheus validation was covered by the Goal 17.2 full Linux Docker Engine validation workflow (run ID 26423354910). That run confirmed `/metrics` returned HTTP 200 with live container data; no raw Docker labels, environment values, or host paths appeared in the output; `/api/metrics` remained JSON; no traceback was observed; CORS default was off. This result was recorded in Issue #36 via a direct cross-link comment.
- **v0.3.1 impact:** none. No release-blocking issues were found in either sample or live mode.
- **Status:** closed/completed. No further action required.

---

## v0.3.1 candidate policy

### Qualifies for v0.3.1

A fix qualifies as a v0.3.1 candidate when **at least one** of these is true:

| Condition | Example |
|---|---|
| Confirmed runtime bug with steps to reproduce | Sample mode crashes on a specific Python version |
| Traceback leak to an HTTP or SSE client | Server returns Python exception in response body |
| Redaction or privacy failure | Raw bind mount host path appears in output when `--redact-host-paths` is active |
| Broken sample mode | `python app.py serve --sample` fails without Docker installed |
| Broken package data / missing static assets | `web/vendor/d3.min.js` missing from installed wheel |
| Broken release readiness check | `scripts/release_check.sh` exits non-zero on a clean install |
| Documented command in `docs/VALIDATION.md` fails and blocks validation | A curl example returns unexpected output |
| High-confidence platform caveat requiring a docs update | Block I/O consistently 0 on macOS Docker Desktop — needs a note |

### Does not currently qualify for v0.3.1

| Condition | Why deferred |
|---|---|
| Speculative feature ideas | No validation evidence |
| Unvalidated diagnostics severity changes | Require real-world evidence per `docs/DIAGNOSTICS_TUNING.md` |
| Package publishing automation | Manual release process not yet stable |
| Production deployment claims | Out of scope for local-first tool |
| External service integrations | Require explicit project decision |
| Optional browser/E2E smoke testing | Infrastructure in place and Chromium smoke passed; not a v0.3.1 blocker unless a real bug is found |
| `HEAD /metrics` returning 501 | Prometheus scrape path uses GET; no concrete affected workflow yet |
| #34 version mismatch | Fixed by PR #44; no remaining v0.3.1 blocker from this item |
| Goal 17.1 Docker live preflight | Passed; enables future full validation but does not itself create a release candidate |

---

## How to process new issues as validation results arrive

When a contributor files a validation result:

1. **Read the classification they chose** (pass / bug / caveat / gap / false positive / false negative / enhancement).
2. **If classification is `pass`:** add a validation note and consider closing only when coverage is sufficient.
3. **If classification is `platform-specific caveat`:** document the caveat and close or downgrade when fully covered.
4. **If classification is `bug`:** open a bug report issue and apply the v0.3.1 candidate criteria above.
5. **If classification is `false positive` or `false negative`:** record rule ID, environment, and configuration; do not change severity until the evidence threshold in `docs/DIAGNOSTICS_TUNING.md` is met.
6. **If classification is `documentation gap`:** open a docs-update issue or fix directly in a docs-only PR.

---

## Goal 17.2 — Full Linux Docker Engine validation workflow

Goal 17.2 added `.github/workflows/linux-docker-validation.yml`, a full
`workflow_dispatch`-only GitHub Actions workflow that performs complete Issue
#34 Linux Docker Engine validation using the Docker-daemon-capable GitHub-
hosted Ubuntu runner path proven by Goal 17.1.

**Result: passed (run ID 26423354910, artifact ID 7206034881).**

The workflow covers nine steps, all of which passed:
1. Environment and Docker preflight (OS, kernel, cgroups, Docker daemon check)
2. Checkout, install, compile, unit tests, `app.py doctor`
3. Disposable validation topology creation (`dtl-validate-*` containers only)
4. Live scan validation (JSON output, redaction, dtl-validate-* presence)
5. Diagnostics validation (findings, warnings, redaction, traceback check)
6. Metrics and Prometheus validation (live server on 127.0.0.1:8099, all API
   endpoints, Prometheus sanitization, CORS default confirmed off)
7. SSE / Docker event validation (bounded; skipped if flaky, not failed)
8. Cleanup (`if: always()`, all `dtl-validate-*` containers and networks)
9. Summary artifact (`linux-docker-validation-summary`)

No runtime bug, traceback leak, redaction failure, broken sample mode, or
package-data issue was found. Issue #34 is closed/completed. v0.3.1 impact
is none.

**Safety confirmation:** `workflow_dispatch` only; no runtime application
changes; only disposable `dtl-validate-*` containers and networks; cleanup
with `if: always()`; no secrets; no external telemetry; no release/tag/PyPI
actions; no production readiness claim; no raw Docker inspect JSON uploaded;
CORS default unchanged; Prometheus remains opt-in in application runtime.

---

## Goal 17.1 — Manual Docker live preflight workflow

Goal 17.1 introduced `.github/workflows/docker-live-preflight.yml`, a
`workflow_dispatch`-only GitHub Actions workflow that verifies whether
GitHub-hosted Ubuntu runners can support Docker-daemon-based live validation
for Docker Topology Live.

**This preflight does not complete Issue #34 by itself.**

The manual run passed after PR #46 was merged. It confirmed that the GitHub-
hosted `ubuntu-latest` runner had Docker daemon access and could run disposable
containers, `app.py doctor`, `app.py scan --redact-host-paths`, and `app.py
diagnose --redact-host-paths`. It also uploaded the `docker-live-preflight-
summary` artifact.

The next step is not another preflight. The next step is a full #34 Linux
Docker Engine validation workflow.

---

## Recommended next actions (ordered)

1. **Continue #32 — macOS Docker Desktop validation.**
   No results have been recorded. Validate on macOS Docker Desktop and record
   the result (pass, bug, or caveat) in Issue #32. Watch for block I/O
   consistently 0 (cgroups v1), bind mount `sourceCategory: "home"` for
   `/Users/` paths, and SSE/EventSource behavior.

2. **Continue #33 — Windows/WSL2 Docker Desktop validation.**
   No results have been recorded. Validate on Windows/WSL2 and record in
   Issue #33. Watch for Windows-style and WSL2-style bind mount path formats
   and `sourceCategory` classification for non-Linux paths.

3. **Continue #35 — Safari and Firefox browser validation.**
   Chromium smoke is green. Safari and Firefox manual validation remain untested.
   Record results in Issue #35.

4. **File bug reports only when validation finds reproducible failures.**
   Do not file speculative bug reports. Each bug report needs steps to reproduce
   and actual vs expected output.

5. **Add platform-specific caveats to `docs/VALIDATION.md`** as they are confirmed.

6. **Defer package publishing automation** until at least one more manual release
   cycle is stable and release readiness passes across validated environments.

7. **Review diagnostics false positives** from real validation runs and update
   `docs/DIAGNOSTICS_TUNING.md` with evidence before changing severity.

---

## v0.3.1 planning baseline

**Current status (as of Issue #36 closure):**

- No confirmed runtime bugs in the issue tracker.
- #34 full Linux Docker Engine validation passed (Goal 17.2, run ID 26423354910). v0.3.1 impact: none. #34 is closed/completed.
- #36 Prometheus export validation complete: sample-mode pass recorded; live-mode evidence recorded via #34 cross-link (Goal 17.3). v0.3.1 impact: none. #36 is closed/completed.
- #35 Chromium sample UI browser smoke workflow has passed; Safari and Firefox remain untested.
- #32 and #33 have no recorded validation results yet.
- #34 and #36 are closed; #32, #33, and #35 remain open; none are v0.3.1 blockers.

**Decision:** v0.3.1 planning remains **deferred** until a confirmed runtime bug,
traceback leak, redaction failure, broken sample mode, broken package data, or
release-readiness failure is recorded.

**Trigger for v0.3.1 release process:**
Any confirmed runtime bug, traceback leak, or redaction failure discovered
during validation should trigger a v0.3.1 release preparation. If validation
passes cleanly across macOS Docker Desktop and Linux Docker Engine with no
bugs, v0.3.0 remains current and v0.3.1 is deferred.

---

## Triage document maintenance

This document should be updated whenever:

- A new issue is filed that affects the inventory.
- A validation result is recorded (pass, bug, caveat, or gap).
- A bug is fixed and released.
- A deferred item is re-evaluated.

The update does not require a separate PR for minor changes. Significant
triage decisions, such as opening a v0.3.1 release process, require a PR with
the updated inventory and rationale.
