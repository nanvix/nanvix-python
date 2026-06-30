# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Clean lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import shutil
from pathlib import Path

from nanvix_zutil import CFG_SYSROOT, log, paths
from nanvix_zutil.paths import repo_root, test_out

from .lib import LibMixin


class CleanMixin(LibMixin):
    """``./z clean`` — remove build artifacts."""

    def clean(self) -> None:
        """Remove build artifacts."""
        # Clean release assets (staged tree + dist archives)
        for d in (paths.release_dir(), paths.dist_dir()):
            if d.is_dir():
                shutil.rmtree(d)
        legacy_release = repo_root() / "release-assets"
        if legacy_release.is_dir():
            shutil.rmtree(legacy_release)

        # Clean ramfs artifacts
        self._cleanup_ramfs()
        ramfs_img = test_out() / "nanvix_rootfs.img"
        ramfs_img.unlink(missing_ok=True)
        ramfs_sentinel = test_out() / ".ramfs-built"
        ramfs_sentinel.unlink(missing_ok=True)

        # Clean initrd
        self._cleanup_initrd()

        # Clean snapshot artifacts produced by the snapshot smoke test
        sysroot_str = self.config.get(CFG_SYSROOT, "")
        if sysroot_str:
            snapshots_dir = Path(sysroot_str) / "snapshots"
            if snapshots_dir.is_dir():
                shutil.rmtree(snapshots_dir)

        log.success("clean complete")
