# -*- coding: UTF-8 -*-

"""
Update terminology rules file for Pology's C{check-rules} sieve.

Pology's C{check-rules} sieve applies series of pattern rules to messages
in a PO file, reporting all those that matched. Each rule can contain
several matching expressions, applied in different ways, and interlinked
in a boolean-semantic way. The rules are written in special rule files.

This sieve updates such a rule file (or creates a new one), adding
basic skeletons of new rules for checking terminology in translations;
rules must then be edited manually to make them applicable.
This is, in fact, almost of no value from the point of view of
a particular rule, as the core of the rule must be created by the user.
The usefulness of the sieve lies instead in that it can be used to
automatically check if any of the existing rules needs to be changed
due to terminology changes, and add rules for new terminology as it becomes
available, without having to keep track of it manually.

If the glossary file is C{gloss.xml}, and contains English and Serbian terms
(en, sr), the terminology rule file C{term.rules} for English to Serbian
translation is both created and updated using::

    $ dgproc.py plrules gloss.xml -s olang:en -s tlang:sr \ 
                                  -s file:term.rules

The C{olang} and C{tlang} parameters specify original and target language,
and C{file} the name of the rule file to be created/updated.
If the glossary contains several environments, one may be selected by
the C{env} parameter, or else the glossary default environment is used.

Each rule in the rule file corresponds to one of the concepts,
with the C{ident} field set to the concept key.
The terminology pair is given by the rule's C{hint} field, in the form of
C{"<original-terms> = <target-terms> [<free-hints>]"}.
The sieve relies on this field when updating the rule file, to detect and
indicate changes in the terminology. Thus, any manual modifications to
the C{hint} field, e.g. comments to help translators with non-obvious rules,
should be within the square brackets following the terms.

Rules for terminology hierarchies can be maintained using the base environment
parameter, C{benv}. In this mode, first the rules are updated for the
base environment C{foo}, i.e. its key given as C{env}::

    $ dgproc.py plrules ... -s env:foo

and then another set of rules is updated for the inheriting environment C{bar},
such that its key is given as C{env}, and base environment's key as C{benv}::

    $ dgproc.py plrules ... -s env:bar -s benv:foo

Rules for the inheriting environment will be updated only for those concepts
with terminology different to that of the base environment.

Newly added rules will have C{@gloss-new} string in their comment.
Existing rules for which the terminology has changed will get C{@gloss-fuzzy},
while those that no longer have a matching concept will get C{@gloss-obsolete}.
When the base environment is given and the terminology has been changed
to match the base one, C{@gloss-merge} will be set instead of C{@gloss-fuzzy}.

Rule files should be UTF-8 encoded (that is what Pology expects).

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import sys
import os
import time
import codecs
import re

from dg.util import p_
from dg.util import error, warning
from dg.textfmt import TextFormatterPlain
from dg.util import langsort


def fill_optparser (parser_view):

    pv = parser_view

    pv.set_desc(p_("subcommand description",
                   "Update rules files for Pology's check-rules sieve."))

    pv.add_subopt("olang", str,
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Original language from the rules point of view."))
    pv.add_subopt("tlang", str,
                  metavar=p_("placeholder for parameter value", "LANGKEY"),
                  desc=p_("subcommand option description",
                          "Target language from the rules point of view."))
    pv.add_subopt("file", str,
                  metavar=p_("placeholder for parameter value", "FILE"),
                  desc=p_("subcommand option description",
                          "Rules file to update or create."))
    pv.add_subopt("env", str, defval="",
                  metavar=p_("placeholder for parameter value", "ENVKEY"),
                  desc=p_("subcommand option description",
                          "Environment for which the rules are updated. "
                          "The glossary default environment is used "
                          "if not given."))
    pv.add_subopt("benv", str, defval="",
                  metavar=p_("placeholder for parameter value", "ENVKEY"),
                  desc=p_("subcommand option description",
                          "Base environment when making hierarchical rules."))


class Subcommand (object):

    def __init__ (self, options, global_options):

        self._options = options


    def __call__ (self, gloss):

        # Resolve languages and environments.
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
        if env and env not in gloss.environments:
            error(p_("error message",
                     "environment '%(env)s' not defined by the glossary")
                  % dict(env=env))
        benv = self._options.benv
        if benv and benv not in gloss.environments:
            error(p_("error message",
                     "environment '%(env)s' not defined by the glossary")
                  % dict(env=benv))
        rulefile = self._options.file

        # Formatters for resolving glossary into plain text.
        tft = TextFormatterPlain(gloss, lang=tlang, env=env)
        tdelim = "|" # to be able to send terms to regex too

        def format_terms (concept, env=env):

            oterms = concept.term(olang, env)
            tterms = concept.term(tlang, env)
            if not oterms or not tterms:
                return None, None

            oterms = [tft(x.nom.text) for x in oterms]
            langsort(oterms, olang)
            otermsall = tdelim.join(oterms)

            tterms = [tft(x.nom.text) for x in tterms]
            langsort(tterms, tlang)
            ttermsall = tdelim.join(tterms)

            return otermsall, ttermsall

        # From concepts which have a term in both langenvs,
        # assemble the data needed to construct rules.
        # Also collect keys of concepts which are shared with
        # the base environment *from the viewpoint of rules*.
        concepts_data = {}
        concepts_shared = set()
        for ckey, concept in gloss.concepts.iteritems():
            oterms, tterms = format_terms(concept)
            if oterms and tterms:
                concepts_data[ckey] = (oterms, tterms)
                if benv:
                    # Concept shared if original/target terminology same.
                    boterms, btterms = format_terms(concept, benv)
                    if oterms == boterms and tterms == btterms:
                        concepts_shared.add(ckey)

        if not concepts_data:
            warning(p_("warning message",
                       "no concepts found for PO view that have terms in both "
                       "the requested origin and target language"))

        # Parse rules file.
        rules, rmap, plines, elines = [], {}, [], []
        if os.path.isfile(rulefile):
            rules, rmap, plines, elines = self._load_rules(rulefile)

        # Flag all existing rules.
        for rkey, rule in rmap.iteritems():

            if rkey not in concepts_data:
                rule.set_flag("obsolete")
                continue

            oterms, tterms = concepts_data[rkey]

            if benv and rkey in concepts_shared:
                note = None
                if oterms != rule.oterms or tterms != rule.tterms:
                    note = "%s = %s" % (oterms, tterms)
                rule.set_flag("merge", note)
                continue

            if oterms != rule.oterms or tterms != rule.tterms:
                note = "%s = %s" % (oterms, tterms)
                rule.set_flag("fuzzy", note)
                continue

            if not rule.has_flag("new"):
                rule.set_flag("")

        # Add new rules, in lexicographical order by keys.
        ckeys = concepts_data.keys()
        ckeys.sort()
        last_ins_pos = -1
        for ckey in ckeys:
            if ckey in rmap:
                continue
            if ckey in concepts_shared:
                continue

            nrule = self._Rule()
            nrule.ckey = ckey
            nrule.oterms, nrule.tterms = concepts_data[ckey]
            nrule.disabled = True
            # Add all fields for establishing ordering;
            # some will get their real values on sync.
            if tdelim not in nrule.oterms:
                topmatch = "{\\b%s}" % nrule.oterms
            else:
                topmatch = "{\\b(%s)}" % nrule.oterms
            if nrule.oterms.islower():
                topmatch += "i"
            nrule.lines.append(topmatch)
            nrule.lines.append("id=\"\"")
            nrule.lines.append("hint=\"\"")
            if tdelim not in nrule.tterms:
                valmatch = "valid msgstr=\"\\b%s\"" % nrule.tterms
            else:
                valmatch = "valid msgstr=\"\\b(%s)\"" % nrule.tterms
            nrule.lines.append(valmatch)
            nrule.lines.append("disabled")
            nrule.set_flag("new")

            inserted = False
            for i in range(last_ins_pos + 1, len(rules)):
                if ckey < rules[i].ckey:
                    last_ins_pos = i
                    rules.insert(i, nrule)
                    inserted = True
                    break
            if not inserted:
                last_ins_pos = len(rules)
                rules.append(nrule)
            rmap[ckey] = nrule

        # Write rules back.
        ofl = codecs.open(rulefile, "w", "UTF-8")
        ofl.writelines([x + "\n" for x in plines])
        for rule in rules:
            ofl.writelines(rule.format_lines())
        ofl.writelines([x + "\n" for x in elines])
        ofl.close()

        # All done.


    class _Rule:

        hint_rx = re.compile(r"^\s*hint\s*=\s*(.)(.*)\1")
        free_hint_rx = re.compile(r"\[(.*)\]")
        ident_rx = re.compile(r"^\s*id\s*=\s*(.)(.*)\1")
        disabled_rx = re.compile(r"^\s*disabled\b")

        flag_pref = "@gloss-"
        flag_rx = re.compile(r"^\s*#\s*%s(\w+)" % flag_pref)

        def __init__ (self):

            self.ckey = u""
            self.oterms = u""
            self.tterms = u""
            self.freehint = None
            self.disabled = False

            self.lines = []


        def set_flag (self, flag, note=None):

            flag_cmnt = ""
            if flag:
                flag_cmnt = "# " + self.flag_pref + flag
                if note is not None:
                    flag_cmnt += " [%s]" % note
            self.set_line(lambda x: x.startswith("#") and self.flag_pref in x,
                          flag_cmnt, 0)


        def has_flag (self, flag):

            for line in self.lines:
                m = self.flag_rx.search(line)
                if m:
                    cflag = m.group(1)
                    if cflag == flag:
                        return True

            return False


        def sync_lines (self):

            # Create or remove ident.
            identstr = ""
            if self.ckey:
                identstr = "id=\"%s\"" % self.ckey
            self.set_line(lambda x: self.ident_rx.search(x), identstr)

            # Create or remove hint.
            hintstr = ""
            if self.oterms and self.tterms and self.freehint is not None:
                hintstr = "hint=\"%s = %s [%s]\"" % (self.oterms, self.tterms,
                                                     self.freehint)
            elif self.oterms and self.tterms:
                hintstr = "hint=\"%s = %s\"" % (self.oterms, self.tterms)
            elif self.freehint is not None:
                hintstr = "hint=\"%s\"" % self.freehint
            self.set_line(lambda x: self.hint_rx.search(x), hintstr)

            # Create or remove disabled state.
            disabledstr = ""
            if self.disabled:
                disabledstr = "disabled"
            self.set_line(lambda x: self.disabled_rx.search(x), disabledstr)


        def set_line (self, check, nline, defpos=None):

            inspos = -1
            i = 0
            while i < len(self.lines):
                if check(self.lines[i]):
                    if inspos < 0:
                        inspos = i
                    self.lines.pop(i)
                else:
                    i += 1
            if inspos < 0:
                if defpos is None:
                    inspos = len(self.lines)
                else:
                    inspos = defpos
            if nline:
                self.lines.insert(inspos, nline)


        def format_lines (self):

            self.sync_lines()

            flines = [x + "\n" for x in self.lines]
            flines.append("\n")

            return flines


    def _load_rules (self, fpath):
        """
        Loads rules files in a simplified format.

        For each rule the needed fields are parsed (e.g. ident, hint),
        and the rest is just kept as a bunch of lines.

        Return list of parsed rule objects and dictionary mapping to
        it for rules recognized as glossary concepts (by concept key).
        Also the file prologue and epilogue as lists of lines.
        """

        # The syntax of rules files is a bit ad-hoc;
        # hence some of the parsing below may be strange.

        ifl = codecs.open(fpath, "UTF-8")

        hint_rx = self._Rule.hint_rx
        free_hint_rx = self._Rule.free_hint_rx
        ident_rx = self._Rule.ident_rx
        disabled_rx = self._Rule.disabled_rx

        prologue = []
        rules = []
        rmap = {}

        in_prologue = True
        crule = self._Rule()
        for line in ifl:
            line = line.rstrip("\n")

            if line.strip().startswith("#"): # comment
                if in_prologue:
                    prologue.append(line)
                else:
                    crule.lines.append(line)
                continue

            if not line: # rule finished
                if in_prologue: # last line of file prologue
                    in_prologue = False
                    prologue.append(line)
                    continue
                if not crule.lines: # empty rule, shouldn't have, but...
                    continue
                rules.append(crule)
                crule = self._Rule()
                continue

            m = ident_rx.search(line)
            if m:
                crule.ckey = m.group(2).strip()
                rmap[crule.ckey] = crule

            m = hint_rx.search(line)
            if m:
                hintstr = m.group(2)
                orig_hintstr = hintstr

                m = free_hint_rx.search(hintstr)
                if m:
                    crule.freehint = m.group(1)
                hintstr = free_hint_rx.sub("", hintstr)

                p = hintstr.find("=")
                if p >= 0:
                    crule.oterms = hintstr[:p].strip()
                    crule.tterms = hintstr[p+1:].strip()
                else:
                    crule.freehint = orig_hintstr

            m = disabled_rx.search(line)
            if m:
                crule.disabled = True

            crule.lines.append(line)

        # Last rule actually contains file epilogue.
        epilogue = crule.lines

        ifl.close()

        return rules, rmap, prologue, epilogue

