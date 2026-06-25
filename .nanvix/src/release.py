# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Release lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import shutil
import subprocess
import zipfile

from nanvix_zutil import log, paths
from nanvix_zutil.exitcodes import EXIT_MISSING_DEP
from nanvix_zutil.paths import repo_root

from .lib import IS_WINDOWS, LibMixin


class ReleaseMixin(LibMixin):
    """``./z release`` — archive the runtime bundle for distribution.

    The bundle tree is populated during ``./z build`` (see
    ``BuildMixin._stage_release``) under ``paths.release_dir()``;
    ``release`` only compresses that tree into ``paths.dist_dir()``.
    """

    def release(self) -> None:
        sysroot = self._sysroot_path()
        bundle_dir = paths.release_dir()
        dist_dir = paths.dist_dir()
        asset_prefix = self._asset_prefix()

        if not bundle_dir.is_dir():
            log.fatal(
                f"staged release tree not found at {bundle_dir}.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        dist_dir.mkdir(parents=True, exist_ok=True)

        if IS_WINDOWS:
            log.info("release: creating zip archive")
            archive = dist_dir / f"{asset_prefix}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                for entry in sorted(bundle_dir.rglob("*")):
                    arcname = f"{asset_prefix}/{entry.relative_to(bundle_dir)}"
                    if entry.is_dir():
                        zf.writestr(f"{arcname}/", b"")
                    elif entry.is_file():
                        zf.write(entry, arcname)
        else:
            log.info("release: creating tarball")
            archive = dist_dir / f"{asset_prefix}.tar.gz"
            subprocess.run(
                [
                    "tar",
                    "-czf",
                    str(archive),
                    "-C",
                    str(bundle_dir.parent),
                    f"--transform=s,^{bundle_dir.name},{asset_prefix},",
                    bundle_dir.name,
                ],
                check=True,
            )

        # Expose ELF binaries in a visible directory so that CI artifact
        # upload globs (e.g. **/*.elf) can find them — hidden directories
        # like .nanvix/ are excluded by actions/upload-artifact by default.
        elf_out = repo_root() / "elf-binaries"
        if elf_out.exists():
            shutil.rmtree(elf_out)
        elf_out.mkdir()
        for elf in (sysroot / "bin").glob("*.elf"):
            shutil.copy2(elf, elf_out)

        log.success(f"release: {archive}")
