# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes |
| < 0.2   | No  |

## Reporting a Vulnerability

Please report security issues via GitHub Issues (tag: `security`).

## Security Design

- **Read-only Docker access** – no container stop/remove, image remove, volume remove, network remove, or pruning operations are ever called.
- **Loopback bind by default** – the HTTP server binds to `127.0.0.1` unless explicitly overridden.
- **No secret export** – environment variables and secrets are never included in topology output.
- **Label redaction** – label keys containing `password`, `passwd`, `secret`, `token`, `apikey`, `api_key`, `credential`, `auth`, `private_key`, or `access_key` have their values replaced with `***REDACTED***`.
- **No outbound connections** – the package never initiates outbound network connections except to the local Docker socket.
