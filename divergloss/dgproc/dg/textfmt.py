# -*- coding: UTF-8 -*-

"""
Format text in glossary for different outputs.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import re
from textwrap import TextWrapper
import copy
import codecs

from dg.util import p_
from dg.construct import Text, Para, Ref, Em, Ol, Link


class TextFormatterPlain (object):
    """
    Format divergloss text into plain text.
    """

    def __init__ (self, gloss, lang=None, env=None,
                        wcol=None, indent=None, first_indent=None,
                        prefix=None, suffix=None):
        """
        Constructor.

        If the language or environment is C{None}, the glossary default is used.

        @param gloss: the glossary to which the text belongs
        @type gloss: L{Glossary}

        @param lang: the language for which the text is formatted
        @type lang: string or C{None}

        @param env: the environment for which the text is formatted
        @type env: string or C{None}

        @param wcol: the column after which the text is wrapped
        @type wcol: int or C{None}

        @param indent: indent for each line of the text
        @type indent: string or C{None}

        @param first_indent: indent for first line of the text
        @type first_indent: string or C{None}

        @param prefix: prefix to add to the text (independent of the indent)
        @type prefix: string or C{None}

        @param suffix: suffix to add to the text
        @type suffix: string or C{None}
        """

        self._gloss = gloss
        self._lang = lang or self._gloss.lang
        self._env = env or (gloss.env and gloss.env[0])

        self._prefix = prefix
        self._suffix = suffix

        self._indent = indent
        self._wrapper = None
        if wcol:
            if indent is None:
                indent = ""
            if first_indent is None:
                first_indent = indent
            self._wrapper_first = TextWrapper(initial_indent=first_indent,
                                              subsequent_indent=indent,
                                              width=wcol)
            self._wrapper = TextWrapper(initial_indent=indent,
                                        subsequent_indent=indent,
                                        width=wcol)


    def __call__ (self, text, prefix=None, suffix=None):
        """
        Format the text.

        Prefix and suffix given by the constructor may be overrident here.
        This is useful e.g. for enumerations.

        @param text: the text to be formatted
        @type text: instance of C{Text}

        @param prefix: overriding prefix for the text
        @type prefix: string or C{None}

        @param suffix: overriding suffix for the text
        @type suffix: string or C{None}

        @return: formatted plain text
        @rtype: string
        """

        # Basic format, resolve tags.
        fmt_text = self._format_sub(text)

        # Prefixate and suffixate if requested.
        prefix = prefix or self._prefix
        if prefix:
            fmt_text = prefix + fmt_text
        suffix = suffix or self._suffix
        if suffix:
            fmt_text = fmt_text + suffix

        # Split into lines by masked line breaks.
        fmt_lines = fmt_text.strip("\x04").split("\x04")

        # Strip superfluous whitespace.
        fmt_lines = [re.sub("\s+", " ", x).strip() for x in fmt_lines]

        # Wrap if requested, or just indent.
        if self._wrapper:
            fmt_lines = (  [self._wrapper_first.fill(fmt_lines[0])]
                         + [self._wrapper.fill(x) for x in fmt_lines[1:]])
        elif self._indent:
            fmt_lines = [self._indent + x for x in fmt_lines]

        # Add indent for emtpy lines (can happen also after wrapping).
        if self._indent:
            for i in range(len(fmt_lines)):
                if not fmt_lines[i]:
                    fmt_lines[i] = self._indent + fmt_lines[i]

        # Put lines back into single string.
        fmt_text = "\n".join(fmt_lines)

        return fmt_text


    def _format_sub (self, text):

        fmt_text = []
        for seg in text:
            if isinstance(seg, Para):
                fmt_seg = self._format_sub(seg) + "\x04\x04"
            elif isinstance(seg, Ref):
                # FIXME: Better way to handle reference?
                fmt_seg = self._format_sub(seg) + "°"
            elif isinstance(seg, Em):
                fmt_seg = p_("formatting of an emphasized phrase in "
                             "running plain text",
                             "*%(phrase)s*") \
                          % dict(phrase=self._format_sub(seg))
            elif isinstance(seg, Ol):
                if not seg.wl:
                    fmt_seg = p_("formatting of a foreign language phrase in "
                                 "running plain text",
                                 "/%(phrase)s/") \
                              % dict(phrase=self._format_sub(seg))
                else:
                    lnode = self._gloss.languages[seg.lang]\
                                .shortname(self._lang, self._env)[0]
                    fmt_seg = p_("formatting of a foreign language phrase in "
                                 "running plain text, where the short "
                                 "language name is provided too",
                                 "%(lang)s /%(phrase)s/") \
                              % dict(lang=self._format_sub(lnode.text),
                                     phrase=self._format_sub(seg))
            elif isinstance(seg, Text):
                # Any unhandled text type.
                fmt_seg = self._format_sub(seg)
            elif isinstance(seg, Link):
                fmt_seg = p_("formatting of a linked phrase "
                             "in running plain text",
                             "%(phrase)s (%(url)s)") \
                          % dict(phrase=self._format_sub(seg), url=seg.url)
            else:
                # Must be a string
                fmt_seg = seg

            fmt_text.append(fmt_seg)

        return "".join(fmt_text)


class TextFormatterHtml (object):
    """
    Format divergloss text into HTML segment.
    """

    def __init__ (self, gloss, lang=None, env=None,
                        prefix=None, suffix=None, refbase=None,
                        wtag=None, wattrs=None, wcond=True,
                        pclass=None):
        """
        Constructor.

        If the language or environment is C{None}, the glossary default is used.

        References in the text are linked as C{base#ckey},
        where C{ckey} is the concept key as pointed to by the reference,
        and C{base} is the page where the concept is anchored.
        The C{refbase} parameter is the mapping of concept keys to pages.
        If the mapping is not given, C{base} will always be empty;
        if the mapping is given and the key that a reference points to
        is not present in it, no link will be made.

        @param gloss: the glossary to which the text belongs
        @type gloss: L{Glossary}

        @param lang: the language for which the text is formatted
        @type lang: string or C{None}

        @param env: the environment for which the text is formatted
        @type env: string or C{None}

        @param prefix: prefix to add to the text
        @type prefix: string or C{None}

        @param suffix: suffix to add to the text
        @type suffix: string or C{None}

        @param refbase: mapping of concept keys to source pages
        @type refbase: dict of string:string

        @param wtag: tag to wrap the resulting text with
        @type wtag: string or C{None}

        @param wattrs: attributes to the wrapping tag, as name->value mapping
        @type wattrs: dict or C{None}

        @param wcond: add wrapping tag only if not wrapped with it as it is
        @type wcond: bool

        @param pclass: class attribute to assign to paragraphs
        @type pclass: string or C{None}
        """

        self._gloss = gloss
        self._lang = lang or self._gloss.lang
        self._env = env or (gloss.env and gloss.env[0])

        self._prefix = prefix
        self._suffix = suffix
        self._wtag = wtag
        self._wattrs = wattrs
        self._wcond = wcond
        self._pclass = pclass

        self._refbase = refbase


    def __call__ (self, text, prefix=None, suffix=None,
                  wtag=None, wattrs=None, wcond=None,
                  pclass=None):
        """
        Format the text.

        Prefix/suffix and wrapping given by the constructor may be overriden
        here. This is useful e.g. for lists.

        The formatted text is stripped of leading and trailing whitespace.

        @param text: the text to be formatted
        @type text: instance of C{Text}

        @param prefix: overriding prefix for the text
        @type prefix: string or C{None}

        @param suffix: overriding suffix for the text
        @type suffix: string or C{None}

        @param wtag: tag to wrap the resulting text with
        @type wtag: string or C{None}

        @param wattrs: attributes to the wrapping tag, as name->value mapping
        @type wattrs: dict or C{None}

        @param wcond: add wrapping tag only if not wrapped with it as it is
        @type wcond: bool or C{None}

        @param pclass: class attribute to assign to paragraphs
        @type pclass: string or C{None}

        @return: formatted HTML text
        @rtype: string
        """

        # Basic format, resolve tags.
        pclass = pclass or self._pclass
        fmt_text = self._format_sub(text, pclass)

        # Prefixate and suffixate if requested.
        prefix = prefix or self._prefix
        if prefix:
            fmt_text = prefix + fmt_text
        suffix = suffix or self._suffix
        if suffix:
            fmt_text = fmt_text + suffix

        # Strip superfluous whitespace.
        fmt_text = re.sub("\s+", " ", fmt_text).strip()

        # Split into lines by some closing tags.
        tmp = re.sub(r"(</(p|ul|li)>)", "\\1\n", fmt_text).strip()
        fmt_lines = [x.strip() for x in tmp.split("\n")]

        # Wrap if requested.
        wtag = wtag or self._wtag
        wattrs = wattrs or self._wattrs
        if wcond is None:
            wcond = self._wcond
        if wtag and (not wcond or not fmt_text.startswith("<" + wtag)):
            rwattrs = wattrs
            if wtag.lower() == "p" and pclass:
                rwattrs = {}
                if wattrs:
                    rwattrs = wattrs.copy()
                rwattrs["class"] = pclass
            if len(fmt_lines) > 1:
                fmt_lines.insert(0, stag(wtag, rwattrs))
                fmt_lines.append(etag(wtag))
            else:
                fmt_lines[0] = wtext(fmt_lines[0], wtag, rwattrs)

        return "\n".join(fmt_lines)


    def _format_sub (self, text, pclass=None):

        pattrs = {}
        if pclass is not None:
            pattrs["class"] = pclass

        fmt_text = []
        for seg in text:
            if isinstance(seg, Para):
                fmt_seg = wtext(self._format_sub(seg), "p", pattrs)
            elif isinstance(seg, Ref):
                if self._refbase is None or seg.c in self._refbase:
                    if self._refbase is None:
                        target = "#%s" % seg.c
                    else:
                        target = "%s#%s" % (self._refbase[seg.c], seg.c)
                    fmt_seg = wtext(self._format_sub(seg),
                                    "a", {"class":"cref", "href":target})
                else:
                    fmt_seg = self._format_sub(seg)
            elif isinstance(seg, Em):
                fmt_seg = p_("formatting of an emphasized phrase in "
                             "running HTML text",
                             "<em>%(phrase)s</em>") \
                          % dict(phrase=self._format_sub(seg))
            elif isinstance(seg, Ol):
                if not seg.wl:
                    fmt_seg = p_("formatting of a foreign language phrase in "
                                 "running HTML text",
                                 "<em class='frlng'>%(phrase)s</em>") \
                              % dict(phrase=self._format_sub(seg))
                else:
                    lnode = self._gloss.languages[seg.lang]\
                                .shortname(self._lang, self._env)[0]
                    fmt_seg = p_("formatting of a foreign language phrase in "
                                 "running HTML text, where the short "
                                 "language name is provided too",
                                 "%(lang)s <em class='frlng'>%(phrase)s</em>") \
                              % dict(lang=self._format_sub(lnode.text),
                                     phrase=self._format_sub(seg))
            elif isinstance(seg, Link):
                phrase = self._format_sub(seg)
                fmt_seg = wtext(phrase, "a", {"class":"ext", "href":seg.url})
            elif isinstance(seg, Text):
                # Any unhandled text type.
                fmt_seg = self._format_sub(seg, pclass)
            else:
                # Must be a string.
                fmt_seg = seg

            fmt_text.append(fmt_seg)

        return "".join(fmt_text)


def escape_xml (text):
    """
    Escape plain text to be valid in XML context, using entities.

    @param text: text to escape
    @type text: string

    @return: escaped text
    @rtype: string
    """

    text = text.replace("&", "&amp;") # must be first
    text = text.replace("'", "&quot;")
    text = text.replace('"', "&apos;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    return text


def stag (tag, attrs=None, close=False):
    """
    Format starting tag.

    @param tag: tag name
    @type tag: string
    @param attrs: attributes and their values
    @type attrs: dict or C{None}
    @param close: close tag immediately
    @type close: bool

    @return: formatted starting tag
    @rtype: string
    """

    fmt_attr = ""
    if attrs is not None:
        atts_vals = attrs.items()
        atts_vals = [(x[0], escape_xml(x[1])) for x in atts_vals]
        atts_vals.sort(lambda x, y: cmp(x[0], y[0]))
        fmt_attr = "".join([" %s='%s'" % x for x in atts_vals])

    cslash = ""
    if close:
        cslash = "/"

    return "<%s%s%s>" % (tag, fmt_attr, cslash)


def etag (tag):
    """
    Format ending tag.

    @param tag: tag name
    @type tag: string

    @return: formatted ending tag
    @rtype: string
    """

    return "</%s>" % tag


def wtext (text, tag, attrs=None):
    """
    Wrap text with a tag.

    @param tag: tag name
    @type tag: string
    @param text: text to wrap
    @type text: string
    @param attrs: attributes and their values
    @type attrs: dict or C{None}

    @return: text wrapped in tag
    @rtype: string
    """

    return stag(tag, attrs) + text + etag(tag)


def itext (indent, text, strip=False, empty=False):
    """
    Indent text possibly containing internal newlines.

    @param indent: line indent
    @type indent: string
    @param text: text to indent
    @type text: string
    @param strip: whether to strip lines before indenting
    @type strip: bool
    @param empty: whether to indent empty lines too
    @type empty: bool

    @return: indented text
    @rtype: string
    """

    lines = text.split("\n")

    nlines = []
    for line in lines:
        if strip:
            line = line.strip()
        if empty or line.strip():
            line = indent + line
        nlines.append(line)

    return "\n".join(nlines)


class LineAccumulator (object):
    """
    An accumulator of lines of text.

    The accumulated lines are reached through the C{lines} member variable.

    @ivar lines: stored lines
    @type lines: list of strings
    """

    def __init__ (self, indent="  ", ilevel=0, strip=False, empty=False):
        """
        Constructor.

        @param indent: line indent per level
        @type indent: string
        @param ilevel: base indenting level
        @type ilevel: int >= 0
        @param strip: whether to strip lines before indenting
        @type strip: bool
        @param empty: whether to indent empty lines too
        @type empty: bool
        """

        self._indent = indent
        self._ilevel = ilevel
        self._strip = strip
        self._empty = empty

        self.lines = []


    def __call__ (self, text="", level=0):
        """
        Accumulate line of text, with given indent level.

        The indent level is added to the base level given to the constructor.
        The newline is added to the text.

        @param text: text to accumulate
        @type text: string, list of strings, or another L{LineAccumulator}
        @param level: indenting level
        @type level: int >= 0
        """

        if isinstance(text, LineAccumulator):
            lines = text.lines
        elif isinstance(text, (str, unicode)):
            lines = [text]
        else:
            lines = list(text)

        for text in lines:
            cindent = self._indent * (self._ilevel + level)
            text = itext(cindent, text, self._strip, self._empty)
            if not text.endswith("\n"):
                text += "\n"
            self.lines.append(text)


    def newind (self, dlevel=1):
        """
        A new accumulator with same line storage but different
        base indent level.

        @param dlevel: increase in indent level
        @type dlevel: int

        @return: accumulator with different indent level
        @rtype: L{LineAccumulator}
        """

        acc = copy.copy(self)
        acc._ilevel += dlevel
        acc.lines = self.lines
        return acc


    def write (self, fpath, enc="UTF-8"):
        """
        Write accumulated lines into a file.

        @param fpath: path of the file to write
        @type fpath: string
        @param enc: encoding for the text
        @type enc: string
        """

        ofl = codecs.open(fpath, "w", enc)
        ofl.writelines(self.lines)
        ofl.close()


    def read (self, fpath, enc="UTF-8"):
        """
        Accumulate lines from the file.

        @param fpath: path of the file to read
        @type fpath: string
        @param enc: encoding for the text
        @type enc: string
        """

        ifl = codecs.open(fpath, "r", enc)
        self.lines.extend(ifl.readlines())
        ifl.close()

