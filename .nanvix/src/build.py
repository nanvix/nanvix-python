# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Build lifecycle for the nanvix-python ZScript.

Owns ramfs/initrd construction, site-packages installation, the PIL shim,
the openpyxl lxml patch, and the standalone-mode Docker-based .pyc
pre-compilation pipeline.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from nanvix_zutil import log, make_initrd
from nanvix_zutil import paths
from nanvix_zutil.exitcodes import EXIT_BUILD_FAILURE, EXIT_MISSING_DEP
from nanvix_zutil.helpers import InitRdArgs
from nanvix_zutil.paths import nanvix_root, repo_root, test_out

from .lib import LibMixin, mkramfs_binary, nanvixd_binary


class BuildMixin(LibMixin):
    """``./z build`` \u2014 site-packages, ramfs, initrd."""

    # ------------------------------------------------------------------
    # Standalone / ramfs helpers
    # ------------------------------------------------------------------

    def _ramfs_input_hash(self, sysroot: Path) -> str:
        """Compute a hash representing the current ramfs inputs."""
        h = hashlib.sha256()

        # Factor in cpython version sentinel
        cpython_sentinel = sysroot / ".cpython-installed"
        if cpython_sentinel.is_file():
            h.update(cpython_sentinel.read_bytes())

        # Factor in site-packages sentinel
        site_sentinel = (
            sysroot / "lib" / "python3.12" / "site-packages" / ".nanvix-installed"
        )
        if site_sentinel.is_file():
            h.update(site_sentinel.read_bytes())

        # Factor in PIL shim sources
        pil_shim = repo_root() / "patches" / "PIL"
        if pil_shim.is_dir():
            for src in sorted(pil_shim.rglob("*.py")):
                h.update(src.read_bytes())

        # Factor in test scripts (kept in sync with `_stage_test_scripts`,
        # which stages `tests/func/test_*.py` plus `smoke_test_l2.py`).
        for src in sorted(sysroot.glob("smoke_test_l2.py")):
            h.update(src.read_bytes())
        for src in sorted(sysroot.glob("test_*.py")):
            h.update(src.read_bytes())

        # Factor in _boot.py entry point
        boot_script = sysroot / "_boot.py"
        if boot_script.is_file():
            h.update(boot_script.read_bytes())

        # Factor in the nanvix runtime package sources (copied into
        # sysroot/lib/python3.12/nanvix/ by _install_boot_script).  The
        # site-packages sentinel does not cover this tree.
        nanvix_pkg_src = repo_root() / "lib" / "nanvix"
        if nanvix_pkg_src.is_dir():
            for src in sorted(nanvix_pkg_src.rglob("*")):
                if src.is_file():
                    h.update(str(src.relative_to(nanvix_pkg_src)).encode())
                    h.update(src.read_bytes())

        return h.hexdigest()

    def _ensure_ramfs(self, sysroot: Path) -> Path:
        """Validate that an up-to-date ramfs image exists.

        Used by ``test``, ``release``, and ``benchmark``: never builds.
        Building the ramfs requires Docker (for .pyc pre-compilation)
        and is therefore confined to ``./z build`` via
        :meth:`_build_ramfs`.  A missing or stale image is fatal.
        """
        if self._ramfs_img and self._ramfs_img.is_file():
            return self._ramfs_img

        work_dir = test_out()
        img = work_dir / "nanvix_rootfs.img"
        sentinel = work_dir / ".ramfs-built"
        current_hash = self._ramfs_input_hash(sysroot)

        if not (
            img.is_file()
            and sentinel.is_file()
            and sentinel.read_text().strip() == current_hash
        ):
            log.fatal(
                "ramfs image missing or stale.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first (requires Docker).",
            )

        self._ramfs_img = img
        return img

    def _build_ramfs(self, sysroot: Path) -> Path:
        """Build (or reuse) a ramfs image for standalone mode.

        Only ``./z build`` may call this: it invokes Docker via
        :meth:`_precompile_pyc` and is the sole producer of the ramfs.
        """
        if self._ramfs_img and self._ramfs_img.is_file():
            return self._ramfs_img

        work_dir = test_out()
        img = work_dir / "nanvix_rootfs.img"
        sentinel = work_dir / ".ramfs-built"
        current_hash = self._ramfs_input_hash(sysroot)
        work_dir.mkdir(parents=True, exist_ok=True)

        # Skip rebuild if ramfs image and sentinel are up-to-date
        if (
            img.is_file()
            and sentinel.is_file()
            and sentinel.read_text().strip() == current_hash
        ):
            log.info("ramfs image already up-to-date, skipping rebuild")
            self._ramfs_img = img
            return img

        stripped = nanvix_root() / "stripped-sysroot"
        self._create_stripped_sysroot(sysroot, stripped)
        self._stripped_sysroot = stripped

        # Copy test scripts into the stripped sysroot
        stripped_root = stripped / "sysroot"
        for src in sysroot.glob("smoke_test_l2.py"):
            shutil.copy2(src, stripped_root)
        for src in sysroot.glob("test_*.py"):
            shutil.copy2(src, stripped_root)

        # _boot.pyc is compiled inside _create_stripped_sysroot via
        # Docker (Python 3.12) and placed at the sysroot root.

        # Generate build manifests for post-build inspection
        self._write_build_manifests(sysroot, stripped, nanvix_root())

        log.info("building ramfs image for standalone mode")
        mkramfs = str((sysroot / "bin" / mkramfs_binary()).resolve())
        subprocess.run(
            [mkramfs, "-o", str(img), str(stripped)],
            check=True,
        )
        sentinel.write_text(current_hash)
        self._ramfs_img = img
        return img

    def _write_build_manifests(
        self, sysroot: Path, stripped: Path, work_dir: Path
    ) -> None:
        """Write manifest files recording Python lib contents before/after stripping.

        Produces three files under .nanvix/manifests/ covering the
        lib/python3.12/ subtree (stdlib + site-packages):
          - sysroot-full.txt:    all files before stripping
          - sysroot-ramfs.txt:   all files that end up in the ramfs image
          - sysroot-trimmed.txt: files present in full but absent from ramfs

        All three use paths relative to the sysroot root (e.g.
        lib/python3.12/site-packages/foo.pyc) so they can be directly
        diffed and grepped as a consistent set.
        """
        manifests_dir = work_dir / "manifests"
        manifests_dir.mkdir(exist_ok=True)

        src_pylib = sysroot / "lib" / "python3.12"
        dst_root = stripped / "sysroot"

        # Collect file lists relative to the sysroot root (not pylib)
        # so all manifests share the same lib/python3.12/ prefix.
        full_files = sorted(
            str(f.relative_to(sysroot)) for f in src_pylib.rglob("*") if f.is_file()
        )
        ramfs_files = sorted(
            str(f.relative_to(dst_root)) for f in dst_root.rglob("*") if f.is_file()
        )

        # Compute trimmed as direct set difference (same path basis).
        trimmed = sorted(set(full_files) - set(ramfs_files))

        (manifests_dir / "sysroot-full.txt").write_text("\n".join(full_files) + "\n")
        (manifests_dir / "sysroot-ramfs.txt").write_text("\n".join(ramfs_files) + "\n")
        (manifests_dir / "sysroot-trimmed.txt").write_text("\n".join(trimmed) + "\n")

        log.info(
            f"build manifests: {len(full_files)} original, "
            f"{len(ramfs_files)} in ramfs, {len(trimmed)} trimmed"
        )

    def _create_stripped_sysroot(self, src: Path, dst: Path) -> None:
        """Create a stripped copy of the sysroot for standalone mode."""
        log.info("creating stripped sysroot for standalone mode")
        if dst.exists():
            shutil.rmtree(dst)

        root = dst / "sysroot"
        root.mkdir(parents=True)

        # Python stdlib + site-packages
        lib_dir = root / "lib"
        lib_dir.mkdir()
        src_pylib = src / "lib" / "python3.12"
        if src_pylib.is_dir():
            shutil.copytree(src_pylib, lib_dir / "python3.12")

        pylib = lib_dir / "python3.12"
        # Ensure platform-dependent library landmark exists for CPython
        # startup path resolution, even when no extension modules are shipped.
        platlib = pylib / "lib-dynload"
        platlib.mkdir(parents=True, exist_ok=True)

        # Remove development artifacts
        for name in (
            "config-3.12",
            "idlelib",
            "turtledemo",
            "ensurepip",
            "lib2to3",
            "tkinter",
            "pydoc_data",
        ):
            p = pylib / name
            if p.is_dir():
                shutil.rmtree(p)

        # Remove test directories
        for d in pylib.rglob("test"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        for d in pylib.rglob("tests"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

        # Remove heavy site-packages
        site_pkg = pylib / "site-packages"
        heavy_pkgs = [
            "plotly",
            "jupyterlab_plotly",
            "sympy",
            "nltk",
            "share",
            "textblob",
            "joblib",
        ]
        for pkg in heavy_pkgs:
            p = site_pkg / pkg
            if p.is_dir():
                shutil.rmtree(p)
            for di in site_pkg.glob(f"{pkg}-*.dist-info"):
                shutil.rmtree(di, ignore_errors=True)
            for di in site_pkg.glob(f"{pkg.replace('-', '_')}-*.dist-info"):
                shutil.rmtree(di, ignore_errors=True)

        # Remove build/packaging tools (not needed at runtime)
        build_pkgs = [
            "setuptools",
            "wheel",
            "pkg_resources",
            "_plotly_utils",
        ]
        for pkg in build_pkgs:
            p = site_pkg / pkg
            if p.is_dir():
                shutil.rmtree(p)
            for di in site_pkg.glob(f"{pkg}-*.dist-info"):
                shutil.rmtree(di, ignore_errors=True)
            for di in site_pkg.glob(f"{pkg.replace('-', '_')}-*.dist-info"):
                shutil.rmtree(di, ignore_errors=True)

        # Remove console script executables (unusable on Nanvix)
        bin_dir = site_pkg / "bin"
        if bin_dir.is_dir():
            shutil.rmtree(bin_dir)

        # Strip .dist-info to just METADATA (needed by importlib.metadata)
        for di in site_pkg.glob("*.dist-info"):
            metadata = di / "METADATA"
            if metadata.is_file():
                content = metadata.read_bytes()
                shutil.rmtree(di)
                di.mkdir()
                (di / "METADATA").write_bytes(content)
            else:
                shutil.rmtree(di, ignore_errors=True)

        # Remove __pycache__ directories (stale host-compiled bytecode)
        for d in root.rglob("__pycache__"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

        # Remove native/build source from site-packages
        for ext in ("*.pyx", "*.pxd", "*.c", "*.h", "*.cpp"):
            for f in site_pkg.rglob(ext):
                f.unlink(missing_ok=True)

        # Remove non-Python assets that are dead weight at runtime
        # - py.typed markers (type-checker only)
        # - .pyi stub files (type-checker only)
        # - pandoc test/JS files (unused bridge code)
        # - docutils theme assets (CSS/JS/ODT/RST)
        for f in pylib.rglob("py.typed"):
            f.unlink(missing_ok=True)
        for f in pylib.rglob("*.pyi"):
            f.unlink(missing_ok=True)
        pandoc_pkg = site_pkg / "pandoc"
        if pandoc_pkg.is_dir():
            for f in pandoc_pkg.iterdir():
                if f.suffix == ".md":
                    f.unlink(missing_ok=True)
            # Preserve utils.py source: ply uses function docstrings
            # for parser generation which -OO strips from .pyc files.
            pandoc_utils = pandoc_pkg / "utils.py"
            if pandoc_utils.is_file():
                pandoc_utils_backup = pandoc_pkg / "utils.py.keep"
                shutil.copy2(pandoc_utils, pandoc_utils_backup)
        docutils_pkg = site_pkg / "docutils"
        if docutils_pkg.is_dir():
            for ext in ("*.css", "*.js", "*.odt", "*.sty"):
                for f in docutils_pkg.rglob(ext):
                    f.unlink(missing_ok=True)

        # Pre-compile .py → .pyc using Docker toolchain (Python 3.12)
        # then strip .py sources so ramfs ships only bytecode.
        #
        # Place _boot.py inside pylib so it's compiled with the correct
        # Python 3.12 magic number (host Python may differ).  After
        # precompilation, move the resulting .pyc to the sysroot root.
        boot_src = repo_root() / "lib" / "nanvix" / "_boot.py"
        boot_in_pylib = pylib / "_boot.py"
        if boot_src.is_file():
            shutil.copy2(boot_src, boot_in_pylib)

        self._precompile_pyc(pylib)

        # Restore pandoc/utils.py source (ply needs docstrings at runtime)
        pandoc_utils_backup = pylib / "site-packages" / "pandoc" / "utils.py.keep"
        if pandoc_utils_backup.is_file():
            pandoc_utils_dst = pandoc_utils_backup.with_suffix("")
            shutil.move(str(pandoc_utils_backup), str(pandoc_utils_dst))

        # Move _boot.pyc from pylib to the sysroot root
        boot_pyc_in_pylib = pylib / "_boot.pyc"
        if boot_pyc_in_pylib.is_file():
            shutil.move(str(boot_pyc_in_pylib), str(root / "_boot.pyc"))

    def _precompile_pyc(self, pylib: Path) -> None:
        """Pre-compile .py to .pyc using Docker toolchain's Python 3.12.

        Uses ``compileall -b`` to write .pyc alongside sources, then
        removes .py files.  To avoid slow volume-mount I/O on Windows,
        the directory is tarred into the container and extracted back.

        Hard-fails if Docker is unavailable: the standalone ramfs ships
        .pyc-only contents (including ``/sysroot/_boot.pyc``), so a
        Docker-less build would produce an unusable image.  This is
        only reachable from ``./z build`` via :meth:`_build_ramfs`;
        ``test``/``release``/``benchmark`` go through
        :meth:`_ensure_ramfs` and never reach here.
        """
        _DOCKER_IMAGE = "ghcr.io/nanvix/toolchain-python:latest"

        if shutil.which("docker") is None:
            log.fatal(
                "Docker is required to build the standalone ramfs "
                "(needed to pre-compile _boot.pyc and the stdlib).",
                code=EXIT_MISSING_DEP,
                hint="Install Docker and rerun `./z build`.",
            )

        log.info("pre-compiling .py to .pyc via Docker (Python 3.12)")

        container_work = "/tmp/pylib"
        script = (
            f"mkdir -p {container_work} && "
            f"tar -xf - -C {container_work} && "
            f"python3 -O -m compileall -b -q {container_work} && "
            f"find {container_work} -name '*.py' -delete && "
            f"tar -cf - -C {container_work} ."
        )

        # Tar the pylib directory, pipe into a Docker container that
        # compiles in-place, then extract the result back.
        import io

        in_buf = io.BytesIO()
        with tarfile.open(fileobj=in_buf, mode="w") as tf:
            tf.add(str(pylib), arcname=".")
        in_bytes = in_buf.getvalue()

        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            _DOCKER_IMAGE,
            "sh",
            "-c",
            script,
        ]
        result = subprocess.run(
            cmd,
            input=in_bytes,
            capture_output=True,
        )
        if result.returncode != 0:
            log.fatal(
                "Docker compileall failed (rc="
                f"{result.returncode}): {result.stderr.decode(errors='replace').strip()}",
                code=EXIT_BUILD_FAILURE,
                hint="Inspect the Docker output above and rerun `./z build`.",
            )

        # Extract the compiled output back over pylib
        shutil.rmtree(pylib)
        pylib.mkdir(parents=True)
        out_buf = io.BytesIO(result.stdout)
        with tarfile.open(fileobj=out_buf, mode="r") as tf:
            tf.extractall(path=pylib, filter="data")

        # Validate that the entry-point bytecode was produced; without
        # it the standalone initrd cannot warm-start.
        if not (pylib / "_boot.pyc").is_file():
            log.fatal(
                "Docker compileall did not produce _boot.pyc",
                code=EXIT_BUILD_FAILURE,
                hint="Inspect the Docker output above and rerun `./z build`.",
            )

        count = sum(1 for _ in pylib.rglob("*.pyc"))
        log.info(f"pre-compiled {count} .pyc files (source .py removed)")

    def _cleanup_ramfs(self) -> None:
        """Remove intermediate ramfs build artifacts (keeps cached image)."""
        if self._stripped_sysroot and self._stripped_sysroot.is_dir():
            shutil.rmtree(self._stripped_sysroot, ignore_errors=True)
            self._stripped_sysroot = None

    # ------------------------------------------------------------------
    # Initrd / snapshot helpers
    # ------------------------------------------------------------------

    def _install_boot_script(self, sysroot: Path) -> None:
        """Install the nanvix package and _boot.py entry point into sysroot.

        Copies:
        - lib/nanvix/ → sysroot/lib/python3.12/nanvix/ (runtime package)
        - lib/nanvix/_boot.py → sysroot/_boot.py (initrd entry point)
        """
        nanvix_pkg_src = repo_root() / "lib" / "nanvix"
        if not nanvix_pkg_src.is_dir():
            log.fatal(
                "lib/nanvix/ not found.",
                code=EXIT_BUILD_FAILURE,
                hint="Ensure the repository is intact.",
            )

        # Install nanvix package into stdlib so 'import nanvix' works
        nanvix_pkg_dst = sysroot / "lib" / "python3.12" / "nanvix"
        if nanvix_pkg_dst.exists():
            shutil.rmtree(nanvix_pkg_dst)
        shutil.copytree(nanvix_pkg_src, nanvix_pkg_dst)

        # Place _boot.py at sysroot root as the initrd entry point
        boot_src = nanvix_pkg_src / "_boot.py"
        shutil.copy2(boot_src, sysroot / "_boot.py")

    def _ensure_initrd(self, sysroot: Path) -> Path:
        """Build or reuse the multi-binary initrd with _boot.py as entry point.

        The initrd bundles python3.12 + system daemons and uses the
        nanvix._boot warm-start protocol as entry point.
        """
        if self._initrd and self._initrd.is_file():
            return self._initrd

        initrd: Path = make_initrd(
            self,
            sysroot / "bin" / "python3.12",
            # Output goes to test_out() so the bundle's bin/ stays clean.
            test_out(),
            args=InitRdArgs(
                app_args=[
                    "-S",
                    "-O",
                    "-B",
                    "-X",
                    "frozen_modules=on",
                    "/sysroot/_boot.pyc",
                ],
                app_env=[
                    "PYTHONHOME=/sysroot",
                    "PYTHONPATH=/sysroot/lib/python3.12/site-packages",
                    "PYTHONDONTWRITEBYTECODE=1",
                ],
            ),
        )
        self._initrd = initrd
        return initrd

    def _cleanup_initrd(self) -> None:
        """Remove the cached initrd file."""
        if self._initrd and self._initrd.exists():
            self._initrd.unlink()
            self._initrd = None

    # ------------------------------------------------------------------
    # pip site-packages installer
    # ------------------------------------------------------------------

    def _install_site_packages(self, site_pkg: Path) -> None:
        """Install pip packages from requirements files into *site_pkg*."""
        pip_cmd = [sys.executable, "-m", "pip"]
        req_dir = repo_root() / "requirements"

        # Compute a combined hash of all requirements files so we can
        # skip a redundant pip install when nothing changed.
        sentinel = site_pkg / ".nanvix-installed"
        h = hashlib.sha256()
        req_paths: list[Path] = []
        for req_file in ("site-packages-base.txt", "site-packages-extra.txt"):
            req_path = req_dir / req_file
            if req_path.is_file():
                h.update(req_path.read_bytes())
                req_paths.append(req_path)
        req_hash = h.hexdigest()

        if sentinel.is_file() and sentinel.read_text().strip() == req_hash:
            log.info("site-packages already up-to-date, skipping pip install")
            return

        for req_path in req_paths:
            subprocess.run(
                [
                    *pip_cmd,
                    "install",
                    f"--target={site_pkg}",
                    "--no-deps",
                    "--no-compile",
                    "--quiet",
                    "-r",
                    str(req_path),
                ],
                check=True,
            )

        # Remove native .so/.pyd files (not usable on Nanvix)
        for ext in ("*.so", "*.pyd"):
            for f in site_pkg.rglob(ext):
                f.unlink(missing_ok=True)
        pth = site_pkg / "distutils-precedence.pth"
        pth.unlink(missing_ok=True)

        sentinel.write_text(req_hash)

    def _install_pil_shim(self, site_pkg: Path) -> None:
        """Copy the pure-Python PIL shim into site-packages.

        Replaces Pillow's C extension with lightweight header-only
        parsing that python-pptx needs for image handling.
        """
        pil_src = repo_root() / "patches" / "PIL"
        pil_dst = site_pkg / "PIL"
        if not pil_src.is_dir():
            log.warning("patches/PIL not found; skipping PIL shim installation")
            return
        if pil_dst.exists():
            shutil.rmtree(pil_dst)
        shutil.copytree(pil_src, pil_dst)
        log.info(f"installed PIL shim into {pil_dst}")

    def _patch_openpyxl_lxml(self, site_pkg: Path) -> None:
        """Disable lxml usage in openpyxl.

        The Nanvix lxml binary does not provide the full API (e.g.
        lxml.etree.xmlfile is missing).  Force openpyxl to use the
        pure-Python et_xmlfile fallback instead.
        """
        xml_init = site_pkg / "openpyxl" / "xml" / "__init__.py"
        if not xml_init.is_file():
            return
        content = xml_init.read_text()
        if "LXML = False" in content:
            return
        # Replace the dynamic lxml detection with a forced False
        patched = content.replace(
            "LXML = lxml_available() and lxml_env_set()",
            "LXML = False  # Nanvix: lxml lacks xmlfile; use et_xmlfile fallback",
        )
        if patched != content:
            xml_init.write_text(patched)
            log.info("patched openpyxl to disable lxml (missing xmlfile)")

    def _stage_test_scripts(self, sysroot: Path) -> None:
        """Copy test scripts from tests/ into the sysroot root."""
        tests_dir = repo_root() / "tests"
        smoke_test = tests_dir / "smoke_test_l2.py"
        if smoke_test.is_file():
            shutil.copy2(smoke_test, sysroot)
        for t in (tests_dir / "func").glob("test_*.py"):
            shutil.copy2(t, sysroot)

    def _stage_release(self) -> None:
        sysroot = self._sysroot_path()
        nanvixd_name = nanvixd_binary()
        mode = self.config.deployment_mode
        platform_name = self.config.machine
        asset_prefix = self._asset_prefix()
        # Stage under <asset_prefix>/ so the archive extracts into that dir.
        bundle_dir = paths.release_dir() / asset_prefix

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

        log.info(f"release: staging artifacts for {asset_prefix}")

        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
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
            # Copy rather than symlink: the archive packagers skip symlinks.
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

        # Validate staged bundle
        log.info("release: validating staged bundle")
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
        log.success("release: staging complete")

        # Expose ELF binaries in a visible directory so that CI artifact
        # upload globs (e.g. **/*.elf) can find them — hidden directories
        # like .nanvix/ are excluded by actions/upload-artifact by default.
        elf_out = repo_root() / "elf-binaries"
        if elf_out.exists():
            shutil.rmtree(elf_out)
        elf_out.mkdir()
        for elf in (sysroot / "bin").glob("*.elf"):
            shutil.copy2(elf, elf_out)

    # ------------------------------------------------------------------
    # Lifecycle entry point
    # ------------------------------------------------------------------

    def build(self) -> None:
        """Install pure Python packages and generate ramfs from pre-built sysroot."""
        sysroot = self._sysroot_path()

        if not (sysroot / "bin" / "python3.12").is_file():
            log.fatal(
                "python3.12 not found in sysroot.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the pre-built buildroot.",
            )

        log.info("installing pure Python packages")
        site_pkg = sysroot / "lib" / "python3.12" / "site-packages"
        site_pkg.mkdir(parents=True, exist_ok=True)
        self._install_site_packages(site_pkg)

        # PIL shim (pure-Python Pillow replacement for python-pptx)
        self._install_pil_shim(site_pkg)

        # Patch openpyxl to use et_xmlfile instead of lxml.etree.xmlfile
        self._patch_openpyxl_lxml(site_pkg)

        # Install _boot.py warm-start entry point into sysroot root
        self._install_boot_script(sysroot)

        # Stage test scripts into the sysroot so they are included in
        # the ramfs and contribute to its input hash. ``./z test``
        # re-copies the same files; the hash matches so the ramfs is
        # reused without rebuilding (and without invoking Docker).
        self._stage_test_scripts(sysroot)

        if self.config.deployment_mode == "standalone":
            self._build_ramfs(sysroot)

            # Build the multi-binary initrd with _boot.py as entry point
            self._ensure_initrd(sysroot)

        self._stage_release()

        log.success("build complete")
