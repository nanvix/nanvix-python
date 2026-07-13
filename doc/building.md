# Building from Source

This guide covers assembling the Nanvix Python runtime from the SDK-built
CPython 3.12 release and pure Python pip packages.

## Prerequisites

| Requirement            | Notes                                                               |
| ---------------------- | ------------------------------------------------------------------- |
| **Linux x86-64 host**  | Full build/test support; Windows 11 uses the PowerShell flow         |
| **Nanvix SDK**         | Pinned `nanvix-sdk-c-clang` image shown below                        |
| **Python 3.12+**       | Host Python for nanvix-zutil and build orchestration                |
| **nanvix-zutil**       | Auto-bootstrapped by `./z` wrapper scripts                          |
| **Docker**             | Runs SDK host Python 3.12 for deterministic bytecode generation     |
| **KVM** (`/dev/kvm`)   | Required to run Nanvix guests during Linux testing                  |

## Commands

All interaction is through the `./z` build script:

| Command       | Description                                                                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `./z setup`   | Download the Nanvix 0.20.0 runtime-only sysroot and exact SDK-built CPython 3.12.3 dependency.                                                               |
| `./z build`   | Install pure Python packages and generate Python 3.12 bytecode and the standalone ramfs.                                                                      |
| `./z test`    | Install pip site-packages, run the smoke test (built-in modules), then run functional tests on `nanvixd.elf`.                                                |
| `./z release` | Package the sysroot into a standalone runtime tarball under `./dist/`.                                                                                       |
| `./z clean`   | Remove all build artifacts, the sysroot, work directory, and release assets.                                                                                 |

## Build Walkthrough

```bash
# 1. Clone with submodules
git clone --recurse-submodules https://github.com/nanvix/nanvix-python.git
cd nanvix-python

# 2. Download the runtime and exact SDK-built CPython dependency
./z setup

# 3. Install packages and generate the bytecode-only ramfs
./z build

# 4. Install pip packages and run all tests
./z test

# 5. (Optional) Package a standalone runtime bundle
./z release
```

### Windows

On Windows, use the PowerShell wrapper:

```powershell
.\z.ps1 setup
.\z.ps1 build
.\z.ps1 test
```

## Environment Variables

| Variable                  | Default      | Description                                   |
| ------------------------- | ------------ | --------------------------------------------- |
| `NANVIX_MACHINE`          | `microvm`    | Runtime platform (only `microvm` is supported) |
| `NANVIX_DEPLOYMENT_MODE`  | `standalone` | Runtime mode (only `standalone` is supported) |
| `NANVIX_MEMORY_SIZE`      | `256mb`      | Runtime memory size                           |
| `TEST_START`              | `1`          | First test number to run (inclusive)          |
| `TEST_END`                | `999`        | Last test number to run (inclusive)           |
| `TIMEOUT_SECONDS`         | `300`        | Per-test timeout in seconds                   |
| `GH_TOKEN`                | —            | GitHub token for authenticated API calls      |

## Project Layout

```text
nanvix-python/
├── z                        # Cross-platform entry point (delegates to z.sh or z.ps1)
├── z.sh                     # Linux/macOS wrapper (self-bootstraps nanvix-zutil)
├── z.ps1                    # Windows wrapper (self-bootstraps nanvix-zutil)
├── .nanvix/
│   ├── nanvix.toml          # Package manifest (name, version, dependencies)
│   └── z.py                 # Build script (ZScript subclass)
├── patches/                 # Build documentation
├── requirements/            # Pip package lists (base + extra)
├── tests/
│   ├── smoke_test_l2.py     # Built-in module validation
│   └── func/                # Per-package functional tests
├── doc/                     # Documentation
├── scripts/                 # Helper scripts
└── dist/                    # Output of ./z release
```
