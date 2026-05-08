# CI / CD

The GitHub Actions workflow
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) is a thin
caller that invokes the reusable
[`nanvix/workflows/.github/workflows/nanvix-ci.yml`](https://github.com/nanvix/workflows)
workflow, following the same pattern used by all `usr/` packages.

## Pipeline Stages

1. **Get Nanvix Info** — resolves sysroot metadata via `nanvix-zutil resolve`.
2. **Build** (matrix) — runs `./z setup` → `./z build` → `./z test` → `./z release`
   for each platform/process-mode combination.
3. **Benchmark** — runs `./z benchmark` and publishes the `Execution time: X.XXXs`
   line in the job log, step summary, and `hello-world-benchmark` artifact.
4. **Release** — collects build artifacts, generates a lockfile, and creates
   a GitHub release tagged `{version}-nanvix-{nanvix_version}`.
5. **Report Failure** — opens a GitHub issue on scheduled-run failures.

## Platform Matrix

The CI matrix tests every combination of platform and process mode:

| Platform     | Process Mode     | Status       |
| ------------ | ---------------- | ------------ |
| `hyperlight` | `multi-process`  | Tested in CI |
| `hyperlight` | `single-process` | Tested in CI |
| `microvm`    | `multi-process`  | Tested in CI |
| `microvm`    | `single-process` | Tested in CI |

## Triggers

- **Nightly** — scheduled at UTC 00:00
- **Push** — to `main` and `nanvix/**` branches
- **Pull Request** — targeting `main` and `nanvix/**` branches
- **Dispatch** — manual trigger or `cpython-release` repository dispatch

## Failure Handling

On failure, debug logs are uploaded as workflow artifacts and a GitHub
issue is automatically created and assigned to the maintainers.
