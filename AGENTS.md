# Contributor instructions

- Work on a dedicated `codex/`, `claude/`, or other executor-prefixed branch; use a pull request for changes after repository initialization.
- Keep credentials, `.env`, databases, models, generated media and local state out of Git and release archives.
- Run `python -m unittest discover -s tests -v` and `python -m unittest discover -s tests/canvas -v` before claiming backend validation.
- Browser UI tests must use isolated data and must not submit GPU jobs without authorization.
- Generated results remain `COMPLETED_UNREVIEWED`. Unknown ComfyUI submission results require reconciliation rather than automatic duplicate submission.
- Preserve Apache-2.0 for application code and third-party notices/licenses.
