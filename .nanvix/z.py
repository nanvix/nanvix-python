# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for the nanvix-python distribution.

Consumes a pre-built CPython 3.12 buildroot release artifact, installs
pure Python pip packages, and generates a custom ramfs image for the
Nanvix microkernel.

Usage:
    ./z setup     # Download Nanvix sysroot and pre-built CPython buildroot
    ./z build     # Install pip packages and generate ramfs
    ./z test      # Run smoke test and functional tests
    ./z release   # Package standalone runtime bundle
    ./z clean     # Remove build artifacts
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


from nanvix_zutil import (
    CFG_SYSROOT,
    TOOLCHAIN_CONTAINER_PATH,
    ZScript,
    log,
    make_initrd,
)
from nanvix_zutil import paths
from nanvix_zutil.exitcodes import (
    EXIT_BUILD_FAILURE,
    EXIT_MISSING_DEP,
    EXIT_TEST_FAILURE,
)
from nanvix_zutil.github import download_release_asset, resolve_release
from nanvix_zutil.helpers import InitRdArgs
from nanvix_zutil.paths import nanvix_root, repo_root

# Per-test timeout in seconds (overridable via TIMEOUT_SECONDS env var).
_DEFAULT_TIMEOUT = 300

# CPython startup warning emitted when lib-dynload cannot be resolved.
# Keep this in sync with CPython's warning text in Modules/getpath.py.
_PLATLIB_WARNING_RE = re.compile(
    r"\bcould not find platform dependent libraries\b", re.I
)

# Platform detection
_IS_WINDOWS = sys.platform == "win32"


def _nanvixd_binary() -> str:
    """Return the nanvixd binary name for the current host platform."""
    return "nanvixd.exe" if _IS_WINDOWS else "nanvixd.elf"


def _mkramfs_binary() -> str:
    """Return the mkramfs binary name for the current host platform."""
    return "mkramfs.exe" if _IS_WINDOWS else "mkramfs.elf"


class NanvixPythonBuild(ZScript):
    """Build script for the nanvix-python distribution."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sysroot_path(self) -> Path:
        """Return the resolved host sysroot path."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        return Path(sysroot)

    def _toolchain_str(self) -> str:
        """Return the raw host toolchain root path as a string."""
        return str(TOOLCHAIN_CONTAINER_PATH)

    def _host_python(self) -> str | None:
        """Find a usable host Python interpreter."""
        toolchain = self._toolchain_str()
        toolchain_python = Path(toolchain) / "bin" / "python3"
        if toolchain_python.is_file():
            return str(toolchain_python)
        for name in ("python3", "python"):
            if shutil.which(name):
                return name
        return None

    def _ensure_python_in_repo_root(self, sysroot: Path) -> None:
        """Copy python3.12 to repo_root for make_initrd if not already present."""
        repo_python = repo_root() / "python3.12"
        if repo_python.exists():
            return
        python_bin = sysroot / "bin" / "python3.12"
        shutil.copy2(python_bin, repo_python)

    def _cleanup_python_in_repo_root(self) -> None:
        """Remove the python3.12 copy from repo_root."""
        repo_python = repo_root() / "python3.12"
        repo_python.unlink(missing_ok=True)

    def _nanvix_run(
        self,
        sysroot: Path,
        script_path: str,
        log_file: Path,
        *,
        timeout: int | None = None,
    ) -> None:
        """Run a Python script under nanvixd using the _boot.py warm-start protocol.

        Uses nanvixd.exe on Windows and nanvixd.elf on Linux/macOS.
        Captures output to *log_file*.  Does NOT raise on non-zero exit
        (the caller inspects the log for PASS/FAIL).

        In standalone mode, uses the cached initrd (with _boot.py entry
        point) and communicates the script to run via a mounted directory
        containing an argv.txt file.
        """
        if timeout is None:
            timeout = int(os.environ.get("TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT)))

        deployment = self.config.deployment_mode
        nanvixd = str((sysroot / "bin" / _nanvixd_binary()).resolve())

        cmd: list[str]
        if deployment == "standalone":
            if not self._ramfs_img or not self._ramfs_img.is_file():
                log.fatal(
                    "ramfs image not found.",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z build` first.",
                )
            initrd = self._ensure_initrd(sysroot)

            # Create a temp mount directory with argv.txt pointing to
            # the script inside the ramfs sysroot.
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
            cmd = [
                nanvixd,
                "--",
                f"./bin/python3.12",
                f"./{script_path}",
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

    # -- Standalone / ramfs helpers ----------------------------------------

    _ramfs_img: Path | None = None
    _stripped_sysroot: Path | None = None
    _initrd: Path | None = None

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

        work_dir = nanvix_root()
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

        work_dir = nanvix_root()
        img = work_dir / "nanvix_rootfs.img"
        sentinel = work_dir / ".ramfs-built"
        current_hash = self._ramfs_input_hash(sysroot)

        # Skip rebuild if ramfs image and sentinel are up-to-date
        if (
            img.is_file()
            and sentinel.is_file()
            and sentinel.read_text().strip() == current_hash
        ):
            log.info("ramfs image already up-to-date, skipping rebuild")
            self._ramfs_img = img
            return img

        stripped = work_dir / "stripped-sysroot"
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
        self._write_build_manifests(sysroot, stripped, work_dir)

        log.info("building ramfs image for standalone mode")
        mkramfs = str((sysroot / "bin" / _mkramfs_binary()).resolve())
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

        # Tar the pylib directory, pipe into a Docker container that
        # compiles in-place, then extract the result back.
        container_work = "/tmp/pylib"
        script = (
            f"mkdir -p {container_work} && "
            f"tar -xf - -C {container_work} && "
            f"python3 -O -m compileall -b -q {container_work} && "
            f"find {container_work} -name '*.py' -delete && "
            f"tar -cf - -C {container_work} ."
        )

        # Create input tar from pylib
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

    # -- Initrd / snapshot helpers -----------------------------------------

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

        self._ensure_python_in_repo_root(sysroot)
        initrd: Path = make_initrd(
            self,
            "python3.12",
            test=False,
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

    # -- pip site-packages installer ----------------------------------------

    def _install_site_packages(self, site_pkg: Path) -> None:
        """Install pip packages from requirements files into *site_pkg*."""
        pip_cmd: list[str] | None = None
        toolchain = self._toolchain_str()

        if shutil.which("pip3"):
            pip_cmd = ["pip3"]
        elif Path(toolchain, "bin", "pip3").is_file():
            pip_cmd = [str(Path(toolchain, "bin", "pip3"))]
        elif shutil.which("python3"):
            pip_cmd = ["python3", "-m", "pip"]
        elif shutil.which("python"):
            pip_cmd = ["python", "-m", "pip"]
        elif Path(toolchain, "bin", "python3").is_file():
            pip_cmd = [str(Path(toolchain, "bin", "python3")), "-m", "pip"]
        else:
            log.warning("pip not found; skipping site-packages installation")
            return

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
                capture_output=True,
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

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def setup(self) -> bool:
        """Download sysroot and pre-built CPython buildroot.

        The base ``super().setup()`` downloads the Nanvix sysroot and
        resolves dependencies declared in ``nanvix.toml``.  Then we
        download the pre-built CPython release artifact and extract the
        interpreter binary and standard library into the sysroot.
        """
        result = super().setup()

        sysroot = self._sysroot_path()

        # Download and install pre-built CPython into sysroot
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

        # Check if already installed
        sentinel = sysroot / ".cpython-installed"
        if sentinel.is_file() and sentinel.read_text().strip() == version_specifier:
            log.info("CPython already installed, skipping")
            return

        log.info(f"downloading pre-built CPython ({asset_name})")

        # Resolve release
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

        # Extract CPython into sysroot
        log.info("extracting CPython into sysroot")
        with tarfile.open(asset_path, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue

                # bin/python.elf → sysroot/bin/python3.12
                if member.name == "bin/python.elf":
                    member.name = "bin/python3.12"
                    tf.extract(member, path=sysroot, filter="data")
                # sysroot/lib/python3.12/* → sysroot/lib/python3.12/*
                elif member.name.startswith("sysroot/lib/python3.12/"):
                    # Strip leading "sysroot/" prefix
                    member.name = member.name.removeprefix("sysroot/")
                    tf.extract(member, path=sysroot, filter="data")

        sentinel.write_text(version_specifier)
        log.success("CPython installed into sysroot")

    def build(self) -> None:
        """Install pure Python packages and generate ramfs from pre-built sysroot."""
        sysroot = self._sysroot_path()

        # Verify the pre-built CPython binary is present in the sysroot
        if not (sysroot / "bin" / "python3.12").is_file():
            log.fatal(
                "python3.12 not found in sysroot.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the pre-built buildroot.",
            )

        # Install pure Python packages
        log.info("installing pure Python packages")
        site_pkg = sysroot / "lib" / "python3.12" / "site-packages"
        site_pkg.mkdir(parents=True, exist_ok=True)
        self._install_site_packages(site_pkg)

        # Install PIL shim (pure-Python Pillow replacement for python-pptx)
        self._install_pil_shim(site_pkg)

        # Patch openpyxl to use et_xmlfile instead of lxml.etree.xmlfile
        self._patch_openpyxl_lxml(site_pkg)

        # Install _boot.py warm-start entry point into sysroot root
        self._install_boot_script(sysroot)

        # Stage test scripts into the sysroot so they are included in
        # the ramfs and contribute to its input hash.  ``./z test``
        # re-copies the same files; the hash matches so the ramfs is
        # reused without rebuilding (and without invoking Docker).
        self._stage_test_scripts(sysroot)

        # Build ramfs image for standalone deployment
        if self.config.deployment_mode == "standalone":
            self._build_ramfs(sysroot)

            # Build the multi-binary initrd with _boot.py as entry point
            self._ensure_initrd(sysroot)

        log.success("build complete")

    def _stage_test_scripts(self, sysroot: Path) -> None:
        """Copy test scripts from tests/ into the sysroot root."""
        tests_dir = repo_root() / "tests"
        smoke_test = tests_dir / "smoke_test_l2.py"
        if smoke_test.is_file():
            shutil.copy2(smoke_test, sysroot)
        for t in (tests_dir / "func").glob("test_*.py"):
            shutil.copy2(t, sysroot)

    def test(self) -> None:
        """Run smoke and functional tests.

        Without targets, runs both smoke and functional tests.
        Pass targets after ``--`` to select:
          ``./z test -- test-smoke``       — smoke test only
          ``./z test -- test-integration`` — functional tests only
        """
        sysroot = self._sysroot_path()

        nanvixd = sysroot / "bin" / _nanvixd_binary()
        if not nanvixd.is_file():
            log.fatal(
                f"{_nanvixd_binary()} not found in sysroot.",
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
            mkramfs = sysroot / "bin" / _mkramfs_binary()
            if not mkramfs.is_file():
                log.fatal(
                    f"{_mkramfs_binary()} not found (required for standalone mode).",
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

            prebuilt = os.environ.get("NANVIX_PREBUILT_RAMFS")
            if prebuilt:
                p = Path(prebuilt)
                if not p.is_file():
                    log.fatal(
                        f"NANVIX_PREBUILT_RAMFS points to non-existent file: {p}",
                        code=EXIT_MISSING_DEP,
                    )
                log.info(f"using pre-built ramfs: {p}")
                self._ramfs_img = p
            else:
                self._ensure_ramfs(sysroot)

        # Standalone exclusions
        exclude_tests = os.environ.get("EXCLUDE_TESTS", "")
        if deployment == "standalone" and not exclude_tests:
            # Stripped from standalone ramfs: plotly(83), setuptools(89), wheel(90)
            exclude_tests = "83 89 90"

        # Determine which tests to run
        default_targets = {"test-smoke", "test-integration"}
        if deployment == "standalone" and _IS_WINDOWS:
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
            self._cleanup_python_in_repo_root()

    def _run_smoke_test(self, sysroot: Path) -> None:
        """Run the layer-2 smoke test."""
        log.info("=== smoke test ===")
        tmp = Path(tempfile.gettempdir())
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

        # 2) Wait for vmem size to stabilize (kernel may still be
        #    flushing the memory image after cbor appears).  Keep
        #    waiting even if the process has already exited — the OS
        #    may still be flushing buffered writes.
        last_size = -1
        stable_since: float | None = None
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
        if not _IS_WINDOWS:
            log.info("snapshot smoke test: skipped (Windows-only / WHP)")
            return
        if self.config.deployment_mode != "standalone":
            log.info("snapshot smoke test: skipped (standalone-only)")
            return
        if not self._ramfs_img or not self._ramfs_img.is_file():
            log.fatal(
                "ramfs image not found (required for snapshot smoke test).",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        log.info("=== snapshot smoke test ===")
        initrd = self._ensure_initrd(sysroot)
        nanvixd = str((sysroot / "bin" / _nanvixd_binary()).resolve())
        timeout = int(os.environ.get("TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT)))

        snapshots_dir = sysroot / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        vmem = snapshots_dir / "kernel.vmem"
        cbor = snapshots_dir / "kernel.whp.cbor"
        vmem.unlink(missing_ok=True)
        cbor.unlink(missing_ok=True)

        tmp = Path(tempfile.gettempdir())

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
        mount_dir = Path(tempfile.mkdtemp(prefix="nanvix-snap-smoke-"))
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

        # Precompile stdlib and tests
        host_python = self._host_python()
        if host_python:
            subprocess.run(
                [
                    host_python,
                    "-m",
                    "compileall",
                    "-q",
                    str(sysroot / "lib" / "python3.12"),
                ],
                capture_output=True,
            )
            for t in sysroot.glob("test_*.py"):
                subprocess.run(
                    [host_python, "-m", "py_compile", str(t)],
                    capture_output=True,
                )

        tmp = Path(tempfile.gettempdir())
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

    def benchmark(self) -> None:
        """Run a hello-world command and report total execution time."""
        sysroot = self._sysroot_path()

        nanvixd = sysroot / "bin" / _nanvixd_binary()
        if not nanvixd.is_file():
            log.fatal(
                f"{_nanvixd_binary()} not found in sysroot.",
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
        timeout = int(os.environ.get("TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT)))

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
            self._cleanup_python_in_repo_root()

        if "hello" not in output:
            print(output)
            log.fatal(
                "benchmark failed: expected output not found", code=EXIT_BUILD_FAILURE
            )

        print(f"Execution time: {elapsed:.3f}s")
        log.success("benchmark complete")

    def clean(self) -> None:
        """Remove build artifacts."""
        # Clean release assets
        dist_dir = paths.dist_dir()
        if dist_dir.is_dir():
            shutil.rmtree(dist_dir)
        release_dir = repo_root() / "release-assets"
        if release_dir.is_dir():
            shutil.rmtree(release_dir)

        # Clean ramfs artifacts
        self._cleanup_ramfs()
        ramfs_img = nanvix_root() / "nanvix_rootfs.img"
        ramfs_img.unlink(missing_ok=True)
        ramfs_sentinel = nanvix_root() / ".ramfs-built"
        ramfs_sentinel.unlink(missing_ok=True)

        # Clean initrd
        self._cleanup_initrd()

        # Clean snapshot artifacts produced by the snapshot smoke test
        sysroot_str = self.config.get(CFG_SYSROOT, "")
        if sysroot_str:
            snapshots_dir = Path(sysroot_str) / "snapshots"
            if snapshots_dir.is_dir():
                shutil.rmtree(snapshots_dir)

        # Clean python3.12 copy used by make_initrd
        self._cleanup_python_in_repo_root()

        log.success("clean complete")


if __name__ == "__main__":
    NanvixPythonBuild.main()
