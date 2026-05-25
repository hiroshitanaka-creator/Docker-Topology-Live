# Post-Release Issue Triage

This document converts post-v0.3.0 feedback and validation tracking into
actionable v0.3.1 planning.

It is maintained as a living document.  Update the inventory and
recommendations as validation results arrive and new issues are filed.

---

## Purpose

After v0.3.0 was published, five validation tracking issues were opened
(#32–#36).  No runtime bugs have been filed yet.  This triage document:

1. Inventories all known open issues and their current classification.
2. Defines what qualifies for v0.3.1 vs what should be deferred.
3. Proposes an ordered list of next actions.
4. Establishes how new issues should be processed as validation results arrive.

---

## Issue inventory (as of Goal 15, 2026-05-25)

All open issues are validation tracking issues.  No confirmed runtime bugs,
traceback leaks, or redaction failures have been reported.

| # | Title | Classification | Priority | Recommended action | v0.3.1 candidate? |
|---|---|---|---|---|---|
| #32 | Validation: Docker Desktop on macOS | validation tracking | high | Keep open; record results when available | Only if a bug is found |
| #33 | Validation: Docker Desktop on Windows / WSL2 | validation tracking | medium | Keep open; record results when available | Only if a bug is found |
| #34 | Validation: Linux Docker Engine | validation tracking | high | Keep open; record results when available | Only if a bug is found |
| #35 | Validation: Browser UI across Chrome, Safari, Firefox | validation tracking | medium | Keep open; record results when available | Only if a bug is found |
| #36 | Validation: Prometheus export in sample and live modes | validation tracking | medium | Keep open; record results when available | Only if a bug is found |

**Current status:** All five issues are open.  No pass or fail results have
been recorded yet.  No bug reports have been filed from real validation runs.

---

## Classification definitions

| Classification | Meaning | Default action |
|---|---|---|
| **validation tracking** | Open issue collecting real-world validation run results | Keep open until at least one result is recorded |
| **bug** | Confirmed reproducible failure — wrong behavior with steps to reproduce | Prioritize for v0.3.1 if it affects core functionality |
| **platform-specific caveat** | Expected difference from the primary Linux target | Document in `docs/VALIDATION.md`; close or downgrade the issue |
| **documentation gap** | Existing docs are unclear, incomplete, or wrong | Fix in a docs-only PR; does not require a runtime change |
| **enhancement** | The feature works but could be improved | Defer unless directly tied to a confirmed bug or validation gap |
| **release/process** | CI, release scripts, package metadata | Triage separately; do not block runtime releases |
| **deferred** | Not actionable now; revisit after more validation data | Leave open with a `deferred` note; do not close prematurely |

---

## Validation tracking issues: initial classification

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
  - Caveat → add a Known caveat entry to `docs/VALIDATION.md`; close the issue or downgrade to `platform-specific caveat`
  - Bug → open a new bug report issue using `.github/ISSUE_TEMPLATE/bug-report.md`; prioritize for v0.3.1 if it affects core functionality

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
- **Current state:** no results recorded
- **Expected platform-specific caveats to watch for:**
  - cgroups v2: all metric fields (CPU, memory, block I/O, PIDs) should be non-zero for active containers — confirm
  - Docker API-side event filter support (expected on CE ≥ 20.x)
  - `/var/run/docker.sock` bind mount detection → `sourceCategory: "docker-socket"` → `broad-bind-mount` high severity
- **Diagnostics false-positive recording:** any `exposed-port`, `no-network`, or `exited-container` finding that fires for an intentional configuration should be recorded here and fed into `docs/DIAGNOSTICS_TUNING.md`

### #35 — Validation: Browser UI across Chrome, Safari, Firefox

- **Classification:** validation tracking
- **Priority:** Chrome high; Safari and Firefox medium
- **Current state:** no results recorded
- **Expected platform-specific caveats to watch for:**
  - EventSource reconnect timing differences between browsers
  - SVG sparkline rendering differences (all should use `createElementNS` — verify)
  - Safari `EventSource` reconnect after server restart
- **Action when results arrive:** same pattern as #32; browser-specific rendering bugs go to a new bug report issue

### #36 — Validation: Prometheus export in sample and live modes

- **Classification:** validation tracking
- **Priority:** medium
- **Current state:** no results recorded
- **Key checks:**
  - HTTP 404 without `--prometheus` (behavioral correctness)
  - `Content-Type: text/plain; version=0.0.4; charset=utf-8`
  - No raw Docker labels, env vars, or host paths in output
  - `/api/metrics` JSON unaffected when `--prometheus` is active
- **Action when results arrive:** same pattern as #32

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

### Does not yet qualify for v0.3.1

| Condition | Why deferred |
|---|---|
| Speculative feature ideas | No validation evidence |
| Unvalidated diagnostics severity changes | Require real-world evidence per `docs/DIAGNOSTICS_TUNING.md` |
| Package publishing automation | Manual release process not yet stable |
| Production deployment claims | Out of scope for local-first tool |
| External service integrations | Require explicit project decision |
| Optional browser/E2E smoke testing | Depends on validation feedback first |

---

## How to process new issues as validation results arrive

When a contributor files a validation result (using `.github/ISSUE_TEMPLATE/validation-result.md`):

1. **Read the classification they chose** (pass / bug / caveat / gap / false positive / false negative / enhancement).

2. **If classification is `pass`:**
   - Add a "Validated on [platform] [version]" note to `docs/VALIDATION.md` under the relevant section.
   - Consider closing the validation tracking issue if coverage is sufficient.

3. **If classification is `platform-specific caveat`:**
   - Add a "Known caveat — [platform]" entry to `docs/VALIDATION.md`.
   - Close or downgrade the tracking issue.
   - No runtime code change needed.

4. **If classification is `bug`:**
   - Open a new bug report issue using `.github/ISSUE_TEMPLATE/bug-report.md`.
   - Apply the v0.3.1 candidate criteria above.
   - Assign the bug to the tracking issue as a follow-up.

5. **If classification is `false positive` or `false negative`:**
   - Record the rule ID, environment, and configuration in the tracking issue.
   - Open a diagnostics-tuning issue referencing the validation run.
   - Do not change severity until the evidence threshold in `docs/DIAGNOSTICS_TUNING.md` is met.

6. **If classification is `documentation gap`:**
   - Open a docs-update issue or fix directly in a docs-only PR.
   - No runtime code change needed.

---

## Recommended next actions (ordered)

1. **Collect validation results for #32–#36.**
   Run validation on at least one real Docker environment following `docs/VALIDATION_ISSUES.md`.
   Record results using the issue template.

2. **File bug reports only when validation finds reproducible failures.**
   Do not file speculative bug reports.  Each bug report needs steps to reproduce
   and actual vs expected output.

3. **Add platform-specific caveats to `docs/VALIDATION.md`** as they are confirmed
   (e.g. block I/O stats on macOS Docker Desktop, Windows bind mount path format).

4. **Defer package publishing automation** until at least one more manual release
   cycle (v0.3.1) is stable and the release readiness check passes cleanly across
   the validated environments.

5. **Consider optional browser/E2E smoke testing** after validation feedback is
   collected — current unit tests cover Python logic but not browser rendering.

6. **Review diagnostics false positives** from real validation runs and update
   `docs/DIAGNOSTICS_TUNING.md` with evidence before making any severity changes.

---

## v0.3.1 planning baseline

**Current status (as of Goal 15):**

- No confirmed bugs in the issue tracker.
- No validation results recorded yet for any of #32–#36.
- All five open issues are validation tracking; none are blockers.

**Decision:** v0.3.1 planning is **on hold** until at least one real-world
validation result is recorded.  The triage document will be updated when
evidence arrives.

**Trigger for v0.3.1 release process:**
Any confirmed runtime bug, traceback leak, or redaction failure discovered
during validation should trigger a v0.3.1 release preparation.  If validation
passes cleanly across macOS Docker Desktop and Linux Docker Engine with no
bugs, v0.3.0 remains current and v0.3.1 is deferred.

---

## Triage document maintenance

This document should be updated whenever:

- A new issue is filed that affects the inventory.
- A validation result is recorded (pass, bug, caveat, or gap).
- A bug is fixed and released.
- A deferred item is re-evaluated.

The update does not require a separate PR for minor changes (e.g. adding a
"Validated on macOS" note).  Significant triage decisions (e.g. opening a
v0.3.1 release process) require a PR with the updated inventory and rationale.
