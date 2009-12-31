"""
This module contains an ODT style library
"""

import os
import re
from glob import glob

# pylint: disable-msg=C0103

style_name_re = re.compile('style:name="([^"]+)"') 
need_font_re = re.compile('font-name="([^"]+)"')

def _build_style_lib(template_dirs):
    """build a library of available styles"""
    template_files = _build_templates_list(template_dirs)
    style_lib = {}
    for style_file in template_files.values():
        style_tpl = open(style_file)
        style_xml = style_tpl.read()
        style_tpl.close()
        style = _build_style(style_xml)
        if not style:
            continue
        style_lib[style["name"]] = style
    return style_lib

def _build_templates_list(template_dirs):
    """select the preferred template (used-defined or default)"""
    template_files = {}
    for template_dir in template_dirs:
        for style_file in glob(os.path.join(template_dir, "*.txt")):
            basename = os.path.basename(style_file)
            if basename not in template_files:
                template_files[basename] = style_file
    return template_files

def _build_style(style_xml):
    style_name_mo = style_name_re.search(style_xml)
    if not style_name_mo:
        return False
    style = {
        "name": style_name_mo.group(1),
        "xml": style_xml,
    }
    is_mainstyle = (style_xml.count("style:display-name=") > 0)
    style["mainstyle"] = is_mainstyle
    need_font = need_font_re.search(style_xml)
    if need_font:
        style["need_font"] = need_font.group(1)
    return style


def add_styles(template_dirs, content_xml, import_style_callback, import_font_callback):
    """
    Add the missing styles using callbacks
    """
    style_lib = _build_style_lib(template_dirs)
    for stylename in style_lib:
        if content_xml.count('style-name="%s"' % stylename) == 0:
            continue # style is not used
        style_xml = style_lib[stylename]["xml"]
        is_mainstyle = style_lib[stylename]["mainstyle"]
        import_style_callback(style_xml, is_mainstyle)
        if "need_font" in style_lib[stylename]:
            font_name = style_lib[stylename]["need_font"]
            font_xml = style_lib[font_name]["xml"]
            import_font_callback(font_xml)
    # now the more complex list and numbering items
    template_files = _build_templates_list(template_dirs)
    list_styles = '<text:list-style style:name="List_20_1" style:display-name="List 1">'
    list_item_tpl = open(template_files["list_level.txt"])
    list_item = list_item_tpl.read()
    list_item_tpl.close()
    for i in range(10):
        list_styles += list_item % {"level": i+1, "space": 0.4 * i}
    list_styles += '</text:list-style>'
    import_style_callback(list_styles, True)
    list_styles = '<text:list-style style:name="Numbering_20_1" style:display-name="Numbering 1">'
    list_item_tpl = open(template_files["numbering_level.txt"])
    list_item = list_item_tpl.read()
    list_item_tpl.close()
    for i in range(10):
        list_styles += list_item % {"level": i+1, "space": 0.5 * i}
    list_styles += '</text:list-style>'
    import_style_callback(list_styles, True)

