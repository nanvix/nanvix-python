# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Benchmark lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from nanvix_zutil import log
from nanvix_zutil.exitcodes import EXIT_BUILD_FAILURE, EXIT_MISSING_DEP

from .lib import DEFAULT_TIMEOUT, LibMixin, nanvixd_binary


class BenchmarkMixin(LibMixin):
    """``./z benchmark`` — run a hello-world command and report wall time."""

    def benchmark(self) -> None:
        """Run a hello-world command and report total execution time."""
        sysroot = self._sysroot_path()

        nanvixd = sysroot / "bin" / nanvixd_binary()
        if not nanvixd.is_file():
            log.fatal(
                f"{nanvixd_binary()} not found in sysroot.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first.",
            )
        if not (sysroot / "bin" / "python3.12").is_file():
            log.fatal(
                "python3.12 not found in sysroot.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        deployment = self.config.deployment_mode
        nanvixd_bin = str(nanvixd.resolve())
        timeout = int(os.environ.get("TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))

        mount_dir: Path | None = None

        if deployment == "standalone":
            self._ensure_ramfs(sysroot)
            if not self._ramfs_img or not self._ramfs_img.is_file():
                log.fatal(
                    "ramfs image not found.",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z build` first.",
                )
            initrd = self._ensure_initrd(sysroot)

            # Create a temp mount directory with a hello-world bootstrap.py
            mount_dir = Path(tempfile.mkdtemp(prefix="nanvix-bench-"))
            (mount_dir / "bootstrap.py").write_text('print("hello")\n')
            cmd = [
                nanvixd_bin,
                "-bin-dir",
                str((sysroot / "bin").resolve()),
                "-ramfs",
                str(self._ramfs_img),
                "-mount",
                str(mount_dir),
                "--",
                str(initrd),
            ]
        else:
            cmd = [
                nanvixd_bin,
                "--",
                "./bin/python3.12",
                '-c print("hello")',
            ]

        tmp = Path(tempfile.gettempdir())
        log_file = tmp / "benchmark.log"

        log.info("running benchmark: hello world")
        log.info(f"command: {' '.join(cmd)}")
        start = time.perf_counter()
        with log_file.open("w") as fh:
            try:
                subprocess.run(
                    cmd,
                    cwd=sysroot,
                    stdin=subprocess.DEVNULL,
                    stdout=fh,
                    stderr=fh,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                fh.write(f"\nTIMEOUT after {timeout}s\n")
            finally:
                if mount_dir is not None:
                    shutil.rmtree(mount_dir, ignore_errors=True)
        elapsed = time.perf_counter() - start

        output = log_file.read_text(errors="replace") if log_file.is_file() else ""
        log_file.unlink(missing_ok=True)

        if deployment == "standalone":
            self._cleanup_ramfs()
            self._cleanup_initrd()

        if "hello" not in output:
            print(output)
            log.fatal(
                "benchmark failed: expected output not found", code=EXIT_BUILD_FAILURE
            )

        print(f"Execution time: {elapsed:.3f}s")
        log.success("benchmark complete")
