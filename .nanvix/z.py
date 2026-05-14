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
import zipfile
from pathlib import Path

from nanvix_zutil import (
    CFG_SYSROOT,
    CFG_TOOLCHAIN,
    ZScript,
    log,
)
from nanvix_zutil.docker import docker_available
from nanvix_zutil.exitcodes import (
    EXIT_BUILD_FAILURE,
    EXIT_MISSING_DEP,
    EXIT_TEST_FAILURE,
)
from nanvix_zutil.github import download_release_asset, resolve_release

# Per-test timeout in seconds (overridable via TIMEOUT_SECONDS env var).
_DEFAULT_TIMEOUT = 300

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
        return self.config.get(CFG_TOOLCHAIN, "/opt/nanvix") or "/opt/nanvix"

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

    def _nanvix_run(
        self,
        sysroot: Path,
        script_path: str,
        log_file: Path,
        *,
        timeout: int | None = None,
    ) -> None:
        """Run a Python script under nanvixd.

        Uses nanvixd.exe on Windows and nanvixd.elf on Linux/macOS.
        Captures output to *log_file*.  Does NOT raise on non-zero exit
        (the caller inspects the log for PASS/FAIL).
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
            cmd = [
                nanvixd,
                "-bin-dir",
                str((sysroot / "bin").resolve()),
                "-ramfs",
                str(self._ramfs_img),
                "--",
                f"./bin/python3.12",
                f"-B /sysroot/{script_path};PYTHONHOME=/sysroot PYTHONDONTWRITEBYTECODE=1",
            ]
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

        # Factor in all patch/shim sources (PIL, numpy, pandas, etc.)
        patches_dir = self.repo_root / "patches"
        if patches_dir.is_dir():
            for src in sorted(patches_dir.rglob("*.py")):
                h.update(src.read_bytes())

        # Factor in test scripts
        for src in sorted(sysroot.glob("smoke_test_l2.py")):
            h.update(src.read_bytes())
        for src in sorted(sysroot.glob("test_[0-9]*.py")):
            h.update(src.read_bytes())

        return h.hexdigest()

    def _ensure_ramfs(self, sysroot: Path) -> Path:
        """Build (or reuse) a ramfs image for standalone mode."""
        if self._ramfs_img and self._ramfs_img.is_file():
            return self._ramfs_img

        work_dir = self.nanvix_dir
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
        docutils_pkg = site_pkg / "docutils"
        if docutils_pkg.is_dir():
            for ext in ("*.css", "*.js", "*.odt", "*.sty"):
                for f in docutils_pkg.rglob(ext):
                    f.unlink(missing_ok=True)

        # Pre-compile .py → .pyc using Docker toolchain (Python 3.12)
        # then strip .py sources so ramfs ships only bytecode.
        self._precompile_pyc(pylib)

    def _precompile_pyc(self, pylib: Path) -> None:
        """Pre-compile .py to .pyc using Docker toolchain's Python 3.12.

        Uses ``compileall -b`` to write .pyc alongside sources, then
        removes .py files.  To avoid slow volume-mount I/O on Windows,
        the directory is tarred into the container and extracted back.
        Falls back to skipping if Docker is not available.
        """
        _DOCKER_IMAGE = "ghcr.io/nanvix/toolchain-python:latest"

        if not docker_available():
            log.warning("Docker not available; skipping .pyc pre-compilation")
            return

        log.info("pre-compiling .py to .pyc via Docker (Python 3.12)")

        # Tar the pylib directory, pipe into a Docker container that
        # compiles in-place, then extract the result back.
        container_work = "/tmp/pylib"
        script = (
            f"mkdir -p {container_work} && "
            f"tar -xf - -C {container_work} && "
            f"python3 -m compileall -b -q {container_work} && "
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
            log.warning(f"Docker compileall failed: {result.stderr.decode().strip()}")
            return

        # Extract the compiled output back over pylib
        shutil.rmtree(pylib)
        pylib.mkdir(parents=True)
        out_buf = io.BytesIO(result.stdout)
        with tarfile.open(fileobj=out_buf, mode="r") as tf:
            tf.extractall(path=pylib, filter="data")

        count = sum(1 for _ in pylib.rglob("*.pyc"))
        log.info(f"pre-compiled {count} .pyc files (source .py removed)")

    def _cleanup_ramfs(self) -> None:
        """Remove intermediate ramfs build artifacts (keeps cached image)."""
        if self._stripped_sysroot and self._stripped_sysroot.is_dir():
            shutil.rmtree(self._stripped_sysroot, ignore_errors=True)
            self._stripped_sysroot = None

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

        req_dir = self.repo_root / "requirements"

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
        """Copy all pure-Python shim packages from patches/ into site-packages.

        Each first-level directory under patches/ (PIL, numpy, pandas, etc.)
        is treated as a shim package that replaces a C extension dependency
        with a lightweight pure-Python stub.
        """
        patches_dir = self.repo_root / "patches"
        if not patches_dir.is_dir():
            log.warning("patches/ not found; skipping shim installation")
            return
        for shim_src in sorted(patches_dir.iterdir()):
            if not shim_src.is_dir() or shim_src.name.startswith("."):
                continue
            shim_dst = site_pkg / shim_src.name
            if shim_dst.exists():
                shutil.rmtree(shim_dst)
            shutil.copytree(shim_src, shim_dst)
            log.info(f"installed {shim_src.name} shim into {shim_dst}")

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

    def _install_lxml_python(self, site_pkg: Path) -> None:
        """Copy lxml Python wrapper files into site-packages.

        The lxml C extensions (_lxml_etree, _lxml_elementpath) are statically
        linked into the CPython interpreter.  The Python wrapper files that
        make ``import lxml.etree`` work live in the cpython buildroot at
        ``.nanvix/buildroot/python-packages/lxml/``.  This method copies
        them and writes a thin ``etree.py`` shim that bridges from the
        built-in C module name to the ``lxml.etree`` import path.
        """
        # Try to locate lxml Python files from the cpython buildroot
        cpython_lxml = (
            self.repo_root.parent
            / "usr"
            / "bin"
            / "cpython"
            / ".nanvix"
            / "buildroot"
            / "python-packages"
            / "lxml"
        )
        if not cpython_lxml.is_dir():
            log.warning(
                f"lxml Python files not found at {cpython_lxml}; "
                "lxml.etree will not be available"
            )
            return

        dst = site_pkg / "lxml"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cpython_lxml, dst)

        # Write the etree.py shim bridging _lxml_etree → lxml.etree
        etree_shim = dst / "etree.py"
        etree_shim.write_text(
            "from _lxml_etree import *\n"
            "from _lxml_etree import _Element, _ElementTree, "
            "_Comment, _ProcessingInstruction, ElementBase, QName, _Attrib\n"
            "from _lxml_etree import xmlfile, htmlfile\n",
            encoding="utf-8",
        )

        # Write _elementpath.py shim if not already present
        epath_shim = dst / "_elementpath.py"
        if not epath_shim.exists() or epath_shim.stat().st_size < 10:
            epath_shim.write_text(
                "from _lxml_elementpath import *\n",
                encoding="utf-8",
            )

        log.info(f"installed lxml Python wrappers from {cpython_lxml}")

    def _install_rapidfuzz_python(self, site_pkg: Path) -> None:
        """Copy rapidfuzz Python wrapper files into site-packages.

        The rapidfuzz C++ extensions (_rf_utils_cpp, _rf_fuzz_cpp, etc.)
        are statically linked into the CPython interpreter.  The Python
        files that make ``import rapidfuzz`` work live in the cpython
        buildroot at ``.nanvix/buildroot/python-packages/rapidfuzz/``.
        This method copies them and writes thin Python shims that bridge
        from the flat built-in module names to the expected import paths.
        """
        cpython_rf = (
            self.repo_root.parent
            / "usr"
            / "bin"
            / "cpython"
            / ".nanvix"
            / "buildroot"
            / "python-packages"
            / "rapidfuzz"
        )
        if not cpython_rf.is_dir():
            log.warning(
                f"rapidfuzz Python files not found at {cpython_rf}; "
                "rapidfuzz C++ extensions will not be available"
            )
            return

        dst = site_pkg / "rapidfuzz"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cpython_rf, dst)

        # Write Python shims bridging flat builtin names to package paths
        for name, src in {
            "utils_cpp.py": "from _rf_utils_cpp import *\n",
            "fuzz_cpp.py": "from _rf_fuzz_cpp import *\n",
            "fuzz_cpp_sse2.py": "from _rf_fuzz_cpp_sse2 import *\n",
            "_feature_detector_cpp.py": "from _rf_feature_detector_cpp import *\n",
        }.items():
            (dst / name).write_text(src, encoding="utf-8")

        dist_dir = dst / "distance"
        dist_dir.mkdir(exist_ok=True)
        for name, src in {
            "_initialize_cpp.py": "from _rf_dist_initialize_cpp import *\n",
            "metrics_cpp.py": "from _rf_dist_metrics_cpp import *\n",
            "metrics_cpp_sse2.py": "from _rf_dist_metrics_cpp_sse2 import *\n",
        }.items():
            (dist_dir / name).write_text(src, encoding="utf-8")

        log.info(f"installed rapidfuzz Python wrappers from {cpython_rf}")

    def _install_wordcloud_python(self, site_pkg: Path) -> None:
        """Copy wordcloud Python files into site-packages.

        The wordcloud Cython extension (_wc_query_integral_image) is
        statically linked into CPython.  This copies the Python files
        and writes a shim for the native module.
        """
        cpython_wc = (
            self.repo_root.parent
            / "usr"
            / "bin"
            / "cpython"
            / ".nanvix"
            / "buildroot"
            / "python-packages"
            / "wordcloud"
        )
        if not cpython_wc.is_dir():
            log.warning(
                f"wordcloud Python files not found at {cpython_wc}; "
                "wordcloud C extension will not be available"
            )
            return

        dst = site_pkg / "wordcloud"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cpython_wc, dst)

        # Write Python shim with fallback for when numpy shim lacks buffer protocol
        (dst / "query_integral_image.py").write_text(
            '''"""Bridge to native C extension with pure-Python fallback."""
try:
    from _wc_query_integral_image import query_integral_image as _c_impl
except ImportError:
    _c_impl = None


def query_integral_image(integral_image, size_x, size_y, random_state):
    """Query integral image for free rectangles.

    Uses the native C extension when numpy arrays support the buffer
    protocol (i.e. real numpy).  Falls back to pure Python otherwise.
    """
    if _c_impl is not None:
        try:
            return _c_impl(integral_image, size_x, size_y, random_state)
        except TypeError:
            pass  # ndarray shim — fall through to Python impl

    # Pure-Python fallback
    x = integral_image.shape[0]
    y = integral_image.shape[1]
    hits = 0
    for i in range(x - size_x):
        for j in range(y - size_y):
            area = (integral_image[i, j] + integral_image[i + size_x, j + size_y]
                    - integral_image[i + size_x, j] - integral_image[i, j + size_y])
            if not area:
                hits += 1
    if not hits:
        return None
    goal = random_state.randint(0, hits)
    hits = 0
    for i in range(x - size_x):
        for j in range(y - size_y):
            area = (integral_image[i, j] + integral_image[i + size_x, j + size_y]
                    - integral_image[i + size_x, j] - integral_image[i, j + size_y])
            if not area:
                hits += 1
                if hits == goal:
                    return i, j
''',
            encoding="utf-8",
        )

        log.info(f"installed wordcloud Python wrappers from {cpython_wc}")

    def _install_pillow_python(self, site_pkg: Path) -> None:
        """Copy real Pillow Python files into site-packages.

        The Pillow C extensions (_pil_imaging, _pil_imagingmath,
        _pil_imagingmorph) are statically linked into CPython.  This
        copies the real Pillow Python files and writes shim modules.
        """
        cpython_pil = (
            self.repo_root.parent
            / "usr"
            / "bin"
            / "cpython"
            / ".nanvix"
            / "buildroot"
            / "python-packages"
            / "PIL"
        )
        if not cpython_pil.is_dir():
            log.warning(
                f"Pillow Python files not found at {cpython_pil}; "
                "Pillow C extensions will not be available"
            )
            return

        dst = site_pkg / "PIL"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cpython_pil, dst)

        # Write Python shims bridging flat builtin names to package paths
        (dst / "_imaging.py").write_text(
            "from _pil_imaging import *\n",
            encoding="utf-8",
        )
        (dst / "_imagingmath.py").write_text(
            "from _pil_imagingmath import *\n",
            encoding="utf-8",
        )
        (dst / "_imagingmorph.py").write_text(
            "from _pil_imagingmorph import *\n",
            encoding="utf-8",
        )

        log.info(f"installed Pillow Python wrappers from {cpython_pil}")

    def _install_numpy_python(self, site_pkg: Path) -> None:
        """Copy real NumPy Python files into site-packages.

        The NumPy _multiarray_umath C extension is statically linked
        into CPython as _np_multiarray_umath.  This copies the Python
        package and writes a bridge shim at numpy/core/_multiarray_umath.py.
        """
        cpython_np = (
            self.repo_root.parent
            / "usr"
            / "bin"
            / "cpython"
            / ".nanvix"
            / "buildroot"
            / "python-packages"
            / "numpy"
        )
        if not cpython_np.is_dir():
            log.warning(
                f"NumPy Python files not found at {cpython_np}; "
                "NumPy C extension will not be available"
            )
            return

        dst = site_pkg / "numpy"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cpython_np, dst)

        # The bridge shim should already be in place from the buildroot copy

        log.info(f"installed NumPy Python wrappers from {cpython_np}")

    def _install_pandas_python(self, site_pkg: Path) -> None:
        """Copy real pandas Python files into site-packages.

        The pandas C extensions (45 modules) are statically linked into
        CPython as _pd_* builtins.  This copies the Python package with
        bridge shims that redirect imports to the flat builtins.
        """
        cpython_pd = (
            self.repo_root.parent
            / "usr"
            / "bin"
            / "cpython"
            / ".nanvix"
            / "buildroot"
            / "python-packages"
            / "pandas"
        )
        if not cpython_pd.is_dir():
            log.warning(
                f"pandas Python files not found at {cpython_pd}; "
                "pandas C extensions will not be available"
            )
            return

        dst = site_pkg / "pandas"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cpython_pd, dst)

        log.info(f"installed pandas Python wrappers from {cpython_pd}")

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
        cache_dir = self.nanvix_dir / "cache"

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
            gh_token=self.config.get("NANVIX_GH_TOKEN"),
        )

        asset_path = download_release_asset(
            repo="nanvix/cpython",
            version_specifier=version_specifier,
            asset_name=asset_name,
            dest=cache_dir,
            gh_token=self.config.get("NANVIX_GH_TOKEN"),
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

        # Install lxml Python wrappers (C extensions are in the interpreter)
        self._install_lxml_python(site_pkg)

        # Install rapidfuzz Python wrappers (C++ extensions in interpreter)
        self._install_rapidfuzz_python(site_pkg)

        # Install wordcloud Python wrappers (Cython extension in interpreter)
        self._install_wordcloud_python(site_pkg)

        # Install real Pillow Python files (C extensions in interpreter)
        # This overwrites the PIL shim installed above
        self._install_pillow_python(site_pkg)

        # Install numpy Python files (C extension in interpreter)
        self._install_numpy_python(site_pkg)

        # Install pandas Python files (C extensions in interpreter)
        self._install_pandas_python(site_pkg)

        # Build ramfs image for standalone deployment
        if self.config.deployment_mode == "standalone":
            self._ensure_ramfs(sysroot)

        log.success("build complete")

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
        self._install_lxml_python(site_pkg)
        self._install_rapidfuzz_python(site_pkg)
        self._install_wordcloud_python(site_pkg)
        self._install_pillow_python(site_pkg)
        self._install_numpy_python(site_pkg)
        self._install_pandas_python(site_pkg)

        # Copy test scripts into sysroot
        tests_dir = self.repo_root / "tests"
        smoke_test = tests_dir / "smoke_test_l2.py"
        if smoke_test.is_file():
            shutil.copy2(smoke_test, sysroot)
        for t in (tests_dir / "func").glob("test_*.py"):
            shutil.copy2(t, sysroot)

        # Build ramfs for standalone mode (needed fresh each test run
        # since test scripts are copied into it).
        # When NANVIX_PREBUILT_RAMFS is set (e.g. by CI to reuse the
        # Linux-built ramfs on Windows), skip the rebuild entirely.
        if deployment == "standalone":
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
        targets = (
            set(self.targets) if self.targets else {"test-smoke", "test-integration"}
        )

        try:
            if "test-smoke" in targets:
                self._run_smoke_test(sysroot)
            if "test-integration" in targets:
                self._run_functional_tests(sysroot, exclude_tests)
        finally:
            self._cleanup_ramfs()

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
        if "PASS" in output:
            log.success("smoke test: PASS")
        elif output.strip():
            print(output)
        else:
            log.fatal("smoke test produced no output", code=EXIT_TEST_FAILURE)

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

    def release(self) -> None:
        """Package the runtime bundle for distribution."""
        sysroot = self._sysroot_path()

        nanvixd_name = _nanvixd_binary()
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

        dist_dir = self.repo_root / "dist"
        bundle_root = self.nanvix_dir / "release-bundle"
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
            mkramfs = sysroot / "bin" / _mkramfs_binary()
            if not mkramfs.is_file():
                log.fatal(
                    f"{_mkramfs_binary()} not found (required for standalone mode).",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z setup` first.",
                )
            log.info("release: building ramfs image")
            try:
                self._ensure_ramfs(sysroot)
                if self._ramfs_img and self._ramfs_img.is_file():
                    shutil.copy2(self._ramfs_img, bundle_dir / "nanvix_rootfs.img")
                else:
                    log.fatal(
                        "ramfs image not found after build.",
                        code=EXIT_BUILD_FAILURE,
                        hint="Ensure `./z build` completed successfully.",
                    )
            finally:
                self._cleanup_ramfs()

        # README
        if mode == "standalone":
            run_cmd = (
                f"./bin/{nanvixd_name} -ramfs nanvix_rootfs.img -- ./bin/python3.12"
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
            f"```\n\n"
            f"**Note:** The `-c` flag only supports code without spaces "
            f"(a nanvixd limitation).\n"
            f"Use script files for multi-word Python commands:\n\n"
            f"```sh\n"
            f"echo \"print('Hello from Nanvix!')\" > test.py\n"
            f"{run_cmd} test.py\n"
            f"```\n"
        )
        (bundle_dir / "README.md").write_text(readme_text)

        # Validate bundle
        log.info("release: validating bundle")
        required = [
            f"bin/{nanvixd_name}",
            "bin/kernel.elf",
            "bin/python3.12",
            "lib/python3.12/os.py",
            "lib/python3.12/site.py",
        ]
        if mode == "standalone":
            required.append("nanvix_rootfs.img")
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
        if _IS_WINDOWS:
            log.info("release: creating zip archive")
            archive = dist_dir / f"{asset_prefix}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in bundle_dir.rglob("*"):
                    if file.is_file():
                        arcname = f"{asset_prefix}/{file.relative_to(bundle_dir)}"
                        zf.write(file, arcname)
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
        elf_out = self.repo_root / "elf-binaries"
        if elf_out.exists():
            shutil.rmtree(elf_out)
        elf_out.mkdir()
        for elf in (sysroot / "bin").glob("*.elf"):
            shutil.copy2(elf, elf_out)

        log.success(f"release: {archive}")

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

        if deployment == "standalone":
            self._ensure_ramfs(sysroot)
            if not self._ramfs_img or not self._ramfs_img.is_file():
                log.fatal(
                    "ramfs image not found.",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z build` first.",
                )
            cmd = [
                nanvixd_bin,
                "-bin-dir",
                str((sysroot / "bin").resolve()),
                "-ramfs",
                str(self._ramfs_img),
                "--",
                "./bin/python3.12",
                '-c print("hello");PYTHONHOME=/sysroot PYTHONDONTWRITEBYTECODE=1',
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
        elapsed = time.perf_counter() - start

        output = log_file.read_text(errors="replace") if log_file.is_file() else ""
        log_file.unlink(missing_ok=True)

        if deployment == "standalone":
            self._cleanup_ramfs()

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
        dist_dir = self.repo_root / "dist"
        if dist_dir.is_dir():
            shutil.rmtree(dist_dir)
        release_dir = self.repo_root / "release-assets"
        if release_dir.is_dir():
            shutil.rmtree(release_dir)

        # Clean ramfs artifacts
        self._cleanup_ramfs()
        ramfs_img = self.nanvix_dir / "nanvix_rootfs.img"
        ramfs_img.unlink(missing_ok=True)
        ramfs_sentinel = self.nanvix_dir / ".ramfs-built"
        ramfs_sentinel.unlink(missing_ok=True)

        log.success("clean complete")


if __name__ == "__main__":
    NanvixPythonBuild.main()
