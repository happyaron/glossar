# -*- coding: UTF-8 -*-

"""
Construct internal glossary out of a Divergloss XML document.


Glossary Structure
==================

For manipulations in the client code, the glossary is structured as
a tree of node object, where XML attributes and children elements map to
data attributes (sequences when required) of a node object.

All node objects are of base type L{Gnode}, which is subclassed to match
corresponding Divergloss XML elements. For example, C{<concept>} XML
elements are represented by objects of the L{Concept} subclass of L{Gnode}.

A g-node may have data attributes of types as follows:

  - string: used to represent XML element attributes
  - list of strings: used to represent list-valued XML element attributes
  - g-node: for non-repeating children of an XML element
  - list of g-nodes: repeating children XML elements without a unique ID
  - dict of g-nodes: repeating children having a unique ID
  - d-set of g-nodes: repeating children having C{lang}/C{env} attributes

String and list of string attributes are just that, named as the underlying
XML attribute and having its value or list of values. E.g. if the top
glossary node is C{gloss}, and there is a concept with the ID C{con},
the list of its related concepts (i.e. their keys) may be reached by
C{gloss.concepts[con].related}.

XML elements which are unique children of their parent are represented by
a L{Gnode} attribute. For example, the email address of an editor with
the ID C{ed} is obtained by C{gloss.editors[ed].email}.

List and dict attributes are named as the corresponding XML elements, but
additionally in plural (-s ending) to indicate their sequence nature.
These were already seen in previous passages, e.g. to get to the concept
with ID C{con} one uses C{gloss.concepts[con]}.

The most peculiar members of g-nodes' ensemble of attributes are I{d-sets},
short for "diversity sets". Many of Divergloss elements can carry language
and environment (langenv for short) attributes, as a "diversification"
moment of the glossary. It would be burdensome to represent such children
elements as ordinary sequences, since they usually need to be accessed by
a langenv combination. A d-set attribute of a g-node is named same as its
XML namesake (not in plural), but has the type L{Dset}, and is callable for
specialization by langenv. For example, if there is a language C{lang} and
environment C{env} in the glossary, the terms naming the concept C{con} in
that langenv are obtained by the quering the term d-set like
C{gloss.concepts[ckey].term(lang, env)}; this will return a I{list} of
term g-nodes, which may have one, more, or zero elements, depending if in
that langenv the term is unique, has synonyms, or isn't defined at all.

Additional notes on the structure:

  - The internal structure closely follows the Divergloss XML element
    structure, but for the top containers, the C{<metadata>}, C{<keydefs>},
    and C{<concepts>} elements. These are not present internally, their
    content having been flattened in the top g-node. Thus, instead of e.g.
    C{gloss.keydefs.editors[ed]}, the path is just C{gloss.editors[ed]}.
    This is because in the XML, these containers serve only to allow
    better chunking of the document.

  - Dual XML elements, such as C{desc}/C{ldesc} or C{term}/C{eterm} are
    always represented as an attribute of the shorter name. This is because
    the duality is caused by constraints of XML, while there is no need for
    it internally. For terms, this means that internally the nominal form
    of the term is always accessed as C{termnode.nom}, regardless if the
    XML was C{<term>...</term>} or C{<eterm><nom>...</nom></eterm>}.

  - Attributes and elements defined as optional by Divergloss DTD for a
    particular element, are always present in its corresponding g-node.
    For attributes or child elements that the XML element didn't contain,
    g-node attributes will have appropriate null-value: non-sequences
    will be C{None}, and sequences empty.

  - The C{env} attribute, when present in a g-node, will never be an
    empty sequence. It is, like language, inherited from first parent
    g-node that has it, and the top g-node will set it to C{[None]} if
    not explicitly provided.

  - Each g-node has a C{parent} attribute, which points to the parent g-node.
    For the top g-node its value is C{None}. Remember this if at any time
    you want to make deep copy a g-node.

  - D-sets may be queried without providing language and environment
    parameters, in which case they use langenv of their parent.

See L{Glossary} for full hierarchical overview of data attributes.

Text Representation
===================

Text within Diverloss XML elements is always internally represented as a
C{text} attribute of a g-node. The type of this attribute is always L{Text},
regardless if the XML element allowed text markup or only plain text.
L{Text} is a base class for text segments, from which other segment types
are subclassed, like C{Para}, C{Ref}, etc. according to XML markup elements.
L{Text} is itself a subclass of list, i.e. on the basic level text markup
is represented as nested list of lists, with terminal elements pure strings.
For example, XML text such as::

    Blah blah <ref c='whatever'>one</ref> blah <em>other</em> blah.

would be represented in pseudo-form as::

    Text['Blah blah ', Ref['one'], ' blah ', Em['other'], ' blah.']

where C{Foo[]} stands for instance of C{Text}, i.e. of list, of type C{Foo}.
The C{Ref} object in the list would further have a C{c} attribute with the
referenced concept key as its value.

To convert text represented like this into an output format, like plain or
HTML text, there is the L{textfmt} module which contains various formatters.
E.g. to turn a certain concept description into plain text, in a certain
langenv context, we would do::

    tf = textfmt.TextFormatterPlain(gloss, lang, env)
    plaindesc = tf(gloss.concepts[con].desc(lang, env)[0].text)

where the langenv must be specified when creating the formatter too,
in order to resolve any internal markup which draws strings from other
places in the glossary (e.g. the language name in C{<ol lang="...">}).

When writing search filters, it is probably best to pass the text through
the formatter and search on the plain text version of it.


@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

import os
import copy
import random
from lxml import etree

from dg.dset import Dset
from dg.util import p_
from dg.util import error, warning
from dg.util import lstr
from dg import _dtd_dir


def from_file (dgfile, validate=True):
    """
    Construct glossary from a Divergloss file.

    The glossary file may use XInclude to include subdocuments.

    @param dgfile: Divergloss file name
    @type dgfile: string
    @param validate: whether to validate the glossary
    @type validate: bool

    @return: constructed glossary
    @rtype: L{Gnode}
    """

    try:
        # Do not validate at parse time, but afterwards.
        # Must resolve xincludes beforehand.
        parser = etree.XMLParser(dtd_validation=False, remove_comments=True)
        tree = etree.parse(dgfile, parser=parser)
        tree.xinclude()
    except (etree.XMLSyntaxError, etree.XIncludeError), e:
        errlins = "\n".join([str(x) for x in list(e.error_log)])
        error(p_("error message",
                 "XML parsing failed:\n"
                 "%(msg)s") % {"msg":errlins})

    if validate:
        # Work around a bug: non-unique identifiers do not produce any
        # message when validation fails.
        ids = tree.xpath("//*/@id")
        iddict = {}
        for id in ids:
            if id in iddict:
                # Keep the message format same as below, just report ids.
                error(p_("error message",
                         "DTD validation failed:\n"
                         "%(msg)s") % {"msg":p_("error message",
                                                "duplicate ID '%(id)s'")
                                             % {"id": id}})
            iddict[id] = True

        # Resolve the DTD file and validate the tree according to it.
        # FIXME: Better determination of dtd file (by public ID, etc.)
        if tree.docinfo.system_url:
            dtdname = tree.docinfo.system_url
        else:
            # Fallback to latest DTD.
            dtdname = "divergloss.dtd"
        dtdfile = os.path.join(_dtd_dir, dtdname)
        dtd = etree.DTD(dtdfile)
        if not dtd.validate(tree):
            errlins = "\n".join([str(x) for x in list(dtd.error_log)])
            error(p_("error message",
                     "DTD validation failed:\n"
                     "%(msg)s") % {"msg":errlins})

    # Construct glossary from the document tree.
    gloss = from_tree(tree, validate=validate)

    return gloss


def from_tree (tree, validate=True):
    """
    Construct glossary from a Divergloss document tree.

    @param tree: Divergloss tree
    @type tree: etree from C{lxml.etree}
    @param validate: whether to validate the glossary
    @type validate: bool

    @return: constructed glossary
    @rtype: L{Gnode}
    """

    root = tree.getroot()
    gloss = Glossary(root)

    # Post-DTD validation.
    if validate:
        _post_dtd_validate(gloss)

    return gloss

# --------------------------------------
# Validation.

def _post_dtd_validate (gloss):

    _post_dtd_in_node(gloss, gloss)


def _post_dtd_in_node (gloss, gnode):

    # Do checks.
    _post_dtd_check_keys(gloss, gnode)

    # Traverse further.
    for att, obj in gnode.__dict__.iteritems():
        if att == "parent":
            continue
        if isinstance(obj, Text):
            _post_dtd_in_text(gloss, obj)
        else:
            subns = []
            if isinstance(obj, Gnode):
                subns = [obj]
            elif isinstance(obj, Dset):
                subns = obj.values() # all in Dset are Gnode
            elif isinstance(obj, dict):
                subns = [x for x in obj.values() if isinstance(x, Gnode)]
            elif isinstance(obj, list):
                subns = [x for x in obj if isinstance(x, Gnode)]

            for subn in subns:
                _post_dtd_in_node(gloss, subn)


def _post_dtd_in_text (gloss, text):

    # Do checks.
    _post_dtd_check_keys(gloss, text)

    # Traverse further.
    for seg in text:
        if isinstance(seg, Text):
            _post_dtd_in_text(gloss, seg)


def _post_dtd_check_keys (gloss, gnode):

    _post_dtd_ch_key(gloss, gnode, "lang", gloss.languages,
        p_("error message",
           "attribute '%(att)s' states a non-language key: %(key)s"))

    _post_dtd_ch_keyseq(gloss, gnode, "env", gloss.environments,
        p_("error message",
           "attribute '%(att)s' states non-environment keys: %(keys)s"))

    _post_dtd_ch_key(gloss, gnode, "by", gloss.editors,
        p_("error message",
           "attribute '%(att)s' states a non-editor key: %(key)s"))

    _post_dtd_ch_key(gloss, gnode, "src", gloss.sources,
        p_("error message",
           "attribute '%(att)s' states a non-source key: %(key)s"))

    _post_dtd_ch_key(gloss, gnode, "gr", gloss.grammar,
        p_("error message",
           "attribute '%(att)s' states a non-grammar key: %(key)s"))

    _post_dtd_ch_key(gloss, gnode, "root", gloss.extroots,
        p_("error message",
           "attribute '%(att)s' states a non-root key: %(key)s"))

    _post_dtd_ch_key(gloss, gnode, "c", gloss.concepts,
        p_("error message",
           "attribute '%(att)s' states a non-concept key: %(key)s"))

    _post_dtd_ch_keyseq(gloss, gnode, "closeto", gloss.environments,
        p_("error message",
           "attribute '%(att)s' states non-environment keys: %(keys)s"))

    _post_dtd_ch_keyseq(gloss, gnode, "topic", gloss.topics,
        p_("error message",
           "attribute '%(att)s' states non-topic keys: %(keys)s"))

    _post_dtd_ch_keyseq(gloss, gnode, "level", gloss.levels,
        p_("error message",
           "attribute '%(att)s' states non-level keys: %(keys)s"))

    _post_dtd_ch_keyseq(gloss, gnode, "related", gloss.concepts,
        p_("error message",
           "attribute '%(att)s' states non-concept keys: %(keys)s"))


def _post_dtd_ch_key (gloss, gnode, attname, keydict, msg):

    key = getattr(gnode, attname, None)
    if key is not None and key not in keydict:
        _post_dtd_error(gloss, gnode, msg % {"att":attname, "key":key})


def _post_dtd_ch_keyseq (gloss, gnode, attname, keydict, msg):

    keys = getattr(gnode, attname, [])
    if keys is None:
        keys = []
    badkeys = [x for x in keys if x not in keydict and x is not None]
    if badkeys:
        fmtk = " ".join(badkeys)
        _post_dtd_error(gloss, gnode, msg % {"att":attname, "keys":fmtk})


def _post_dtd_error (gloss, gnode, msg):

    lmsg = p_("message with the location it speaks of",
              "%(file)s:%(line)s: %(msg)s") \
           % {"file":gnode.src_file, "line":gnode.src_line, "msg":msg,}

    error(p_("error message",
             "post-DTD validation failed:\n"
             "%(msg)s") % {"msg":lmsg})


# --------------------------------------
# XML extractors.

def _attval (node, attname, defval=None):

    if node is None:
        return defval
    return node.attrib.get(attname, defval)


def _attkey (node, attname):

    key = _attval(node, attname)
    if key is not None:
        key = key.strip()
    return key


def _child_els_by_tag (node, tags, defnodes=[]):

    if node is None:
        return defnodes
    if isinstance(tags, (str, unicode)):
        tags = (tags,)

    selnodes = [x for x in node if x.tag in tags]
    if not selnodes:
        return defnodes
    return selnodes


def _text_segments (seg_node, exp_tags):

    if seg_node is None:
        return []

    segs = []
    if seg_node.text:
        segs.append(seg_node.text)
    for node in seg_node:
        if node.tag in exp_tags:
            segs.append(_tseg_name_type[node.tag](node))
        else:
            segs.append(_pure_text(node))
        if node.tail:
            segs.append(node.tail)

    return segs


def _pure_text (string_node):

    if string_node is None:
        return ""
    sl = []
    sl.append(string_node.text)
    for node in string_node:
        sl.append(_pure_text(node))
        sl.append(node.tail)

    return "".join(sl)


# --------------------------------------
# Content constructors.

def _content (obj, gloss, node, parse_bundles):

    for consf, args in parse_bundles:
        consf(obj, gloss, node, *args)


def _attributes (obj, gloss, node, attspecs):

    for attspec in attspecs:
        if isinstance(attspec, tuple):
            attname, defval = attspec
        else:
            attname, defval = attspec, None
        if node is not None:
            val = _attval(node, attname, defval)
        else:
            val = defval
        obj.__dict__[attname] = val


def _attrib_lists (obj, gloss, node, attspecs):

    for attspec in attspecs:
        if isinstance(attspec, tuple):
            attname, deflst = attspec
        else:
            attname, deflst = attspec, []
        if node is not None:
            val = _attval(node, attname, deflst)
        else:
            val = deflst
        if isinstance(val, (str, unicode)):
            val = val.split()
        obj.__dict__[attname] = val


def _child_dsets (obj, gloss, node, chdspecs):

    for chdspec in chdspecs:
        if len(chdspec) == 3:
            attname, subtype, tagnames = chdspec
        else:
            attname, subtype = chdspec
            tagnames = (attname,)
        if attname not in obj.__dict__:
            obj.__dict__[attname] = Dset(gloss, obj)
        dst = obj.__dict__[attname]
        if node is not None:
            for cnode in _child_els_by_tag(node, tagnames):
                subobj = subtype(gloss, obj, cnode)
                # Add several resolved objects if any embedded selections.
                for rsubobj in _res_embsel(gloss, subobj):
                    dst.add(rsubobj)


def _child_lists (obj, gloss, node, chlspecs):

    for chlspec in chlspecs:
        if len(chlspec) == 3:
            attname, subtype, tagnames = chlspec
        else:
            attname, subtype = chlspec
            tagnames = (attname,)
        if attname not in obj.__dict__:
            obj.__dict__[attname] = []
        lst = obj.__dict__[attname]
        if node is not None:
            for cnode in _child_els_by_tag(node, tagnames):
                lst.append(subtype(gloss, obj, cnode))


def _child_dicts (obj, gloss, node, chmspecs):

    for dictname, subtype, tagname in chmspecs:
        if dictname not in obj.__dict__:
            obj.__dict__[dictname] = {}
        dct = obj.__dict__[dictname]
        if node is not None:
            for cnode in _child_els_by_tag(node, tagname):
                o = subtype(gloss, obj, cnode)
                dct[o.id] = o


def _children (obj, gloss, node, chspecs):

    for chspec in chspecs:
        if len(chspec) == 3:
            attname, subtype, tagnames = chspec
        else:
            attname, subtype = chspec
            tagnames = (attname,)
        if node is not None:
            for cnode in _child_els_by_tag(node, tagnames):
                obj.__dict__[attname] = subtype(gloss, obj, cnode)
                break # a single node expected, so take first
        else:
            obj.__dict__[attname] = None


def _text (obj, gloss, node):

    obj.text = Text(node)


# --------------------------------------
# Self-constructing glossary from XML nodes.

# Base of glossary nodes.
class Gnode:

    def __init__ (self, parent, node=None):

        self.parent = parent

        self.src_line = 0
        self.src_file = p_("an unknown file", "<unknown>")
        if node is not None:
            self.src_line = node.sourceline
            # self.src_file = ?


# Glossary.
class Glossary (Gnode):
    """
    Root node of internal representation of the glossary.

    Any element of the glossary may be reached through attributes and
    subattributes of objects of this class, accessed in the appropriate
    way for their types. Here is the hierachical overview, with type in
    parenthesis, an followed by I{idem.} when the attribute has been
    detailed previously in another context::

        concepts (dict)
            id (string)
            topic (list of strings)
            level (list of strings)
            related (list of strings)
            desc (d-set)
                lang (string)
                env (list of strings)
                by (string)
                src (string)
                text (text)
            term (d-set)
                lang (string)
                env (list of strings)
                gr (string)
                by (string)
                src (string)
                nom (g-node)
                    text (text)
                stem (g-node)
                    text (text)
                decl (list of g-nodes)
                    lang (string)
                    env (list of strings)
                    gr (string)
                    text (text)
                comment (d-set)
                    lang (string)
                    env (list of strings)
                    by (string)
                    text (text)
                origin (d-set)
                    lang (string)
                    env (list of strings)
                    by (string)
                    src (string)
                    text (text)
            details (d-set)
                lang (string)
                env (list of strings)
                root (string)
                rel (string)
                by (string)
                text (text)
            media (d-set)
                lang (string)
                env (list of strings)
                root (string)
                rel (string)
                text (text)
            comment (d-set) ibid.
            origin (d-set) ibid.
        languages (dict)
            id (string)
            name (d-set)
                lang (string)
                env (list of strings)
                text (text)
            shortname (d-set)
                lang (string)
                env (list of strings)
                text (text)
        environments (dict)
            id (string)
            weight (string)
            meta (string)
            closeto (list of strings)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
        editors (dict)
            id (string)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
            email (g-node)
                text (text)
            affiliation (d-set)
                lang (string)
                env (list of strings)
                text (text)
        sources (dict)
            id (string)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
            email (g-node) ibid.
            url (g-node) text
        topics (dict)
            id (string)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
        levels (dict)
            id (string)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
        grammar (dict)
            id (string)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
        extroots (dict)
            id (string)
            name (d-set) ibid.
            shortname (d-set) ibid.
            desc (d-set) ibid.
            rooturl (g-node)
                text (text)
            browseurl (g-node)
                text (text)

    All C{string} values are keys into one of the dictionaries.
    All C{text} values are glossary texts of the structure as explained
    in the module overview.

    For example, to reach the language name of the term of the concept
    with id C{"foo"}, in language with id C{"lang"} and environment
    with id C{"env"}::

        langkey = gloss.concepts["foo"].term("lang", "env")[0].lang
        langname = gloss.languages[langkey].name("lang", "env")[0].text

    assuming that the term and language name are defined for given langenv.

    If the glossary has no explicit environments or has a single environment,
    the environment id can be omitted in d-set element selection calls;
    similarly, if there is a single language in the glossary, language id
    may be omitted too. In fact, both may be omitted in any case, when
    default language and environment will be used if there are multiple.

    @note: At the moment, glossaries are mostly read-only; while elements
    can be added internally if convenient for processing, serializing
    a modified glossary is not implemented yet.
    """

    def __init__ (self, node=None):

        Gnode.__init__(self, None, node)

        _content(self, self, node,
                 [(_attributes,
                   [["id",
                     "lang"]]),
                  (_attrib_lists,
                   [[("env", [None])]])])

        for md_node in _child_els_by_tag(node, "metadata", [None]):
            _content(self, self, md_node,
                     [(_child_dsets,
                       [[("title", Title),
                         ("desc", Desc, ("desc", "ldesc")),
                         ("version", Version)]]),
                      (_children,
                       [[("date", Date)]])])

        for kd_node in _child_els_by_tag(node, "keydefs", [None]):
            for chmspec in [("languages", Language, "language"),
                            ("environments", Environment, "environment"),
                            ("editors", Editor, "editor"),
                            ("sources", Source, "source"),
                            ("topics", Topic, "topic"),
                            ("levels", Level, "level"),
                            ("grammar", Gramm, "gramm"),
                            ("extroots", Extroot, "extroot")]:
                for kds_node in _child_els_by_tag(kd_node, chmspec[0], [None]):
                    _content(self, self, kds_node,
                             [(_child_dicts, [[chmspec]])])

        # Concepts must be parsed after keydefs,
        # e.g. for proper resolution of embedded selectors.
        for cn_node in _child_els_by_tag(node, "concepts", [None]):
            _content(self, self, cn_node,
                     [(_child_dicts, [[("concepts", Concept, "concept")]])])


class Language (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname)]])])


class Environment (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id", "weight", "meta"]]),
                  (_attrib_lists,
                   [["closeto"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("desc", Desc, ("desc", "ldesc"))]])])

        # Make no-environment close to all defined environments.
        self.closeto.append(None)


class Editor (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("affiliation", Affiliation),
                     ("desc", Desc, ("desc", "ldesc"))]]),
                  (_children,
                   [[("email", Email)]])])


class Source (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("desc", Desc, ("desc", "ldesc"))]]),
                  (_children,
                   [[("url", Url),
                     ("email", Email)]])])


class Topic (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("desc", Desc, ("desc", "ldesc"))]])])


class Level (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("desc", Desc, ("desc", "ldesc"))]])])


class Gramm (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("desc", Desc, ("desc", "ldesc"))]])])


class Extroot (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_child_dsets,
                   [[("name", Name),
                     ("shortname", Shortname),
                     ("desc", Desc, ("desc", "ldesc"))]]),
                  (_children,
                   [[("rooturl", RootUrl),
                     ("browseurl", BrowseUrl)]])])


class Concept (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [["id"]]),
                  (_attrib_lists,
                   [["topic",
                     "level",
                     "related"]]),
                  (_child_dsets,
                   [[("desc", Desc, ("desc", "ldesc")),
                     ("term", Term, ("term", "eterm")),
                     ("details", Details),
                     ("media", Media),
                     ("origin", Origin, ("origin", "lorigin")),
                     ("comment", Comment, ("comment", "lcomment"))]])])


class Term (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                     "by",
                     "src",
                     "gr"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]])])

        # In case of simple term, run this through with node=None
        # to have proper initialization of all attributes.
        vnode = None
        if _child_els_by_tag(node, "nom"):
            vnode = node
        _content(self, gloss, vnode,
                 [(_child_dsets,
                   [[("origin", Origin, ("origin", "lorigin")),
                     ("comment", Comment, ("comment", "lcomment"))]]),
                  (_child_lists,
                   [[("decl", Decl)]]),
                  (_children,
                   [[("nom", Nom),
                     ("stem", Stem)]])])
        if vnode is None:
            self.nom = Nom(gloss, self, node)


class Title (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang)]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Version (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang)]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Name (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang)]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Shortname (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang)]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Affiliation (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang)]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Desc (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                     "by",
                     "src"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Origin (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                     "by"
                     "src"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Comment (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                     "by"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Details (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                     "by",
                     "root",
                     "rel"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Media (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                     "by",
                     "root",
                     "rel"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Decl (Gnode):

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang),
                      "gr"]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class OnlyText (Gnode): # subclass for nodes having no attributes, only text

    def __init__ (self, gloss, parent, node=None):

        Gnode.__init__(self, parent, node)

        _content(self, gloss, node,
                 [(_attributes,
                   [[("lang", gloss.lang)]]),
                  (_attrib_lists,
                   [[("env", gloss.env)]]),
                  (_text,
                   [])])


class Date (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


class Email (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


class Url (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


class RootUrl (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


class BrowseUrl (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


class Nom (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


class Stem (OnlyText):

    def __init__ (self, gloss, parent, node=None):

        OnlyText.__init__(self, gloss, parent, node)


# Text.
# Organized as a list of structured text segments,
# where the basic segment is plain string.

class Text (list): # base class for all in-text elements

    def __init__ (self, node=None, tags=None):

        self.src_line = 0
        self.src_file = p_("an unknown file", "<unknown>")
        if node is not None:
            self.src_line = node.sourceline
            # self.src_file = ?

        if tags is None:
            tags = ["para", "ref", "em", "ol", "link"]

        self.extend(_text_segments(node, tags))


class Para (Text):

    def __init__ (self, node=None):

        Text.__init__(self, node, ["ref", "em", "ol", "link"])


class Ref (Text):

    def __init__ (self, node=None):

        Text.__init__(self, node, ["em", "ol"])
        self.c = _attkey(node, "c")


class Em (Text):

    def __init__ (self, node=None):

        Text.__init__(self, node, ["ref", "em", "ol", "link"])


class Ol (Text):

    def __init__ (self, node=None):

        Text.__init__(self, node, ["ref", "em", "ol"])
        self.lang = _attkey(node, "lang")
        self.wl = _attkey(node, "wl")


class Link (Text):

    def __init__ (self, node=None):

        Text.__init__(self, node, ["em", "ol"])
        self.url = _attkey(node, "url")


# Map between text segment types and their tag names.
# Used in _text_segments()
_tseg_name_type = {"para":Para, "ref":Ref, "em":Em, "ol":Ol, "link":Link}


# Resolving of embedded selectors.

# Based on the given object with embedded selectors,
# return list of objects with different languages/environments,
# and the text in them resolved accordingly.
def _res_embsel (gloss, obj):

    if not (hasattr(obj, "text") and hasattr(obj, "env")):
        return [obj]

    # Normalize text: each embedded selector is turned into its own segment
    # of the text, a dictionary of env/string;
    # all encountered environments are reported.
    ntext, envs = _res_embsel_norm_text(obj.text, obj.env)
    if not envs:
        return [obj]

    # Create a version of the object for each of the environments.
    robjs = []
    parent = obj.parent
    obj.parent = None # to avoid going up on deep copy
    for env in envs:
        # Piece up the best version of text for current environment.
        text = _res_embsel_best_text(gloss, ntext, env)

        # Create object with this environment and text.
        robj = copy.deepcopy(obj)
        robj.parent = parent
        robj.env = [env]
        robj.text = text
        robjs.append(robj)

    return robjs


def _res_embsel_norm_text (text, denvs):

    ntext = copy.copy(text)
    ntext[:] = []
    envs = set()

    for i in range(len(text)):
        seg = text[i]
        if isinstance(seg, Text):
            # Sublist of segments.
            subntext, subenvs = _res_embsel_norm_text(seg, denvs)
            ntext.append(subntext)
            envs.update(subenvs)
        else:
            if "~" in seg:
                # Split each embedded selector into an env/string dictionary.
                locntext, locenvs = _res_embsel_parse_one(seg, denvs)
                ntext.extend(locntext)
                envs.update(locenvs)
                text[i] = seg.replace("~~", "~") # unescape segment
            else:
                # A clean string.
                ntext.append(seg)

    return ntext, envs


def _res_embsel_parse_one (seg, denvs):

    ntext = Text()
    envs = set()

    p1 = seg.find("~")
    p2 = -1

    while p1 >= 0:
        head = seg[p2+1:p1]
        if head:
            ntext.append(head)
        p2 = seg.find("~", p1 + 1)
        if p2 < 0:
            warning(p_("warning message",
                       "unterminated embedded selector '%(esel)s'")
                    % {"esel":seg})
            p2 = p1 - 1
            break

        class DictWProps (dict): pass
        envsegs = DictWProps()
        locenvs = set()
        for eseg in seg[p1+1:p2].split("|"):
            pc = eseg.find(":")
            if pc >= 0:
                cenvs = eseg[:pc].split()
                cseg = eseg[pc+1:]
            else:
                cenvs = denvs
                cseg = eseg

            repenvs = locenvs.intersection(cenvs)
            if repenvs:
                fmtes = " ".join([str(x) for x in list(repenvs)])
                warning(p_("warning message",
                           "segment '%(eseg)s' in embedded selector "
                           "'%(esel)s' repeats environments: %(envs)s")
                        % {"esel":seg, "eseg":eseg, "envs":fmtes})

            locenvs.update(cenvs)
            for cenv in cenvs:
                envsegs[cenv] = cseg

        # Add embedded selector string under a dummy environment,
        # needed later for error reporting.
        envsegs.unparsed = seg

        ntext.append(envsegs)
        envs.update(locenvs)

        p1 = seg.find("~", p2 + 1)

    tail = seg[p2+1:]
    if tail:
        ntext.append(tail)

    return ntext, envs


def _res_embsel_best_text (gloss, ntext, env):

    text = copy.copy(ntext)
    text[:] = []
    for seg in ntext:
        if isinstance(seg, Text):
            text.append(_res_embsel_best_text(gloss, seg, env))
        elif isinstance(seg, dict):
            # Try first direct match for environment.
            if env in seg:
                text.append(seg[env])
            else:
                # Try a close environment.
                found_close = False
                if env in gloss.environments:
                    for cenv in gloss.environments[env].closeto:
                        if cenv in seg:
                            text.append(seg[cenv])
                            found_close = True
                            break

                # Take a best shot.
                if not found_close:
                    if env not in gloss.env:
                        warning(p_("warning message",
                                   "no resolution for expected environment "
                                   "'%(env)s' in embedded selector '%(esel)s'")
                                % dict(env=env, esel=seg.unparsed))
                    # Pick at random.
                    text.append(random.choice(seg.values()))
        else:
            text.append(seg)

    return text

