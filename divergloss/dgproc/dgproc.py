#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Query and build outputs of a Divergloss XML document.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import sys, os, locale, mimetypes
from optparse import OptionParser

sys.path.append(os.path.dirname(sys.argv[0]))

from dg.util import p_
from dg.util import error
from dg.util import lstr
import dg.construct
import dg.subcmd
import dg.sieve


def main ():

    # Use Psyco specializing compiler if available.
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass

    reload(sys)
    cmdlenc = locale.getdefaultlocale()[1]
    sys.setdefaultencoding(cmdlenc)

    # Setup options and parse the command line.
    usage = p_("command usage",
               "%(cmd)s [OPTIONS] [SIEVES] DGFILE") % dict(cmd="%prog")
    description = p_("command description",
                     "Query a Divergloss XML document and "
                     "build various outputs. "
                     "Also fully validates the document, "
                     "past what the DTD only can do.")
    version = p_("command version",
                 "%(cmd)s experimental\n"
                 "Copyright 2008, Chusslove Illich <caslav.ilic@gmx.net>") \
              % dict(cmd="%prog")

    opars = OptionParser(usage=usage, description=description, version=version)
    opars.add_option(
        "--no-check",
        action="store_false", dest="check", default=True,
        help=p_("description of cmdline option",
                "do not check the glossary for validity"))
    opars.add_option(
        "-s", "--sieve-par",
        metavar=p_("placeholder for value to cmdline option", "PARSPEC"),
        dest="sieve_par", action="append", default=[],
        help=p_("description of cmdline option",
                "specify parameter to sieves"))
    opars.add_option(
        "-S", "--list-sieves",
        action="store_true", dest="list_sieves", default=False,
        help=p_("description of cmdline option",
                "list available sieves and exit"))
    opars.add_option(
        "-H", "--help-sieves",
        action="store_true", dest="help_sieves", default=False,
        help=p_("description of cmdline option",
                "display help on sieves and exit"))
    (options, free_args) = opars.parse_args()

    # Register subcommands.
    schandler = dg.subcmd.SubcmdHandler([(dg.sieve, None)])

    if len(free_args) > 2:
        error(p_("error in command line", "too many free arguments"))

    # If any subcommand listing required, show and exit.
    if options.list_sieves:
        print p_("header to listing", "Available sieves:")
        print schandler.subcmd_overview(dg.sieve, indent="  ")
        sys.exit(0)

    # Collect sieves and glossary file.
    if not options.help_sieves:
        if len(free_args) < 1:
            error(p_("error in command line", "no file given"))
        dgfile = free_args.pop()
        if not os.path.isfile(dgfile):
            error(p_("error in command line",
                     "file '%(file)s' does not exists") % dict(file=dgfile))
    else:
        free_args = free_args[:1]

    # Parse sieve names.
    sieve_names = []
    if free_args:
        sievespec = free_args.pop()
        sieve_names = [x for x in sievespec.split(",")]

    # If help on subcommands required, show and exit.
    if options.help_sieves:
        if sieve_names:
            print p_("header to listing", "Help on sieves:")
            print
            print schandler.help([(dg.sieve, sieve_names)])
        else:
            print p_("message", "No sieves specified to provide help on.")
        sys.exit(0)

    # Create subcommands.
    sieves = schandler.make_subcmds(
        [(dg.sieve, sieve_names, options.sieve_par)],
        options)[0]

    # Construct the glossary.
    gloss = dg.construct.from_file(dgfile, validate=options.check)

    # Sieve the glossary.
    for sieve in sieves:
        ret = sieve(gloss)
        if ret is not None:
            gloss = ret


if __name__ == '__main__':
    main()

