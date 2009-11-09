# -*- coding: UTF-8 -*-

"""
Create HTML pages out of the glossary.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import sys
import os
import time
import unicodedata
import re
import shutil
import random

from dg import rootdir
from dg.util import p_, np_
from dg.util import error, warning
from dg.textfmt import TextFormatterPlain, TextFormatterHtml
from dg.textfmt import etag, stag, wtext
from dg.textfmt import LineAccumulator
from dg.util import langsort, langsort_tuples
from dg.util import mkdirpath
from dg.construct import Text, Para
from dg.util import lstr
import dg.construct as D


_src_style_dir = os.path.join(rootdir(), "sieve", "html_extras", "style")


def fill_optparser (parser_view):

    # Collect available CSS sheets.
    styles = []
    for item in os.listdir(_src_style_dir):
        path = os.path.join(_src_style_dir, item)
        if os.path.isdir(path):
            styles.append(item)

    pv = parser_view

    pv.set_desc(p_("subcommand description",
                   "Create HTML pages out of the glossary."))

    pv.add_subopt("lang", str, defval="",
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Pivotal language for the view. The glossary "
                          "default language is used if not given."))
    pv.add_subopt("env", str, defval="",
                  metavar=p_("placeholder for parameter value", "ENVKEY"),
                  desc=p_("subcommand option description",
                          "Pivotal environment for the view. If not given, "
                          "there is no pivotal environment."))
    pv.add_subopt("base", str, defval="",
                  metavar=p_("placeholder for parameter value", "BASENAME"),
                  desc=p_("subcommand option description",
                          "Base name for writing generated HTML to disk, "
                          "used to derive file names by chunking policy. "
                          "If not given, glossary ID is used."))
    pv.add_subopt("chunk", str,
                  defval="alpha", admvals=["alpha", "chlim", "none"],
                  metavar=p_("placeholder for parameter value", "POLICY"),
                  desc=p_("subcommand option description",
                          "How to subdivide the glossary into chunks. "
                          "The possible policies are:\n"
                          "\n"
                          "%(alpha)s: concepts alphabetically split by pages, "
                          "a separate title page with main glossary data, "
                          "and another page for rest of the global data.\n"
                          "\n"
                          "%(chlim)s: similar to '%(alpha)s', but concept "
                          "pages are split based on the limit of maximum "
                          "characters per page (see '%(maxch)s' option).\n"
                          "\n"
                          "%(none)s: no chunking, all glossary content on "
                          "a single page.\n")
                        % dict(alpha="alpha", chlim="chlim", none="none",
                               maxch="maxch"))
    pv.add_subopt("maxch", int, defval=10000,
                  metavar=p_("placeholder for parameter value", "NCHAR"),
                  desc=p_("subcommand option description",
                          "The character limit when using the '%(chlim)s' "
                          "chunking policy.") % dict(chlim="chlim"))
    pv.add_subopt("no-term-olang", bool, defval=False,
                  desc=p_("subcommand option description",
                          "Do not present terms in non-pivotal languages."))
    pv.add_subopt("no-term-oenv", bool, defval=False,
                  desc=p_("subcommand option description",
                          "Do not present terms in non-pivotal environments."))
    pv.add_subopt("style", str,
                  defval="apricot", admvals=styles,
                  metavar=p_("placeholder for parameter value", "STYLE"),
                  desc=p_("subcommand option description",
                          "Style sheet for the HTML pages."))
    pv.add_subopt("indcols", int, defval=4,
                  metavar=p_("placeholder for parameter value", "NUM"),
                  desc=p_("subcommand option description",
                          "Number of columns in index of terms."))


class Subcommand (object):

    def __init__ (self, options, global_options):

        self._options = options

        if self._options.chunk == "chlim":
            error(p_("error message",
                     "chunking by character count not implemented yet"))

    def __call__ (self, gloss):

        self._indent = "  "

        self._gloss = gloss

        # Resolve pivotal language and environment.
        self._lang = self._options.lang or gloss.lang
        if self._lang not in gloss.languages:
            error(p_("error message",
                     "language '%(lang)s' not present in the glossary")
                    % dict(lang=self._lang))
        self._env = self._options.env or None # pivotal environment not required
        if self._env is not None and self._env not in gloss.environments:
            error(p_("error message",
                     "environment '%(env)s' not defined by the glossary")
                  % dict(env=self._env))
        self._pivoted = (self._env is not None) or (not gloss.environments)

        # Environments by weight, descending (for picking and sorting).
        ebv = {}
        for eobj in self._gloss.environments.values():
            weight = eobj.weight or 0
            if weight not in ebv:
                ebv[weight] = []
            ebv[weight].append(eobj.id)
        for elst in ebv.itervalues():
            random.shuffle(elst)
        ebv = ebv.items()
        ebv.sort(lambda x, y: cmp(y[0], x[0]))
        self._envs_by_weight = ebv

        # Create directory structure and copy overscaffolding.
        chunked = self._options.chunk not in ["none"]
        root_dir, global_dir, concept_dir, \
        global_media_dir, concept_media_dir = \
            self._setup_output_tree(chunked)

        # Determine concepts to present and in which order,
        # and chunk them into pages.
        pages_concepts, pages_to_filenames, ckeys_to_filenames = \
            self._chunk_concepts()
        self._pages_concepts = pages_concepts
        self._pages_to_filenames = pages_to_filenames
        self._ckeys_to_filenames = ckeys_to_filenames

        # Prepare text formatters.
        self._tf = TextFormatterHtml(gloss, lang=self._lang, env=self._env,
                                     refbase=ckeys_to_filenames)
        self._tfp = TextFormatterHtml(gloss, lang=self._lang, env=self._env,
                                      refbase=ckeys_to_filenames,
                                      wtag="p")
        self._tfn = TextFormatterPlain(gloss, lang=self._lang, env=self._env)

        # Data for global entries, by object type, and as an ordered list.
        self._set_globals_props()

        # Create HTML pages.
        self._top_fname = "index.html"
        self._concepts_fname = "concepts.html"
        self._index_fname = "terms.html"

        # - top
        accl = LineAccumulator(self._indent)
        self._fmt_prologue(accl)
        self._fmt_top(accl.newind(2), chunked)
        self._fmt_epilogue(accl)
        accl.write(os.path.join(root_dir, self._top_fname))

        # - concepts
        if self._options.chunk == "none":
            self._crtop = ""
            accl = LineAccumulator(self._indent)
            concepts = pages_concepts[0][1]
            self._fmt_prologue(accl)
            self._fmt_header_concepts(accl.newind(2), concepts, "", 1)
            self._fmt_concepts(accl.newind(2), concepts, 1)
            self._fmt_epilogue(accl)
            accl.write(os.path.join(root_dir, self._concepts_fname))

        else:
            self._crtop = ".." # return to root from a concepts page
            for page, concepts in pages_concepts:
                accl = LineAccumulator(self._indent)
                self._fmt_prologue(accl, self._crtop)
                self._fmt_header_concepts(accl.newind(2), concepts, page)
                self._fmt_concepts(accl.newind(2), concepts)
                self._fmt_epilogue(accl)
                accl.write(os.path.join(concept_dir, pages_to_filenames[page]))

        # - terms index
        accl = LineAccumulator(self._indent)
        self._fmt_prologue(accl)
        self._fmt_index(accl.newind(2))
        self._fmt_epilogue(accl)
        accl.write(os.path.join(root_dir, self._index_fname))

        # - global data
        self._artop = ""
        if chunked:
            self._artop = ".."
        for gp in self._globals_props_lst:
            if gp.entries:
                self._fmt_global(gp.fmt, os.path.join(global_dir, gp.fname))

        # - access info
        self._write_access_info(root_dir)


    def _dset_pick (self, dset):
        """
        Pick "best" langenv list from a d-set.

        For pivoted build that means by chosen environment,
        while for non-pivoted build by environment weights.
        """

        if dset is None: # so that it can consume getattr() result
            return []

        if self._pivoted:
            return dset(self._lang, self._env)
        else:
            for weight, envs in self._envs_by_weight:
                for env in envs:
                    pick = dset(self._lang, env)
                    if pick:
                        break
                if pick:
                    break
            return pick


    def _key_term (self, concept):
        """
        Pick "best" term representing the concept.

        For pivoted build this means the first term in chosen langenv,
        for non-pivoted build the concept key.
        """

        if self._pivoted:
            return concept.term(self._lang, self._env)[0]
        else:
            return concept.id


    def _envsort (self, env_packs, full=True):
        """
        Sort (envkey, phrase) pairs given as dict or list,
        taking into account any defined environment weights.

        Return sorted (envkey, phrase) tuples when C{full} is C{True},
        or just sorted phrases otherwise.
        """

        # Construct a dictionary by environment, with phrases in a list.
        env_packs_d = {}
        if isinstance(env_packs, dict):
            for env, phrase in env_packs.iteritems():
                env_packs_d[env] = [phrase]
        else:
            for env, phrase in env_packs:
                if env not in env_packs_d:
                    env_packs_d[env] = []
                env_packs_d[env].append(phrase)

        # Go by weight groups, sort lexicographically within each group.
        env_packs_sorted = []
        for weight, wenvs in self._envs_by_weight:
            loc_packs = []
            for wenv in wenvs:
                phrases = env_packs_d.get(wenv)
                if phrases is not None:
                    for phrase in phrases:
                        loc_packs.append((wenv, phrase))
            langsort_tuples(loc_packs, 1, self._lang)
            env_packs_sorted.extend(loc_packs)

        if full:
            return env_packs_sorted
        else:
            return [y for x, y in env_packs_sorted]


    def _alpha_class (self, this=False):

        if self._pivoted:
            if this:
                return "page-this-alpha"
            else:
                return "page-to-alpha"
        else:
            if this:
                return "page-this-alpha-key"
            else:
                return "page-to-alpha-key"


    def _set_globals_props (self):

        gloss = self._gloss

        class GlProps: pass
        self._globals_props = {}
        self._globals_props_lst = []
        def make_gl_props (clss):
            gp = GlProps()
            self._globals_props[clss.__name__] = gp
            self._globals_props_lst.append(gp)
            return gp

        gp = make_gl_props(D.Environment)
        gp.fname = "environments.html"
        gp.entries = gloss.environments
        gp.fmt = self._fmt_global_environments
        gp.lntext = p_("link to an about-page in running text", "environments")

        gp = make_gl_props(D.Editor)
        gp.fname = "editors.html"
        gp.entries = gloss.editors
        gp.fmt = self._fmt_global_editors
        gp.lntext = p_("link to an about-page in running text", "editors")

        gp = make_gl_props(D.Source)
        gp.fname = "sources.html"
        gp.entries = gloss.sources
        gp.fmt = self._fmt_global_sources
        gp.lntext = p_("link to an about-page in running text", "sources")

        gp = make_gl_props(D.Topic)
        gp.fname = "topics.html"
        gp.entries = gloss.topics
        gp.fmt = self._fmt_global_topics
        gp.lntext = p_("link to an about-page in running text", "topics")

        # TODO global: languages?, levels, grammar, extroots.


    def _chunk_concepts (self):

        gloss, lang, env = self._gloss, self._lang, self._env

        # Select concepts to present by:
        # - having a term in pivotal language
        # - having a term in pivotal environment, if specified
        selected_concepts = {}
        for ckey, concept in self._gloss.concepts.iteritems():
            if lang in concept.term.langs():
                if not self._pivoted or env in concept.term.envs(lang):
                    selected_concepts[ckey] = concept

        # Sort presentable concepts,
        # either by term if the pivotal environment is defined,
        # or by concept key otherwise.
        ordering_links = []
        if self._pivoted:
            tfp = TextFormatterPlain(gloss, lang=lang, env=env)
            for concept in selected_concepts.itervalues():
                ordterm = tfp(concept.term(lang, env)[0].nom.text).lower()
                if ordterm: # ignore concepts with empty terms
                    ordering_links.append((ordterm, concept))
        else:
            for ckey, concept in selected_concepts.iteritems():
                ordering_links.append((ckey, concept))
        langsort_tuples(ordering_links, 0, lang)

        # Chunk into pages.
        pages_concepts = [] # ordered list of tuples (pagename, concepts)
        pages_to_filenames = {} # mapping pagename->filename
        ckeys_to_filenames = {} # mapping ckey->filename

        if self._options.chunk == "none":
            pages_concepts.append(("", [y for x, y in ordering_links]))
            pages_to_filenames[""] = ""
            for x, concept in ordering_links:
                ckeys_to_filenames[concept.id] = ""

        elif self._options.chunk == "alpha":
            genordchar = "#" # ordinal for terms not starting with a letter
            encountered_filenames = []
            ordchars_to_filenames = {}
            ordchars_to_pages = {}
            nonal_rx = re.compile(r"[^a-z]+", re.I)

            for ordterm, concept in ordering_links:
                # The page names are determined as follows:
                # - if the ordering term starts with a letter,
                #   use that letter in the user-visible name of the page,
                #   and part of its Unicode name for the page file name
                # - if the ordering term does not start with a letter,
                #   use one fixed character for page user-visible name,
                #   and similarly fixed string for the page file name
                ordchar = ordterm[0]
                if not ordchar.isalpha():
                    ordchar = genordchar
                if ordchar not in ordchars_to_filenames:
                    # Construct file name for the page.
                    if ordchar != genordchar:
                        ucns = unicodedata.name(unicode(ordchar)).split()
                        ucns = [x.lower() for x in ucns]
                        ucns = [nonal_rx.sub("", x) for x in ucns]
                        basename = ucns[0][:3] + "-" + ucns[-1]
                    else:
                        basename = "nonalpha"
                    filename = basename + ".html"
                    if filename in encountered_filenames:
                        error(p_("error message",
                                 "internal: while chunking concepts, "
                                 "produced file name '%(fname)s' twice")
                              % dict(fname = filename))
                    encountered_filenames.append(filename)
                    ordchars_to_filenames[ordchar] = filename

                    # Construct user-visible name of the page.
                    if self._pivoted:
                        page = ordchar.upper() # only the ordering character
                    else:
                        page = ordchar.lower() # ...but lowercase if non-piv.
                    ordchars_to_pages[ordchar] = page
                    pages_to_filenames[page] = filename

                    # Add new entry in ordered concepts.
                    pages_concepts.append((page, []))

                filename = ordchars_to_filenames[ordchar]
                page = ordchars_to_pages[ordchar]
                ckeys_to_filenames[concept.id] = filename

                # Find entry in ordered concepts where to add the current.
                for opage, oconcepts in pages_concepts:
                    if page == opage:
                        break
                oconcepts.append(concept)

        #elif self._options.chunk == "chlim":
            #pass

        else:
            pass # cannot reach

        return (pages_concepts, pages_to_filenames, ckeys_to_filenames)


    def _setup_output_tree (self, chunked):

        root_dir = self._options.base or self._gloss.id
        if os.path.exists(root_dir):
            shutil.rmtree(root_dir)
        mkdirpath(root_dir)

        self._concept_base = "concepts"
        self._style_base = "style"
        self._media_base = "media"

        if chunked:
            self._global_base = "about"
            global_dir = os.path.join(root_dir, self._global_base)
            concept_dir = os.path.join(root_dir, self._concept_base)
        else:
            self._global_base = ""
            global_dir = root_dir
            concept_dir = root_dir

        mkdirpath(global_dir)
        mkdirpath(concept_dir)

        global_media_dir = os.path.join(global_dir, self._media_base)
        concept_media_dir = os.path.join(concept_dir, self._media_base)
        # Do not create these, they will be created on first copy of media.

        style_src_dir = os.path.join(_src_style_dir, self._options.style)
        style_dir = os.path.join(root_dir, self._style_base)
        shutil.copytree(style_src_dir, style_dir)

        return (root_dir, global_dir, concept_dir,
                global_media_dir, concept_media_dir)


    def _fmt_prologue (self, accl, base="", title=""):

        accl("<?xml version='1.0' encoding='UTF-8'?>");
        accl(  "<!DOCTYPE html PUBLIC '-//W3C//DTD XHTML 1.0 Strict//EN' "
             + "'http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd'>");
        accl(  "<!-- "
             + p_('comment in generated files (warning to user)',
                  '===== AUTOGENERATED FILE, DO NOT EDIT =====')
             + " -->")

        accl(stag("html", {"xmlns":"http://www.w3.org/1999/xhtml",
                           "lang":self._lang, "xml:lang":self._lang}))

        accl(stag("head"), 1)

        accl(stag("meta", {"http-equiv":"Content-type",
                           "content":"text/html; charset=UTF-8"},
                  close=True), 2)

        stylepath = self._style_base + "/" + "global.css"
        if base:
            stylepath = base + "/" + stylepath
        accl(stag("link", {"rel":"stylesheet", "type":"text/css",
                           "href":stylepath}, close=True), 2)

        if not title:
            title = self._tfn(self._dset_pick(self._gloss.title)[0].text)
        accl(wtext(title, "title"), 2)

        accl(etag("head"), 1)

        accl(stag("body"), 1)
        accl()


    def _fmt_epilogue (self, accl):

        accl(etag("body"), 1)
        accl(etag("html"))


    def _fmt_top (self, accl, chunked=True):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf, tfp = self._tf, self._tfp
        le_ = self._dset_pick

        accl(stag("div", {"class":"tpage-header"}))
        gname = tf(le_(gloss.title)[0].text)
        gname = wtext(gname, "span", {"class":"page-gloss"})
        if env:
            ename = tf(le_(gloss.environments[env].name)[0].text)
            ename = wtext(ename, "span", {"class":"page-env"})
            title_line = p_("top page title",
                            "%(gloss)s (%(env)s)") \
                         % dict(gloss=gname, env=ename)
        else:
            title_line = gname
        title_line = wtext(title_line, "p", {"class":"tpage-title"})
        accl(title_line, 1)
        accl(etag("div"))

        accl(stag("div", {"class":"tpage-body"}))

        descs = le_(gloss.desc)
        for desc in descs:
            accl(tfp(desc.text))
        # TODO: version, date.
        nconcepts = len(self._ckeys_to_filenames.keys())
        if self._pivoted and env:
            ename = tf(le_(gloss.environments[env].name)[0].text)
            fetext = np_("a paragraph on the top page",
                         "This view of the glossary has been specialized "
                         "for the <em>%(env)s</em> environment, "
                         "and contains one concept.",
                         "This view of the glossary has been specialized "
                         "for the <em>%(env)s</em> environment, "
                         "and contains %(n)d concepts.",
                         nconcepts) \
                     % dict(env=ename, n=nconcepts)
        else:
            fetext = np_("a paragraph on the top page",
                         "This view of the glossary contains one concept.",
                         "This view of the glossary contains "
                         "%(n)d concepts.",
                         nconcepts) \
                     % dict(n=nconcepts)
        accl(wtext(fetext, "p"))

        chead = p_("contents header on the top page", "Table of Contents")
        accl(wtext(chead, "p", {"class":"tpage-content-header"}))

        if chunked:
            cplinks = self._cpage_link_row("", self._concept_base)
            if self._pivoted:
                cnt_concepts =  p_("alphabetical concepts links in contents",
                                   "Concepts: %(alpha)s") \
                                % dict(alpha=cplinks)
            else:
                cnt_concepts =  p_("alphabetical concepts links in contents",
                                   "Concepts by key: %(alpha)s") \
                                % dict(alpha=cplinks)

        else:
            cplink =  p_("concepts link in contents",
                         "Concepts")
            cnt_concepts = wtext(cplink, "a", {"href":self._concepts_fname})
        cnt_concepts = wtext(cnt_concepts, "p", {"class":"tpage-content"})
        accl(cnt_concepts, 1)

        cnt_index = p_("index of terms link in contents",
                       "Index of Terms")
        cnt_index = wtext(cnt_index, "a", {"href":self._index_fname})
        cnt_index = wtext(cnt_index, "p", {"class":"tpage-content"})
        accl(cnt_index, 1)

        glinks = []
        for gp in self._globals_props_lst:
            if gp.entries:
                gref = gp.fname
                if self._global_base:
                    gref = self._global_base + "/" + gref
                glink = wtext(gp.lntext, "a", {"href":gref})
                glinks.append(glink)
        if glinks:
            fglinks = ", ".join(glinks)
            cnt_about = p_("links to about-pages in contents",
                           "About the glossary: %(topics)s") \
                        % dict(topics=fglinks)
            cnt_about = wtext(cnt_about, "p", {"class":"tpage-content"})
            accl(cnt_about, 1)

        accl(etag("div"))


    def _fmt_header (self, accl, subtitle=None, title=None, base="",
                     ltop=False, lindex=False):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf = self._tf
        le_ = self._dset_pick

        accl(stag("div", {"class":"page-header"}))

        title_line = ""
        if title is None:
            gname = tf(le_(gloss.title)[0].text)
            gname = wtext(gname, "span", {"class":"page-gloss"})
            if env:
                ename = tf(le_(gloss.environments[env].name)[0].text)
                ename = wtext(ename, "span", {"class":"page-env"})
                title = p_("page title",
                           "%(gloss)s (%(env)s)") \
                        % dict(gloss=gname, env=ename)
            else:
                title = gname
        title_line += title

        stitle_line = ""
        if subtitle is not None:
            stitle_line += subtitle

        navs_line = ""
        navs = []
        if lindex:
            text = p_("link text for going to index of terms",
                      "[index]")
            path = self._index_fname
            if base:
                path = base + "/" + path
            nav = wtext(text, "a", {"href":path, "class":"page-nav"})
            navs.append(nav)
        if ltop:
            text = p_("link text for returning to top page",
                      "[top]")
            path = self._top_fname
            if base:
                path = base + "/" + path
            nav = wtext(text, "a", {"href":path, "class":"page-nav"})
            navs.append(nav)
        if navs:
            navs_line = "".join(navs)

        if navs_line:
            navs_line = wtext(navs_line, "div", {"class":"page-navs"})
            accl(navs_line, 1)
        if title_line:
            title_line = wtext(title_line, "h1", {"class":"page-title"})
            accl(title_line, 1)
        if stitle_line:
            stitle_line = wtext(stitle_line, "h2", {"class":"page-subtitle"})
            accl(stitle_line, 1)

        accl(etag("div"))
        accl()


    def _fmt_header_concepts (self, accl, concepts, page, divlev=0):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf, tfp = self._tf, self._tfp
        crtop = self._crtop

        if page:
            plinks = self._cpage_link_row(page)
        else:
            plinks = self._cpage_single_link_row(concepts, divlev)

        subtitle = p_("page subtitle", "Concepts: %(alpha)s") \
                   % dict(alpha=plinks)

        self._fmt_header(accl, subtitle=subtitle, base=crtop,
                         ltop=True, lindex=True)


    def _cpage_link_row (self, page="", base=""):

        plinks = []
        for opage, dummy in self._pages_concepts:
            if opage != page:
                fpath = self._pages_to_filenames[opage]
                if base:
                    fpath = base + "/" + fpath
                plink = wtext(opage, "a", {"href":fpath,
                                           "class":self._alpha_class()})
            else:
                plink = wtext(page, "span", {"class":self._alpha_class(True)})
            plinks.append(plink)

        plinks = " ".join(plinks)
        return plinks


    def _term_alpha (self, term, divlev):
        """
        Alphabetical start of a term,
        which may be given as a final string, or a term g-node.
        """
        if not isinstance(term, (str, unicode)):
            term = self._tf(term.nom.text)
        alpha = term[:divlev].title()
        if alpha and not alpha.isalpha():
            alpha = "#"
        return alpha


    def _glref (self, globj, base=""):
        """
        Return internal reference to the definition of a global object,
        such as an environement, topic, etc.
        """
        fname = self._globals_props[globj.__class__.__name__].fname
        ref = fname + "#" + globj.id
        if self._global_base:
            ref = self._global_base + "/" + ref
        if base:
            ref = base + "/" + ref
        return ref


    def _cpage_single_link_row (self, concepts, divlev):

        lang, env = self._lang, self._env

        plinks = []
        palpha = ""
        ndivs = 0
        for concept in concepts:
            alpha = self._term_alpha(self._key_term(concept), divlev)
            if palpha != alpha:
                div_id = self._concept_div_id(ndivs)
                plink = wtext(alpha, "a", {"href":"#"+div_id,
                                           "class":self._alpha_class()})
                plinks.append(plink)
                ndivs += 1
                palpha = alpha

        plinks = " ".join(plinks)
        return plinks


    def _concept_div_id (self, ndiv):

        return "cdiv-%d" % ndiv


    def _fmt_concepts (self, accl, concepts, divlev=0):

        cpt_class = ""
        pconcept = None
        accl1 = accl.newind(1)
        ndivs = 0
        for concept in concepts:
            # Possibly insert alphabetical division.
            adiv = self._fmt_concept_div(accl, pconcept, concept,
                                         divlev, ndivs)
            if adiv:
                ndivs += 1

            accl(stag("div", {"id":concept.id, "class":"concept"}))
            self._fmt_concept(accl1, concept)
            accl(etag("div"))
            accl()

            pconcept = concept


    def _fmt_concept_div (self, accl, pconcept, concept, divlev, ndiv):

        lang, env = self._lang, self._env
        palpha = ""
        if pconcept:
            palpha = self._term_alpha(self._key_term(pconcept), divlev)
        alpha = self._term_alpha(self._key_term(concept), divlev)
        if palpha == alpha:
            return False

        div_id = self._concept_div_id(ndiv)
        accl(stag("div", {"id":div_id, "class":"concept-div"}))
        alpha_line = wtext(alpha.upper(), "span", {"class":"concept-div-alpha"})
        accl(alpha_line)
        accl(etag("div"))

        return True


    def _fmt_concept (self, accl, concept):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf, tfp = self._tf, self._tfp
        le_ = self._dset_pick
        crtop = self._crtop

        # Assemble terms.
        if self._pivoted:
            terms, terms_line, secterms_line = self._fmt_terms_pivoted(concept)
        else:
            terms, terms_accl = self._fmt_terms_free(concept)

        # Assemble descriptions.
        desc_accl = LineAccumulator()
        descs = le_(concept.desc)
        for i in range(len(descs)):
            desc_line = ""
            desc_line += tfp(descs[i].text, pclass="desc-para")
            desc_accl(stag("div", {"class":"desc"}))
            if len(descs) > 1:
                deschead = p_("identifier of a description when "
                              "the concept has several descriptions",
                              "#%(no)s)") % dict(no=(i + 1))
                deschead = wtext(deschead, "span", {"class":"desc-no"})
                desc_line = desc_line.replace(">", ">" + deschead + " ", 1)
            desc_accl(desc_line, 1)
            # TODO: editor, source.
            desc_accl(etag("div"))

        # Assemble details.
        details_line = ""
        details = le_(concept.details)
        if details:
            dlst = []
            for detail in details:
                extroot = gloss.extroots[detail.root]
                extlink = tf(extroot.rooturl.text) + "/" + detail.rel
                extname = le_(extroot.name)
                if extname:
                    extname = tf(extname[0].text)
                    extname = wtext(extname, "span", {"class":"detail"})
                    extname = wtext(extname, "a", {"class":"ext",
                                                   "href":extlink})
                else:
                    extname = wtext(extlink, "a", {"class":"ext",
                                                   "href":extlink})
                dtext = ""
                if detail.text:
                    dtext = tf(detail.text)

                if dtext:
                    dfmt = p_("concept details: link to external source, "
                              "and some text describing it",
                              "%(srclink)s (%(srctext)s)") \
                           % dict(srclink=extname, srctext=dtext)
                else:
                    dfmt = extname
                dlst.append(dfmt)
            if dlst:
                details_line = p_("more details about a concept",
                                  "Details:") + " " + ", ".join(dlst)
                details_line = wtext(details_line, "p", {"class":"details"})

        # Assemble related concepts.
        related_line = ""
        rlst = []
        for ckey in concept.related:
            pageref = self._ckeys_to_filenames.get(ckey)
            if pageref is not None:
                rname = tf(le_(gloss.concepts[ckey].term)[0].nom.text)
                rname = wtext(rname, "span", {"class":"term"})
                rfmt = wtext(rname, "a", {"href":pageref+"#"+ckey})
                rlst.append(rfmt)
        if rlst:
            related_line = p_("concepts related to current concept",
                              "See also:") + " " + ", ".join(rlst)
            related_line = wtext(related_line, "p", {"class":"related"})

        # Assemble comments.
        comment_accl = LineAccumulator()
        # - on the concept
        for ccomm in le_(concept.comment):
            comment_accl(stag("div", {"class":"comment"}))

            if ccomm.by:
                edobj = gloss.editors[ccomm.by]
                ednames = le_(edobj.shortname)
                edname = tf(ednames[0].text)
                edname = wtext(edname, "a", {"href":self._glref(edobj, crtop)})
                clabel = p_("comment label (by an editor on the concept)",
                            "%(editor)s on the concept:") \
                            % dict(editor=edname)
            else:
                clabel = p_("comment label (on the concept)",
                            "On the concept:")
            clabel = wtext(clabel, "p", {"class":"comment-label"})
            comment_accl(clabel, 1)
            cbody = tfp(ccomm.text, pclass="comment-para")
            comment_accl(cbody, 1)
            comment_accl(etag("div"))
        # - on terms
        for term in terms:
            tcomms = le_(term.comment)
            ctext = tf(term.nom.text)
            ctext = wtext(ctext, "span", {"class":"comment-term"})
            for tcomm in tcomms:
                comment_accl(stag("div", {"class":"comment"}))
                if tcomm.by:
                    edobj = gloss.editors[tcomm.by]
                    ednames = le_(edobj.shortname)
                    edname = tf(ednames[0].text)
                    edname = wtext(edname, "a",
                                   {"href":self._glref(edobj, crtop)})
                    clabel = p_("comment label (by an editor on a term)",
                                "%(editor)s on %(term)s:") \
                             % dict(editor=edname, term=ctext)
                else:
                    clabel = p_("comment label (on a term)",
                                "On %(term)s:") \
                             % dict(term=ctext)
                clabel = wtext(clabel, "p", {"class":"comment-label"})
                comment_accl(clabel, 1)
                cbody = tfp(tcomm.text, pclass="comment-para")
                comment_accl(cbody, 1)
                comment_accl(etag("div"))
        # - comments grouped
        if comment_accl.lines:
            comment_accl_tmp = comment_accl
            comment_accl = LineAccumulator()
            comment_accl(stag("div", {"class":"comments"}))
            chead = p_("header to list of comments", "Comments:")
            comment_accl(wtext(chead, "p", {"class":"comments-header"}), 1)
            comment_accl(comment_accl_tmp, 1)
            comment_accl(etag("div"))

        # TODO:
        # Media.
        # Origin: concept/terms.

        # Assemble all together.
        if self._pivoted:
            accl(terms_line)
            accl(desc_accl)
            if secterms_line:
                accl(secterms_line)
        else:
            accl(terms_accl)
            accl(desc_accl)
        if details_line:
            accl(details_line)
        if related_line:
            accl(related_line)
        accl(comment_accl)


    def _fmt_terms_line (self, concept, oenv, wtopic=True):

        gloss, lang = self._gloss, self._lang
        tf = self._tf
        crtop = self._crtop

        terms = concept.term(lang, oenv)
        if not terms:
            return "", []

        # Terms for this environment.
        terms_sub = ""
        terms = concept.term(lang, oenv)
        fterms = []
        for term in terms:
            fterm = ""
            # - the term proper
            fterm = tf(term.nom.text)
            fterm = wtext(fterm, "span", {"class":"term-tt"})
            # - grammar category
            if term.gr is not None:
                gr = gloss.grammar[term.gr].shortname(lang, oenv)
                if gr:
                    fgr = wtext(tf(gr[0].text), "span", {"class":"gr"})
                    fterm = p_("formatting pattern for a term with "
                               "its grammar category",
                               "%(term)s %(gr)s") % dict(term=fterm, gr=fgr)
            fterms.append(fterm)
        terms_sub += ", ".join(fterms)

        # Terms in other languages for same environment
        olterms_sub = ""
        if not self._options.no_term_olang:
            olterms_all = []
            for olang in concept.term.langs():
                if olang == lang:
                    continue
                olterms = concept.term(olang, oenv)
                if olterms:
                    olterms = [tf(x.nom.text) for x in olterms]
                    olterms = ", ".join([wtext(x, "span", {"class":"term-ol"})
                                         for x in olterms])
                    olname = gloss.languages[olang].shortname(lang, oenv)
                    if olname:
                        olname = tf(olname[0].text)
                        olterms_all.append("%s %s" % (olname, olterms))
            if olterms_all:
                olterms_sub += "; ".join(olterms_all)

        # Topics to which this concept belongs
        topic_sub = ""
        if wtopic and concept.topic:
            ftnames = []
            for tkey in concept.topic:
                tobj = gloss.topics[tkey]
                tnames = tobj.shortname(lang, oenv)
                if tnames:
                    ftname = tf(tnames[0].text)
                    ftname = wtext(ftname, "span", {"class":"topic"})
                    ftname = wtext(ftname, "a",
                                   {"href":self._glref(tobj, crtop)})
                    ftnames.append(ftname)
            if ftnames:
                topic_sub = ", ".join(ftnames)

        # Declensions.
        decls_sub = ""
        fdecls = []
        for term in terms:
            lfdecls = []
            for decl in term.decl:
                fdecl = tf(decl.text)
                fdecl = wtext(fdecl, "span", {"class":"decl"})
                fgr = tf(gloss.grammar[decl.gr].shortname(lang, oenv)[0].text)
                fgr = wtext(fgr, "span", {"class":"gr"})
                fdecl =  p_("formatting pattern for a declination with "
                            "its grammar category",
                            "%(gr)s %(decl)s") % dict(gr=fgr, decl=fdecl)
                lfdecls.append(fdecl)
            if lfdecls:
                fdecls.append(", ".join(lfdecls))
        if fdecls:
            decls_sub += "; ".join(fdecls)

        # Format the line.
        if olterms_sub and topic_sub and decls_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s (%(olterms)s) [%(topics)s] -- %(decls)s") \
                         % dict(terms=terms_sub, olterms=olterms_sub,
                                topics=topic_sub, decls=decls_sub)
        elif olterms_sub and topic_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s (%(olterms)s) [%(topics)s]") \
                         % dict(terms=terms_sub, olterms=olterms_sub,
                                topics=topic_sub)
        elif topic_sub and decls_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s [%(topics)s] -- %(decls)s") \
                         % dict(terms=terms_sub, topics=topic_sub,
                                decls=decls_sub)
        elif olterms_sub and decls_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s (%(olterms)s) -- %(decls)s") \
                         % dict(terms=terms_sub, olterms=olterms_sub,
                                decls=decls_sub)
        elif olterms_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s (%(olterms)s)") \
                         % dict(terms=terms_sub, olterms=olterms_sub)
        elif topic_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s [%(topics)s]") \
                         % dict(terms=terms_sub, topics=topic_sub)
        elif decls_sub:
            terms_line = p_("format of the terms line",
                            "%(terms)s -- %(decls)s") \
                         % dict(terms=terms_sub, decls=decls_sub)
        else:
            terms_line = terms_sub

        return terms_line, terms


    def _fmt_terms_pivoted (self, concept):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf = self._tf
        crtop = self._crtop

        # There has to be at least one term in selected langenv,
        # or else the concept would not have been selected.
        terms_line, terms = self._fmt_terms_line(concept, env)
        terms_line = wtext(terms_line, "p", {"class":"terms"})

        # Assemble terms in other environments, for same language.
        secterms_line = ""
        if not self._options.no_term_oenv:
            # Collect environments by the term which they use,
            # sort list by environment priority.
            oeterms_all = {}
            for oenv in concept.term.envs(lang):
                if oenv == env:
                    continue
                oeterms = concept.term(lang, oenv)
                if oeterms:
                    oeterms = [tf(x.nom.text) for x in oeterms]
                    oeterms = [wtext(x, "span", {"class":"term-oe"})
                               for x in oeterms]
                    # Also need to collect formatted environment names,
                    # for sorting later on.
                    oenvft = gloss.environments[oenv].shortname(lang, env)[0]
                    oenvft = tf(oenvft.text)
                    for oeterm in oeterms:
                        if oeterm not in oeterms_all:
                            oeterms_all[oeterm] = []
                        oeterms_all[oeterm].append((oenv, oenvft))
            if oeterms_all:
                # For each term, sort environments.
                oeterms_all_es = {}
                for oeterm, oenv_packs in oeterms_all.iteritems():
                    oeterms_all_es[oeterm] = self._envsort(dict(oenv_packs))
                # Sort terms by considering first environment of each.
                sort_packs = [(y[0][0], x) for x, y in oeterms_all_es.items()]
                sorted_oeterms = self._envsort(sort_packs, full=False)
                oeterms_all_sorted = []
                for oeterm in sorted_oeterms:
                    oeterms_all_sorted.append((oeterm, oeterms_all_es[oeterm]))
                # Collapse terms with same environment sets.
                oeterms_all_sortcoll = []
                for oeterm, env_packs in oeterms_all_sorted:
                    if (   not oeterms_all_sortcoll
                        or oeterms_all_sortcoll[-1][1] != env_packs
                    ):
                        oeterms_all_sortcoll.append(([oeterm], env_packs))
                    else:
                        oeterms_all_sortcoll[-1][0].append(oeterm)
                # Assemble the line.
                oeterms_joined = []
                for oeterms, oenv_packs in oeterms_all_sortcoll:
                    foenvs = self._fmt_env_list([x for x, y in oenv_packs])
                    foeterms = ", ".join(oeterms)
                    oeterms_joined += ["%s (%s)" % (foeterms, foenvs)]
                secterms_line = "; ".join(oeterms_joined)
                secterms_line = p_("terms naming the concept in environments "
                                   "other than the pivotal one",
                                   "In other environments: %(terms)s") \
                                % dict(terms=secterms_line)
                secterms_line = wtext(secterms_line, "p", {"class":"terms-sec"})

        # TODO:
        # Level.

        return terms, terms_line, secterms_line


    def _fmt_terms_free (self, concept):

        gloss, lang = self._gloss, self._lang
        tf = self._tf
        le_ = self._dset_pick
        crtop = self._crtop

        accl = LineAccumulator()

        # Concept key and other concept-only related data.
        ckey_sub = wtext(concept.id, "span", {"class":"ckey-tt"})
        # - topic
        topic_sub = ""
        if concept.topic:
            ftnames = []
            for tkey in concept.topic:
                tobj = gloss.topics[tkey]
                tnames = le_(tobj.shortname)
                if tnames:
                    ftname = tf(tnames[0].text)
                    ftname = wtext(ftname, "span", {"class":"topic"})
                    ftname = wtext(ftname, "a",
                                   {"href":self._glref(tobj, crtop)})
                    ftnames.append(ftname)
            if tnames:
                topic_sub = ", ".join(ftnames)

        if topic_sub:
            ckeys_line = p_("format of the concept key line",
                            "c.k. %(ckey)s [%(topics)s]") \
                         % dict(ckey=ckey_sub, topics=topic_sub)
        else:
            ckeys_line = p_("format of the concept key line",
                            "c.k. %(ckey)s") \
                         % dict(ckey=ckey_sub)

        ckeys_line = wtext(ckeys_line, "p", {"class":"ckeys"})
        accl(ckeys_line)

        # Terms in all environments.
        # Compose lines per environment, in weighted-sorted order.
        aterms = []
        term_lines = []
        for weight, wenvs in self._envs_by_weight:
            # Sort envs of current weight lexicographically.
            wenv_packs = {}
            for wenv in wenvs:
                wename = tf(le_(gloss.environments[wenv].shortname)[0].text)
                wenv_packs[wenv] = wename
            wenv_packs = self._envsort(wenv_packs)

            # Compose the term line per environment.
            for wenv, wename in wenv_packs:
                tline, terms = self._fmt_terms_line(concept, wenv,
                                                    wtopic=False)
                if tline:
                    term_lines.append((wenv, wename, tline))
                for term in terms:
                    if term not in aterms:
                        aterms.append(term)

        # Collapse same lines across enivronments.
        term_lines_cl = []
        tlen = len(term_lines)
        i = 0
        while i < tlen:
            wenvs = [term_lines[i][0]]
            wenames = [term_lines[i][1]]
            j = i + 1
            while j < tlen:
                if term_lines[i][2] == term_lines[j][2]:
                    wenvs.append(term_lines[j][0])
                    wenames.append(term_lines[j][1])
                    term_lines.pop(j)
                    tlen -= 1
                else:
                    j += 1
            term_lines_cl.append((wenvs, wenames, term_lines[i][2]))
            i += 1

        # Present in a table.
        accl(stag("table", {"class":"terms-table",
                            "border":"0", "width":"100%"}))
        for wenvs, wenames, tline in term_lines_cl:
            accl(stag("tr", {"class":"terms-row"}), 1)
            fenvs = self._fmt_env_list(wenvs)
            fenvs = wtext(fenvs, "nobr")
            accl(wtext(fenvs, "td", {"class":"terms-cell-envs"}), 2)
            accl(wtext(tline, "td", {"class":"terms-cell-terms"}), 2)
            accl(etag("tr"), 1)
        accl(etag("table"))

        # TODO:
        # Level.

        return aterms, accl


    def _fmt_env_list (self, wenvs, omit=True):
        """
        Format list of environments (given by keys) into sequence of
        linked short names, e.g. for displaying next to a term.

        When there are several environments, the hierarchically lower
        environments will be omitted when a higher one is also in the list.
        Controlled by C{omit} parameter.
        """

        gloss = self._gloss
        tf = self._tf
        le_ = self._dset_pick
        crtop = self._crtop

        # Equip links to environment names.
        # Omit environments which inherit previous in the list.
        wenames_linked = []
        prev_wenvs = []
        for wenv in wenvs:
            wenvob = gloss.environments[wenv]
            wename = tf(le_(gloss.environments[wenv].shortname)[0].text)
            omit = False
            for prev_wenv in prev_wenvs:
                if prev_wenv in wenvob.closeto:
                    omit = True
                    break
            if not omit:
                if wenvob.meta:
                    wename = wtext(wename, "span", {"class":"env-meta"})
                else:
                    wename = wtext(wename, "span", {"class":"env"})
                wename = wtext(wename, "a",
                               {"href":self._glref(wenvob, crtop)})
                wenames_linked.append(wename)
            prev_wenvs.append(wenv)

        fenvs = "/".join(wenames_linked)
        if len(wenames_linked) < len(prev_wenvs):
            fenvs = p_("list of environments where some have been omitted",
                        "%(envs)s etc.") % dict(envs=fenvs)

        return fenvs


    def _fmt_index (self, accl):

        term_links = self._fmt_index_collect()

        subtitle = p_("page subtitle", "Index of Terms")
        self._fmt_header(accl, subtitle=subtitle, ltop=True)

        for langname, terms in term_links:
            accl(stag("div", {"class":"index-lang-sect"}))
            if len(term_links) > 1:
                # Language header only if more than one language.
                lhdr_line = wtext(langname, "p", {"class":"index-lang-header"})
                accl(lhdr_line, 1)

            loc_terms = []
            palpha = self._term_alpha("...", 1)
            for term, links in terms:
                # See if alphabetical break is needed.
                alpha = self._term_alpha(term, 1)
                if alpha.isalpha() and palpha != alpha:
                    # Build term listing for previous alphabetical division.
                    if loc_terms:
                        self._fmt_index_termlist(accl.newind(1), loc_terms)
                        loc_terms = []

                    # New alphabetical division.
                    palpha = alpha
                    aldiv_line = wtext(alpha, "p", {"class":"index-alpha-div"})
                    accl(aldiv_line, 1)

                loc_terms.append((term, links))
            if loc_terms:
                self._fmt_index_termlist(accl.newind(1), loc_terms)

            accl(etag("div"))
            accl()


    def _fmt_index_termlist (self, accl, term_links):

        ntot = len(term_links)
        ncols = self._options.indcols
        nbycol = ntot // ncols
        if nbycol * ncols < ntot:
            nbycol += 1 # so that each column but last is equally sized

        cells_by_row = [[] for x in range(nbycol)]
        row = 0
        col = 0
        for i in range(ntot):
            term, links = term_links[i]
            if len(links) == 1:
                term_cell = wtext(term, "a", {"class":"index-term",
                                              "href":links[0]})
            else:
                term_cell = term
                flinks = []
                for j in range(len(links)):
                    num = str(j + 1)
                    flink = wtext(num, "a", {"class":"index-term-refnum",
                                             "href":links[j]})
                    flinks.append(flink)
                term_cell += " " + " ".join(flinks)

            if i >= col * nbycol:
                row = 0
                col += 1
            cells_by_row[row].append(term_cell)
            row += 1


        accl(stag("div", {"class":"index-alpha-sect"}))

        colwp = str(round(100.0 / ncols, 0)) + "%"
        accl(stag("table", {"class":"index-term-table",
                            "border":"0", "width":"100%"}), 1)
        for cells in cells_by_row:
            accl(stag("tr", {"class":"index-term-row"}), 2)
            while len(cells) < ncols:
                cells.append("")
            for cell in cells:
                accl(wtext(cell, "td", {"class":"index-term-cell",
                                        "width":colwp}), 3)
            accl(etag("tr"), 2)
        accl(etag("table"), 1)

        accl(etag("div"))


    def _fmt_index_collect (self):

        gloss, lang, env = self._gloss, self._lang, self._env
        tf = self._tf
        le_ = self._dset_pick

        # Terms with links to pages, nested as:
        # dict by language -> dict by term -> list of links
        term_links = {lang:{}}
        for page, concepts in self._pages_concepts:
            for concept in concepts:
                lang_terms = {}
                if self._pivoted:
                    terms = concept.term(lang, env)
                    lang_terms[lang] = [tf(x.nom.text) for x in terms]
                    if not self._options.no_term_olang:
                        for olang in concept.term.langs():
                            if olang == lang:
                                continue
                            oterms = concept.term(olang, env)
                            lang_terms[olang] = [tf(x.nom.text) for x in oterms]
                else:
                    for olang in concept.term.langs():
                        lang_terms[olang] = []
                        for oenv in concept.term.envs(olang):
                            oterms = concept.term(olang, oenv)
                            lang_terms[olang].extend([tf(x.nom.text)
                                                      for x in oterms])

                ckey = concept.id
                cbase = self._ckeys_to_filenames[ckey]
                if cbase:
                    page = self._concept_base + "/" + cbase
                else:
                    page = self._concepts_fname
                cref = page + "#" + ckey
                for olang in lang_terms:
                    if olang not in term_links:
                        term_links[olang] = {}
                    lang_term_links = term_links[olang]
                    for fterm in lang_terms[olang]:
                        if fterm not in lang_term_links:
                            lang_term_links[fterm] = []
                        if cref not in lang_term_links[fterm]:
                            lang_term_links[fterm].append(cref)

        # Eliminate terms in pivot language equal to terms
        # in other languages and naming exact same concepts.
        olangs = [x for x in term_links.keys() if x != lang]
        if not self._options.no_term_olang:
            term_links_filtered = {}
            for term, links in term_links[lang].iteritems():
                matched = False
                for olang in olangs:
                    olinks = term_links[olang].get(term)
                    if links == olinks:
                        matched = True
                        break
                if not matched:
                    term_links_filtered[term] = links
            term_links[lang] = term_links_filtered

        # Sorted terms with link, nested as:
        # list of (langname, list of (terms, list of links))
        # Keep pivot language entry out of the list.
        term_links_sorted = []
        for olang in term_links:
            olname = tf(le_(gloss.languages[olang].name)[0].text)
            if olang != lang:
                term_links_sorted.append((olname, []))
                csorted = term_links_sorted[-1]
            else:
                term_links_sorted_pivlang = (olname, [])
                csorted = term_links_sorted_pivlang
            clinks = term_links[olang]
            for term in clinks:
                csorted[1].append((term, clinks[term]))
            langsort_tuples(csorted[1], 0, olang)

        # Put pivot language first, sort rest by language name.
        langsort_tuples(term_links_sorted, 0, lang)
        term_links_sorted.insert(0, term_links_sorted_pivlang)

        return term_links_sorted


    def _fmt_global (self, fmt_global_x, fpath):

        accl = LineAccumulator(self._indent)
        self._fmt_prologue(accl, base=self._artop)
        fmt_global_x(accl.newind(2))
        self._fmt_epilogue(accl)
        accl.write(fpath)


    def _fmt_global_entry_basics (self, accl, gobj):

        tf, tfp = self._tf, self._tfp
        le_ = self._dset_pick

        gp = self._globals_props[gobj.__class__.__name__]

        # Header.
        hdr_line = ""

        # - name
        names = le_(gobj.name) # assume name exists
        fname = tf(names[0].text)
        if getattr(gobj, "meta", False):
            fname = wtext(fname, "span", {"class":"about-entry-name-meta"})
        else:
            fname = wtext(fname, "span", {"class":"about-entry-name"})
        shnames = le_(gobj.shortname)

        # - email
        femail = ""
        email = getattr(gobj, "email", None)
        if email:
            femail = tf(email.text)
            femail = wtext(femail, "a", {"class":"email",
                                         "href":"mailto:"+femail})

        # - url
        furl = ""
        url = getattr(gobj, "url", None) or getattr(gobj, "browseurl", None)
        if url:
            furl = tf(url.text)
            p = furl.find("://")
            if p >= 0:
                ltext = furl[p+3:]
            else:
                ltext = furl
                furl = "http://" + furl
            furl = wtext(ltext, "a", {"class":"ext", "href":furl})

        # - short name
        fshname = ""
        if shnames:
            fshname = tf(shnames[0].text)
            fshname = wtext(fshname, "span", {"class":"about-entry-shname"})


        if fshname and femail and furl:
            hdr = p_("about pages: entry header",
                     "%(name)s (short: %(shortname)s) &lt;%(email)s&gt; "
                     "-- %(url)s") \
                  % dict(name=fname, shortname=fshname, email=femail, url=furl)
        elif fshname and femail:
            hdr = p_("about pages: entry header",
                     "%(name)s (short: %(shortname)s) &lt;%(email)s&gt;") \
                  % dict(name=fname, shortname=fshname, email=femail)
        elif fshname and furl:
            hdr = p_("about pages: entry header",
                     "%(name)s (short: %(shortname)s) -- %(url)s") \
                  % dict(name=fname, shortname=fshname, url=furl)
        elif femail and furl:
            hdr = p_("about pages: entry header",
                     "%(name)s &lt;%(email)s&gt; -- %(url)s") \
                  % dict(name=fname, email=femail, url=furl)
        elif fshname:
            hdr = p_("about pages: entry header",
                     "%(name)s (short: %(shortname)s)") \
                  % dict(name=fname, shortname=fshname)
        elif femail:
            hdr = p_("about pages: entry header",
                     "%(name)s &lt;%(email)s&gt;") \
                  % dict(name=fname, email=femail)
        elif furl:
            hdr = p_("about pages: entry header",
                     "%(name)s -- %(url)s") \
                  % dict(name=fname, url=furl)
        else:
            hdr = fname

        hdr_line = wtext(hdr, "p", {"class":"about-entry-header"})
        accl(hdr_line)

        # Description.
        descs = le_(gobj.desc)
        if descs:
            fdesc = tfp(descs[0].text, pclass="about-desc-para")
            accl(fdesc)


    def _order_objs_by_name (self, entries):

        obj_packs = []
        for obj in entries.itervalues():
            names = self._dset_pick(obj.name)
            if names:
                obj_packs.append((obj, self._tf(names[0].text)))
        langsort_tuples(obj_packs, 1, self._lang)
        return [x for x, y in obj_packs]


    def _fmt_global_environments (self, accl):

        gloss = self._gloss
        tf = self._tf
        le_ = self._dset_pick

        subtitle = p_("page subtitle", "About: Environments")
        self._fmt_header(accl, subtitle=subtitle, base=self._artop, ltop=True)

        # Order for listing.
        key_packs = {}
        for envob in gloss.environments.itervalues():
            names = le_(envob.name)
            if names:
                key_packs[envob.id] = tf(names[0].text)
        key_packs = self._envsort(key_packs)

        for key, dummy in key_packs:
            obj = gloss.environments[key]
            accl(stag("div", {"id":obj.id, "class":"about-entry"}))
            self._fmt_global_entry_basics(accl.newind(1), obj)
            accl(etag("div"))
            accl()


    def _fmt_global_sources (self, accl):

        gloss = self._gloss
        le_ = self._dset_pick

        subtitle = p_("page subtitle", "About: Sources")
        self._fmt_header(accl, subtitle=subtitle, base=self._artop, ltop=True)

        for obj in self._order_objs_by_name(gloss.sources):
            accl(stag("div", {"id":obj.id, "class":"about-entry"}))
            self._fmt_global_entry_basics(accl.newind(1), obj)
            accl(etag("div"))
            accl()


    def _fmt_global_editors (self, accl):

        gloss = self._gloss
        tf = self._tf
        le_ = self._dset_pick

        subtitle = p_("page subtitle", "About: Editors")
        self._fmt_header(accl, subtitle=subtitle, base=self._artop, ltop=True)

        for obj in self._order_objs_by_name(gloss.editors):
            accl(stag("div", {"id":obj.id, "class":"about-entry"}))
            self._fmt_global_entry_basics(accl.newind(1), obj)

            # - affiliation
            affs = le_(obj.affiliation)
            if affs:
                faffs = "; ".join([tf(x.text) for x in affs])
                aff_line = p_("editor's affiliation",
                              "Affiliation: %(aff)s") \
                           % dict(aff=faffs)
                aff_line = wtext(aff_line, "p", {"class":"about-affiliation"})
                accl(aff_line)

            accl(etag("div"))
            accl()


    def _fmt_global_topics (self, accl):

        gloss = self._gloss
        le_ = self._dset_pick

        subtitle = p_("page subtitle", "About: Topics")
        self._fmt_header(accl, subtitle=subtitle, base=self._artop, ltop=True)

        for obj in self._order_objs_by_name(gloss.topics):
            accl(stag("div", {"id":obj.id, "class":"about-entry"}))
            self._fmt_global_entry_basics(accl.newind(1), obj)
            accl(etag("div"))
            accl()


    def _write_access_info (self, root):

        # Apache.
        accl = LineAccumulator(self._indent)
        accl("AddType application/xhtml+xml .html")
        accl("AddCharset UTF-8 .html")
        accl.write(os.path.join(root, ".htaccess"))

