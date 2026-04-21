# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for the nanvix-python distribution.

Cross-compiles CPython 3.12 with 8 statically linked C extensions and
108 pip packages for the Nanvix microkernel.

Usage:
    ./z setup     # Download Nanvix sysroot and dependencies, init submodules
    ./z build     # Cross-compile extensions and CPython with built-in modules
    ./z test      # Run smoke test and 108 functional tests
    ./z release   # Package standalone runtime bundle
    ./z clean     # Remove build artifacts
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from nanvix_zutil import CFG_SYSROOT, CFG_TOOLCHAIN, ZScript, log
from nanvix_zutil.exitcodes import EXIT_BUILD_FAILURE, EXIT_MISSING_DEP, EXIT_TEST_FAILURE

# Makefile variable names used by the extension Makefile.nanvix files.
_MAKE_VAR_CONFIG = "CONFIG_NANVIX"
_MAKE_VAR_HOME = "NANVIX_HOME"
_MAKE_VAR_TOOLCHAIN = "NANVIX_TOOLCHAIN"
_MAKE_VAR_PLATFORM = "PLATFORM"
_MAKE_VAR_PROCESS_MODE = "PROCESS_MODE"
_MAKE_VAR_MEMORY_SIZE = "MEMORY_SIZE"
_MAKE_VAR_INSTALL_PREFIX = "INSTALL_PREFIX"

# CPython embeds --prefix into the binary (sys.prefix, sys.path).
# Use /sysroot so release tarballs don't contain ephemeral runner paths.
_DEFAULT_INSTALL_PREFIX = "/sysroot"

# Per-test timeout in seconds (overridable via TIMEOUT_SECONDS env var).
_DEFAULT_TIMEOUT = 300


class NanvixPythonBuild(ZScript):
    """Build script for the nanvix-python distribution."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sysroot_path(self) -> Path:
        """Return the resolved sysroot path."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        return Path(sysroot)

    def _toolchain_str(self) -> str:
        """Return the toolchain root path as a string."""
        return self.config.get(CFG_TOOLCHAIN, "/opt/nanvix") or "/opt/nanvix"

    def _make_args(
        self,
        build_dir: Path | str,
        *targets: str,
        extra_vars: dict[str, str] | None = None,
    ) -> list[str]:
        """Build argument list for ``make -f Makefile.nanvix``."""
        sysroot = str(self._sysroot_path())
        toolchain = self._toolchain_str()

        args = [
            "make",
            "-C",
            str(build_dir),
            "-f",
            "Makefile.nanvix",
            f"{_MAKE_VAR_CONFIG}=y",
            f"{_MAKE_VAR_HOME}={sysroot}",
        ]
        if toolchain:
            args.append(f"{_MAKE_VAR_TOOLCHAIN}={toolchain}")
        args.extend(targets)
        if extra_vars:
            for key, val in extra_vars.items():
                args.append(f"{key}={val}")
        return args

    def _cpython_make_args(self, *targets: str) -> list[str]:
        """Build argument list for CPython's Makefile.nanvix."""
        sysroot = str(self._sysroot_path())
        toolchain = self._toolchain_str()

        args = [
            "make",
            "-f",
            "Makefile.nanvix",
            f"{_MAKE_VAR_CONFIG}=y",
            f"{_MAKE_VAR_HOME}={sysroot}",
            f"{_MAKE_VAR_TOOLCHAIN}={toolchain}",
            f"{_MAKE_VAR_PLATFORM}={self.config.machine}",
            f"{_MAKE_VAR_PROCESS_MODE}={self.config.deployment_mode}",
            f"{_MAKE_VAR_MEMORY_SIZE}={self.config.memory_size}",
            f"{_MAKE_VAR_INSTALL_PREFIX}={_DEFAULT_INSTALL_PREFIX}",
        ]
        args.extend(targets)
        return args

    def _host_python(self) -> str | None:
        """Find a usable host Python interpreter."""
        toolchain = self._toolchain_str()
        toolchain_python = Path(toolchain) / "bin" / "python3"
        if toolchain_python.is_file():
            return str(toolchain_python)
        if shutil.which("python3"):
            return "python3"
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

        Uses nanvixd.exe on Windows, nanvixd.elf on Linux.
        Captures output to *log_file*.  Does NOT raise on non-zero exit
        (the caller inspects the log for PASS/FAIL).
        """
        if timeout is None:
            timeout = int(os.environ.get("TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT)))

        deployment = self.config.deployment_mode
        is_windows = sys.platform == "win32"
        nanvixd_name = "nanvixd.exe" if is_windows else "nanvixd.elf"
        nanvixd = str((sysroot / "bin" / nanvixd_name).resolve())

        cmd: list[str]
        if deployment == "standalone":
            ramfs_img = self._ensure_ramfs(sysroot)
            nanvixd_args = [
                nanvixd,
                "-bin-dir",
                str((sysroot / "bin").resolve()),
                "-ramfs",
                str(ramfs_img),
                "--",
                str((sysroot / "bin" / "python3.12").resolve()),
                f"-B /sysroot/{script_path};PYTHONHOME=/sysroot PYTHONDONTWRITEBYTECODE=1",
            ]
        else:
            nanvixd_args = [
                nanvixd,
                "--",
                str((sysroot / "bin" / "python3.12").resolve()),
                f"./{script_path}",
            ]

        # On Linux, wrap with `timeout --foreground` to enforce deadline.
        # On Windows, use subprocess.run(timeout=...) instead.
        if is_windows:
            cmd = nanvixd_args
        else:
            cmd = ["timeout", "--foreground", str(timeout)] + nanvixd_args

        with log_file.open("w") as fh:
            subprocess.run(
                cmd,
                cwd=str(sysroot),
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=fh,
                timeout=timeout if is_windows else None,
            )

    # -- Standalone / ramfs helpers ----------------------------------------

    _ramfs_img: Path | None = None
    _stripped_sysroot: Path | None = None

    def _ensure_ramfs(self, sysroot: Path) -> Path:
        """Build (or reuse) a ramfs image for standalone mode."""
        if self._ramfs_img and self._ramfs_img.is_file():
            return self._ramfs_img

        work_dir = self.nanvix_dir
        stripped = work_dir / "stripped-sysroot"
        self._create_stripped_sysroot(sysroot, stripped)
        self._stripped_sysroot = stripped

        # Copy test scripts into the stripped sysroot
        stripped_root = stripped / "sysroot"
        for src in sysroot.glob("smoke_test_l2.py"):
            shutil.copy2(src, stripped_root)
        for src in sysroot.glob("test_*.py"):
            shutil.copy2(src, stripped_root)

        img = Path(f"/tmp/nanvix_rootfs_{os.getpid()}.img")
        log.info("building ramfs image for standalone mode")
        subprocess.run(
            [str(stripped_root / "bin" / "mkramfs.elf"), "-o", str(img), str(stripped)],
            check=True,
        )
        self._ramfs_img = img
        return img

    def _create_stripped_sysroot(self, src: Path, dst: Path) -> None:
        """Create a stripped copy of the sysroot for standalone mode."""
        log.info("creating stripped sysroot for standalone mode")
        if dst.exists():
            shutil.rmtree(dst)

        root = dst / "sysroot"
        root.mkdir(parents=True)

        # Runtime binaries
        bin_dir = root / "bin"
        bin_dir.mkdir()
        for name in ("nanvixd.elf", "kernel.elf", "python3.12", "mkramfs.elf"):
            src_bin = src / "bin" / name
            if src_bin.is_file():
                shutil.copy2(src_bin, bin_dir)
        (bin_dir / "python3").symlink_to("python3.12")

        # Python stdlib + site-packages
        lib_dir = root / "lib"
        lib_dir.mkdir()
        src_pylib = src / "lib" / "python3.12"
        if src_pylib.is_dir():
            shutil.copytree(src_pylib, lib_dir / "python3.12")

        # Linker script
        user_ld = src / "lib" / "user.ld"
        if user_ld.is_file():
            shutil.copy2(user_ld, lib_dir)

        pylib = lib_dir / "python3.12"

        # Remove development artifacts
        for name in ("config-3.12", "idlelib", "turtledemo", "ensurepip",
                      "lib2to3", "tkinter", "pydoc_data"):
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
            "plotly", "jupyterlab_plotly", "sympy", "nltk",
            "reportlab", "share", "textblob", "joblib",
        ]
        for pkg in heavy_pkgs:
            p = site_pkg / pkg
            if p.is_dir():
                shutil.rmtree(p)
            # Also remove dist-info
            for di in site_pkg.glob(f"{pkg}-*.dist-info"):
                shutil.rmtree(di, ignore_errors=True)
            for di in site_pkg.glob(f"{pkg.replace('-', '_')}-*.dist-info"):
                shutil.rmtree(di, ignore_errors=True)

        # Remove __pycache__ and source files from site-packages
        for d in root.rglob("__pycache__"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        for ext in ("*.pyx", "*.pxd", "*.c", "*.h", "*.cpp"):
            for f in site_pkg.rglob(ext):
                f.unlink(missing_ok=True)

        # Precompile
        host_python = self._host_python()
        if host_python:
            subprocess.run(
                [host_python, "-m", "compileall", "-q", str(pylib)],
                capture_output=True,
            )

    def _cleanup_ramfs(self) -> None:
        """Remove temporary ramfs artifacts."""
        if self._ramfs_img and self._ramfs_img.is_file():
            self._ramfs_img.unlink(missing_ok=True)
            self._ramfs_img = None
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
        elif Path(toolchain, "bin", "python3").is_file():
            pip_cmd = [str(Path(toolchain, "bin", "python3")), "-m", "pip"]
        else:
            log.warning("pip3 not found; skipping site-packages installation")
            return

        req_dir = self.repo_root / "requirements"
        for req_file in ("site-packages-base.txt", "site-packages-extra.txt"):
            req_path = req_dir / req_file
            if not req_path.is_file():
                continue
            subprocess.run(
                [*pip_cmd, "install", f"--target={site_pkg}", "--no-deps",
                 "--no-compile", "--quiet", "-r", str(req_path)],
                capture_output=True,
            )

        # Remove native .so files (not usable on Nanvix)
        for so in site_pkg.rglob("*.so"):
            so.unlink(missing_ok=True)
        pth = site_pkg / "distutils-precedence.pth"
        pth.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Download sysroot, resolve dependencies, and init submodules.

        The base ``super().setup()`` downloads the Nanvix sysroot and
        library dependencies (zlib, sqlite, openssl, bzip2, libffi) into
        the buildroot.  Then we merge the buildroot into the sysroot and
        initialise the git submodules for the C extensions.
        """
        super().setup()

        # Merge buildroot (lib/ and include/) into sysroot so the
        # Makefile.nanvix files can find headers and .a archives.
        buildroot = self.nanvix_dir / "buildroot"
        sysroot = self._sysroot_path()
        if buildroot.is_dir():
            for subdir in ("lib", "include"):
                src = buildroot / subdir
                dst = sysroot / subdir
                if not src.is_dir():
                    continue
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    target = dst / item.name
                    if item.is_dir():
                        shutil.copytree(item, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, target)
                log.info(f"Merged buildroot/{subdir} into sysroot")

        # Configure git safe directories for CI containers
        log.info("configuring git safe directories")
        root = str(self.repo_root)
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", root],
            capture_output=True,
        )
        for dep in ("cpython", "cymem", "numpy", "kiwi", "libexpat",
                     "murmurhash", "preshed", "srsly"):
            dep_dir = str(self.repo_root / "deps" / dep)
            subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", dep_dir],
                capture_output=True,
            )

        # Initialise git submodules
        log.info("initializing submodules")
        subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive", "--depth", "1"],
            cwd=self.repo_root,
            check=True,
        )

        # Install Cython and cppy (required by numpy meson build)
        log.info("installing Cython and cppy")
        venv_dir = self.nanvix_dir / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
        )
        subprocess.run(
            [str(venv_dir / "bin" / "pip"), "install", "--quiet", "cython", "cppy"],
            check=True,
        )

        log.success("setup complete")

    def build(self) -> None:
        """Cross-compile extensions and CPython with built-in modules."""
        sysroot = self._sysroot_path()
        root = self.repo_root
        cpython_dir = root / "deps" / "cpython"
        cymem_dir = root / "deps" / "cymem"
        numpy_dir = root / "deps" / "numpy"
        kiwi_dir = root / "deps" / "kiwi"
        murmurhash_dir = root / "deps" / "murmurhash"
        preshed_dir = root / "deps" / "preshed"
        srsly_dir = root / "deps" / "srsly"
        libexpat_dir = root / "deps" / "libexpat"
        patches_dir = root / "patches"

        # Verify submodules
        for d in (cpython_dir, cymem_dir, numpy_dir, kiwi_dir,
                  murmurhash_dir, preshed_dir, srsly_dir, libexpat_dir):
            if not d.is_dir() or not any(d.iterdir()):
                log.fatal(
                    f"Submodule {d.name} not initialised.",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z setup` first.",
                )

        # Activate build venv (provides Cython)
        venv_bin = self.nanvix_dir / "venv" / "bin"
        if venv_bin.is_dir():
            os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"

        # Step 1: Configure CPython
        log.info("configuring CPython")
        self.run(*self._cpython_make_args("configure"), cwd=cpython_dir)

        # Step 2: Install CPython headers into sysroot
        log.info("installing CPython headers into sysroot")
        py_inc = sysroot / "include" / "python3.12"
        py_inc.mkdir(parents=True, exist_ok=True)
        for h in (cpython_dir / "Include").glob("*.h"):
            shutil.copy2(h, py_inc)
        for subdir in ("cpython", "internal"):
            src = cpython_dir / "Include" / subdir
            if src.is_dir():
                shutil.copytree(src, py_inc / subdir, dirs_exist_ok=True)
        pyconfig = cpython_dir / "pyconfig.h"
        if pyconfig.is_file():
            shutil.copy2(pyconfig, py_inc)

        # Step 2a: Generate Python pkg-config files so that meson's Python
        # detection finds the sysroot headers instead of the host's.
        pkgconfig_dir = sysroot / "lib" / "pkgconfig"
        pkgconfig_dir.mkdir(parents=True, exist_ok=True)
        pc_content = (
            f"prefix={sysroot}\n"
            f"includedir=${{prefix}}/include/python3.12\n"
            f"libdir=${{prefix}}/lib\n"
            "\n"
            "Name: Python\n"
            "Description: Embed Python into an application\n"
            "Version: 3.12.3\n"
            "Cflags: -I${includedir}\n"
            "Libs: -L${libdir} -lpython3.12\n"
        )
        for pc_name in ("python3.pc", "python3-embed.pc", "python-3.12.pc",
                        "python-3.12-embed.pc"):
            (pkgconfig_dir / pc_name).write_text(pc_content)

        # Step 3: Build cymem
        log.info("building cymem")
        self.run(*self._make_args(cymem_dir, "all"))
        shutil.copy2(cymem_dir / "libcymem.a", sysroot / "lib")

        # Step 3a0: Build murmurhash
        log.info("building murmurhash")
        shutil.copy2(
            patches_dir / "murmurhash_cwrap_nanvix.c",
            murmurhash_dir / "murmurhash" / "murmurhash_cwrap.c",
        )
        self.run(*self._make_args(murmurhash_dir, "all"))
        shutil.copy2(murmurhash_dir / "libmurmurhash.a", sysroot / "lib")

        # Step 3a1: Build preshed (depends on cymem + murmurhash headers)
        log.info("building preshed")
        self.run(
            *self._make_args(
                preshed_dir, "all",
                extra_vars={
                    "CYMEM_DIR": str(cymem_dir),
                    "MURMURHASH_DIR": str(murmurhash_dir),
                },
            )
        )
        shutil.copy2(preshed_dir / "libpreshed.a", sysroot / "lib")

        # Step 3a2: Build srsly ujson
        log.info("building srsly (ujson)")
        self.run(*self._make_args(srsly_dir, "all"))
        shutil.copy2(srsly_dir / "libsrsly_ujson.a", sysroot / "lib")

        # Step 3a: Build libexpat
        log.info("building libexpat")
        self.run(*self._make_args(libexpat_dir, "all"))
        shutil.copy2(libexpat_dir / "libexpat.a", sysroot / "lib")
        shutil.copy2(libexpat_dir / "expat" / "lib" / "expat.h", sysroot / "include")
        shutil.copy2(
            libexpat_dir / "expat" / "lib" / "expat_external.h",
            sysroot / "include",
        )

        # Step 3b: Build kiwisolver
        log.info("building kiwisolver")
        # Install cppy headers into sysroot
        cppy_include = subprocess.run(
            ["python3", "-c",
             "import cppy, os; print(os.path.join(os.path.dirname(cppy.__file__), 'include'))"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if cppy_include and Path(cppy_include).is_dir():
            for item in Path(cppy_include).iterdir():
                dst = sysroot / "include" / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)
        # Install kiwi C++ headers
        kiwi_headers = kiwi_dir / "kiwi"
        if kiwi_headers.is_dir():
            shutil.copytree(kiwi_headers, sysroot / "include" / "kiwi", dirs_exist_ok=True)
        self.run(
            *self._make_args(
                kiwi_dir, "all",
                extra_vars={"CPPY_INCLUDE": "$(SYSROOT_INCLUDE)"},
            )
        )
        shutil.copy2(kiwi_dir / "libkiwisolver.a", sysroot / "lib")

        # Step 4: Patch numpy for static built-in support
        log.info("patching numpy for static built-in support")
        multiarray_c = numpy_dir / "numpy" / "core" / "src" / "multiarray" / "multiarraymodule.c"
        if multiarray_c.is_file():
            content = multiarray_c.read_text(errors="replace")
            if "Nanvix" not in content and "re-entrant" not in content:
                subprocess.run(
                    ["git", "apply", str(patches_dir / "numpy_static_builtin.patch")],
                    cwd=numpy_dir, capture_output=True,
                )
        subprocess.run(
            ["git", "apply", str(patches_dir / "numpy_makefile_nanvix.patch")],
            cwd=numpy_dir, capture_output=True,
        )

        # Step 5: Build numpy static archives
        log.info("building numpy archives")
        for p in (numpy_dir / "builddir", numpy_dir / ".nanvix-configured",
                  numpy_dir / "nanvix-cross.ini"):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()
        self._build_numpy(numpy_dir)

        # Step 6: Patch CPython with built-in module definitions
        log.info("patching CPython for built-in modules")
        for name in ("cymem_builtin.c", "kiwi_builtin.c", "murmurhash_builtin.c",
                      "preshed_builtin.c", "srsly_ujson_builtin.c"):
            shutil.copy2(patches_dir / name, cpython_dir / "Modules")
        numpy_builtin_dir = cpython_dir / "Modules" / "numpy_builtin"
        numpy_builtin_dir.mkdir(exist_ok=True)
        shutil.copy2(
            patches_dir / "numpy_libm_compat.c",
            numpy_builtin_dir / "numpy_libm_compat.c",
        )

        # Determine sysroot path for Setup.local (Docker vs native)
        toolchain = self._toolchain_str()
        toolchain_gcc = Path(toolchain) / "bin" / "i686-nanvix-gcc"
        if not toolchain_gcc.is_file():
            cpython_numpy_sysroot = "/mnt/sysroot"
        else:
            cpython_numpy_sysroot = str(sysroot)
        numpy_lib_dir = f"{cpython_numpy_sysroot}/lib/numpy"

        setup_local = cpython_dir / "Modules" / "Setup.local"
        setup_content = f"""\
# Built-in extensions for Nanvix (auto-generated by nanvix-python ./z build)
# cymem: Cython memory pool helper - linked statically as _cymem
*static*
_cymem cymem_builtin.c -lcymem

# kiwisolver: Cassowary constraint solver - linked statically as _kiwi_cext
_kiwi_cext kiwi_builtin.c -lkiwisolver -lstdc++

# murmurhash: Cython MurmurHash bindings - linked statically as _murmurhash_mrmr
_murmurhash_mrmr murmurhash_builtin.c -lmurmurhash -lstdc++

# preshed: Cython hash tables - linked statically
_preshed_maps preshed_builtin.c -lpreshed
_preshed_counter preshed_builtin.c -lpreshed
_preshed_bloom preshed_builtin.c -lpreshed

# srsly ujson: fast JSON serialization - linked statically
_srsly_ujson srsly_ujson_builtin.c -lsrsly_ujson

# numpy built-ins (flattened names due makesetup dotted-name restrictions)
_np_multiarray_umath numpy_builtin/_multiarray_umath_dummy.c numpy_builtin/numpy_libm_compat.c {numpy_lib_dir}/lib_multiarray_umath_all.a {numpy_lib_dir}/libnpymath.a
"""
        pocketfft = Path(f"{sysroot}/lib/numpy/lib_pocketfft_internal.a")
        if pocketfft.is_file():
            setup_content += (
                f"_pocketfft_internal numpy_builtin/_pocketfft_internal_dummy.c "
                f"{numpy_lib_dir}/lib_pocketfft_internal.a {numpy_lib_dir}/libnpymath.a\n"
            )
        setup_local.write_text(setup_content)
        (cpython_dir / "Modules" / "config.c").unlink(missing_ok=True)

        # Step 7: Build CPython with extensions
        log.info("building CPython")
        self.run(*self._cpython_make_args("build"), cwd=cpython_dir)

        # Step 8: Install CPython into sysroot
        log.info("installing CPython into sysroot")
        staging = cpython_dir / ".nanvix" / "_install_staging"
        if staging.exists():
            shutil.rmtree(staging)
        self.run(
            *self._cpython_make_args("install", f"DESTDIR={staging}"),
            cwd=cpython_dir,
        )
        staging_sysroot = staging / "sysroot"
        if staging_sysroot.is_dir():
            shutil.copytree(staging_sysroot, sysroot, dirs_exist_ok=True)
        shutil.rmtree(staging, ignore_errors=True)

        # Step 9: Install Python shims and packages
        self._install_python_packages(sysroot, root)

        log.success("build complete")

    def _build_numpy(self, numpy_dir: Path) -> None:
        """Build numpy archives, with Docker fallback."""
        toolchain = self._toolchain_str()
        toolchain_gcc = Path(toolchain) / "bin" / "i686-nanvix-gcc"

        if toolchain_gcc.is_file():
            self.run(*self._make_args(numpy_dir, "all"))
            return

        # Docker fallback
        if not shutil.which("docker"):
            log.fatal(
                "Docker not found and native toolchain is unavailable.",
                code=EXIT_MISSING_DEP,
            )

        sysroot = self._sysroot_path()
        host_cython_dir = Path("/usr/lib/python3/dist-packages/Cython")
        if not host_cython_dir.is_dir():
            log.fatal(
                f"Host Cython package not found at {host_cython_dir}.",
                code=EXIT_MISSING_DEP,
            )

        # Create cython shim for Docker
        cython_shim_dir = numpy_dir / ".nanvix-cython-bin"
        cython_shim_dir.mkdir(exist_ok=True)
        cython_shim = cython_shim_dir / "cython"
        cython_shim.write_text(
            "#!/usr/bin/env sh\n"
            'if [ "$#" -gt 0 ] && { [ "$1" = "-V" ] || [ "$1" = "--version" ]; }; then\n'
            "  python3 - <<'PY'\n"
            "import Cython\n"
            'print(f"Cython version {Cython.__version__}")\n'
            "PY\n"
            "  exit 0\n"
            "fi\n"
            'exec python3 -m Cython.Compiler.Main "$@"\n'
        )
        cython_shim.chmod(0o755)
        shutil.copy2(cython_shim, cython_shim_dir / "cython3")

        uid = os.getuid()
        gid = os.getgid()
        subprocess.run(
            [
                "docker", "run", "--rm",
                "--user", f"{uid}:{gid}",
                "-v", f"{numpy_dir}:/mnt/workspace",
                "-v", f"{sysroot}:/mnt/sysroot",
                "-v", f"{sysroot}:/sysroot",
                "-v", f"{cython_shim_dir}:/mnt/cython-bin:ro",
                "-v", f"{host_cython_dir}:/mnt/host-cython/Cython:ro",
                "-w", "/mnt/workspace",
                "-e", "HOME=/tmp",
                "-e", "PYTHONPATH=/mnt/host-cython",
                "-e", "PATH=/mnt/cython-bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "nanvix/toolchain:latest-minimal",
                "make", "-f", "Makefile.nanvix",
                "CONFIG_NANVIX=y",
                "NANVIX_HOME=/mnt/sysroot",
                "NANVIX_TOOLCHAIN=/opt/nanvix",
                "all",
            ],
            check=True,
        )

    def _install_python_packages(self, sysroot: Path, root: Path) -> None:
        """Install Python shims and packages into the sysroot."""
        patches_dir = root / "patches"
        site_packages = sysroot / "lib" / "python3.12" / "site-packages"

        # cymem shim
        log.info("installing cymem Python shim")
        cymem_pkg = site_packages / "cymem"
        cymem_pkg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(patches_dir / "cymem_shim.py", cymem_pkg / "cymem.py")

        # kiwisolver package + shim
        log.info("installing kiwisolver Python package")
        kiwi_dir = root / "deps" / "kiwi"
        kiwi_pkg = site_packages / "kiwisolver"
        if kiwi_pkg.exists():
            shutil.rmtree(kiwi_pkg)
        shutil.copytree(kiwi_dir / "py" / "kiwisolver", kiwi_pkg)
        shutil.copy2(patches_dir / "kiwi_cext_shim.py", kiwi_pkg / "_cext.py")

        # murmurhash package + shim
        log.info("installing murmurhash Python package")
        murmurhash_dir = root / "deps" / "murmurhash"
        murmurhash_pkg = site_packages / "murmurhash"
        if murmurhash_pkg.exists():
            shutil.rmtree(murmurhash_pkg)
        shutil.copytree(murmurhash_dir / "murmurhash", murmurhash_pkg)
        shutil.copy2(patches_dir / "murmurhash_mrmr_shim.py", murmurhash_pkg / "mrmr.py")
        for ext in ("*.pyx", "*.pxd", "*.c", "*.cpp"):
            for f in murmurhash_pkg.rglob(ext):
                f.unlink(missing_ok=True)

        # preshed package + shims
        log.info("installing preshed Python package")
        preshed_dir = root / "deps" / "preshed"
        preshed_pkg = site_packages / "preshed"
        if preshed_pkg.exists():
            shutil.rmtree(preshed_pkg)
        shutil.copytree(preshed_dir / "preshed", preshed_pkg)
        shutil.copy2(patches_dir / "preshed_maps_shim.py", preshed_pkg / "maps.py")
        shutil.copy2(patches_dir / "preshed_counter_shim.py", preshed_pkg / "counter.py")
        shutil.copy2(patches_dir / "preshed_bloom_shim.py", preshed_pkg / "bloom.py")
        for ext in ("*.pyx", "*.pxd", "*.c"):
            for f in preshed_pkg.rglob(ext):
                f.unlink(missing_ok=True)

        # srsly package + ujson shim
        log.info("installing srsly Python package")
        srsly_dir = root / "deps" / "srsly"
        srsly_pkg = site_packages / "srsly"
        if srsly_pkg.exists():
            shutil.rmtree(srsly_pkg)
        shutil.copytree(srsly_dir / "srsly", srsly_pkg)
        shutil.copy2(patches_dir / "srsly_ujson_shim.py", srsly_pkg / "ujson" / "ujson.py")
        for ext in ("*.pyx", "*.pxd", "*.c", "*.cpp", "*.h"):
            for f in srsly_pkg.rglob(ext):
                f.unlink(missing_ok=True)

        # numpy package + bootstrap
        log.info("installing numpy Python package")
        numpy_dir = root / "deps" / "numpy"
        numpy_pkg = site_packages / "numpy"
        if numpy_pkg.exists():
            shutil.rmtree(numpy_pkg)
        shutil.copytree(numpy_dir / "numpy", numpy_pkg)

        # numpy version.py
        builddir_version = numpy_dir / "builddir" / "numpy" / "version.py"
        if builddir_version.is_file():
            shutil.copy2(builddir_version, numpy_pkg / "version.py")
        else:
            (numpy_pkg / "version.py").write_text(
                'version = "1.26.4"\n'
                "__version__ = version\n"
                "full_version = version\n"
                "short_version = version\n"
                'git_revision = "nanvix"\n'
                "release = True\n"
            )

        (numpy_pkg / "__config__.py").write_text(
            "def show():\n    return None\n\n"
            "def get_info(*args, **kwargs):\n    return {}\n"
        )
        (numpy_pkg / "__config__.py.in").unlink(missing_ok=True)

        # sitecustomize.py (numpy + srsly bootstraps)
        site_customize = sysroot / "lib" / "python3.12" / "sitecustomize.py"
        shutil.copy2(patches_dir / "nanvix_numpy_bootstrap.py", site_customize)
        srsly_bootstrap = patches_dir / "nanvix_srsly_bootstrap.py"
        if srsly_bootstrap.is_file():
            with site_customize.open("a") as fh:
                fh.write(srsly_bootstrap.read_text())

        # Remove stale .pth loader
        pth = site_packages / "nanvix_numpy_bootstrap.pth"
        pth.unlink(missing_ok=True)

    def test(self) -> None:
        """Run smoke and functional tests.

        Without targets, runs both smoke and functional tests.
        Pass targets after ``--`` to select:
          ``./z test -- test-smoke``       — smoke test only
          ``./z test -- test-integration`` — functional tests only
        """
        sysroot = self._sysroot_path()
        is_windows = sys.platform == "win32"
        nanvixd_name = "nanvixd.exe" if is_windows else "nanvixd.elf"
        mkramfs_name = "mkramfs.exe" if is_windows else "mkramfs.elf"

        if not (sysroot / "bin" / nanvixd_name).is_file():
            log.fatal(
                f"{nanvixd_name} not found in sysroot.",
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
            mkramfs = sysroot / "bin" / mkramfs_name
            if not mkramfs.is_file():
                log.fatal(
                    f"{mkramfs_name} not found (required for standalone mode).",
                    code=EXIT_MISSING_DEP,
                )

        # Install site-packages
        site_pkg = sysroot / "lib" / "python3.12" / "site-packages"
        site_pkg.mkdir(parents=True, exist_ok=True)
        self._install_site_packages(site_pkg)

        # Copy test scripts into sysroot
        tests_dir = self.repo_root / "tests"
        smoke_test = tests_dir / "smoke_test_l2.py"
        if smoke_test.is_file():
            shutil.copy2(smoke_test, sysroot)
        for t in (tests_dir / "func").glob("test_*.py"):
            shutil.copy2(t, sysroot)

        # Standalone exclusions
        exclude_tests = os.environ.get("EXCLUDE_TESTS", "")
        if deployment == "standalone" and not exclude_tests:
            exclude_tests = "83"  # plotly stripped from standalone sysroot

        # Determine which tests to run
        targets = set(self.targets) if self.targets else {"test-smoke", "test-integration"}

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
        log_file = Path("/tmp/smoke.log")
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
        excluded = set(exclude_tests.split()) if exclude_tests else set()

        # Precompile stdlib and tests
        host_python = self._host_python()
        if host_python:
            subprocess.run(
                [host_python, "-m", "compileall", "-q",
                 str(sysroot / "lib" / "python3.12")],
                capture_output=True,
            )
            for t in sysroot.glob("test_*.py"):
                subprocess.run(
                    [host_python, "-m", "py_compile", str(t)],
                    capture_output=True,
                )

        total_pass = 0
        total_fail = 0
        total_skip = 0
        failed_tests: list[str] = []

        test_files = sorted(sysroot.glob("test_[0-9]*.py"))
        for test_file in test_files:
            name = test_file.name

            # Extract test number for filtering
            import re
            match = re.search(r"test_(\d+)", name)
            if not match:
                continue
            num = int(match.group(1))
            if num < test_start or num > test_end:
                continue
            if str(num) in excluded:
                continue

            log_file = Path(f"/tmp/{name}.log")
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
                skip_log = Path(f"/tmp/skip_{name}.log")
                skip_log.write_text(output)

        print(f"Results: {total_pass} passed, {total_fail} failed, {total_skip} skipped")

        if total_fail > 0:
            print(f"Failed tests: {' '.join(failed_tests)}")
            log.fatal("functional tests failed", code=EXIT_TEST_FAILURE)
        if total_pass == 0:
            log.fatal("no tests passed (all skipped or none found)", code=EXIT_TEST_FAILURE)

        log.success("all functional tests passed")

    def release(self) -> None:
        """Package the runtime bundle for distribution."""
        sysroot = self._sysroot_path()

        if not (sysroot / "bin" / "nanvixd.elf").is_file():
            log.fatal(
                "nanvixd.elf not found in sysroot.",
                code=EXIT_MISSING_DEP,
            )
        if not (sysroot / "bin" / "python3.12").is_file():
            log.fatal(
                "python3.12 not found in sysroot.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        platform = self.config.machine
        mode = self.config.deployment_mode
        memory = self.config.memory_size
        asset_prefix = f"{platform}-{mode}-{memory}"

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
        runtime_bins = ["nanvixd.elf", "kernel.elf", "python3.12"]
        if mode == "multi-process":
            runtime_bins.extend(["linuxd.elf", "uservm.elf"])
        for name in runtime_bins:
            src = sysroot / "bin" / name
            if src.is_file():
                shutil.copy2(src, bin_dir)
        (bin_dir / "python3").symlink_to("python3.12")

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
                [host_python, "-m", "compileall", "-q",
                 str(lib_dir / "python3.12")],
                capture_output=True,
            )

        # README
        (bundle_dir / "README.md").write_text(f"""\
# Nanvix Python Runtime

Platform: {platform}
Process mode: {mode}

## Quick Start

After extracting the archive, enter the directory and run:

```sh
cd {asset_prefix}
./bin/nanvixd.elf -- ./bin/python3.12 script.py
```

**Note:** The `-c` flag only supports code without spaces (a nanvixd limitation).
Use script files for multi-word Python commands:

```sh
echo "import numpy; print(numpy.__version__)" > test.py
./bin/nanvixd.elf -- ./bin/python3.12 test.py
```
""")

        # Validate bundle
        log.info("release: validating bundle")
        required = [
            "bin/nanvixd.elf", "bin/kernel.elf", "bin/python3.12",
            "lib/python3.12/os.py", "lib/python3.12/site.py",
            "lib/python3.12/sitecustomize.py",
            "lib/python3.12/site-packages/numpy/__init__.py",
        ]
        if mode == "multi-process":
            required.extend(["bin/linuxd.elf", "bin/uservm.elf"])
        missing = [f for f in required if not (bundle_dir / f).is_file()]
        if missing:
            log.fatal(
                "bundle validation failed — missing files:\n"
                + "\n".join(f"  {f}" for f in missing),
                code=EXIT_BUILD_FAILURE,
            )
        log.success("release: validation passed")

        # Create tarball
        log.info("release: creating tarball")
        tarball = dist_dir / f"{asset_prefix}.tar.bz2"
        subprocess.run(
            ["tar", "-cjf", str(tarball), "-C", str(bundle_root), asset_prefix],
            check=True,
        )
        shutil.rmtree(bundle_root)

        log.success(f"release: {tarball}")

    def clean(self) -> None:
        """Remove build artifacts."""
        # Clean release assets
        dist_dir = self.repo_root / "dist"
        if dist_dir.is_dir():
            shutil.rmtree(dist_dir)
        release_dir = self.repo_root / "release-assets"
        if release_dir.is_dir():
            shutil.rmtree(release_dir)

        # Clean dependency build artifacts
        deps = self.repo_root / "deps"

        cpython = deps / "cpython"
        if (cpython / "Makefile.nanvix").is_file():
            subprocess.run(
                ["make", "-C", str(cpython), "-f", "Makefile.nanvix", "clean"],
                capture_output=True,
            )
            for name in ("Setup.local", "config.c", "cymem_builtin.c",
                          "kiwi_builtin.c", "murmurhash_builtin.c",
                          "preshed_builtin.c", "srsly_ujson_builtin.c"):
                (cpython / "Modules" / name).unlink(missing_ok=True)
            shutil.rmtree(cpython / "Modules" / "numpy_builtin", ignore_errors=True)

        for lib_name, lib_file in [
            ("cymem", "libcymem.a"), ("murmurhash", "libmurmurhash.a"),
            ("preshed", "libpreshed.a"), ("srsly", "libsrsly_ujson.a"),
            ("libexpat", "libexpat.a"), ("kiwi", "libkiwisolver.a"),
        ]:
            lib_dir = deps / lib_name
            if (lib_dir / "Makefile.nanvix").is_file():
                subprocess.run(
                    ["make", "-C", str(lib_dir), "-f", "Makefile.nanvix", "clean"],
                    capture_output=True,
                )
            (lib_dir / lib_file).unlink(missing_ok=True)

        # numpy
        numpy = deps / "numpy"
        for p in ("builddir", ".nanvix-configured", "nanvix-cross.ini",
                   ".nanvix-cython-bin"):
            target = numpy / p
            if target.is_dir():
                shutil.rmtree(target)
            elif target.is_file():
                target.unlink()

        log.success("clean complete")


if __name__ == "__main__":
    NanvixPythonBuild.main()
