# -*- coding: UTF-8 -*-

"""
Handler for glossary parts which can differ by language and environment.

@author: Chusslove Illich (Часлав Илић) <caslav.ilic@gmx.net>
@license: GPLv3
"""

from dg.util import p_
from dg.util import error


class Dset (object):

    def __init__ (self, gloss, parent=None):

        self.gloss = gloss
        self.parent = parent
        if parent is None:
            self.parent = gloss

        self._data = {}


    def _parent_att (self, att, defval):

        val = defval
        parent = self.parent
        while parent:
            if hasattr(parent, att):
                val = getattr(parent, att)
                break
            parent = getattr(parent, "parent", None)
        return val


    def add (self, obj):

        lang = obj.lang
        if lang is None:
            lang = self._parent_att("lang", None)
        envs = obj.env
        if not envs:
            envs = self._parent_att("env", [None])

        if lang not in self._data:
            self._data[lang] = {}
        for env in envs:
            if env not in self._data[lang]:
                self._data[lang][env] = []
            self._data[lang][env].append(obj)


    def __call__ (self, lang=None, env=None):

        if lang is None:
            lang = self._parent_att("lang", None)
        if env is None:
            env = self._parent_att("env", [None])[0]

        if lang not in self._data:
            return []

        if env not in self._data[lang] and self.gloss.environments:
            # Try to select environment by closeness.
            environment = self.gloss.environments[env]
            for close_env in environment.closeto:
                if close_env in self._data[lang]:
                    env = close_env
                    break

        if env not in self._data[lang]:
            return []

        return self._data[lang][env]


    def values (self):

        return [z for x in self._data.values() for y in x.values() for z in y]


    def langs (self):

        return self._data.keys()


    def envs (self, lang=None):

        if lang is None:
            lang = self._parent_att("lang", None)

        if lang not in self._data:
            return None

        # Must collect also the environments close to this one.
        envs = []
        for env in self._data[lang]:
            if env not in envs:
                envs.append(env)
            for env2, environment in self.gloss.environments.iteritems():
                if env in environment.closeto and env2 not in envs:
                    envs.append(env2)

        return envs


    def rename_lang (self, olang, nlang):

        if olang in self._data:
            self._data[nlang] = self._data.pop(olang)


    def rename_env (self, oenv, nenv):

        for lang, envs in self._data.iteritems():
            if oenv in envs:
                envs[nenv] = envs.pop(oenv)

