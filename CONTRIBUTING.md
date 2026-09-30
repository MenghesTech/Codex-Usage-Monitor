# Contributing to Codex Usage Monitor

Thanks for your interest in improving Codex Usage Monitor.

## Before opening an issue

- Check whether a similar issue already exists.
- Use the Bug Report form for reproducible problems.
- Use the Feature Request form for new ideas.
- Do not post credentials, tokens, `auth.json`, account identifiers, or other private data.

## Development

Codex Usage Monitor targets Windows 10/11 x64 and is built with Python and PySide6.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

For build instructions, see the project README.

## Pull requests

Keep changes focused and avoid unrelated refactors. Add or update tests when behavior changes, and confirm the test suite passes before submitting a pull request.

Please do not include generated builds, installers, virtual environments, personal settings, logs, credentials, or other local artifacts in commits.

## Privacy and security

The project is intentionally local and read-only with respect to Codex rate limits. Contributions must not add telemetry, analytics, credential collection, or calls that consume reset credits without explicit project discussion.

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
