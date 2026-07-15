# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Shared utilities for the nanvix-python ZScript.

Holds helpers used by more than one lifecycle stage. Lifecycle mixins
inherit from :class:`LibMixin` so that ``self.<helper>`` calls type-check
cleanly under basedpyright without any ``Protocol`` plumbing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from nanvix_zutil import CFG_SYSROOT, ZScript, log
from nanvix_zutil.exitcodes import EXIT_MISSING_DEP
from nanvix_zutil.paths import test_out

__all__ = (
    "DEFAULT_TIMEOUT",
    "IS_WINDOWS",
    "LibMixin",
    "mkramfs_binary",
    "nanvixd_binary",
)

# Per-test timeout in seconds (overridable via TIMEOUT_SECONDS env var).
DEFAULT_TIMEOUT = 300

IS_WINDOWS = sys.platform == "win32"

def nanvixd_binary() -> str:
    """Return the nanvixd binary name for the current host platform."""
    return "nanvixd.exe" if IS_WINDOWS else "nanvixd.elf"


def mkramfs_binary() -> str:
    """Return the mkramfs binary name for the current host platform."""
    return "mkramfs.exe" if IS_WINDOWS else "mkramfs.elf"


class LibMixin(ZScript):
    """Shared state + helpers for nanvix-python lifecycle mixins."""

    # The downloaded sysroot is runtime-only. Build-time headers, libraries,
    # startup objects, and linker scripts live exclusively in the SDK.
    SYSROOT_REQUIRED_FILES: tuple[str, ...] = (
        "bin/nanvixd.elf",
        "bin/kernel.elf",
        "bin/mkramfs.elf",
    )
    SYSROOT_REQUIRED_FILES_WINDOWS: tuple[str, ...] = (
        "bin/nanvixd.exe",
        "bin/kernel.elf",
        "bin/mkramfs.exe",
    )
    SYSROOT_MULTI_PROCESS_FILES: tuple[str, ...] = ()

    # Standalone / ramfs artefacts shared across build and test stages.
    _ramfs_img: Path | None = None
    _stripped_sysroot: Path | None = None
    _initrd: Path | None = None

    def _sysroot_path(self) -> Path:
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        return Path(sysroot)

    @staticmethod
    def _temporary_directory(prefix: str) -> Path:
        """Create a temporary directory under the ignored test output."""
        temp_root = test_out() / "temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=prefix, dir=temp_root))

    @staticmethod
    def _log_directory() -> Path:
        """Return the ignored directory used for transient command logs."""
        logs = test_out() / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        return logs

    def _nanvix_run(
        self,
        sysroot: Path,
        script_path: str,
        log_file: Path,
        *,
        timeout: int | None = None,
    ) -> None:
        """Run a Python script under nanvixd. See original docstring in z.py."""
        if timeout is None:
            timeout = int(os.environ.get("TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))

        deployment = self.config.deployment_mode
        nanvixd = str((sysroot / "bin" / nanvixd_binary()).resolve())

        if deployment == "standalone":
            if not self._ramfs_img or not self._ramfs_img.is_file():
                log.fatal(
                    "ramfs image not found.",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z build` first.",
                )
            initrd = self._ensure_initrd(sysroot)
            mount_dir = self._temporary_directory("nanvix-mount-")
            (mount_dir / "argv.txt").write_text(f"/sysroot/{script_path}\n")
            cmd = [
                nanvixd,
                "-bin-dir",
                str((sysroot / "bin").resolve()),
                "-ramfs",
                str(self._ramfs_img),
                "-mount",
                str(mount_dir),
                "--",
                str(initrd),
            ]
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
                    shutil.rmtree(mount_dir, ignore_errors=True)
        else:
            cmd = [nanvixd, "--", "./bin/python3.12", f"./{script_path}"]
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

    def _asset_prefix(self) -> str:
        """Return the archive stem used both for the release archive filename
        and as the wrapping subdir inside the archive.

        Matches ``nanvix-zutil release``'s magic-path naming
        (``{pkg}-{host}-{target}-{machine}-{mode}-{mem}``) so that
        ``tar xf {archive}.tar.gz && cd {stem}`` lands the user inside
        the extracted bundle.
        """
        return (
            f"{self.manifest.name}"
            f"-{self.config.host}"
            f"-{self.config.target}"
            f"-{self.config.machine}"
            f"-{self.config.deployment_mode}"
            f"-{self.config.memory_size}"
        )

    # ------------------------------------------------------------------
    # Forward declarations — concrete implementations live in BuildMixin.
    # Declared here so basedpyright resolves cross-mixin self.<helper>()
    # calls without Protocol plumbing. Each subclass mixin overrides.
    #
    # Rename hazard: basedpyright cannot distinguish a stub from the real
    # implementation, so renaming one of these methods on BuildMixin
    # without also renaming the stub here will silently disable the
    # cross-mixin call (callers will hit NotImplementedError at runtime).
    # When renaming, grep for both names and update both sites.
    # ------------------------------------------------------------------
    def _ensure_initrd(self, sysroot: Path) -> Path:  # pragma: no cover
        raise NotImplementedError

    def _cleanup_initrd(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _ensure_ramfs(self, sysroot: Path) -> Path:  # pragma: no cover
        raise NotImplementedError

    def _cleanup_ramfs(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _install_boot_script(self, sysroot: Path) -> None:  # pragma: no cover
        raise NotImplementedError

    def _install_site_packages(self, site_pkg: Path) -> None:  # pragma: no cover
        raise NotImplementedError

    def _install_pil_shim(self, site_pkg: Path) -> None:  # pragma: no cover
        raise NotImplementedError

    def _patch_openpyxl_lxml(self, site_pkg: Path) -> None:  # pragma: no cover
        raise NotImplementedError

    def _stage_test_scripts(self, sysroot: Path) -> None:  # pragma: no cover
        raise NotImplementedError

    def _precompile_pyc(
        self,
        pylib: Path,
        *,
        legacy: bool = True,
        strip_sources: bool = True,
    ) -> None:  # pragma: no cover
        raise NotImplementedError
