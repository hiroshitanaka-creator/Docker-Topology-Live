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
- #35 Chromium sample UI browser smoke workflow: **pass**
- #34 Linux Docker Engine validation attempt: **partial pass / live Docker unable to run**

The #34 run found a package version mismatch. That mismatch was fixed in PR
#44. No confirmed runtime bug, traceback leak, redaction failure, broken sample
mode report, or broken package-data issue is currently open.

This triage document:

1. Inventories all known open issues and their current classification.
2. Defines what qualifies for v0.3.1 vs what should be deferred.
3. Proposes an ordered list of next actions.
4. Establishes how new issues should be processed as validation results arrive.

---

## Issue inventory (as of PR #44, 2026-05-25)

All open issues remain validation tracking issues. No confirmed runtime bugs,
traceback leaks, or redaction failures are open.

| # | Title | Classification | Priority | Recommended action | v0.3.1 candidate? |
|---|---|---|---|---|---|
| #32 | Validation: Docker Desktop on macOS | validation tracking | high | Keep open; record results when available | Only if a bug is found |
| #33 | Validation: Docker Desktop on Windows / WSL2 | validation tracking | medium | Keep open; record results when available | Only if a bug is found |
| #34 | Validation: Linux Docker Engine | validation tracking | high | Keep open; sample/static sections partially validated; live Docker daemon validation still required | No current blocker; version mismatch fixed in PR #44 |
| #35 | Validation: Browser UI across Chrome, Safari, Firefox | validation tracking | medium | Keep open; Chromium smoke pass recorded; Safari/Firefox remain | No current v0.3.1 impact |
| #36 | Validation: Prometheus export in sample and live modes | validation tracking | medium | Keep open; sample-mode pass recorded; live-mode validation remains | No current v0.3.1 impact |

**Current status:** All five issues are open. #34 has a partial validation
result, #35 has a Chromium sample UI pass, and #36 has a sample-mode Prometheus
pass. The version mismatch found during #34 validation has been fixed by PR #44.
No open validation result currently requires v0.3.1.

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

- **Classification:** validation tracking
- **Priority:** high (closest to production Docker behavior)
- **Current state:** partial validation recorded. Docker CLI was present, but the Docker daemon was unavailable because `/var/run/docker.sock` was absent.
- **Recorded partial result:**
  - install/package smoke: pass
  - sample mode: pass
  - sample server API checks: pass
  - sample SSE metrics/diagnostics: pass
  - sample diagnostics: pass
  - sample Prometheus export: pass
  - host path redaction: pass
  - offline D3 route: pass
  - CORS/default bind checks: pass
  - live Docker scan/events/cgroups v2 metrics: unable to run
- **Resolved follow-up:** package version mismatch found during this run was fixed by PR #44. `pyproject.toml`, package `__version__`, and CLI version output now agree on `0.3.0`.
- **Remaining validation:** run #34 again on a Linux host with a running Docker daemon to validate live topology scan, Docker event stream, cgroups v2 metrics, live Prometheus output, and live redaction behavior.
- **v0.3.1 impact:** none currently open after PR #44; live Docker validation remains required.
- **Diagnostics false-positive recording:** any `exposed-port`, `no-network`, or `exited-container` finding that fires for an intentional configuration should be recorded here and fed into `docs/DIAGNOSTICS_TUNING.md`.

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

- **Classification:** validation tracking
- **Priority:** medium
- **Current state:** sample-mode validation recorded as **pass**; live Docker mode not yet tested
- **Recorded sample-mode result:**
  - `--prometheus` enabled → `/metrics` returned HTTP 200
  - Prometheus text output contained `# HELP`, `# TYPE`, summary metrics, and per-container metrics
  - labels were limited to `container_id`, `container_name`, and `status`
  - no Docker labels, environment variables, or host paths appeared in the output
  - `/metrics` returned HTTP 404 when `--prometheus` was not used
  - `/api/metrics` remained JSON when `--prometheus` was enabled
  - no traceback was observed
- **Non-blocking caveat:** `HEAD /metrics` returned HTTP 501 in the sample validation environment. Prometheus scrapes with `GET`, so this is not a release blocker.
- **Remaining validation:** live Docker mode, especially real container labels, live metric values, and absence of raw Docker labels/host paths in Prometheus output
- **v0.3.1 impact:** none from the sample-mode result

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

## Recommended next actions (ordered)

1. **Repeat #34 on a Docker-daemon-capable Linux host.**
   The first #34 attempt validated sample/static behavior but could not test live Docker because the daemon was unavailable.

2. **Continue collecting validation results for #32–#36.**
   #35 Chromium and #36 sample Prometheus have passes. #32, #33, #34 live Docker, #35 Safari/Firefox, and #36 live Prometheus still need coverage.

3. **Keep #35 open until Safari and Firefox coverage, or an explicit split decision, is recorded.**
   Chromium browser smoke is green, but Safari and Firefox remain untested.

4. **Keep #36 open until live-mode Prometheus validation is complete.**
   The sample-mode path is green, but live Docker labels and live metric values remain untested.

5. **File bug reports only when validation finds reproducible failures.**
   Do not file speculative bug reports. Each bug report needs steps to reproduce and actual vs expected output.

6. **Add platform-specific caveats to `docs/VALIDATION.md`** as they are confirmed.

7. **Defer package publishing automation** until at least one more manual release cycle is stable and release readiness passes across validated environments.

8. **Review diagnostics false positives** from real validation runs and update `docs/DIAGNOSTICS_TUNING.md` with evidence before changing severity.

---

## v0.3.1 planning baseline

**Current status (as of PR #44):**

- No confirmed runtime bugs in the issue tracker.
- #34 partial Linux validation recorded: sample/static checks passed; live Docker daemon unavailable.
- #34 version mismatch found during validation was fixed by PR #44.
- #35 Chromium sample UI browser smoke workflow has passed.
- #35 Safari and Firefox validation remain untested.
- #36 sample-mode Prometheus validation has passed.
- #36 live Docker mode remains untested.
- #32 and #33 have no recorded validation results yet.
- All five open issues remain validation tracking; none are blockers.

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
