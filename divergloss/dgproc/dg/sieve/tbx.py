# -*- coding: UTF-8 -*-

"""
Create a TBX view of the glossary.

TBX output is intended for read-only use, e.g. in tools for glossary viewing,
searching, or CAT (computer-aided translation). A TBX glossary created by
this sieve cannot be, in general, converted back or synced with the original
Divergloss glossary.

If the glossary contains several languages or environments, I{pivotal} ones
may be selected by giving their keys with sieve parameters C{lang} and C{env};
when these parameters are not given, default language and environment are used.
By default, output TBX glossary will contain terms for all languages, but all
other language-specific content (e.g. descriptions) are given only in the
pivotal language. All content in non-pivotal environment is ignored.

TBX glossary is output as a single file, the name of which is either
given by the C{file} parameter, or derived from the glossary ID.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import os
import shutil

from dg import rootdir
from dg.util import p_
from dg.util import error, warning
from dg.textfmt import TextFormatterPlain, TextFormatterHtml
from dg.textfmt import etag, stag, wtext
from dg.textfmt import LineAccumulator
from dg.util import langsort, langsort_tuples
from dg.util import mkdirpath
from dg.util import lstr


def fill_optparser (parser_view):

    pv = parser_view

    pv.set_desc(p_("subcommand description",
                   "Create a TBX view of the glossary."))

    pv.add_subopt("lang", str, defval="",
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Pivotal language for the view. The glossary "
                          "default language is used if not given."))
    pv.add_subopt("env", str, defval="",
                  metavar=p_("placeholder for parameter value", "ENVKEY"),
                  desc=p_("subcommand option description",
                          "Pivotal environment for the view. The glossary "
                          "default environment is used if not given."))
    pv.add_subopt("file", str, defval="",
                  metavar=p_("placeholder for parameter value", "NAME"),
                  desc=p_("subcommand option description",
                          "Name of the TBX file to create. If not given, "
                          "the name is derived from glossary ID."))


class Subcommand (object):

    def __init__ (self, options, global_options):

        self._options = options


    def __call__ (self, gloss):

        self._indent = "  "
        self._gloss = gloss

        # Resolve pivotal language and environment.
        self._lang = self._options.lang or gloss.lang
        if self._lang not in gloss.languages:
            error(p_("error message",
                     "language '%(lang)s' not present in the glossary")
                    % dict(lang=self._lang))
        self._env = self._options.env or gloss.env[0]
        if self._env and self._env not in gloss.environments:
            error(p_("error message",
                     "environment '%(env)s' not defined by the glossary")
                  % dict(env=self._env))

        # Determine concepts to present and in which order.
        concepts = self._select_concepts()

        # Prepare text formatters.
        self._tf = TextFormatterPlain(gloss, lang=self._lang, env=self._env)

        # Create TBX.
        accl = LineAccumulator(self._indent)
        self._fmt_prologue(accl)
        self._fmt_concepts(accl.newind(2), concepts)
        self._fmt_epilogue(accl)

        if self._options.file:
            tbx_fname = self._options.file
        else:
            tbx_fname = gloss.id + ".tbx"
        accl.write(tbx_fname)


    def _select_concepts (self):

        gloss, lang, env = self._gloss, self._lang, self._env

        # Select concepts to present by having a term in pivotal langenv.
        selected_concepts = {}
        for ckey, concept in self._gloss.concepts.iteritems():
            if lang in concept.term.langs():
                if env in concept.term.envs(lang):
                    selected_concepts[ckey] = concept

        # Sort presentable concepts by concept key.
        ordering_links = []
        for ckey, concept in selected_concepts.iteritems():
            ordering_links.append((ckey, concept))
        langsort_tuples(ordering_links, 0, lang)

        return [concept for ckey, concept in ordering_links]


    def _by_langenv_fmt (self, dset):
        """
        When just any single text in pivotal langenv is needed formatted.
        """
        texts = dset(self._lang, self._env)
        if texts:
            return self._tf(texts[0].text)
        else:
            return ""


    def _fmt_prologue (self, accl):

        gloss, lang, env = self._gloss, self._lang, self._env
        fle = self._by_langenv_fmt

        accl("<?xml version='1.0' encoding='UTF-8'?>");
        accl(  "<!DOCTYPE martif "
             + "PUBLIC 'ISO 12200:1999A//DTD MARTIF core (DXFcdV04)//EN' "
             + "'TBXcdv04.dtd' "
             + ">");
        accl(  "<!-- "
             + p_('comment in generated files (warning to user)',
                  '===== AUTOGENERATED FILE, DO NOT EDIT =====')
             + " -->")
        accl(stag("martif", {"type":"TBX", "xml:lang":lang}))

        accl(stag("martifHeader"), 1)

        accl(stag("fileDesc"), 2)
        accl(stag("titleStmt"), 3)
        ftitle = fle(gloss.title)
        if not ftitle:
            ftitle = p_("glossary title, when undefined", "Unnamed")
        if env:
            fenv = fle(gloss.environments[env].name)
            if fenv:
                ftitle = p_("glossary title format",
                            "%(title)s (%(env)s)") \
                         % dict(title=ftitle, env=fenv)
        accl(wtext(ftitle, "title"), 4)
        accl(etag("titleStmt"), 3)
        accl(etag("fileDesc"), 2)

        accl(etag("martifHeader"), 1)

        accl(stag("text"), 1)


    def _fmt_epilogue (self, accl):

        accl(etag("text"), 1)
        accl(etag("martif"))


    def _fmt_concepts (self, accl, concepts):

        accl(stag("body"))
        accl()
        accl2 = accl.newind(2)
        for concept in concepts:
            accl(stag("termEntry", {"id":concept.id}), 1)
            self._fmt_concept(accl2, concept)
            accl(etag("termEntry"), 1)
            accl()

        accl(etag("body"))


    def _fmt_concept (self, accl, concept):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf = self._tf
        fle = self._by_langenv_fmt

        fdesc = fle(concept.desc)
        if fdesc:
            accl(wtext(fdesc, "descrip", {"type":"definition"}))

        for tkey in concept.topic:
            ftname = fle(gloss.topics[tkey].name)
            if ftname:
                accl(wtext(ftname, "descrip", {"type":"subjectField"}))

        # Sort languages by key, but pivotal first.
        alangs = concept.term.langs()
        alangs.remove(lang)
        alangs.sort()
        alangs.insert(0, lang)

        for clang in alangs:
            for term in concept.term(clang, env):
                accl(stag("langSet", {"xml:lang":clang}))
                accl(stag("ntig"), 1)

                accl(stag("termGrp"), 2)
                fterm = tf(term.nom.text)
                accl(wtext(fterm, "term"), 3)
                if term.gr:
                    fgname = fle(gloss.grammar[term.gr].shortname)
                    if fgname:
                        accl(wtext(fgname, "termNote",
                                   {"type":"partOfSpeech"}), 3)
                accl(etag("termGrp"), 2)

                accl(etag("ntig"), 1)
                accl(etag("langSet"))

