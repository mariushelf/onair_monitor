# Project Guidelines

## Package Management

Use `uv` for all dependency management (not `pip`). Examples:
- `uv add <package>` to add a dependency
- `uv pip install -e .` to install the project
- `uv run <command>` to run commands in the project environment

## Git Conventions

Use semantic commit messages:

- `feat:` new feature
- `fix:` bug fix (something was actually broken)
- `docs:` documentation changes
- `style:` formatting, missing semicolons, etc. (no code change)
- `refactor:` code restructuring without changing behavior
- `test:` adding or updating tests
- `chore:` maintenance tasks, dependency updates, CI config, cleanup of things that work but are unnecessary

Do NOT add "Co-Authored-By" or any AI attribution trailers to commit messages.

## Known Issues

### Tray icon blank when installed via pyenv

If `onair-monitor` is installed into a pyenv-managed Python (e.g. via `uv pip install`
while pyenv is active), the tray icon may render as a grey rectangle. This happens
because pyenv's Python lacks PyGObject (`gi`), so pystray falls back to the `_xorg`
backend which doesn't render icons properly.

**Fix:** Uninstall from pyenv (`~/.pyenv/versions/<ver>/bin/pip uninstall onair-monitor`)
and use `uv tool install onair-monitor[tray]` instead. The uv tool environment picks up
the system `python3-gi` package, enabling the AppIndicator backend.

Note that pyenv shims (`~/.pyenv/shims/`) typically come before `~/.local/bin/` in PATH,
so a pyenv-installed entry point will shadow the uv tool version.
