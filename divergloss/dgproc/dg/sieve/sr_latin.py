# -*- coding: UTF-8 -*-

"""
Transform Serbian Cyrillic text in the glossary into Serbian Latin.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

from dg.util import p_
from dg.util import error
import dg.construct
import dg.query


def fill_optparser (parser_view):

    pv = parser_view

    pv.set_desc(p_("subcommand description",
                   "Transform Serbian Cyrillic text in the glossary into "
                   "Serbian Latin."))


class Subcommand (object):

    def __init__ (self, options, global_options):

        self._options = options


    def __call__ (self, gloss):

        srkey = "sr"
        srlatkey = "sr@latin"

        # Do nothing if Serbian is not one of the glossary languages.
        if srkey not in gloss.languages:
            return gloss

        # Convert text in all nodes where it exists and is in Serbian.
        for gnode in dg.query.descendant_nodes(gloss):
            if getattr(gnode, "lang", "") == srkey:
                gnode.lang = srlatkey
                if hasattr(gnode, "text"):
                    gnode.text = self._conv_text(gnode.text)
        if gloss.lang == srkey:
            gloss.lang = srlatkey

        # Convert Wikipedia root links.
        for gnode in dg.query.descendant_nodes(gloss, dg.construct.Extroot):
            for i in range(len(gnode.rooturl.text)):
                url = gnode.rooturl.text[i]
                if "sr.wikipedia" in url:
                    gnode.rooturl.text[i] = url.replace("sr-ec", "sr-el")

        # Convert language ID of Serbian to Serbian Latin.
        serbian = gloss.languages.pop(srkey)
        serbian.id = srlatkey
        gloss.languages[srlatkey] = serbian

        # Convert language ID in all d-sets too.
        for dset in dg.query.descendant_dsets(gloss):
            dset.rename_lang(srkey, srlatkey)

        return gloss


    def _conv_text (self, text):

        ntext = type(text)()
        for seg in text:
            if isinstance(seg, dg.construct.Text):
                if getattr(seg, "lang", "sr") == "sr":
                    ntext.append(self._conv_text(seg))
                else:
                    ntext.append(seg)
            else:
                ntext.append(sr_c2l(seg))

        return ntext


_dict_c2l = {
    u'а':u'a', u'б':u'b', u'в':u'v', u'г':u'g', u'д':u'd', u'ђ':u'đ',
    u'е':u'e', u'ж':u'ž', u'з':u'z', u'и':u'i', u'ј':u'j', u'к':u'k',
    u'л':u'l', u'љ':u'lj',u'м':u'm', u'н':u'n', u'њ':u'nj',u'о':u'o',
    u'п':u'p', u'р':u'r', u'с':u's', u'т':u't', u'ћ':u'ć', u'у':u'u',
    u'ф':u'f', u'х':u'h', u'ц':u'c', u'ч':u'č', u'џ':u'dž',u'ш':u'š',
    u'А':u'A', u'Б':u'B', u'В':u'V', u'Г':u'G', u'Д':u'D', u'Ђ':u'Đ',
    u'Е':u'E', u'Ж':u'Ž', u'З':u'Z', u'И':u'I', u'Ј':u'J', u'К':u'K',
    u'Л':u'L', u'Љ':u'Lj',u'М':u'M', u'Н':u'N', u'Њ':u'Nj',u'О':u'O',
    u'П':u'P', u'Р':u'R', u'С':u'S', u'Т':u'T', u'Ћ':u'Ć', u'У':u'U',
    u'Ф':u'F', u'Х':u'H', u'Ц':u'C', u'Ч':u'Č', u'Џ':u'Dž',u'Ш':u'Š',
    # accented (the keys are now 2-char):
    #u'а̑':u'â', u'о̑':u'ô',
}

def sr_c2l (text):
    """
    Transliterate Serbian Cyrillic text to Serbian Latin.

    Properly converts uppercase digraphs, e.g.
    Љубљана→Ljubljana, but ЉУБЉАНА→LJUBLJANA.

    @param text: Cyrillic text to transform
    @type text: string

    @returns: the text in Latin
    @rtype: string
    """

    tlen = len(text)
    nlist = []
    for i in range(tlen):
        c = text[i]
        c2 = text[i:i+2]
        r = _dict_c2l.get(c2) or _dict_c2l.get(c)
        if r is not None:
            if (    len(r) > 1 and c.isupper()
                and (   (i + 1 < tlen and text[i + 1].isupper())
                     or (i > 0 and text[i - 1].isupper()))
            ):
                nlist.append(r.upper())
            else:
                nlist.append(r)
        else:
            nlist.append(c);
    ntext = "".join(nlist)
    return ntext

