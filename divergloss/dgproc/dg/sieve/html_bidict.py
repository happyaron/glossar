# -*- coding: UTF-8 -*-

"""
Create HTML table with bilingual dictionary.

For example, having a bilingual English/Serbian (en/sr) glossary C{gloss.xml},
the HTML page with the dictionary table could be created by::

    $ dgproc.py html-bidict gloss.xml -s olang:en -s tlang:sr \ 
                                      -s file:gloss.html -s style:igloo

The C{olang} parameter specifies the original language for the dictionary,
and C{tlang} the target language. The C{file} parameter names the file
of the resulting HTML page, as well as the basename for the accompanying
style sheet and JavaScript control files included by the HTML page header.
The C{style} parameter selects one of the internal style sheets
(which are listed in the sieve help, using C{--help-sieve} option).
The given command will ultimately produce three files: C{gloss.html},
C{gloss.css}, and C{gloss.js}.

The HTML page will contain only a single compact two-column table, with
the left column containing distinct terms from the original language,
and the right column the corresponding terms in the target language.
If, for a given original term, there are several target terms, and all
of them name name the same concept, the target terms will be given as
a comma-separated list in the right column. On the other hand,
if the original term names several different concepts, and there are
different target terms for them, such target terms will be given
one below the other in the right column, as an enumerated list.

The description and other details on the concepts behind each term
in the target language will be provided as folded sections of the table,
which can be unrolled with a +/- button somewhere in the table row.
If there several concepts are named by the same term, the details of
all of them are given in the folding section for that term.

The C{style} parameter is optional; if not given, the page will be left
without a style sheet. This is handy when the user has prepared
an own style sheet (which can be based on one of the internal sheets);
in such case, the user will probably also make use of the C{header} parameter.

Using the parameters C{header} and C{footer}, the user can specify text
files to be prepended before and appended after the HTML code for the table
(without them, the sieve provides minimal header and footer to make
a valid standalone HTML page).

The user can explicitly specify names for the accompanying CSS and JS files
to be created, using the C{cssfile} and C{jsfile} parameters,
instead of these names being derived from the name of the HTML file.
Again, this is mostly useful in conjunction with external header and footer.

Instead of creating separate CSS and JS files, using C{phpinc} parameter
both the style sheet and control functions can be written into a single file,
wrapped in appropriate tags for PHP inclusion into the body of the HTML file.
The file name of this file too will be derived from the HTML file name as
C{gloss.inc}, but an explicit name can be given by the C{incfile} parameter.
Note that in this case the file name of the page (given by C{file} parameter)
should probably end in C{.php}.

Finally, both the CSS and JS content can be directly embedded into the page,
so that only this one HTML file is produced by the sieve. This is done by
specifyng the C{allinone} parameter. Note that it conflicts all parameters
which deal with auxiliary files for inclusion.

If the glossary contains several environments, one of them may be selected
by the usual C{env} parameter. If not given, the default environment is used.
Only those concepts which have at least one term in the original and target
language and environment will be used as sources of terms.

Internal style sheets (as selected by the C{style} parameter) contain
some values which can be tuned through the command line using the C{styleopt}
parameter. It takes a comma-separated list of C{name=value} pairs.
For example, to set the width of the column with terms in the original
language to a third of the table width, use::

    $ dgproc.py html-bidict ... -sstyleopt:'oterm_col_width=33%'

Available style options are listed in the sieve help (C{-H}),
under the description of the C{styleopt} parameter.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import os
import shutil
import re

from dg import rootdir
from dg.util import p_
from dg.util import error, warning

from dg.textfmt import TextFormatterPlain, TextFormatterHtml
from dg.textfmt import etag, stag, wtext
from dg.textfmt import LineAccumulator
from dg.util import langsort, langsort_tuples
from dg.util import mkdirpath


_src_style_dir = os.path.join(rootdir(), "sieve", "html_bidict_extras", "style")
_src_dctl_file = os.path.join(rootdir(), "sieve", "html_bidict_extras", "dctl.js")

# Style elements which may be specified through the command line.
_styleopt_spec = [
    ("oterm_col_width", "10em",
     p_("style option description",
        "The width of the column with terms in the original language. "
        "It can be set in absolute terms, e.g. '10em' for 10 widths of M, "
        "or relative, e.g. '33%' for a third of the table width.")),
]


def fill_optparser (parser_view):

    # Collect available CSS sheets.
    styles = [""]
    for item in os.listdir(_src_style_dir):
        path = os.path.join(_src_style_dir, item)
        if os.path.isfile(path) and path.endswith(".css.in"):
            p = item.rfind(".css.in")
            styles.append(item[:p])

    pv = parser_view

    pv.set_desc(p_("subcommand description",
                   "Create HTML page with bilingual dictionary."))

    pv.add_subopt("olang", str,
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Original language in the dictionary."))
    pv.add_subopt("tlang", str,
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Target language in the dictionary."))
    pv.add_subopt("env", str, defval="",
                  metavar=p_("placeholder for parameter value", "ENVKEY"),
                  desc=p_("subcommand option description",
                          "Environment for which the dictionary is produced. "
                          "If not given, the glossary default is used."))
    pv.add_subopt("file", str,
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File to output the HTML page to."))
    pv.add_subopt("style", str, defval="", admvals=styles,
                  metavar=p_("placeholder for parameter value", "STYLE"),
                  desc=p_("subcommand option description",
                          "Style sheet for the HTML page. "
                          "If not given, the page will not be styled."))
    pv.add_subopt("cssfile", str, defval="",
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File path where to copy the selected style sheet, "
                          "relative to the directory of the HTML page file. "
                          "If not given, the path is constructed as that of "
                          "the HTML page, with extension replaced by .css."))
    pv.add_subopt("jsfile", str, defval="",
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File path where to copy the JavaScript functions, "
                          "relative to the directory of the HTML page file. "
                          "If not given, the path is constructed as that of "
                          "the HTML page, with extension replaced by .js."))
    pv.add_subopt("phpinc", bool, defval=False,
                  desc=p_("subcommand option description",
                          "Place both the style sheet and the JavaScript "
                          "functions into a single file, wrapped in "
                          "appropriate tags for PHP inclusion into "
                          "the body of the HTML page."))
    pv.add_subopt("incfile", str, defval="",
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File path of the file for raw inclusion, "
                          "relative to the directory of the HTML page file. "
                          "If not given, the path is constructed as that of "
                          "the HTML page, with extension replaced by .inc."))
    pv.add_subopt("header", str, defval="",
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File that contains the page header section to use "
                          "instead of the default, including the <body> "
                          "tag and possibly some preface text."))
    pv.add_subopt("footer", str, defval="",
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File that contains the page footer section to use "
                          "instead of the default, possibly including some "
                          "closing text before the </body> tag."))
    pv.add_subopt("allinone", bool, defval=False,
                  desc=p_("subcommand option description",
                          "Create only the HTML page file, with style sheet "
                          "and control functions embedded in it."))

    styleopts = "\n\n".join(["%s [%s]: %s" % x for x in _styleopt_spec])
    pv.add_subopt("styleopt", str, multival=True, seplist=True, defval=[],
                  metavar=p_("placeholder for parameter value",
                             "NAME=VALUE,..."),
                  desc=p_("subcommand option description",
                          "Some elements of internal style sheets may be "
                          "customized, by providing a comma-separated list "
                          "of name=value pairs, drawn from the following set "
                          "(default values in brackets):\n"
                          "\n"
                          "%(ellist)s") % dict(ellist=styleopts))


class Subcommand (object):

    def __init__ (self, options, global_options):

        self._options = options


    def __call__ (self, gloss):

        self._indent = "  "

        # Resolve languages and environment.
        olang = self._options.olang
        if olang not in gloss.languages:
            error(p_("error message",
                     "origin language '%(lang)s' not present in the glossary")
                    % dict(lang=olang))
        tlang = self._options.tlang
        if tlang not in gloss.languages:
            error(p_("error message",
                     "target language '%(lang)s' not present in the glossary")
                    % dict(lang=tlang))
        env = self._options.env or gloss.env[0]
        if env is not None and env not in gloss.environments:
            error(p_("error message",
                     "environment '%(env)s' not defined by the glossary")
                  % dict(env=env))

        # Select all concepts which have a term in both langenvs.
        concepts = {}
        for ckey, concept in gloss.concepts.iteritems():
            if concept.term(olang, env) and concept.term(tlang, env):
                concepts[ckey] = concept
        if not concepts:
            warning(p_("warning message",
                       "no concepts found which have terms in both "
                       "the origin and the target language and environment"))

        # Prepare text formatters.
        refbase = dict([(ckey, "") for ckey in concepts])
        tfn = TextFormatterPlain(gloss, lang=tlang, env=env)
        tf = TextFormatterHtml(gloss, lang=tlang, env=env, refbase=refbase)
        tfp = TextFormatterHtml(gloss, lang=tlang, env=env, refbase=refbase,
                                wtag="p")

        # Dictionary is presented as follows:
        # - all unique terms in the origin language presented
        # - for each unique origin term, all corresponding unique terms
        #   in the target language presented
        # - for each unique (origin, target) term pair, the descriptions of
        #   all concepts named by it are presented in the target language

        # Collect dict(oterm: dict(tterm: set(ckey)))
        # Collect dict(tterm: dict(gr: set(decl)))
        tdecls = {}
        bidict = {}
        for ckey, concept in concepts.iteritems():
            oterms = concept.term(olang, env)
            tterms = concept.term(tlang, env)
            for oterm in oterms:
                otnom = tfn(oterm.nom.text)
                if otnom not in bidict:
                    bidict[otnom] = {}
                for tterm in tterms:
                    # Target terms.
                    ttnom = tfn(tterm.nom.text)
                    if ttnom not in bidict[otnom]:
                        bidict[otnom][ttnom] = set()
                    bidict[otnom][ttnom].add(ckey)

                    # Declensions.
                    if ttnom not in tdecls:
                        tdecls[ttnom] = {}
                    for decl in tterm.decl:
                        gr = gloss.grammar[decl.gr]
                        grnam = tfn(gr.shortname(tlang, env)[0].text)
                        if grnam not in tdecls[ttnom]:
                            tdecls[ttnom][grnam] = set()
                        ttdecl = tfn(decl.text)
                        tdecls[ttnom][grnam].add(ttdecl)

        # Alphabetically sort origin terms.
        oterms_sorted = bidict.keys()
        langsort(oterms_sorted, olang)

        # Compose the dictionary table.
        accl = LineAccumulator(self._indent, 2)

        accl(stag("table", {"class":"bd-table"}))
        accl()

        # Header.
        accl(stag("tr", {"class":"bd-header"}), 1)
        olname = tfn(gloss.languages[olang].name(tlang, env)[0].text)
        accl(wtext(olname, "th", {"class":"bd-header-ol"}), 2)
        tlname = tfn(gloss.languages[tlang].name(tlang, env)[0].text)
        accl(wtext(tlname, "th", {"class":"bd-header-tl"}), 2)
        accl(etag("tr"), 1)

        # Entries by origin term.
        anchored = {}
        n_entry = 0
        n_entry_by_alpha = 0
        curr_alpha = None
        for oterm in oterms_sorted:
            n_entry += 1
            n_entry_by_alpha += 1

            # Add new alphabetical separator if needed.
            prev_alpha = curr_alpha
            curr_alpha = _term_alpha(oterm)
            if prev_alpha != curr_alpha:
                n_entry_by_alpha = 1
                accl(stag("tr", {"class":"bd-alsep"}), 1)
                accl(wtext(curr_alpha, "td", {"class":"bd-alsep-al",
                                              "colspan":"2"}), 2)
                accl(etag("tr"), 1)

            # Collapse all target terms which have same concepts.
            # Sort them alphabetically within the group,
            # then groups alphabetically by first term in the group.
            tterms_by_ckeygr = {}
            for tterm in bidict[oterm]:
                ckeys = list(bidict[oterm][tterm])
                ckeys.sort()
                ckeygr = tuple(ckeys)
                if ckeygr not in tterms_by_ckeygr:
                    tterms_by_ckeygr[ckeygr] = []
                tterms_by_ckeygr[ckeygr].append(tterm)
            tterms_groups = []
            for ckeys, tterms in tterms_by_ckeygr.iteritems():
                langsort(tterms, tlang)
                tterms_groups.append((tterms[0], tterms, ckeys))
            langsort_tuples(tterms_groups, 0, tlang)
            tterms_ckeys = [x[1:] for x in tterms_groups]

            if n_entry_by_alpha % 2 == 1:
                accl(stag("tr", {"class":"bd-entry-odd"}), 1)
            else:
                #accl(stag("tr", {"class":"bd-entry-even"}), 1)
                #... provide as option; randomly increases VCS deltas.
                accl(stag("tr", {"class":"bd-entry-odd"}), 1)

            # Column with origin term and anchors.
            accl(stag("td", {"class":"bd-oterm"}), 2)

            # Dummy anchors, for cross-references in descriptions to work.
            # Add anchors for all concepts covered by this entry,
            # and remember them, to avoid duplicate anchors on synonyms.
            new_ckeys = []
            for tterms, ckeys in tterms_ckeys:
                for ckey in ckeys:
                    if ckey not in anchored:
                        anchored[ckey] = True
                        new_ckeys.append(ckey)
            accl("".join([stag("span", {"id":x}, close=True)
                          for x in new_ckeys]), 3)

            # Origin term.
            accl(wtext(oterm, "p", {"class":"bd-otline"}), 3)
            accl(etag("td"), 2)

            # Column with target terms.
            accl(stag("td", {"class":"bd-tterms"}), 2)

            n_ttgr = 0
            for tterms, ckeys in tterms_ckeys:
                n_ttgr += 1
                accl(stag("div", {"class":"bd-ttgroup"}), 3)

                # Equip each term with extra info.
                tterms_compgr = []
                for tterm in tterms:
                    # Declensions.
                    lsep_dc = p_("list separator: "
                                 "acceptable variants of the same declension",
                                 ", ")
                    fmt_dcgr = p_("declension group: single declension given "
                                  "by its name and acceptable variants",
                                  "<i>%(dname)s</i> %(dvars)s")
                    lsep_gr = p_("list separator: "
                                 "declension groups",
                                 "; ")
                    tdecl = None
                    if tterm in tdecls:
                        lst = []
                        for gr, decls in tdecls[tterm].iteritems():
                            lst2 = list(decls)
                            langsort(lst2, tlang)
                            lst.append((gr, lsep_dc.join(lst2)))
                        langsort_tuples(lst, 0, tlang)
                        tdecl = lsep_gr.join([fmt_dcgr % dict(dname=x[0],
                                                              dvars=x[1])
                                              for x in lst])
                    # Compose.
                    if tdecl:
                        ttcgr = p_("term with declensions",
                                   "%(term)s (%(decls)s)") \
                                % dict(term=tterm, decls=tdecl)
                    else:
                        ttcgr = tterm
                    tterms_compgr.append(ttcgr)

                # Collect details for each term.
                has_details = False
                # - descriptions
                descstrs = []
                for ckey in ckeys:
                    for desc in concepts[ckey].desc(tlang, env):
                        if tfn(desc.text):
                            descstrs.append(tfp(desc.text, pclass="bd-desc"))
                            has_details = True
                if len(descstrs) > 1:
                    for i in range(len(descstrs)):
                        dhead = "%d. " % (i + 1)
                        descstrs[i] = descstrs[i].replace(">", ">" + dhead, 1)

                # Entry display control (if any details present).
                details_id = "opt_%s_%d" % (oterm.replace(" ", "_"), n_ttgr)
                if has_details:
                    accl(stag("div", {"class":"bd-edctl"}), 4)
                    accl(wtext("[+]", "a",
                               {"class":"bd-edctl",
                                "title":p_("tooltip", "Show details"),
                                "href":"#",
                                "onclick":"return show_hide(this, '%s')"
                                          % details_id}), 5)
                    accl(etag("div"), 4)

                # Line with terms.
                lsep_tt = p_("list separator: synonymous terms",
                             ", ")
                ttstr = lsep_tt.join(tterms_compgr)
                if len(tterms_ckeys) > 1:
                    ttstr = p_("enumerated target term in the dictionary, "
                               "one of the meanings of the original term",
                               "%(num)d. %(term)s") \
                            % dict(num=n_ttgr, term=ttstr)
                accl(wtext(ttstr, "p", {"class":"bd-ttline"}), 4)

                # Optional details.
                if has_details:
                    accl(stag("div", {"id":details_id,
                                      "style":"display: none;"}), 4)

                    for descstr in descstrs:
                        accl(descstr, 5)

                    accl(etag("div"), 4)

                accl(etag("div"), 3)

            accl(etag("td"), 2)
            accl(etag("tr"), 1)
            accl()

        accl(etag("table"))
        accl()

        # Prepare style file path.
        stylepath = None
        if self._options.style:
            if self._options.cssfile:
                stylepath = self._options.cssfile
            else:
                stylepath = _replace_ext(os.path.basename(self._options.file),
                                         "css")
            stylepath_nr = os.path.join(os.path.dirname(self._options.file),
                                        stylepath)
            stylesrc = os.path.join(  _src_style_dir, self._options.style
                                    + ".css.in")

        # Prepare JavaScript file path.
        dctlpath = None
        if self._options.jsfile:
            dctlpath = self._options.jsfile
        else:
            dctlpath = _replace_ext(os.path.basename(self._options.file), "js")
        dctlpath_nr = os.path.join(os.path.dirname(self._options.file),
                                   dctlpath)

        # Prepare PHP inclusion file path.
        phpincpath = None
        if self._options.incfile:
            phpincpath = self._options.incfile
        else:
            phpincpath = _replace_ext(os.path.basename(self._options.file),
                                      "inc")
        phpincpath_nr = os.path.join(os.path.dirname(self._options.file),
                                     phpincpath)

        # If style requested, fetch the .in file and resolve placeholders.
        if self._options.style:
            # Parse values given in the command line.
            stodict = dict([x[:2] for x in _styleopt_spec])
            for sopt in self._options.styleopt:
                lst = [x.strip() for x in sopt.split("=", 1)]
                if len(lst) < 2:
                    warning(p_("warning message",
                               "malformed CSS style option '%(opt)s'")
                            % dict(opt=sopt))
                    continue
                name, value = lst
                if name not in stodict:
                    warning(p_("warning message",
                               "unknown CSS style option '%(opt)s'")
                            % dict(opt=sopt))
                    continue
                stodict[name] = value

            # Replace placeholders in the input style sheet.
            raccl = LineAccumulator()
            raccl.read(stylesrc)
            styleaccl = LineAccumulator()
            sto_rx = re.compile("@(\w+)@")
            for line in raccl.lines:
                nline = ""
                lastpos = 0
                for m in sto_rx.finditer(line):
                    nline += line[lastpos:m.span()[0]]
                    lastpos = m.span()[1]
                    soname = m.group(1)
                    sovalue = stodict.get(soname)
                    if soname not in stodict:
                        error(p_("error message",
                                 "unknown CSS style option '%(opt)s' "
                                 "requested by the input style sheet "
                                 "'%(fname)s'")
                              % dict(opt=soname, fname=stylesrc))
                    nline += sovalue
                nline += line[lastpos:]
                styleaccl(nline)

        # Create separate CSS and JS files, or raw inclusion file,
        # or collect everything for direct embedding.
        auxaccl = None
        if not self._options.phpinc and not self._options.allinone:
            shutil.copyfile(_src_dctl_file, dctlpath_nr)
            if self._options.style:
                styleaccl.write(stylepath_nr)
            phpincpath = None # _fmt_header checks this for what to include
        else:
            raccl = LineAccumulator()
            raccl("<script type='text/javascript'>")
            raccl.read(_src_dctl_file)
            raccl("</script>")
            raccl()
            if self._options.style:
                raccl("<style type='text/css'>")
                raccl(styleaccl)
                raccl("</style>")
                raccl()
            if not self._options.allinone:
                raccl.write(phpincpath_nr)
            else:
                auxaccl = raccl

        # Header.
        accl_head = LineAccumulator(self._indent, 0)
        if not self._options.header:
            gname = tfn(gloss.title(tlang, env)[0].text)
            if env:
                ename = tfn(gloss.environments[env].name(tlang, env)[0].text)
                title = p_("top page title",
                           "%(gloss)s (%(env)s)") \
                        % dict(gloss=gname, env=ename)
            else:
                title = gname
            self._fmt_header(accl_head, tlang, title,
                             stylepath, dctlpath, phpincpath)
        else:
            accl_head.read(self._options.header)

        # Footer.
        accl_foot = LineAccumulator(self._indent, 0)
        if not self._options.footer:
            self._fmt_footer(accl_foot)
        else:
            accl_foot.read(self._options.footer)

        # Collect everything and write out the HTML page.
        accl_all = LineAccumulator(self._indent, 0)
        accl_all(accl_head)
        if auxaccl:
            accl_all(auxaccl, 2)
        accl_all(accl)
        accl_all(accl_foot)
        accl_all.write(self._options.file)


    def _fmt_header (self, accl, lang, title,
                           stylepath=None, dctlpath=None, phpincpath=None):
        """
        If C{phpincpath} is given, then PHP inclusion for it is
        issued in the body, while C{stylepath} and C{dctlpath} are ignored.
        Otherwise, HTML inclusions for C{stylepath} and C{dctlpath} are issued
        in the header (if given themselves).
        """

        if not phpincpath:
            accl("<?xml version='1.0' encoding='UTF-8'?>");
        accl(  "<!DOCTYPE html PUBLIC '-//W3C//DTD XHTML 1.0 Strict//EN' "
             + "'http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd'>");
        accl(  "<!-- "
             + p_('comment in generated files (warning to user)',
                  '===== AUTOGENERATED FILE, DO NOT EDIT =====')
             + " -->")

        accl(stag("html", {"xmlns":"http://www.w3.org/1999/xhtml",
                           "lang":lang, "xml:lang":lang}))

        accl(stag("head"), 1)

        accl(stag("meta", {"http-equiv":"Content-type",
                           "content":"text/html; charset=UTF-8"},
                  close=True), 2)

        if not phpincpath:
            if stylepath:
                accl(stag("link", {"rel":"stylesheet", "type":"text/css",
                                   "href":stylepath}, close=True), 2)
            if dctlpath:
                accl(wtext("", "script", {"type":"text/javascript",
                                          "src":dctlpath}), 2)

        accl(wtext(title, "title"), 2)

        accl(etag("head"), 1)

        accl(stag("body"), 1)

        if phpincpath:
            accl("<?php include('%s'); ?>" % phpincpath, 2)

        accl()


    def _fmt_footer (self, accl):

        accl(etag("body"), 1)
        accl(etag("html"))


def _replace_ext (fpath, newext):
    """
    Replace extension of the file name with the new one.

    The new extension is added if the original file name has none.
    """

    p = os.path.basename(fpath).rfind(".")
    if p > 0:
        p = fpath.rfind(".")
        nfpath = fpath[:p] + "." + newext
    else:
        nfpath = fpath + "." + newext

    return nfpath


def _term_alpha (term):
    """
    Alphabetical start of a term given as formatted plain text string.
    """

    alpha = term[:1].title()
    if alpha and not alpha.isalpha():
        alpha = "#"

    return alpha

