# Contributing to PatchWise

## Branch Strategy
- `main` — production releases only
- `dev` — active development, all PRs target here
- `feature/*` — new features
- `fix/*` — bug fixes

## Development Setup
1. Fork the repo
2. Clone your fork
3. Create a feature branch: `git checkout -b feature/your-feature dev`
4. Make changes
5. Run tests: `./run.sh test`
6. Push and open a PR to `dev`

## Commit Convention
```text
feat: add new review criterion
fix: resolve port allocation issue
docs: update README
chore: bump dependencies
test: add agent loop tests
```

## PR Checklist
- [ ] Tests pass
- [ ] Docker builds cleanly
- [ ] No .env secrets committed
- [ ] README updated if needed
