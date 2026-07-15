# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Setup lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from nanvix_zutil import Dependency, log
from nanvix_zutil.exitcodes import EXIT_MISSING_DEP
from nanvix_zutil.paths import nanvix_root

from .lib import LibMixin


class SetupMixin(LibMixin):
    """``./z setup`` — download the runtime and pre-built CPython."""

    def setup(self) -> bool:
        """Download the sysroot and pre-built CPython.

        The base ``super().setup()`` downloads the Nanvix sysroot and
        resolves and caches dependencies declared in ``nanvix.toml``. Then
        we reuse the cached CPython runtime artifact and extract only the
        interpreter binary and standard library into the runtime sysroot.
        """
        dependency = self._cpython_dependency()
        # Magic-path naming (zutils v0.17.0):
        #   {pkg}-{host}-{arch}-{machine}-{mode}-{mem}.{ext}
        # Extension varies by host (windows -> .zip, linux -> .tar.gz);
        # buildroot's artifact_pattern doesn't expose {ext}, so we
        # inline it based on config.host. Pinning the extension also
        # avoids matching the sibling '-dev' archive by prefix.
        archive_ext = ".zip" if str(self.config.host) == "windows" else ".tar.gz"
        dependency.artifact_pattern = (
            "{name}-{host}-{arch}-{machine}-{mode}-{mem}" + archive_ext
        )
        result = super().setup()

        sysroot = self._sysroot_path()
        self._install_cpython(sysroot, dependency)

        log.success("setup complete")
        return result

    def _cpython_dependency(self) -> Dependency:
        """Return the CPython dependency parsed and resolved by zutils."""
        dependency = next(
            (dep for dep in self.manifest.dependencies if dep.name == "cpython"),
            None,
        )
        if dependency is None:
            log.fatal(
                "cpython is not declared in nanvix.toml.",
                code=EXIT_MISSING_DEP,
            )
        return dependency

    def _cached_cpython_artifact(self, dependency: Dependency) -> Path:
        """Return the CPython runtime artifact downloaded by base setup."""
        prefix = dependency.artifact_pattern.format(
            name=dependency.name,
            host=self.config.host,
            arch=self.config.target,
            machine=self.config.machine,
            mode=self.config.deployment_mode,
            mem=self.config.memory_size,
        )
        cache_dir = nanvix_root() / "cache"
        candidates = [
            path
            for path in cache_dir.iterdir()
            if path.is_file()
            and path.name.startswith(prefix)
            and path.name.endswith((".tar.bz2", ".tar.gz", ".zip"))
        ]
        if not candidates:
            log.fatal(
                f"base setup did not cache a CPython artifact matching '{prefix}'.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` again and inspect the dependency download.",
            )
        candidates.sort(
            key=lambda path: (path.stat().st_mtime, path.name),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _cpython_destination(member_name: str, sysroot: Path) -> Path | None:
        """Map a safe CPython archive member to its runtime destination."""
        member_path = PurePosixPath(member_name.replace("\\", "/"))
        if member_path.is_absolute() or ".." in member_path.parts:
            return None
        parts = member_path.parts

        for index in range(len(parts) - 1):
            if parts[index] == "bin" and parts[index + 1] in (
                "python.elf",
                "python3.12",
            ):
                if index + 2 == len(parts):
                    return sysroot / "bin" / "python3.12"

        for index in range(len(parts) - 1):
            if parts[index : index + 2] == ("lib", "python3.12"):
                relative = Path(*parts[index:])
                destination = (sysroot / relative).resolve()
                if destination.is_relative_to(sysroot.resolve()):
                    return destination
        return None

    def _extract_cpython_tar(self, artifact: Path, sysroot: Path) -> None:
        """Safely extract CPython runtime files from a tar archive."""
        with tarfile.open(artifact, "r:*") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                destination = self._cpython_destination(member.name, sysroot)
                if destination is None:
                    continue
                source = archive.extractfile(member)
                if source is None:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                destination.chmod(member.mode & 0o777)

    def _extract_cpython_zip(self, artifact: Path, sysroot: Path) -> None:
        """Safely extract CPython runtime files from a zip archive."""
        with zipfile.ZipFile(artifact) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                destination = self._cpython_destination(member.filename, sysroot)
                if destination is None:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                mode = (member.external_attr >> 16) & 0o777
                if mode:
                    destination.chmod(mode)

    def _install_cpython(self, sysroot: Path, dependency: Dependency) -> None:
        """Extract the base-setup CPython artifact into the runtime sysroot."""
        version = str(dependency.ref.value)

        sentinel = sysroot / ".cpython-installed"
        python = sysroot / "bin" / "python3.12"
        stdlib = sysroot / "lib" / "python3.12"
        if (
            sentinel.is_file()
            and sentinel.read_text().strip() == version
            and python.is_file()
            and (stdlib / "os.py").is_file()
        ):
            self._remove_stdlib_build_artifacts(stdlib)
            log.info("CPython already installed, skipping")
            return

        artifact = self._cached_cpython_artifact(dependency)
        log.info(f"extracting CPython from cached {artifact.name}")
        python.unlink(missing_ok=True)
        if stdlib.is_dir():
            shutil.rmtree(stdlib)
        if zipfile.is_zipfile(artifact):
            self._extract_cpython_zip(artifact, sysroot)
        else:
            self._extract_cpython_tar(artifact, sysroot)

        missing = [
            str(path.relative_to(sysroot))
            for path in (python, stdlib / "os.py", stdlib / "site.py")
            if not path.is_file()
        ]
        if missing:
            log.fatal(
                "CPython artifact is missing runtime files: " + ", ".join(missing),
                code=EXIT_MISSING_DEP,
            )

        self._remove_stdlib_build_artifacts(stdlib)
        sentinel.write_text(version)
        log.success("CPython installed into sysroot")

    @staticmethod
    def _remove_stdlib_build_artifacts(stdlib: Path) -> None:
        """Remove SDK build inputs that are not part of the Python runtime."""
        for pattern in ("*.a", "*.c", "*.cpp", "*.h", "*.pxd", "*.pyx"):
            for path in stdlib.rglob(pattern):
                path.unlink(missing_ok=True)
