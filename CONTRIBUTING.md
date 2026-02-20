# Contributing

## Development Setup

```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev  # Debian/Ubuntu
uv sync
```

## Running Tests

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
make ty
```

## Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Version bumps are determined automatically from commit messages:

| Prefix | Example | Version bump |
|---|---|---|
| `fix:`, `perf:` | `fix: handle missing config` | patch (0.1.0 -> 0.1.1) |
| `feat:` | `feat: add webhook retry` | minor (0.1.0 -> 0.2.0) |
| `feat!:` or `BREAKING CHANGE:` footer | `feat!: change config format` | major (0.1.0 -> 1.0.0) |
| `docs:`, `chore:`, `style:`, `refactor:`, `test:` | `docs: update README` | no release |

While the version is 0.x, breaking changes bump minor instead of major.

## Release Process

Releases use [python-semantic-release](https://python-semantic-release.readthedocs.io/)
and follow a two-step flow: **prepare** then **publish**.

### Step 1 — Prepare the release

1. Go to **Actions > Release > Run workflow** on GitHub.
2. Select the branch to release from (`master` or a `release/*` branch).
3. Optionally choose a **force bump level** (`patch`, `minor`, or `major`)
   to override the automatic version determined from commits.
4. For a pre-release, check **prerelease** and set the **token**
   (e.g., `rc`, `beta`, `alpha`).
5. Click **Run workflow**.

This will:
- Run the full CI suite (lint + tests).
- Determine the next version from commit history (or use the forced level).
- Bump the version in `pyproject.toml`, commit, tag, and push.
- Create a **draft** GitHub Release with auto-generated release notes.

### Step 2 — Publish the release

1. Go to **Releases** on GitHub. The new draft release will be at the top.
2. Edit the release notes as needed.
3. Click **Publish release**.

This triggers the publish workflow, which builds the package and uploads it
to PyPI.

### Override Examples

| Scenario | What to do |
|---|---|
| Force a major release | Select `major` from the dropdown |
| Release with only docs/chore commits | Select `patch` (or `minor`) to force a bump |
| Pre-release (e.g., `1.0.0-rc.1`) | Check `prerelease`, set token to `rc` |
| Beta from a release branch | Run from `release/x.y`, check `prerelease`, token = `beta` |
| Hotfix from a release branch | Run from `release/1.x`, select `patch` |
