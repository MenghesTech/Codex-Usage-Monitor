# Security Policy

## Supported version

Security fixes are provided for the latest published version of Codex Usage Monitor.

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Please **do not open a public GitHub issue** for a suspected security vulnerability or for a report that contains sensitive information.

Use GitHub's private vulnerability reporting feature for this repository when available:

**Security → Report a vulnerability**

If private vulnerability reporting is not available, avoid posting credentials, tokens, `auth.json` contents, account identifiers, personal paths, or other sensitive information publicly. Open a minimal issue stating that you need a private channel for a security report, without including vulnerability details.

Please include, when possible:

- A clear description of the issue and its potential impact.
- Steps to reproduce the issue.
- The affected Codex Usage Monitor version.
- Your Windows version and whether you use the installer or portable build.
- Any relevant screenshots or logs after removing sensitive information.

## Scope and privacy

Codex Usage Monitor is designed to operate locally and communicate with the locally installed Codex app server for rate-limit information. The project does not intentionally collect telemetry, analytics, credentials, or authentication data.

Never include Codex authentication files or secrets in a security report unless a private reporting channel has been established and they are strictly necessary to reproduce the issue.

## Disclosure

Please allow reasonable time to investigate and address a confirmed vulnerability before publishing technical details.
