# Scripts and Development Tools

## Pre-Commit Hook Setup

This directory contains scripts to enforce code quality and build validation before commits.

### Quick Start

After cloning the repository, run:

```bash
bash scripts/install-hooks.sh
```

This installs the pre-commit hook that will automatically run before each commit.

### What Gets Checked

#### Backend (Python)
- **pytest**: Runs the entire test suite to ensure all tests pass
- **Type checking**: Optional type hint validation (if configured)

#### Frontend (Node.js)
- **ESLint**: Runs the linter to catch code quality issues
- **TypeScript**: Type checks the entire codebase with `tsc --noEmit`

### Smart Detection

The hook is intelligent:
- **Checks only what changed**: If you only modify backend files, frontend checks are skipped
- **Fast execution**: Only relevant checks run for your changes
- **Clear feedback**: Color-coded output shows exactly what passed/failed

### Bypass (When Necessary)

If you absolutely need to skip checks (not recommended for push to main):

```bash
git commit --no-verify
```

### Example Hook Output

```
🔍 Running pre-commit checks...

📦 Backend checks (Python)
  → Running pytest... ✓

📦 Frontend checks (Node.js)
  → Running ESLint... ✗
  → Checking TypeScript... ✗

✗ Some checks failed. Please fix the errors above before committing.
```

### How It Works

1. **Before each commit**, git automatically runs `.git/hooks/pre-commit`
2. Hook detects which files you changed (backend, frontend, or both)
3. Runs appropriate checks based on changes
4. If any check fails, commit is blocked with clear error messages
5. Fix the issues and try committing again

### Customizing Checks

The hook script is at `scripts/pre-commit-hook.py`. To modify what gets checked:

1. Edit the `check_backend()` or `check_frontend()` functions
2. Add/remove commands as needed
3. The hook runs automatically on next commit

### Troubleshooting

**"Command not found: pytest"**
- Install backend dependencies: `cd apps/api && pip install -r requirements.txt`

**"Command not found: pnpm"**
- Install pnpm: `npm install -g pnpm`
- Or use: `npm install --frozen-lockfile` in `apps/web`

**Hook not running**
- Reinstall: `bash scripts/install-hooks.sh`
- Check permissions: `ls -la .git/hooks/pre-commit` (should have `x` flag)

**Need to reinstall after git problems**
```bash
rm .git/hooks/pre-commit
bash scripts/install-hooks.sh
```

### Integration with CI/CD

The pre-commit hook mirrors the checks in `.github/workflows/ci.yml`. This ensures:
- Local and CI checks are consistent
- Failures caught locally before pushing
- No surprises on GitHub Actions

---

**Note**: These hooks run *locally* before push. The CI workflow also runs the same checks on the server for additional safety.
