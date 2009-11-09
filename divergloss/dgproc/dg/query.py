# -*- coding: UTF-8 -*-

"""
Methods for selection data within the glossary.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

from dg.dset import Dset
from dg.construct import Gnode, Text


def child_nodes (gnode, gtype=None):
    """
    Get child nodes of a glossary node in a flat list.

    Child nodes may be the attributes of the given node by themselves,
    or stored in list, dict, or Dset attributes of the given Gnode.

    If a particular node type (subclass of Gnode) is given,
    than only the nodes with this type will be selected.
    If several types are wanted, they can be given as a sequence.

    @param gnode: a glossary node
    @type gnode: L{Gnode}
    @param gtype: a type of glossary nodes
    @type gtype: subclass of L{Gnode}, or a sequence thereof

    @return: child nodes
    @rtype: list of L{Gnode}
    """

    flatlst = []
    for attrname, attr in gnode.__dict__.iteritems():
        if attrname.startswith("_") or attrname == "parent":
            continue

        if type(attr) == Dset:
            flatlst.extend(attr.values())
        elif type(attr) == dict:
            flatlst.extend(attr.values())
        elif type(attr) == list:
            flatlst.extend(attr)
        else:
            flatlst.append(attr)

        # NOTE: If at any point changing type() to isinstance() above,
        # take care that Text is a subclass of list.

        if gtype is None:
            gtype = Gnode
        if hasattr(gtype, "__iter__"):
            gtypes = tuple(gtype)
        else:
            gtypes = (gtype,)

    return [x for x in flatlst if isinstance(x, gtypes)]


def descendant_nodes (gnode, gtype=None):
    """
    Get descendent nodes of a glossary node in a flat list.

    If a particular node type (subclass of Gnode) is given,
    than only the nodes with this type will be selected.
    If several types are wanted, they can be given as a sequence.

    @param gnode: a glossary node
    @type gnode: L{Gnode}
    @param gtype: a type of glossary nodes
    @type gtype: subclass of L{Gnode}, or a sequence thereof

    @return: descendant glossary nodes
    @rtype: list of L{Gnode}
    """

    children = child_nodes(gnode)
    descendants = []
    for child in children:
        descendants.append(child)
        descendants.extend(descendant_nodes(child))

    if gtype is not None:
        if hasattr(gtype, "__iter__"):
            gtypes = tuple(gtype)
        else:
            gtypes = (gtype,)
        descendants = [x for x in descendants if isinstance(x, gtypes)]

    return descendants


def descendant_dsets (gnode):
    """
    Get descendent d-sets of a glossary node in a flat list.

    @param gnode: a glossary node
    @type gnode: L{Gnode}

    @return: descendant dsets
    @rtype: list of L{Dset}
    """

    dsets = []
    for attrname, attr in gnode.__dict__.iteritems():
        if attrname.startswith("_") or attrname == "parent":
            continue
        if isinstance(attr, Dset):
            dsets.append(attr)

    for child in child_nodes(gnode):
        dsets.extend(descendant_dsets(child))

    return dsets

