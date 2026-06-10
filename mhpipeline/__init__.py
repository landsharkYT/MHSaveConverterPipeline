"""mhpipeline — CLI wrapper that automates converting Monster Hunter XX / GU
save data between 3DS (encrypted SD extdata) and Switch (cleartext).

Kept import-light on purpose: submodules pull their own dependencies, so
``import mhpipeline`` must not drag in art/colorama. Import the concrete modules
(``mhpipeline.paths``, ``mhpipeline.system_backup``, ``mhpipeline.ui`` ...) as
needed.
"""

__version__ = "0.1.0"
