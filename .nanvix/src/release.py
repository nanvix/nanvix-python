# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Release lifecycle for the nanvix-python ZScript."""

from __future__ import annotations

import shutil
import subprocess
import zipfile

from nanvix_zutil import log, paths
from nanvix_zutil.exitcodes import EXIT_BUILD_FAILURE, EXIT_MISSING_DEP
from nanvix_zutil.paths import nanvix_root, repo_root

from .lib import IS_WINDOWS, LibMixin, mkramfs_binary, nanvixd_binary


class ReleaseMixin(LibMixin):
    """``./z release`` — package the runtime bundle for distribution."""

    def release(self) -> None:
        """Package the runtime bundle for distribution."""
        sysroot = self._sysroot_path()

        nanvixd_name = nanvixd_binary()
        if not (sysroot / "bin" / nanvixd_name).is_file():
            log.fatal(
                f"{nanvixd_name} not found in sysroot.",
                code=EXIT_MISSING_DEP,
            )
        if not (sysroot / "bin" / "python3.12").is_file():
            log.fatal(
                "python3.12 not found in sysroot.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        platform_name = self.config.machine
        mode = self.config.deployment_mode
        memory = self.config.memory_size
        asset_prefix = f"{platform_name}-{mode}-{memory}"

        dist_dir = paths.dist_dir()
        bundle_root = nanvix_root() / "release-bundle"
        bundle_dir = bundle_root / asset_prefix

        log.info(f"release: preparing artifacts for {asset_prefix}")

        if bundle_root.exists():
            shutil.rmtree(bundle_root)
        dist_dir.mkdir(parents=True, exist_ok=True)
        bundle_dir.mkdir(parents=True)

        # Copy runtime binaries
        log.info("release: copying runtime binaries")
        bin_dir = bundle_dir / "bin"
        bin_dir.mkdir()
        runtime_bins = [nanvixd_name, "kernel.elf", "python3.12"]
        if mode == "multi-process":
            runtime_bins.extend(["linuxd.elf", "uservm.elf"])
        for name in runtime_bins:
            src_file = sysroot / "bin" / name
            if src_file.is_file():
                shutil.copy2(src_file, bin_dir)
        python_target = bin_dir / "python3.12"
        python_link = bin_dir / "python3"
        if python_target.is_file():
            try:
                python_link.symlink_to("python3.12")
            except OSError:
                shutil.copy2(python_target, python_link)

        # Copy Python stdlib + site-packages
        log.info("release: copying Python standard library and site-packages")
        lib_dir = bundle_dir / "lib"
        lib_dir.mkdir()
        pylib = sysroot / "lib" / "python3.12"
        if pylib.is_dir():
            shutil.copytree(pylib, lib_dir / "python3.12")

        # Linker script
        user_ld = sysroot / "lib" / "user.ld"
        if user_ld.is_file():
            shutil.copy2(user_ld, lib_dir)

        # Clean build/test artifacts from bundle
        log.info("release: cleaning build and test artifacts")
        for p in bundle_dir.glob("test_*.py"):
            p.unlink()
        smoke = bundle_dir / "smoke_test_l2.py"
        smoke.unlink(missing_ok=True)
        for d in ("logs", "__pycache__"):
            p = bundle_dir / d
            if p.is_dir():
                shutil.rmtree(p)

        # Precompile .py to .pyc
        log.info("release: pre-compiling .pyc bytecode cache")
        host_python = self._host_python()
        if host_python:
            subprocess.run(
                [host_python, "-m", "compileall", "-q", str(lib_dir / "python3.12")],
                capture_output=True,
            )

        # Build and include ramfs image for standalone mode
        if mode == "standalone":
            mkramfs = sysroot / "bin" / mkramfs_binary()
            if not mkramfs.is_file():
                log.fatal(
                    f"{mkramfs_binary()} not found (required for standalone mode).",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z setup` first.",
                )
            log.info("release: validating ramfs image")
            try:
                # Install _boot.py into sysroot and validate the ramfs
                # (built earlier by ``./z build``; ``_ensure_ramfs``
                # never rebuilds and hard-fails if missing/stale).
                self._install_boot_script(sysroot)
                self._ensure_ramfs(sysroot)
                if self._ramfs_img and self._ramfs_img.is_file():
                    shutil.copy2(self._ramfs_img, bundle_dir / "nanvix_rootfs.img")
                else:
                    log.fatal(
                        "ramfs image not found after build.",
                        code=EXIT_BUILD_FAILURE,
                        hint="Ensure `./z build` completed successfully.",
                    )

                # Build multi-binary initrd with _boot.py as entry point
                log.info("release: building python3.initrd")
                initrd = self._ensure_initrd(sysroot)
                shutil.copy2(initrd, bundle_dir / "python3.initrd")

                # Create mnt/ directory for user workloads
                (bundle_dir / "mnt").mkdir(exist_ok=True)

            finally:
                self._cleanup_ramfs()
                self._cleanup_initrd()

        # README
        if mode == "standalone":
            cold_cmd = (
                f"./bin/{nanvixd_name} -ramfs nanvix_rootfs.img"
                f" -mount ./mnt -- python3.initrd"
            )
            readme_text = (
                f"# Nanvix Python Runtime\n\n"
                f"Platform: {platform_name}\n"
                f"Process mode: {mode}\n\n"
                f"## Quick Start (cold boot)\n\n"
                f"After extracting the archive, enter the directory and run:\n\n"
                f"```sh\n"
                f"cd {asset_prefix}\n"
                f"{cold_cmd}\n"
                f"```\n\n"
                f"On startup CPython executes `/mnt/bootstrap.py` if present,\n"
                f"otherwise it drops into an interactive REPL.\n\n"
                f"## Running Your Own Script\n\n"
                f"Place a `bootstrap.py` in a directory and mount it:\n\n"
                f"```sh\n"
                f"echo 'print(\"Hello from Nanvix!\")' > mnt/bootstrap.py\n"
                f"{cold_cmd}\n"
                f"```\n"
            )
        else:
            run_cmd = f"./bin/{nanvixd_name} -- ./bin/python3.12"
            readme_text = (
                f"# Nanvix Python Runtime\n\n"
                f"Platform: {platform_name}\n"
                f"Process mode: {mode}\n\n"
                f"## Quick Start\n\n"
                f"After extracting the archive, enter the directory and run:\n\n"
                f"```sh\n"
                f"cd {asset_prefix}\n"
                f"{run_cmd} script.py\n"
                f"```\n"
            )
        (bundle_dir / "README.md").write_text(readme_text)

        # Validate bundle
        log.info("release: validating bundle")
        required = [
            f"bin/{nanvixd_name}",
            "bin/kernel.elf",
            "bin/python3.12",
        ]
        if mode == "standalone":
            required.extend(
                [
                    "nanvix_rootfs.img",
                    "python3.initrd",
                ]
            )
        else:
            required.extend(
                [
                    "lib/python3.12/os.py",
                    "lib/python3.12/site.py",
                ]
            )
        if mode == "multi-process":
            required.extend(["bin/linuxd.elf", "bin/uservm.elf"])
        missing = [f for f in required if not (bundle_dir / f).is_file()]
        if missing:
            log.fatal(
                "bundle validation failed \u2014 missing files:\n"
                + "\n".join(f"  {f}" for f in missing),
                code=EXIT_BUILD_FAILURE,
            )
        log.success("release: validation passed")

        # Create archive (.zip on Windows, .tar.gz on non-Windows hosts)
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
                ["tar", "-czf", str(archive), "-C", str(bundle_root), asset_prefix],
                check=True,
            )
        shutil.rmtree(bundle_root)

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
