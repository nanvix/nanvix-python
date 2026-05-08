# Nanvix Python

[![CI](https://github.com/nanvix/nanvix-python/actions/workflows/ci.yml/badge.svg)](https://github.com/nanvix/nanvix-python/actions/workflows/ci.yml)

CPython 3.12 distribution for the
[Nanvix](https://github.com/nanvix/nanvix) microkernel — a
self-contained Python runtime with pure Python pip packages.

## Quick Start (Pre-built Release)

Download the latest release artifact from
[Releases](https://github.com/nanvix/nanvix-python/releases) and
run Python under `nanvixd`:

### Linux

```bash
gh release download --repo nanvix/nanvix-python --pattern "*.tar.bz2" --clobber
tar -xjf microvm-standalone-256mb.tar.bz2
cd microvm-standalone-256mb
./bin/nanvixd.elf -- ./bin/python3.12 -c "print('Hello from Nanvix!')"
```

### Windows

```powershell
gh release download --repo nanvix/nanvix-python --pattern "*.zip" --clobber
Expand-Archive microvm-standalone-256mb.zip -DestinationPath .
cd microvm-standalone-256mb
.\bin\nanvixd.exe -- .\bin\python3.12 -c "print('Hello from Nanvix!')"
```

> **Note:** The `-c` flag only works with code that contains no spaces
> (a nanvixd argument-splitting limitation). Use script files instead.

### Using Built-in Packages

All pure Python packages are pre-installed. No `pip install` is needed:

```bash
echo 'import json; print(json.dumps({"hello": "nanvix"}))' > test.py
./bin/nanvixd.elf -- ./bin/python3.12 test.py
```

## Building from Source

All interaction is through the `./z` wrapper script which
auto-bootstraps [nanvix-zutil](https://github.com/nanvix/zutils).

### Prerequisites

- **Python 3.12+** on the host
- **Docker** (for cross-compilation and `.pyc` pre-compilation)
- **KVM** (`/dev/kvm`) on Linux for running Nanvix guests

### Build, Test, and Release

```bash
git clone https://github.com/nanvix/nanvix-python.git
cd nanvix-python

./z setup      # Download Nanvix sysroot and pre-built CPython
./z build      # Install pip packages and generate ramfs image
./z test       # Run smoke test and functional tests
./z benchmark  # Run hello-world benchmark and print execution time
./z release    # Package standalone runtime bundle into dist/
```

On Windows, use the PowerShell wrapper (`.\z.ps1`) or the
cross-platform entry point (`.\z`):

```powershell
.\z setup
.\z build
.\z test
.\z benchmark  # Prints: Execution time: X.XXXs
.\z release    # Produces dist\microvm-standalone-256mb.zip
```

### Environment Variables

| Variable                 | Default       | Description                           |
| ------------------------ | ------------- | ------------------------------------- |
| `NANVIX_MACHINE`         | `microvm`     | Target platform                       |
| `NANVIX_DEPLOYMENT_MODE` | `standalone`  | Deployment mode                       |
| `NANVIX_MEMORY_SIZE`     | `256mb`       | Memory configuration                  |
| `TIMEOUT_SECONDS`        | `300`         | Per-test timeout in seconds           |
| `TEST_START` / `TEST_END`| `1` / `999`   | Functional test range (inclusive)     |

## What's Included

- **CPython 3.12.3** — fully functional interpreter
- **Pure Python pip packages** — attrs, requests, flask, jinja2,
  beautifulsoup4, rich, click, and many more (see [packages](doc/packages.md))

## Supported Platform

| Platform   | Mode         | Memory |
| ---------- | ------------ | ------ |
| `microvm`  | `standalone` | 256 MB |

Tested on both Linux (KVM) and Windows in CI.

## Documentation

| Document                                | Description                            |
| --------------------------------------- | -------------------------------------- |
| [Building from Source](doc/building.md) | Full build prerequisites and walkthrough |
| [Supported Packages](doc/packages.md)   | Complete list of pip packages          |
| [Testing](doc/testing.md)               | Smoke and functional test details      |
| [CI / CD](doc/ci.md)                    | GitHub Actions pipeline                |
| [Contributing](doc/contributing.md)     | How to add packages or fixes           |

## Usage Statement

This project is a prototype. As such, we provide no guarantees that it
will work and you are assuming any risks with using the code. We welcome
comments and feedback. Please send any questions or comments to any of
the following maintainers of the project:

- [Pedro Henrique Penna](https://github.com/ppenna) -
  [ppenna@microsoft.com](mailto:ppenna@microsoft.com)

> By sending feedback, you are consenting that it may be used
> in the further development of this project.

## License

This project is distributed under the [MIT License](LICENSE.txt).
