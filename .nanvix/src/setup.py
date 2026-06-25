# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Setup lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import tarfile
from pathlib import Path

from nanvix_zutil import log
from nanvix_zutil.github import download_release_asset, resolve_release
from nanvix_zutil.paths import nanvix_root

from .lib import LibMixin


class SetupMixin(LibMixin):
    """``./z setup`` — download sysroot and pre-built CPython buildroot."""

    def setup(self) -> bool:
        """Download sysroot and pre-built CPython buildroot.

        The base ``super().setup()`` downloads the Nanvix sysroot and
        resolves dependencies declared in ``nanvix.toml``. Then we
        download the pre-built CPython release artifact and extract the
        interpreter binary and standard library into the sysroot.
        """
        result = super().setup()

        sysroot = self._sysroot_path()
        self._install_cpython(sysroot)

        log.success("setup complete")
        return result

    def _install_cpython(self, sysroot: Path) -> None:
        """Download and extract the pre-built CPython artifact into sysroot."""
        machine = self.config.machine
        mode = self.config.deployment_mode
        memory = self.config.memory_size

        # Resolve the cpython version (suffixed with nanvix sysroot version)
        cpython_version = self.manifest.version
        sysroot_tag = self.config.get("sysroot_tag", "")
        nanvix_ver = sysroot_tag.removeprefix("v") if sysroot_tag else ""
        if sysroot_tag:
            version_specifier = f"{cpython_version}-nanvix-{nanvix_ver}"
        else:
            version_specifier = cpython_version

        asset_name = f"cpython-{machine}-{mode}-{memory}.tar.gz"
        cache_dir = nanvix_root() / "cache"

        sentinel = sysroot / ".cpython-installed"
        if sentinel.is_file() and sentinel.read_text().strip() == version_specifier:
            log.info("CPython already installed, skipping")
            return

        log.info(f"downloading pre-built CPython ({asset_name})")

        release = resolve_release(
            repo="nanvix/cpython",
            version_specifier=version_specifier,
            gh_token=self.config.get("GH_TOKEN"),
        )

        asset_path = download_release_asset(
            repo="nanvix/cpython",
            version_specifier=version_specifier,
            asset_name=asset_name,
            dest=cache_dir,
            gh_token=self.config.get("GH_TOKEN"),
            _release=release,
        )

        log.info("extracting CPython into sysroot")
        with tarfile.open(asset_path, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue

                # Tolerate both the legacy layout (entries rooted under
                # ``sysroot/``) and the post-nanvix/cpython#742 layout
                # where the ``sysroot/`` prefix has been dropped.
                name = member.name.removeprefix("sysroot/")

                # bin/python.elf → sysroot/bin/python3.12
                if name == "bin/python.elf":
                    member.name = "bin/python3.12"
                    tf.extract(member, path=sysroot, filter="data")
                # lib/python3.12/* → sysroot/lib/python3.12/*
                elif name.startswith("lib/python3.12/"):
                    member.name = name
                    tf.extract(member, path=sysroot, filter="data")

        sentinel.write_text(version_specifier)
        log.success("CPython installed into sysroot")
