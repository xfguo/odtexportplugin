"""
This plugin can convert a wiki page to the OpenDocument Text (ODT) format,
standardized as ISO/IEC 26300:2006, and the native format of office suites such
as OpenOffice.org, KOffice, and others.

It uses a template ODT file which will be filled with the converted content of
the exported Wiki page.
"""

from StringIO import StringIO
import tempfile
import shutil
import re
import os
import zipfile
import urllib2

# pylint: disable-msg=E0611
from pkg_resources import resource_filename
from lxml import etree
import tidy
from PIL import Image

#from trac.core import *
from trac.core import Component, implements
from trac.mimeview.api import IContentConverter
from trac.wiki.formatter import wiki_to_html
from trac.web.chrome import Chrome
from trac.config import Option
from trac.attachment import Attachment

import odtstyle

#pylint: disable-msg=C0301,C0111

INCH_TO_CM = 2.54


class ODTExportError(Exception): pass

class ODTExportPlugin(Component):
    """Convert Wiki pages to ODT."""
    implements(IContentConverter)

    img_max_x = Option('odtexport', 'img_max_x', '0')
    img_max_y = Option('odtexport', 'img_max_y', '0')
    img_dpi = Option('odtexport', 'dpi', '96')
    get_remote_images = Option('odtexport', 'get_remote_images', True)
    replace_keyword = Option('odtexport', 'replace_keyword', 'TRAC-ODT-INSERT')
    charset = Option('trac', 'default_charset', 'utf-8')

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('odt', 'OpenDocument', 'odt', 'text/x-trac-wiki', 'application/vnd.oasis.opendocument.text', 5)

    def convert_content(self, req, input_type, content, output_type):
        page_name = req.args.get('page', 'WikiStart')
        #wikipage = WikiPage(self.env, page_name)
        html = self.wiki_to_html(content, req)
        #return (html, "text/plain")
        templates_dir = resource_filename(__name__, 'templates')
        odtfile = ODTFile(os.path.join(templates_dir, "wikipage.odt"),
                          self.env, options={
                              "img_max_x": self.img_max_x,
                              "img_max_y": self.img_max_y,
                              "img_dpi": self.img_dpi,
                              "get_remote_images": self.get_remote_images,
                              "replace_keyword": self.replace_keyword
                          })
        odtfile.open()
        #return (odtfile.import_xhtml(html), "text/plain")
        odtfile.import_xhtml(html)
        newdoc = odtfile.save()
        return (newdoc, "application/vnd.oasis.opendocument.text")

    def wiki_to_html(self, wikitext, req):
        self.env.log.debug('start function wiki_to_html')
        page_name = req.args.get('page', 'WikiStart')

        ##Remove exclude expressions
        #for r in EXCLUDE_RES:
        #    text = r.sub('', text)
       
        # Remove some macros to avoid wiki processing
        for macro in ["PageOutline", "TracGuideToc"]:
            wikitext = wikitext.replace('[[%s]]' % macro, '')

        # expand image macro shortcut
        wikitext = re.sub('\[\[Image\(([^\:)]+)\)\]\]', r'[[Image(%s:\1)]]' % page_name, wikitext)
       
        #context = Context(Resource('wiki', page_name), req.abs_href, req.perm)
        #context.req = req
       
        # Now convert in that context
        # TODO: Use format_to_html instead of old wiki_to_html
        html = wiki_to_html(wikitext, self.env, req, absurls=True)
        html = html.encode(self.charset, 'replace')
        # Remove external link icon
        html = re.sub('<span class="icon">.</span>', '', html)
        # Replace nbsp with entity:
        # http://www.mail-archive.com/analog-help@lists.meer.net/msg03670.html
        html = html.replace("\xa0", "&#160;")
        tidy_options = dict(output_xhtml=1, add_xml_decl=1, indent=1,
                            tidy_mark=0, #input_encoding=str(self.charset),
                            output_encoding='utf8', doctype='auto',
                            wrap=0, char_encoding='utf8')
        html = tidy.parseString(html, **tidy_options)
        # Replace nbsp with entity:
        html = str(html).replace("&nbsp;", "&#160;")
        # Tidy creates newlines after <pre> (by indenting)
        html = re.sub('<pre([^>]*)>\n', '<pre\\1>', html)
        return html

#    def get_title(self, wikitext, req):
#        '''Get page title from first header in outline'''
#        page_name = req.args.get('page', 'WikiStart')
#        out = StringIO()
#        context = Context(Resource('wiki', page_name), req.abs_href, req.perm)
#        context.req = req
#        outline = OutlineFormatter(self.env, context)
#        outline.format(wikitext, out, 1, 1)
#        for depth, anchor, text in outline.outline:
#            if depth == 1:
#                return text
#        return page_name


class ODTFile(object):

    def __init__(self, filename, env, options):
        self.filename = filename
        self.env = env
        self.options = options
        self.xml = {
            "content": "",
            "styles": "",
        }
        self.tmpdir = tempfile.mkdtemp(prefix="trac-odtexport")
        self.styles = {}
        self.autostyles = {}
        self.style_name_re = re.compile('style:name="([^"]+)"') 
        self.fonts = {}

    def open(self):
        self.zfile = zipfile.ZipFile(self.filename, "r")
        for name in self.zfile.namelist():
            fname = os.path.join(self.tmpdir, name)
            if not os.path.exists(os.path.dirname(fname)):
                os.makedirs(os.path.dirname(fname))
            if name[-1] == "/":
                if not os.path.exists(fname):
                    os.mkdir(fname)
                continue
            fname_h = open(fname, "w")
            fname_h.write(self.zfile.read(name))
            fname_h.close()
        for xmlfile in self.xml:
            self.xml[xmlfile] = self.zfile.read("%s.xml" % xmlfile)

    def import_xhtml(self, xhtml):
        odt = self.xhtml_to_odt(xhtml)
        #return odt
        self.insert_content(odt)
        self.add_styles()

    def xhtml_to_odt(self, xhtml):
        xsl_dir = resource_filename(__name__, 'xsl')
        xslt_doc = etree.parse(os.path.join(xsl_dir, "xhtml2odt.xsl"))
        transform = etree.XSLT(xslt_doc)
        xhtml = self.handle_images(xhtml)
        #return xhtml
        xhtml = etree.fromstring(xhtml) # must be valid xml
        root_url = etree.XSLT.strparam(self.env.abs_href("/"))
        odt = transform(xhtml, root_url=root_url, heading_minus_level="0")
        return str(odt).replace('<?xml version="1.0" encoding="utf-8"?>','')

    def handle_images(self, html):
        base_url = self.env.abs_href("/")
        # Make relative links where it makes sense
        #html = re.sub('<img ([^>]*)src="%s' % base_url, '<img \\1src="', html)
        # Handle attached images
        #local_imgs = re.findall('<img [^>]*src="(/[^"]+)"', html)
        html = re.sub('<img [^>]*src="(%s/raw-attachment/([^/]+)(?:/([^"]*))?)"'
                      % base_url, self.handle_attached_img, html)
        # Handle chrome images
        html = re.sub('<img [^>]*src="(%s/chrome/([^"]+))"'
                      % base_url, self.handle_chrome_img, html)
        # Handle remote images
        if self.options["get_remote_images"]:
            html = re.sub('<img [^>]*src="(https?://[^"]+)"',
                          self.handle_remote_img, html)
        return html

    def handle_attached_img(self, img_mo):
        self.env.log.debug('handling local image: %s' % img_mo.group())
        src, realm, path = img_mo.groups()
        path_segments = path.split("/")
        parent_id = '/'.join(path_segments[:-1])
        filename = len(path_segments) > 1 and path_segments[-1]
        attachment = Attachment(self.env, realm, parent_id, filename)
        filename = attachment.path
        if not os.path.exists(filename): # fallback
            return self.handle_remote_img(img_mo)
        return self.handle_img(img_mo.group(), src, filename)

    def handle_chrome_img(self, img_mo):
        """Copied from Chrome.process_request()"""
        self.env.log.debug('handling chrome image: %s' % img_mo.group())
        src, filename = img_mo.groups()
        # Normalize the filename. Some people find it funny to create URLs such as
        # /chrome/site/../common/trac_logo_mini.png. Yes, that's you WikiFormatting.
        normed_filename = os.path.normpath(filename)
        normed_string = img_mo.group().replace(filename, normed_filename)
        base_url = self.env.abs_href("/")
        img_mo = re.match('<img [^>]*src="(%s/chrome/([^/]+)/+([^"]+))"'
                          % base_url, normed_string)
        src, prefix, filename = img_mo.groups()
        chrome = Chrome(self.env)
        for provider in chrome.template_providers:
            for dir in [os.path.normpath(dir[1]) for dir
                        in provider.get_htdocs_dirs() if dir[0] == prefix]:
                path = os.path.normpath(os.path.join(dir, filename))
                assert os.path.commonprefix([dir, path]) == dir
                if os.path.isfile(path):
                    return self.handle_img(img_mo.group(), src, path)
        # fallback
        return self.handle_remote_img(img_mo)

    def handle_remote_img(self, img_mo):
        """
        Download the image to a temporary location and call
        handle_img(html, img_mo, temp_location)
        """
        self.env.log.debug('handling remote image: %s' % img_mo.group())
        src = img_mo.group(1)
        self.env.log.debug('Downloading image: %s' % src)
        # TODO: proxy support
        remoteimg = urllib2.urlopen(src)
        tmpimg_fd, tmpfile = tempfile.mkstemp()
        tmpimg = os.fdopen(tmpimg_fd, 'w')
        tmpimg.write(remoteimg.read())
        tmpimg.close()
        remoteimg.close()
        ret = self.handle_img(img_mo.group(), src, tmpfile)
        os.remove(tmpfile)
        return ret

    def handle_img(self, full_tag, src, filename):
        self.env.log.debug('Importing image: %s' % filename)
        if not os.path.exists(filename):
            raise ODTExportError('Image "%s" is not readable or does not exist' % filename)
        # TODO: generate a filename (with tempfile.mkstemp) to avoid weird filenames.
        #       Maybe use img.format for the extension
        if not os.path.exists(os.path.join(self.tmpdir, "Pictures")):
            os.mkdir(os.path.join(self.tmpdir, "Pictures"))
        shutil.copy(filename, os.path.join(self.tmpdir, "Pictures",
                                           os.path.basename(filename)))
        newsrc = "Pictures/%s" % os.path.basename(filename)
        try:
            img = Image.open(filename)
        except IOError:
            self.env.log.warn('Failed to identify image: %s' % filename)
        else:
            width, height = img.size
            self.env.log.debug('Detected size: %spx x %spx' % (width, height))
            width = width / float(self.options["img_dpi"]) * INCH_TO_CM
            height = height / float(self.options["img_dpi"]) * INCH_TO_CM
            newsrc += '" width="%scm" height="%scm' % (width, height)
        return full_tag.replace(src, newsrc)

    def insert_content(self, content):
        if self.options["replace_keyword"] and \
            self.xml["content"].count(self.options["replace_keyword"]) > 0:
            # TODO: this creates an empty line before and after the
            # replace_keyword. It's not optimal, I should use a regexp to
            # remove the previous opening <text:p> tag and the corresponding
            # closing tag.
            self.xml["content"] = self.xml["content"].replace(
                self.options["replace_keyword"],
                '</text:p>%s<text:p text:style-name="Text_20_body">' % content)
        else:
            self.xml["content"] = self.xml["content"].replace(
                '</office:text>',
                content + '</office:text>')

    def import_style(self, style, is_mainstyle=False):
        style_name_mo = self.style_name_re.search(style)
        name = style_name_mo.group(1)
        if name in self.styles:
            return # already added
        if self.xml["content"].count('style:name="%s"' % name) > 0 or \
           self.xml["styles"].count('style:name="%s"' % name) > 0:
            return # already present in the template
        if is_mainstyle:
            self.styles[name] = style
        else:
            self.autostyles[name] = style

    def import_font(self, font):
        style_name_mo = self.style_name_re.search(font)
        name = style_name_mo.group(1)
        if name in self.fonts:
            return # already added
        if self.xml["styles"].count('<style:font-face style:name="%s"' % name) > 0 or \
            self.xml["content"].count('<style:font-face style:name="%s"' % name) > 0:
            return # already present in the template
        self.fonts[name] = font

    def add_styles(self):
        templates_dir = resource_filename(__name__, 'templates')
        odtstyle.add_styles(templates_dir, self.xml["content"],
                            self.import_style, self.import_font)

    def compile(self):
        # autostyles
        if self.autostyles:
            autostyles = "\n".join(self.autostyles.values())
            for xmlfile in ["content", "styles"]:
                if self.xml[xmlfile].count("<office:automatic-styles/>") > 0:
                    self.xml[xmlfile] = self.xml[xmlfile].replace(
                        "<office:automatic-styles/>",
                        "<office:automatic-styles>%s</office:automatic-styles>" %
                        autostyles)
                else:
                    self.xml[xmlfile] = self.xml[xmlfile].replace(
                        "</office:automatic-styles>",
                        "%s</office:automatic-styles>" % autostyles)
        if self.styles:
            styles = "\n".join(self.styles.values())
            self.xml["styles"] = self.xml["styles"].replace(
                "</office:styles>", "%s</office:styles>" % styles)
        if self.fonts:
            fonts = "\n".join(self.fonts.values())
            for xmlfile in ["content", "styles"]:
                self.xml[xmlfile] = self.xml[xmlfile].replace(
                    "</office:font-face-decls>",
                    "%s</office:font-face-decls>" % fonts)
        # Store the new content
        for xmlfile in self.xml:
            xmlf = open(os.path.join(self.tmpdir, "%s.xml" % xmlfile), "w")
            xmlf.write(self.xml[xmlfile])
            xmlf.close()

    def save(self):
        self.compile()
        # Create the zip file
        document = StringIO()
        newzf = zipfile.ZipFile(document, "w", zipfile.ZIP_DEFLATED)
        for root, dirs, files in os.walk(self.tmpdir):
            for file in files:
                realpath = os.path.join(root, file)
                internalpath = os.path.join(root.replace(self.tmpdir, ""), file)
                newzf.write(realpath, internalpath)
        newzf.close()
        shutil.rmtree(self.tmpdir)
        # Return the StringIO
        return document.getvalue()