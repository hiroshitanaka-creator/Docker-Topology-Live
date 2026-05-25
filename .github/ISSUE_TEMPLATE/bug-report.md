---
name: Bug Report
about: Report a reproducible bug in Docker Topology Live
title: "Bug: [brief description]"
labels: ["bug"]
---

<!--
PRIVACY NOTICE — please read before submitting:

- Do NOT paste secrets, API keys, or environment variable values.
- Do NOT include real production container names, image tags, host paths,
  or client/project names that could identify a production system.
- If sharing topology, metrics, or diagnostics output, always use
  --redact-host-paths first and scrub any remaining identifiers.
- Docker Topology Live is a local read-only tool — bugs should be
  reproducible with harmless demo containers or sample mode.
-->

## Summary

<!-- One-sentence description of the bug. -->

## Steps to reproduce

<!-- Numbered list. Use sample mode or placeholder container names. -->

1. 
2. 
3. 

## Expected behavior

<!-- What should have happened? -->

## Actual behavior

<!-- What actually happened? Paste output below if relevant. -->

## Relevant output or logs

<!-- Trim to the relevant portion.
     - Use --redact-host-paths before copying any output.
     - Remove real container/image names, host paths, and internal project names.
-->

```
(paste here)
```

## Environment

| Field | Value |
|---|---|
| OS | <!-- e.g. macOS 14.5, Ubuntu 24.04 --> |
| Docker platform | <!-- e.g. Docker Desktop 4.x, Docker CE 24.x --> |
| Docker version | <!-- docker version --format '{{.Server.Version}}' --> |
| Python version | <!-- python --version --> |
| Browser (if applicable) | <!-- e.g. Chrome 124 --> |
| Command used | <!-- the exact command --> |
| `--redact-host-paths` active? | yes / no / not applicable |

## Additional context

<!-- Any other relevant information. For diagnostics false positives/negatives,
     include the rule ID and a brief (redacted) description of the container
     configuration. -->
