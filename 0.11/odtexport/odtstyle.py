"""
This module contains an ODT style library
"""

import os
import re

# pylint: disable-msg=C0103

style_name_re = re.compile('style:name="([^"]+)"') 

style_templates = { # ODT style name to template name
    "center": "center",
    "Emphasis": "emphasis",
    "sub": "subscript",
    "sup": "exponent",
    "Heading_20_1": "heading1",
    "Heading_20_2": "heading2",
    "Heading_20_3": "heading3",
    "Heading_20_4": "heading4",
    "Heading_20_5": "heading5",
    "Horizontal_20_Line": "horizontal_line",
    "image-inline": "image_inline",
    "list-item-bullet": "list_item_bullet",
    "list-item-number": "list_item_number",
    "Preformatted_20_Text": "preformatted",
    "Quotations": "quotations",
    "Teletype": "teletype",
    "Strike": "strike",
    "Strong_20_Emphasis": "strong_emphasis",
    "table-default.cell-A1": "table_cell_a1",
    "table-default.cell-B1": "table_cell_b1",
    "table-default.cell-C1": "table_cell_c1",
    "table-default.cell-A2": "table_cell_a2",
    "table-default.cell-B2": "table_cell_b2",
    "table-default.cell-C2": "table_cell_c2",
    "table-default.cell-A3": "table_cell_a3",
    "table-default.cell-B3": "table_cell_b3",
    "table-default.cell-C3": "table_cell_c3",
    "table-default.cell-A4": "table_cell_a4",
    "table-default.cell-B4": "table_cell_b4",
    "table-default.cell-C4": "table_cell_c4",
    "Table_20_Contents": "table_contents",
    "Table_20_Heading": "table_heading",
    "Underline": "underline",
}

font_templates = { # ODT font name to template name
    "Bitstream Vera Sans Mono": "vera_sans_mono",
}

def add_styles(templates_dir, content_xml, import_style_callback, import_font_callback):
    """
    Add the missing styles using callbacks
    """
    font_search_re = re.compile('font-name="([^"]+)"')
    for stylename in style_templates:
        if content_xml.count('style-name="%s"' % stylename) == 0:
            # style is not used
            continue
        style_tpl = open(os.path.join(templates_dir,
                "%s.txt" % style_templates[stylename]))
        style_xml = style_tpl.read()
        style_tpl.close()
        is_mainstyle = (style_xml.count("style:display-name=") > 0)
        import_style_callback(style_xml, is_mainstyle)
        need_font = font_search_re.search(style_xml)
        if need_font:
            font_name = need_font.group(1)
            font_tpl = open(os.path.join(templates_dir,
                "%s.txt" % font_templates[font_name]))
            import_font_callback(font_tpl.read())
            font_tpl.close()
    # now the more complex list and numbering items
    list_styles = '<text:list-style style:name="List_20_1" style:display-name="List 1">'
    list_item_tpl = open(os.path.join(templates_dir, "list_level.txt"))
    list_item = list_item_tpl.read()
    list_item_tpl.close()
    for i in range(10):
        list_styles += list_item % {"level": i+1, "space": 0.4 * i}
    list_styles += '</text:list-style>'
    import_style_callback(list_styles, True)
    list_styles = '<text:list-style style:name="Numbering_20_1" style:display-name="Numbering 1">'
    list_item_tpl = open(os.path.join(templates_dir, "numbering_level.txt"))
    list_item = list_item_tpl.read()
    list_item_tpl.close()
    for i in range(10):
        list_styles += list_item % {"level": i+1, "space": 0.5 * i}
    list_styles += '</text:list-style>'
    import_style_callback(list_styles, True)

