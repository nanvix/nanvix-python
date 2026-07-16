# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Test lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from nanvix_zutil import log
from nanvix_zutil.exitcodes import EXIT_MISSING_DEP, EXIT_TEST_FAILURE

from .lib import (
    DEFAULT_TIMEOUT,
    IS_WINDOWS,
    LibMixin,
    mkramfs_binary,
    nanvixd_binary,
)

# CPython startup warning emitted when lib-dynload cannot be resolved.
# Keep this in sync with CPython's warning text in Modules/getpath.py.
_PLATLIB_WARNING_RE = re.compile(
    r"\bcould not find platform dependent libraries\b", re.I
)


class TestMixin(LibMixin):
    """``./z test`` — smoke + snapshot + functional tests."""

    def test(self) -> None:
        """Run smoke and functional tests.

        Without targets, runs both smoke and functional tests.
        Pass targets after ``--`` to select:
          ``./z test -- test-smoke``       — smoke test only
          ``./z test -- test-integration`` — functional tests only
        """
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
        if deployment == "standalone":
            mkramfs = sysroot / "bin" / mkramfs_binary()
            if not mkramfs.is_file():
                log.fatal(
                    f"{mkramfs_binary()} not found (required for standalone mode).",
                    code=EXIT_MISSING_DEP,
                )

        # Install site-packages
        site_pkg = sysroot / "lib" / "python3.12" / "site-packages"
        site_pkg.mkdir(parents=True, exist_ok=True)
        self._install_site_packages(site_pkg)
        self._install_pil_shim(site_pkg)
        self._patch_openpyxl_lxml(site_pkg)

        # Stage test scripts into sysroot (idempotent w.r.t. ``./z build``,
        # which stages the same files; keeps the ramfs hash consistent).
        self._stage_test_scripts(sysroot)

        # Validate that an up-to-date ramfs image exists for standalone
        # mode; ``_ensure_ramfs`` never rebuilds and hard-fails if the
        # image is missing or stale (instructing the user to run
        # ``./z build``, which is the sole Docker-using producer).
        # When NANVIX_PREBUILT_RAMFS is set (e.g. by CI to reuse the
        # Linux-built ramfs on Windows), skip validation entirely.
        if deployment == "standalone":
            # Install _boot.py entry point into sysroot
            self._install_boot_script(sysroot)
            self._ensure_ramfs(sysroot)

        # Standalone exclusions
        exclude_tests = os.environ.get("EXCLUDE_TESTS", "")
        if deployment == "standalone" and not exclude_tests:
            # Stripped from standalone ramfs: plotly(83), setuptools(89), wheel(90)
            exclude_tests = "83 89 90"

        # Determine which tests to run
        default_targets = {"test-smoke", "test-integration"}
        if deployment == "standalone" and IS_WINDOWS:
            default_targets.add("test-snapshot")
        targets = set(self.targets) if self.targets else default_targets

        try:
            if "test-smoke" in targets:
                self._run_smoke_test(sysroot)
            if "test-snapshot" in targets:
                self._run_snapshot_smoke_test(sysroot)
            if "test-integration" in targets:
                self._run_functional_tests(sysroot, exclude_tests)
        finally:
            self._cleanup_ramfs()
            self._cleanup_initrd()

    def _run_smoke_test(self, sysroot: Path) -> None:
        """Run the layer-2 smoke test."""
        log.info("=== smoke test ===")
        tmp = self._log_directory()
        log_file = tmp / "smoke.log"
        self._nanvix_run(sysroot, "smoke_test_l2.py", log_file)

        output = log_file.read_text(errors="replace") if log_file.is_file() else ""
        log_file.unlink(missing_ok=True)

        if "FAIL" in output:
            print(output)
            log.fatal("smoke test failed", code=EXIT_TEST_FAILURE)
        if _PLATLIB_WARNING_RE.search(output):
            print(output)
            log.fatal(
                "smoke test reported missing platform libraries",
                code=EXIT_TEST_FAILURE,
            )
        if "PASS" in output:
            log.success("smoke test: PASS")
        elif output.strip():
            print(output)
        else:
            log.fatal("smoke test produced no output", code=EXIT_TEST_FAILURE)

    def _await_snapshot_files(
        self,
        proc: "subprocess.Popen[bytes]",
        vmem: Path,
        cbor: Path,
        timeout: int,
        gen_log: Path,
    ) -> None:
        """Wait until snapshot files are written and stable.

        On some host configurations nanvixd does not exit after the
        guest writes its snapshot — the WHP partition is torn down but
        the host process sits idle.  Instead of waiting for the process
        to exit (which would hit ``timeout``), poll for both snapshot
        files, then wait until ``vmem`` stops growing.  Callers are
        responsible for terminating ``proc`` afterwards.
        """

        def _dump_log() -> None:
            # Dump captured nanvixd output so CI reveals how far cold
            # boot got (e.g. reached `nanvix.snapshot()`, hung writing
            # vmem, never reached the boot prompt, etc.).
            print(gen_log.read_text(errors="replace") if gen_log.is_file() else "")

        deadline = time.monotonic() + timeout
        # 1) Wait for both files to appear.  If the process exits
        #    before the files show up, keep polling for a short grace
        #    period — on Windows the filesystem can lag process exit.
        grace_deadline: float | None = None
        while time.monotonic() < deadline:
            if vmem.is_file() and cbor.is_file():
                break
            if proc.poll() is not None and grace_deadline is None:
                grace_deadline = min(deadline, time.monotonic() + 5.0)
            if grace_deadline is not None and time.monotonic() >= grace_deadline:
                _dump_log()
                log.fatal(
                    "snapshot smoke test: process exited before snapshot files appeared",
                    code=EXIT_TEST_FAILURE,
                )
            time.sleep(0.1)
        else:
            _dump_log()
            log.fatal(
                "snapshot smoke test: generation timed out",
                code=EXIT_TEST_FAILURE,
            )

        last_size = -1
        stable_since: float | None = None
        # 2) Wait for vmem size to stabilize (kernel may still be
        #    flushing the memory image after cbor appears).  Keep
        #    waiting even if the process has already exited — the OS
        #    may still be flushing buffered writes.
        while time.monotonic() < deadline:
            try:
                size = vmem.stat().st_size
            except OSError:
                size = -1
            now = time.monotonic()
            if size == last_size and size > 0:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= 1.0:
                    return
            else:
                last_size = size
                stable_since = None
            time.sleep(0.2)
        _dump_log()
        log.fatal(
            "snapshot smoke test: generation timed out",
            code=EXIT_TEST_FAILURE,
        )

    def _run_snapshot_smoke_test(self, sysroot: Path) -> None:
        """Smoke test: generate a VM snapshot then warm-restore hello-world.

        Snapshots are only supported on Windows (WHP) and are not
        portable across machines, so this test is host-local.  It:

          1. Cold-boots nanvixd with ``-kernel-args snapshot`` (no
             ``-mount``).  The _boot.py entry point calls
             ``nanvix.snapshot()`` then ``nanvix.mount()`` which fails
             (no mount provided), causing a clean exit.  The snapshot
             files are written to ``sysroot/snapshots/``.
          2. Warm-restores from the snapshot with a ``-mount`` directory
             whose ``bootstrap.py`` prints ``hello`` and checks for that
             output.
        """
        if not IS_WINDOWS:
            log.info("snapshot smoke test: skipped (Windows-only / WHP)")
            return
        if not self._ramfs_img or not self._ramfs_img.is_file():
            log.fatal(
                "ramfs image not found (required for snapshot smoke test).",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        log.info("=== snapshot smoke test ===")
        initrd = self._ensure_initrd(sysroot)
        nanvixd = str((sysroot / "bin" / nanvixd_binary()).resolve())
        timeout = int(os.environ.get("TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))

        snapshots_dir = sysroot / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        vmem = snapshots_dir / "kernel.vmem"
        cbor = snapshots_dir / "kernel.whp.cbor"
        vmem.unlink(missing_ok=True)
        cbor.unlink(missing_ok=True)

        tmp = self._log_directory()

        # --- Phase 1: cold boot to generate snapshot ---------------------
        # nanvixd writes the snapshot files (kernel.vmem + kernel.whp.cbor)
        # and the guest exits, but on some host configurations the nanvixd
        # process itself does not return — it sits idle after the WHP
        # partition is torn down. Rather than wait for nanvixd to exit
        # (which would hit the per-test timeout), poll for the snapshot
        # files, wait until they stop growing, and then terminate nanvixd.
        log.info("snapshot smoke test: generating snapshot (cold boot)")
        gen_log = tmp / "snapshot-gen.log"
        gen_cmd = [
            nanvixd,
            "-bin-dir",
            str((sysroot / "bin").resolve()),
            "-ramfs",
            str(self._ramfs_img),
            "-kernel-args",
            "snapshot",
            "--",
            str(initrd),
        ]
        with gen_log.open("w") as fh:
            proc = subprocess.Popen(
                gen_cmd,
                cwd=sysroot,
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=fh,
            )
            try:
                self._await_snapshot_files(proc, vmem, cbor, timeout, gen_log)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            log.fatal(
                                "snapshot smoke test: nanvixd did not exit after kill() during cleanup",
                                code=EXIT_TEST_FAILURE,
                            )

        if not vmem.is_file() or not cbor.is_file():
            print(gen_log.read_text(errors="replace") if gen_log.is_file() else "")
            log.fatal(
                "snapshot smoke test: snapshot files not produced",
                code=EXIT_TEST_FAILURE,
            )
        gen_log.unlink(missing_ok=True)

        # --- Phase 2: warm restore to run hello-world --------------------
        log.info("snapshot smoke test: warm-restoring to run hello-world")
        mount_dir = self._temporary_directory("nanvix-snap-smoke-")
        (mount_dir / "bootstrap.py").write_text('print("hello")\n')
        run_log = tmp / "snapshot-run.log"
        run_cmd = [
            nanvixd,
            "-bin-dir",
            str((sysroot / "bin").resolve()),
            "-snapshot",
            str(cbor),
            "-ramfs",
            str(self._ramfs_img),
            "-mount",
            str(mount_dir),
            "-kernel-args",
            "snapshot",
            "--",
            str(initrd),
        ]
        try:
            with run_log.open("w") as fh:
                try:
                    subprocess.run(
                        run_cmd,
                        cwd=sysroot,
                        stdin=subprocess.DEVNULL,
                        stdout=fh,
                        stderr=fh,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired:
                    fh.write(f"\nTIMEOUT after {timeout}s\n")
        finally:
            shutil.rmtree(mount_dir, ignore_errors=True)

        output = run_log.read_text(errors="replace") if run_log.is_file() else ""
        run_log.unlink(missing_ok=True)

        if "hello" not in output:
            print(output)
            log.fatal(
                "snapshot smoke test: expected 'hello' not found in output",
                code=EXIT_TEST_FAILURE,
            )
        log.success("snapshot smoke test: PASS")

    def _run_functional_tests(self, sysroot: Path, exclude_tests: str) -> None:
        """Run the numbered functional tests."""
        log.info("=== functional tests ===")

        test_start = int(os.environ.get("TEST_START", "1"))
        test_end = int(os.environ.get("TEST_END", "999"))
        excluded: set[str] = set(exclude_tests.split()) if exclude_tests else set()

        tmp = self._log_directory()
        total_pass = 0
        total_fail = 0
        total_skip = 0
        failed_tests: list[str] = []

        test_files = sorted(sysroot.glob("test_[0-9]*.py"))
        for test_file in test_files:
            name = test_file.name

            # Extract test number for filtering
            match = re.search(r"test_(\d+)", name)
            if not match:
                continue
            num = int(match.group(1))
            if num < test_start or num > test_end:
                continue
            if str(num) in excluded:
                continue

            log_file = tmp / f"{name}.log"
            self._nanvix_run(sysroot, name, log_file)

            output = log_file.read_text(errors="replace") if log_file.is_file() else ""
            log_file.unlink(missing_ok=True)

            if "PASS" in output:
                # Extract test name from output
                for line in output.splitlines():
                    if "PASS" in line:
                        test_name = line.split(":")[0].strip()
                        print(f"  {test_name}: PASS")
                        break
                total_pass += 1
            elif "FAIL" in output:
                for line in output.splitlines():
                    if "FAIL" in line:
                        print(f"  {line.strip()}")
                total_fail += 1
                failed_tests.append(name)
            else:
                print(f"  {name}: SKIP")
                total_skip += 1
                skip_log = tmp / f"skip_{name}.log"
                skip_log.write_text(output)

        print(
            f"Results: {total_pass} passed, {total_fail} failed, {total_skip} skipped"
        )

        if total_fail > 0:
            print(f"Failed tests: {' '.join(failed_tests)}")
            log.fatal("functional tests failed", code=EXIT_TEST_FAILURE)
        if total_pass == 0:
            log.fatal(
                "no tests passed (all skipped or none found)", code=EXIT_TEST_FAILURE
            )

        log.success("all functional tests passed")
