"""
This is a pseudo-macro which does not output anything, but is used by the ODT
renderer to choose which file to use as the ODT template.
"""

from trac.wiki.macros import WikiMacroBase

class OdtTemplateMacro(WikiMacroBase): # pylint: disable-msg=W0223
    def expand_macro(self, formatter, name, args): # pylint: disable-msg=W0613
        return ''


