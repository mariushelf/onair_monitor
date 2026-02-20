# Project Guidelines

## Package Management

Use `uv` for all dependency management (not `pip`). Examples:
- `uv add <package>` to add a dependency
- `uv pip install -e .` to install the project
- `uv run <command>` to run commands in the project environment

## Git Conventions

Use semantic commit messages:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation changes
- `style:` formatting, missing semicolons, etc. (no code change)
- `refactor:` code restructuring without changing behavior
- `test:` adding or updating tests
- `chore:` maintenance tasks, dependency updates, CI config
