# Diagnostics Tuning Notes

This document records the rationale for current diagnostic rule thresholds and
what evidence is required before any future severity or threshold change.

Use it as the reference for all diagnostics review work.

---

## Tuning principles

1. **Evidence-driven only.**  Severity changes require real Docker validation
   data or concrete documented failure modes.  Do not raise severity merely to
   make findings look more urgent.
2. **Prefer wording improvements first.**  If a finding generates false
   positives in common configurations, improve the description or recommendation
   before touching severity.
3. **Keep thresholds stable.**  Unstable thresholds break automated monitoring
   and confuse operators who rely on consistent signal.
4. **Finding IDs are independent of wording.**  IDs are SHA-256 hashes of
   `ruleId:targetId:extra` — not of description or recommendation text.
   Wording changes are always safe from an ID-stability perspective.
5. **Manual-review phrase is mandatory for cleanup-related rules.**
   `broad-bind-mount`, `privileged-label`, `exited-container`, and
   `orphan-network` must always end with
   `"Manual review required before taking any cleanup action."`.

---

## Current rule inventory

| Rule ID | Category | Severity | Threshold | Confidence |
|---|---|---|---|---|
| `exposed-port` | security | low / medium | loopback → low; public bind → medium | 1.0 |
| `broad-bind-mount` | security | medium / high | docker.sock → high; /etc,/home,/proc,/sys,/var/run,/root,/ → medium | 1.0 |
| `privileged-label` | security | high | label key contains "privileged" with truthy value | 0.75 |
| `secret-like-label-redacted` | security | low | label value is `***REDACTED***` | 1.0 |
| `exited-container` | reliability | medium / high | dead → high; exited or restarting → medium | 1.0 |
| `no-network` | reliability | low | running/paused container with no network links | 1.0 |
| `multi-network-container` | reliability | info | container attached to ≥ 2 networks | 1.0 |
| `high-cpu` | resource | medium / high | ≥ 40% → medium; ≥ 80% → high | 1.0 |
| `high-memory` | resource | medium / high | ≥ 70% → medium; ≥ 85% → high | 1.0 |
| `high-pids` | resource | medium | ≥ 200 PIDs | 1.0 |
| `high-block-write` | resource | medium | ≥ 1 GiB cumulative block write (heuristic) | 0.5 |
| `unnamed-container` | maintenance | low | name < 3 chars or matches 12+ hex chars | 0.6 |
| `missing-compose-labels` | maintenance | info | container lacks Compose labels when others have them | 0.6 |
| `orphan-network` | maintenance | low | named network with no attached containers | 0.85 |

---

## Per-rule rationale

### `exposed-port`

**Rationale for low/medium split:**  A port published on `127.0.0.1` is not
directly reachable from other hosts.  This is the Docker default for local
development and is rarely a concern.  A port published on `0.0.0.0` or an
unspecified IP is reachable from all interfaces, which increases external attack
surface.

**Known false positives:**  Binding to `0.0.0.0` is common in local
development and Docker Compose stacks not intended for production.  The
recommendation now explicitly acknowledges this context.

**What evidence would justify promoting 0.0.0.0 binding to `high`:**
Evidence that a specific well-known port (e.g. 22, 3306, 5432) was exposed
unintentionally in a real-world scenario, combined with a validation run showing
the finding provided actionable signal.

---

### `broad-bind-mount`

**Rationale for high:**  Mounting `/var/run/docker.sock` gives the container
full control over the Docker daemon — equivalent to host root access.  This is
well-documented in Docker security literature.

**Rationale for medium:**  `/etc`, `/home`, `/proc`, `/sys`, `/var/run`, `/root`,
and `/` expose significant host filesystem structure.  However, some are
legitimately used (e.g. read-only `/etc/ssl/certs` for CA certificates,
`/proc` for monitoring tools).  Medium severity reflects real risk without
treating all bind mounts as critical.

**Known false positives:**  Read-only mounts of narrow subdirectories (e.g.
`/etc/ssl/certs:ro`) are common and low-risk in practice.  The recommendation
explicitly suggests restricting to the minimum required subdirectory.

**What evidence would justify moving `/etc` mounts to `high`:**
Demonstrated real-world lateral movement or privilege escalation via a
read-only `/etc` bind mount in a realistic Docker environment.

---

### `privileged-label`

**Rationale for high with 0.75 confidence:**  A label key containing
"privileged" set to a truthy value is a heuristic indicator that the container
may be running in privileged mode.  Confidence is 0.75 (not 1.0) because the
label does not guarantee the `--privileged` runtime flag was also set.

**What evidence would justify raising confidence to 1.0:**  A reliable way to
inspect the actual OCI config from the topology rather than relying on label
heuristics.

---

### `exited-container`

**Rationale for medium/high split:**  A "dead" container could not be stopped
normally, which is a more serious condition than an intentional exit.
"Exited" and "restarting" are medium because:

- An exited container may be intentional (completed batch job, manually stopped
  service).  The description now explicitly acknowledges this to reduce operator
  confusion.
- A restarting container is in a crash-loop, which is an active problem but
  not as severe as a completely unresponsive dead container.

**Wording improvement (Goal 13):**  The "restarting" description previously
stated "A container in 'restarting' state is not serving traffic" — technically
imprecise, since a restarting container is actively attempting to recover.
Updated to "crash-looping — the restart policy is repeatedly bringing it back
up after failures."  The "exited" description now notes that this may be
intentional and directs the operator to check the exit code and logs.

**What evidence would justify making `restarting` → `high`:**  Real-world
data showing that crash-looping containers in a specific environment
consistently indicate a critical service outage requiring immediate escalation,
not just log investigation.

---

### `no-network`

**Rationale for low:**  A running container without network connections cannot
communicate with other containers — this is unusual but may be intentional for
CLI tools, batch processors, or containers using host networking outside
Docker's network model.

**Wording improvement (Goal 13):**  Description now explicitly acknowledges
intentionally isolated containers to reduce false-positive noise.
Recommendation now distinguishes the two cases (network access needed vs
intentional isolation).

**Note:**  This rule does not carry the manual-review phrase because no
destructive action is implied.

**What evidence would justify raising to `medium`:**  Data from real
environments showing that an isolated container consistently indicates a
misconfiguration rather than intentional design.

---

### `multi-network-container`

**Rationale for info:**  Multi-homed containers are legitimate network bridges
in microservice architectures.  Info severity is appropriate — the finding
exists to prompt review of segmentation intent, not to signal a problem.

**No change recommended.**

---

### Resource rules (`high-cpu`, `high-memory`, `high-pids`, `high-block-write`)

**Rationale for thresholds:**

| Rule | Warning | Critical | Source |
|---|---|---|---|
| CPU | 40% | 80% | Conventional application-monitoring thresholds |
| Memory | 70% | 85% | Common OOM-risk thresholds (cgroup2 kill at 100%) |
| PID count | — | 200 | Fork-bomb heuristic; most well-behaved containers run < 50 |
| Block write | — | 1 GiB | Heuristic for excessive write activity |

**Confidence note for `high-block-write`:**  Block write is cumulative since
container start.  A database container with 10 GiB written over a week is
normal; the same amount in an hour is not.  Confidence is 0.5 because duration
is unknown.  The title includes "(heuristic)" to signal this.

**What evidence would justify changing resource thresholds:**  Aggregated Docker
stats data from real validation runs showing false-positive or false-negative
rates at the current thresholds.

---

### `unnamed-container`

**Rationale for low with 0.6 confidence:**  An autogenerated or very short name
reduces operational clarity but is not a security or reliability concern.
Confidence is 0.6 because a short name might be intentional (e.g. a single-
letter test container).

---

### `missing-compose-labels`

**Rationale for info with 0.6 confidence:**  Only fires when at least one other
container has Compose labels, which limits false positives.  Info severity is
correct — a standalone container may be intentional.

---

### `orphan-network`

**Rationale for low with 0.85 confidence:**  An orphan network consumes
resources but is low-risk.  Confidence is 0.85 (not 1.0) because the network
may be transiently orphaned between container restarts.

---

## Evidence required before severity changes

Before changing any severity level or threshold:

1. Run `python app.py diagnose --sample` and `python app.py diagnose` on at
   least one real Docker environment.
2. Record false positives (findings that were not actionable) and false
   negatives (missed issues) per rule.
3. Document the Docker platform, cgroup version, and container types used.
4. For resource rules: capture at least 10 minutes of container stats data.
5. Open a GitHub issue with the evidence before writing code.
6. In the PR body, cite the issue and explain exactly which finding changed,
   why, and what evidence justifies the change.

---

## Goal 13 audit summary

**Reviewed:**  All 14 rules listed above.

**Changed (wording only, no severity change):**

| Rule | Change |
|---|---|
| `exited-container` (restarting) | Description: "not serving traffic" → precise crash-loop wording |
| `exited-container` (exited) | Description: added "may be intentional" context and log-check guidance |
| `no-network` | Description + recommendation: added intentional-isolation context |
| `exposed-port` (medium) | Recommendation: added local-dev context to reduce false-positive noise |

**Intentionally left unchanged:**

- All severity levels — no real Docker validation data was available to justify
  changes.
- All thresholds for resource rules.
- Finding IDs — IDs are derived from `ruleId:targetId:extra`, not from wording.
- `broad-bind-mount` severity split (docker.sock=high, system/home/root=medium).
- `privileged-label` confidence (0.75 — label heuristic, not runtime flag).
- `multi-network-container` (info — intentional multi-homing is common).
- `orphan-network` confidence (0.85 — may be transient).
- `diagnostics.schema.json` — no structural changes.
