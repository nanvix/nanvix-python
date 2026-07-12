# Standalone Runtime Bundle

## Downloading a Pre-built Bundle

Download and run the installer script:

```bash
curl -fsSL -o get-nanvix-python.sh https://raw.githubusercontent.com/nanvix/nanvix-python/main/scripts/get-nanvix-python.sh
bash get-nanvix-python.sh nanvix-python
```

Use `--force` to re-download existing files:

```bash
bash get-nanvix-python.sh --force /tmp/nanvix-python
```

The script accepts the same environment variables as `get-nanvix.sh`:

| Variable                    | Default | Description                                                      |
| --------------------------- | ------- | ---------------------------------------------------------------- |
| `GITHUB_TOKEN` / `GH_TOKEN` | —       | GitHub token for authenticated API requests (avoids rate limits) |
| `NANVIX_CONNECT_TIMEOUT`    | `30`    | Connection timeout in seconds                                    |
| `NANVIX_MAX_TIMEOUT`        | `300`   | Maximum total timeout in seconds                                 |
| `NANVIX_FORCE_DOWNLOAD`     | `false` | Force re-download if `true`                                      |

You can also download bundles manually from
[Releases](https://github.com/nanvix/nanvix-python/releases).

## Building a Bundle from Source

After a successful build and test, package a self-contained tarball
that can run Python scripts on any Linux host with KVM support.

```bash
./z release
```

This writes Linux `.tar.gz` and Windows `.zip` artifacts to `./dist/`.

## Bundle Contents

```text
microvm-standalone-256mb/
  bin/              # nanvixd host binary, kernel.elf, python3.12
  lib/              # Python standard library and site-packages
  mnt/              # User workloads
  nanvix_rootfs.img # Bytecode-only Python stdlib and site-packages
  python3.initrd    # Daemons and CPython interpreter
  README.md         # Usage instructions
```

Only runtime-essential files are included — no static libraries,
headers, or build tools. All `.pyc` bytecode caches are pre-compiled
to avoid runtime file-creation issues
([nanvix/nanvix#1493](https://github.com/nanvix/nanvix/issues/1493)).

## Running from a Bundle

```bash
tar -xzf dist/microvm-standalone-256mb.tar.gz
cd microvm-standalone-256mb

# Run a script through the cold-start path
echo 'print("Hello from Nanvix!")' > mnt/bootstrap.py
./bin/nanvixd.elf -ramfs nanvix_rootfs.img -mount ./mnt -- python3.initrd
```

> **Note:** The `-c` flag only works with code that contains no spaces
> (a nanvixd argument-splitting limitation). Use script files instead.
