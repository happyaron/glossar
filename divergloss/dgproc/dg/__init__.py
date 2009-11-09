# -*- coding: UTF-8 -*-
# dg.__init__

"""
Module for handling Divergloss XML glossaries.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import os

def rootdir():
    """
    Get root directory of Dg installation.

    @return: absolute directory path
    @rtype: string
    """

    return __path__[0]


# Collect data paths.
# Either as installed, when the _paths.py module will be available,
# or assume locations within the repository.
try:
    import dg._paths as _paths
    _mo_dir = _paths.mo
    _dtd_dir = _paths.dtd
except ImportError:
    _mo_dir = os.path.join(os.path.dirname(rootdir()), "mo")
    _dtd_dir = os.path.join(os.path.dirname(rootdir()), "dtd")


# Global translation object, used internally (only calls exposed in dg.util).
import gettext
try:
    _tr = gettext.translation("dgproc", _mo_dir)
except IOError:
    _tr = gettext.NullTranslations()

