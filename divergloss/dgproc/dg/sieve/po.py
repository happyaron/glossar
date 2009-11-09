# -*- coding: UTF-8 -*-

"""
Create a PO file out of the glossary.

The glossary must be at least bilingual by terms.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import sys
import time

from dg.util import p_
from dg.util import error, warning
from dg.textfmt import TextFormatterPlain
from dg.util import langsort_tuples
from dg.util import lstr


def fill_optparser (parser_view):

    pv = parser_view

    pv.set_desc(p_("subcommand description",
                   "Create a PO file out of the glossary."))

    pv.add_subopt("olang", str,
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Original language from the PO point of view."))
    pv.add_subopt("tlang", str,
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Target language from the PO point of view."))
    pv.add_subopt("env", str, defval="",
                  metavar=p_("placeholder for parameter value", "ENVKEY"),
                  desc=p_("subcommand option description",
                          "Environment for which the PO file is produced."))
    pv.add_subopt("file", str, defval="",
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "File to output the PO content (defaults to stdout)."))
    pv.add_subopt("condesc", bool, defval=False,
                  desc=p_("subcommand option description",
                          "Show descriptions only on conflicts, for concepts "
                          "having terms also used to name other concepts."))


class Subcommand (object):

    def __init__ (self, options, global_options):

        self._options = options


    def __call__ (self, gloss):

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

        # Formatters for resolving glossary into plain text.
        tft = TextFormatterPlain(gloss, lang=tlang, env=env)
        s_desc = p_("message comment in the PO view: "
                    "short label preceeding a concept description",
                    "desc: ")
        cpref = "# "
        tfds = TextFormatterPlain(gloss, lang=tlang, env=env,
                                  first_indent=(cpref + s_desc),
                                  indent=(cpref + " " * len(s_desc)),
                                  wcol=79)
        s_decl = p_("message comment in the PO view: "
                    "short label preceeding a declination",
                    "decl: ")
        tfdl = TextFormatterPlain(gloss, lang=tlang, env=env,
                                  prefix=(cpref + s_decl))

        # Select all concepts which have a term in both langenvs.
        # Collect terms from the origin language for lexicographical ordering.
        concepts = {}
        ordering_links = []
        for ckey, concept in gloss.concepts.iteritems():
            oterms = concept.term(olang, env)
            tterms = concept.term(tlang, env)
            if oterms and tterms:
                concepts[ckey] = concept
                # Use first of the synonymous origin terms for ordering.
                # Must format it to plain text beforehand.
                ordering_links.append((tft(oterms[0].nom.text).lower(), ckey))

        if not concepts:
            warning(p_("warning message",
                       "no concepts found for PO view that have terms in both "
                       "the requested origin and target language"))

        langsort_tuples(ordering_links, 0, olang)

        if self._options.condesc:
            # Collect keys of all concepts which have same terms for different
            # concepts, in either of the languages.
            all_ckeys_by_term = {}
            for ckey, concept in concepts.iteritems():
                aterms = (  concept.term(olang, env)
                          + concept.term(tlang, env))
                for term in aterms:
                    nomstr = tft(term.nom.text)
                    if nomstr not in all_ckeys_by_term:
                        all_ckeys_by_term[nomstr] = []
                    all_ckeys_by_term[nomstr].append(ckey)
            conflicted = {}
            for nomstr, ckeys in all_ckeys_by_term.iteritems():
                if len(ckeys) > 1:
                    for ckey in ckeys:
                        conflicted[ckey] = True

        # Create PO messages by fields.
        class Message:
            def __init__ (self):
                self.comments = []
                self.msgctxt = ""
                self.msgid = ""
                self.msgstr = ""

        tdelim = "|" # delimiter for synonyms in msgid and msgstr

        messages = []
        for ckey in [x[1] for x in ordering_links]:
            concept = concepts[ckey]
            msg = Message()
            messages.append(msg)

            # Origin terms into the msgid.
            oterms = concept.term(olang, env)
            msg.msgid = tdelim.join([tft(x.nom.text) for x in oterms])

            # Target terms into the msgstr.
            tterms = concept.term(tlang, env)
            msg.msgstr = tdelim.join([tft(x.nom.text) for x in tterms])

            # Concept key into the msgctxt.
            msg.msgctxt = ckey

            # Auto comments.
            # - full description (possibly only if there is a term conflict)
            if not self._options.condesc or ckey in conflicted:
                # Give priority to description in target language.
                descs = concept.desc(tlang, env)
                if not descs:
                     descs = concept.desc(olang, env)
                if descs:
                    # Pick only first description if there are several.
                    msg.comments.append(tfds(descs[0].text))
            # - any declensions in target language
            for tterm in tterms:
                for decl in tterm.decl:
                    grn = gloss.grammar[decl.gr].shortname(tlang, env)[0]
                    msg.comments.append(tfdl(grn.text + [" "] + decl.text))

            # TODO: Implement source reference when lxml.etree can extract them.

        # Format PO header for output.
        fmt_header = ""
        s_title = tft(gloss.title(tlang, env)[0].text)
        fmt_header += (  '# '
                       + p_('header comment in the PO view (title)',
                            'PO view of a Divergloss glossary: %(title)s')
                         % dict(title=s_title)
                       + '\n')
        s_olang = tft(gloss.languages[olang].name(tlang, env)[0].text)
        s_tlang = tft(gloss.languages[tlang].name(tlang, env)[0].text)
        if env:
            s_env = tft(gloss.environments[env].name(tlang, env)[0].text)
            hcmnt = p_('header comment in the PO view (subtitle)',
                       'languages: %(ol)s->%(tl)s, environment: %(env)s') \
                    % dict(ol=s_olang, tl=s_tlang, env=s_env)
        else:
            hcmnt = p_('header comment in the PO view (subtitle)',
                       'languages: %(ol)s->%(tl)s') \
                    % dict(ol=s_olang, tl=s_tlang)
        fmt_header += (  '# '
                       + hcmnt
                       + '\n')
        fmt_header += (  '# '
                       + p_('comment in generated files (warning to user)',
                            '===== AUTOGENERATED FILE, DO NOT EDIT =====')
                       + '\n')
        fmt_header += 'msgid ""\n'
        fmt_header += 'msgstr ""\n'
        fmt_header += '"Project-Id-Version: %s\\n"\n' % gloss.id
        fmt_header += '"POT-Creation-Date: %s\\n"\n' % time.strftime("%F %R%z")
        fmt_header += '"PO-Revision-Date: %s\\n"\n' % time.strftime("%F %R%z")
        fmt_header += '"Last-Translator: n/a\\n"\n'
        fmt_header += '"Language-Team: n/a\\n"\n'
        fmt_header += '"MIME-Version: 1.0\\n"\n'
        fmt_header += '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        fmt_header += '"Content-Transfer-Encoding: 8bit\\n"\n'

        # Format PO messages for output.
        def poescape (s):
            return s.replace('\n', '\\n').replace('"', '\\"')

        fmt_messages = []
        for msg in messages:
            fmt_msg = ''
            if msg.comments:
                fmt_msg += '\n'.join(msg.comments) + '\n'
            fmt_msg += 'msgctxt "%s"\n' % poescape(msg.msgctxt)
            fmt_msg += 'msgid "%s"\n' % poescape(msg.msgid)
            fmt_msg += 'msgstr "%s"\n' % poescape(msg.msgstr)
            fmt_messages.append(fmt_msg)

        # Output formatted concepts to requested stream.
        outf = sys.stdout
        if self._options.file:
            outf = open(self._options.file, "w")

        outf.write(fmt_header + "\n")
        outf.write("\n".join(fmt_messages) + "\n")

        if outf is not sys.stdout:
            outf.close()

        # All done.

