# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for the nanvix-python distribution.

Consumes a pre-built CPython 3.12 buildroot release artifact, installs
pure Python pip packages, and generates a custom ramfs image for the
Nanvix microkernel.

Usage:
    ./z setup     # Download Nanvix sysroot and pre-built CPython buildroot
    ./z build     # Install pip packages, generate ramfs, stage release bundle
    ./z test      # Run smoke test and functional tests
    ./z release   # Package the staged bundle into a release archive
    ./z benchmark # Run a hello-world wall-time measurement
    ./z clean     # Remove build artifacts

The lifecycle implementations are split across `src/`, one mixin per
stage:

  - src/lib.py        shared helpers + cross-mixin forward declarations
  - src/setup.py      SetupMixin
  - src/build.py      BuildMixin (also owns site-packages + ramfs/initrd
                      and stages the release bundle under regular_out())
  - src/test.py       TestMixin
  - src/benchmark.py  BenchmarkMixin
  - src/clean.py      CleanMixin

`NanvixPythonBuild` simply composes them and ZScript via the MRO.
"""

from __future__ import annotations

from src.benchmark import BenchmarkMixin
from src.build import BuildMixin
from src.clean import CleanMixin
from src.setup import SetupMixin
from src.test import TestMixin


class NanvixPythonBuild(
    SetupMixin,
    BuildMixin,
    TestMixin,
    BenchmarkMixin,
    CleanMixin,
):
    """Build script for the nanvix-python distribution.

    All lifecycle behaviour is contributed by the mixins; this class
    only exists to compose them.
    """


if __name__ == "__main__":
    NanvixPythonBuild.main()

# Remove the mixin classes from the module namespace so that
# `discover_script_class()` in nanvix_zutil (which returns the first
# ZScript subclass found in `vars(module)`) picks `NanvixPythonBuild`
# rather than one of the partial mixin bases. Without this, only the
# lifecycle hooks defined on the *first* mixin show up in the CLI.
# TODO: https://github.com/nanvix/zutils/issues/269
del BenchmarkMixin, BuildMixin, CleanMixin, SetupMixin, TestMixin
