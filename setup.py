"""Opt-in build hook for optional Cython neural-kernel extensions.

Normal installs never attempt to compile native code. To explicitly build it,
install the ``native`` extra and set ``SYNAPSE_PET_BUILD_CYTHON=1`` while running
``python setup.py build_ext --inplace``.
"""

from __future__ import annotations

import os
import sys

from setuptools import setup


extensions = []
if os.environ.get("SYNAPSE_PET_BUILD_CYTHON") == "1":
    import numpy as np
    from Cython.Build import cythonize
    from setuptools import Extension

    # Preserve the reference's explicit float32 rounding between operations.
    strict_fp_args = (
        ["/fp:strict"] if sys.platform == "win32" else ["-ffp-contract=off"]
    )
    extensions = cythonize(
        [
            Extension(
                "synapse_pet.neural_backend._stdp",
                ["src/synapse_pet/neural_backend/kernels/stdp.pyx"],
                extra_compile_args=strict_fp_args,
            ),
            Extension(
                "synapse_pet.neural_backend._lif",
                ["src/synapse_pet/neural_backend/kernels/lif.pyx"],
                include_dirs=[np.get_include()],
                extra_compile_args=strict_fp_args,
            ),
        ],
        build_dir="build/cython",
        compiler_directives={"language_level": 3},
    )

setup(ext_modules=extensions)
