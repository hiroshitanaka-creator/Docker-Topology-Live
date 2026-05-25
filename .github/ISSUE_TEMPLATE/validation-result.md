---
name: Validation Result
about: Report a real-world validation run result (pass, bug, caveat, gap, false positive, or false negative)
title: "Validation: [Environment] — [Section]"
labels: ["validation"]
---

<!--
PRIVACY NOTICE — please read before submitting:

- Do NOT paste secrets, environment variables, or API keys.
- Do NOT include real production container names, image tags, or host paths.
- If sharing topology or diagnostics output, run with --redact-host-paths first.
- Replace any internal project or client names with placeholders.
- Prefer sample mode or a disposable demo stack.

See docs/VALIDATION_ISSUES.md for the full privacy and safety guidance.
-->

## Environment

| Field | Value |
|---|---|
| OS | <!-- e.g. macOS 14.5, Ubuntu 24.04, Windows 11 + WSL2 --> |
| Docker platform | <!-- e.g. Docker Desktop 4.x, Docker CE 24.x, Rancher Desktop --> |
| Docker version | <!-- output of: docker version --format '{{.Server.Version}}' --> |
| Python version | <!-- output of: python --version --> |
| Browser (if applicable) | <!-- e.g. Chrome 124, Safari 17, Firefox 126 --> |
| Command used | <!-- the exact command that triggered this result --> |

## Validation section

<!-- Which section from docs/VALIDATION_ISSUES.md does this cover? -->
<!-- e.g. Section 6 — Metrics, Section 9 — Prometheus export -->

- [ ] 1 — Install and package smoke
- [ ] 2 — Sample mode (no Docker)
- [ ] 3 — Sample server UI
- [ ] 4 — Live topology scan
- [ ] 5 — SSE live updates
- [ ] 6 — Metrics
- [ ] 7 — Metric history and sparklines
- [ ] 8 — Diagnostics
- [ ] 9 — Prometheus export
- [ ] 10 — Host path redaction
- [ ] 11 — Offline D3 check
- [ ] 12 — CORS and bind defaults

## Expected result

<!-- What did docs/VALIDATION_ISSUES.md say should happen? -->

## Actual result

<!-- What actually happened? -->

## Output or logs

<!-- If relevant: paste truncated output here.
     - Run with --redact-host-paths before copying any topology or diagnostics output.
     - Remove any real container names, image tags, and host paths.
     - Trim to the relevant portion only.
-->

```
(paste here)
```

## Context

| Field | Value |
|---|---|
| Was `--redact-host-paths` used? | yes / no / not applicable |
| Does output contain sensitive names? | yes → do not post / no |
| Is this reproducible? | yes / no / intermittent |

## Classification

<!-- Pick one: -->
- [ ] pass — behavior matches expected
- [ ] bug — wrong behavior, reproducible
- [ ] platform-specific caveat — expected difference for this platform
- [ ] documentation gap — docs are unclear or wrong
- [ ] false positive — diagnostic finding fires for an intentional configuration
- [ ] false negative — a real problem is not caught by any diagnostic rule
- [ ] enhancement request — works but could be better

## Notes

<!-- Any additional context. For false positives/negatives, include the rule ID and a brief description of the container configuration. -->
