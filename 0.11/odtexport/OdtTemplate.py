"""
This is a pseudo-macro which does not output anything, but is used by the ODT
renderer to choose which file to use as the ODT template.
"""

from trac.wiki.macros import WikiMacroBase

class OdtTemplateMacro(WikiMacroBase): # pylint: disable-msg=W0223
    """
    Choose which file to use as the ODT template, see the
    [http://trac-hacks.org/wiki/OdtExportPlugin#Choosingatemplate wiki page]
    for details.
    """
    def expand_macro(self, formatter, name, args): # pylint: disable-msg=W0613
        return ''


