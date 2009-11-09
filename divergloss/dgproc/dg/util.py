# -*- coding: UTF-8 -*-

"""
Various utilities.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import sys, os, locale

_cmdname = os.path.basename(sys.argv[0])

# --------------------------------------
# Error reporting.

def error (msg, code=1):

    cmdname = _cmdname
    print p_("error message", "%(cmdname)s: error: %(msg)s") % vars()
    sys.exit(code)


def warning (msg):

    cmdname = _cmdname
    print p_("error message", "%(cmdname)s: warning: %(msg)s") % vars()


# --------------------------------------
# Internationalization.

from dg import _tr

# Wrappers for gettext calls.
# As of Python 2.5, module gettext has no knowledge of Gettext's contexts.
# Implement them in the same way Gettext does; do not use pygettext to
# extract POT, but Gettext's native xgettext (>= 0.16).

# Left out: want contexts for all translatable strings.
"""
# Basic call.
def _(msgid):

    msgstr = _tr.ugettext(msgid)
    return msgstr
"""

# Context call.
def p_(msgctxt, msgid):

    cmsgid = msgctxt + "\x04" + msgid
    msgstr = _tr.ugettext(cmsgid)
    p = msgstr.find("\x04")
    if p > 0:
        msgstr = msgstr[p+1:]
    return msgstr


# Left out: want contexts for all translatable strings.
"""
# Plural call.
def n_(msgid, msgid_plural, n):

    msgstr = _tr.ungettext(msgid, msgid_plural, n)
    return msgstr
"""

# Plural with context call.
def np_(msgctxt, msgid, msgid_plural, n):

    cmsgid = msgctxt + "\x04" + msgid
    msgstr = _tr.ungettext(cmsgid, msgid_plural, n)
    p = msgstr.find("\x04")
    if p > 0:
        msgstr = msgstr[p+1:]
    return msgstr


# --------------------------------------
# Language-aware sorting.

_lang_to_locale = {
    "en": [
        "en_US.UTF-8", "en_US.UTF8", "en_US", "english",
    ],
    "sr": [
        "sr_RS.UTF-8", "sr_CS.UTF-8", "sr_RS",
    ],
    "sr@latin": [
        "sr_RS.UTF-8@latin", "sr_CS.UTF-8@latin", "sr_RS@latin",
    ],
    "ja": [
        "ja_JP.UTF-8",
    ],
}

_no_locale_warning_issued = {}

# Set locale for requested language, and return reset function.
def _set_lang_locale (lang):

    if lang is None:
        return lambda: True

    # Get possible locales from explicit mapping,
    # try auto-resolution as lower priority (not very reliable).
    nlocnames = _lang_to_locale.get(lang, [])
    nlocname_auto = locale.normalize(lang + ".UTF-8")
    if nlocname_auto not in nlocnames:
        nlocnames.append(nlocname_auto)

    # Try to set one of the locales.
    oldloc = locale.getlocale()
    setlocname = None
    for nlocname in nlocnames:
        try:
            setlocname = locale.setlocale(locale.LC_ALL, nlocname)
            break
        except:
            pass
    if setlocname is None and lang not in _no_locale_warning_issued:
        warning(p_("error message",
                    "cannot find a locale for language '%(lang)s', "
                    "tried: %(locales)s")
                % dict(lang=lang, locales=" ".join(nlocnames)))
        _no_locale_warning_issued[lang] = True
        locale.setlocale(locale.LC_ALL, oldloc)

    # Return reset function.
    return lambda: locale.setlocale(locale.LC_ALL, oldloc)


def langsort (lst, lang=None):
    """
    Sort a list of words using collation of the given language.

    If C{lang} is C{None}, current locale is used for collation.

    @param lst: list to sort, in-place
    @type lst: list
    @param lang: language for the collation
    @type lang: string of C{None}
    """

    reset_locale = _set_lang_locale(lang)
    lst.sort(locale.strcoll)
    reset_locale()


def langsort_tuples (lst, index, lang=None):
    """
    Sort a list of tuples by comparing elements of given index,
    using collation for given language.

    If C{lang} is C{None}, current locale is used for collation.

    @param lst: list to sort, in-place
    @type lst: list of tuples
    @param index: sort by tuple elements at this position
    @type index: int
    @param lang: language for the collation
    @type lang: string of C{None}
    """

    reset_locale = _set_lang_locale(lang)
    lst.sort(lambda x, y: locale.strcoll(x[index], y[index]))
    reset_locale()


# --------------------------------------
# Miscellaneous.

def lstr (obj):
    """
    Convert object into locale-encoded string.

    The object has to have the C{__str__} method defined.

    @param obj: an object
    @type obj: object

    @return: string representation of the object
    @rtype: string
    """

    cmdlenc = locale.getdefaultlocale()[1]
    return repr(obj).decode("unicode_escape").encode(cmdlenc)


def mkdirpath (dirpath):
    """
    Make all the directories in the path which do not exist yet.

    Like shell's C{mkdir -p}.

    @param dirpath: the directory path to create
    @type dirpath: string
    """

    if os.path.isdir(dirpath):
        return

    incpath = ""
    for subdir in os.path.normpath(dirpath).split(os.path.sep):
        incpath = os.path.join(incpath, subdir)
        if not os.path.isdir(incpath):
            os.mkdir(incpath)

