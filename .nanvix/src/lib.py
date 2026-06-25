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

from nanvix_zutil import CFG_SYSROOT, TOOLCHAIN_CONTAINER_PATH, ZScript, log
from nanvix_zutil.exitcodes import EXIT_MISSING_DEP
from nanvix_zutil.paths import repo_root

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

    def _toolchain_str(self) -> str:
        return str(TOOLCHAIN_CONTAINER_PATH)

    def _host_python(self) -> str | None:
        toolchain_python = Path(self._toolchain_str()) / "bin" / "python3"
        if toolchain_python.is_file():
            return str(toolchain_python)
        for name in ("python3", "python"):
            if shutil.which(name):
                return name
        return None

    def _ensure_python_in_repo_root(self, sysroot: Path) -> None:
        repo_python = repo_root() / "python3.12"
        if repo_python.exists():
            return
        shutil.copy2(sysroot / "bin" / "python3.12", repo_python)

    def _cleanup_python_in_repo_root(self) -> None:
        (repo_root() / "python3.12").unlink(missing_ok=True)

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
            mount_dir = Path(tempfile.mkdtemp(prefix="nanvix-mount-"))
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
        """Return the platform/mode/memory triple used for archive names."""
        return (
            f"{self.config.machine}-{self.config.deployment_mode}"
            f"-{self.config.memory_size}"
        )

    def release_targets(self) -> dict[str, str]:
        """Name the release archive ``<asset_prefix>.tar.gz``.

        ``release_dir()`` contains a single ``<asset_prefix>/`` subdir
        staged by :meth:`BuildMixin._stage_release`; archive it as-is.
        """
        return {".": self._asset_prefix()}

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
