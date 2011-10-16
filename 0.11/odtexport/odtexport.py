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
import urlparse
import datetime

# pylint: disable-msg=E0611
from pkg_resources import resource_filename
from lxml import etree
import tidy
from PIL import Image

#from trac.core import *
from trac.core import Component, implements
from trac.mimeview.api import IContentConverter, Context
from trac.wiki import Formatter
from trac.util.html import Markup
from trac.util.text import unicode_quote
from trac.web.chrome import Chrome
from trac.config import Option, IntOption, BoolOption, ListOption
from trac.attachment import Attachment

#pylint: disable-msg=C0301,C0111

__all__ = ("ODTExportPlugin")

INCH_TO_CM = 2.54

class ODTExportError(Exception): pass

class ODTExportPlugin(Component):
    """Convert Wiki pages to ODT."""
    implements(IContentConverter)

    img_width = Option('odtexport', 'img_default_width', '8cm')
    img_height = Option('odtexport', 'img_default_height', '6cm')
    img_dpi = IntOption('odtexport', 'dpi', '96')
    get_remote_images = BoolOption('odtexport', 'get_remote_images', True)
    replace_keyword = Option('odtexport', 'replace_keyword', 'TRAC-ODT-INSERT')
    wikiversion_keyword = Option('odtexport', 'wikiversion_keyword',
                                 'TRAC-ODT-WIKIVERSION')
    wikiname_keyword = Option('odtexport', 'wikiname_keyword',
                              'TRAC-ODT-WIKINAME')
    timestamp_keyword = Option('odtexport', 'timestamp_keyword',
                               'TRAC-ODT-TIMESTAMP')
    cut_start_keyword = Option('odtexport', 'cut_start_keyword',
                               'TRAC-ODT-CUT-START')
    cut_stop_keyword = Option('odtexport', 'cut_stop_keyword',
                              'TRAC-ODT-CUT-STOP')
    remove_macros = ListOption('odtexport', 'remove_macros',
                           "PageOutline, TracGuideToc, TOC, TranslatedPages")

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('odt', 'OpenDocument', 'odt', 'text/x-trac-wiki',
               'application/vnd.oasis.opendocument.text', 5)


    def convert_content(self, req, input_type, content, output_type): # pylint: disable-msg=W0613
        self.page_name = req.args.get('page', 'WikiStart')
        #wikipage = WikiPage(self.env, self.page_name)
        template = self.get_template_name(content)
        html = self.wiki_to_html(content, req)
        #return (html, "text/plain")
        odtfile = ODTFile(self.page_name, req.args.get('version', 'latest'),
                          template, self.env, # pylint: disable-msg=E1101
                          options={
                              "img_width": self.img_width,
                              "img_height": self.img_height,
                              "img_dpi": self.img_dpi,
                              "get_remote_images": self.get_remote_images,
                              "replace_keyword": self.replace_keyword,
                              "wikiversion_keyword": self.wikiversion_keyword,
                              "wikiname_keyword": self.wikiname_keyword,
                              "timestamp_keyword": self.timestamp_keyword,
                              "cut_start_keyword": self.cut_start_keyword,
                              "cut_stop_keyword": self.cut_stop_keyword,
                          })
        odtfile.open()
        #return (odtfile.import_xhtml(html), "text/plain")
        odtfile.import_xhtml(html)
        newdoc = odtfile.save()
        return (newdoc, "application/vnd.oasis.opendocument.text")

    def get_template_name(self, wikitext):
        template_macro = re.search('\[\[OdtTemplate\(([^)]+)\)\]\]', wikitext)
        if template_macro:
            tpl = template_macro.group(1)
            if tpl.endswith(".odt"):
                return tpl
            else:
                return "%s.odt" % tpl
        return "wikipage.odt"

    def wiki_to_html(self, wikitext, req):
        self.env.log.debug('start function wiki_to_html') # pylint: disable-msg=E1101

        # Remove some macros (TOC is better handled in ODT itself)
        for macro in self.remove_macros:
            wikitext = re.sub('\[\[%s(\([^)]*\))?\]\]' % macro, "", wikitext)

        # Now convert wiki to HTML
        out = StringIO()
        context = Context.from_request(req, absurls=True)
        Formatter(self.env, # pylint: disable-msg=E1101
                  context('wiki', self.page_name)).format(wikitext, out)
        html = Markup(out.getvalue())
        html = html.encode("utf-8", 'replace')

        # Clean up the HTML
        html = re.sub('<span class="icon">.</span>', '', html) # Remove external link icon
        tidy_options = dict(output_xhtml=1, add_xml_decl=1, indent=1,
                            tidy_mark=0, input_encoding='utf8',
                            output_encoding='utf8', doctype='auto',
                            wrap=0, char_encoding='utf8')
        html = tidy.parseString(html, **tidy_options)
        # Replace nbsp with entity:
        # http://www.mail-archive.com/analog-help@lists.meer.net/msg03670.html
        html = str(html).replace("&nbsp;", "&#160;")
        # Tidy creates newlines after <pre> (by indenting)
        html = re.sub('<pre([^>]*)>\n', '<pre\\1>', html)
        return html

#    def get_title(self, wikitext, req):
#        '''Get page title from first header in outline'''
#        out = StringIO()
#        context = Context(Resource('wiki', self.page_name), req.abs_href, req.perm)
#        context.req = req
#        outline = OutlineFormatter(self.env, context)
#        outline.format(wikitext, out, 1, 1)
#        for depth, anchor, text in outline.outline:
#            if depth == 1:
#                return text
#        return self.page_name


class ODTFile(object):
    """
    The class doing the actual conversion from XHTML to ODT

    The ODT template name is given as an argument to the constructor, and will
    be looked for in the directories of `template_dirs`. Those
    directories are, in order:

    1. the attachments of the current page
    2. the ``templates`` subdirectory of the Trac instance
    3. the ``templates`` subdirectory of the odt plugin installation

    :ivar page_name: the wiki page name
    :type page_name: str
    :ivar template: the filename of the ODT template (without the path)
    :type template: str
    :ivar template_dirs: the list of directories to search for the ODT
        template. The first match found is used.
    """

    def __init__(self, page_name, page_version, template, env, options):
        self.page_name = page_name
        self.page_version = page_version
        self.template = template
        self.env = env
        self.options = options
        self.template_dirs = [
            self.env.get_templates_dir(),
            resource_filename(__name__, 'templates'),
        ]
        self.template_dirs.insert(0, os.path.join(self.env.path,
                'attachments', "wiki", unicode_quote(self.page_name)))
        self.xml = {
            "content": "",
            "styles": "",
        }
        self.tmpdir = tempfile.mkdtemp(prefix="trac-odtexport")
        self.styles = {}
        self.autostyles = {}
        self.style_name_re = re.compile('style:name="([^"]+)"') 
        self.fonts = {}
        self.zfile = None

    def get_template_path(self):
        for tpldir in self.template_dirs:
            cur_filename = os.path.join(tpldir, self.template)
            if os.path.exists(cur_filename):
                return os.path.normpath(cur_filename)
        raise ODTExportError("Can't find ODT template %s" % self.template)

    def open(self):
        template = self.get_template_path()
        self.zfile = zipfile.ZipFile(template, "r")
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
        #self.env.log.debug(odt) # debug
        self.insert_content(odt)
        self.add_styles()

    def xhtml_to_odt(self, xhtml):
        xsl_dir = resource_filename(__name__, 'xsl')
        xslt_doc = etree.parse(os.path.join(xsl_dir, "xhtml2odt.xsl"))
        transform = etree.XSLT(xslt_doc)
        xhtml = self.handle_images(xhtml)
        #self.env.log.debug(xhtml) # debug
        xhtml = etree.fromstring(xhtml) # must be valid xml
        if hasattr(etree.XSLT, "strparam"):
            url = etree.XSLT.strparam(
                      self.env.abs_href("/wiki/%s" % self.page_name))
            img_width = etree.XSLT.strparam(self.options["img_width"])
            img_height = etree.XSLT.strparam(self.options["img_height"])
        else: # lxml < 2.2
            url = "'%s'" % self.env.abs_href("/wiki/%s" % self.page_name)
            img_width = "'%s'" % self.options["img_width"]
            img_height = "'%s'" % self.options["img_height"]
        odt = transform(xhtml, url=url,
                        heading_minus_level="0",
                        img_default_width=img_width,
                        img_default_height=img_height,
                        )
        return str(odt).replace('<?xml version="1.0" encoding="utf-8"?>','')

    def handle_images(self, html):
        base_url = self.env.abs_href("/")
        # Make relative links where it makes sense
        #html = re.sub('<img ([^>]*)src="%s' % base_url, '<img \\1src="', html)
        base_url_parsed = urlparse.urlparse(base_url)
        root_url = str("%s://%s" % (base_url_parsed[0], base_url_parsed[1]))
        # Make server-relative links absolute (we don't know what the
        # document_root is)
        html = re.sub('<img ([^>]*)src="(/[^"]+)"',
                      '<img \\1src="%s\\2"' % root_url, html)
        html = re.sub('<a ([^>]*)href="(/[^"]+)"',
                      '<a \\1href="%s\\2"' % root_url, html)
        # Handle attached images
        html = re.sub('<img [^>]*src="(%s/raw-attachment/([^/]+)(?:/([^"]*))?)"'
                      % base_url, self.handle_attached_img, html)
        # Handle chrome images
        html = re.sub('<img [^>]*src="(%s/chrome/([^"]+))"'
                      % base_url, self.handle_chrome_img, html)
        # Handle remote images
        if self.options["get_remote_images"] and \
                str(self.options["get_remote_images"]).lower() != "false":
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
            for tpdir in [os.path.normpath(htdir[1]) for htdir
                        in provider.get_htdocs_dirs() if htdir[0] == prefix]:
                path = os.path.normpath(os.path.join(tpdir, filename))
                assert os.path.commonprefix([tpdir, path]) == tpdir
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
        try:
            remoteimg = urllib2.urlopen(src)
            tmpimg_fd, tmpfile = tempfile.mkstemp()
            tmpimg = os.fdopen(tmpimg_fd, 'w')
            tmpimg.write(remoteimg.read())
            tmpimg.close()
            remoteimg.close()
            ret = self.handle_img(img_mo.group(), src, tmpfile)
            os.remove(tmpfile)
            return ret
        except (urllib2.HTTPError, urllib2.URLError):
            return img_mo.group()

    def handle_img(self, full_tag, src, filename):
        self.env.log.debug('Importing image: %s' % filename)
        if not os.path.exists(filename):
            raise ODTExportError('Image "%s" is not readable or does not exist'
                                 % filename)
        # TODO: generate a filename (with tempfile.mkstemp) to avoid weird
        # filenames. Maybe use img.format for the extension
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
            width_mo = re.search('width="([0-9]+)(?:px)?"', full_tag)
            if width_mo:
                newwidth = (float(width_mo.group(1)) /
                            float(self.options["img_dpi"]) * INCH_TO_CM)
                height = height * newwidth / width
                width = newwidth
                self.env.log.debug('Forced width: %spx. Size will be: %scm x %scm'
                                   % (width_mo.group(1), width, height))
                full_tag = full_tag.replace(width_mo.group(), "")
            else:
                width = width / float(self.options["img_dpi"]) * INCH_TO_CM
                height = height / float(self.options["img_dpi"]) * INCH_TO_CM
            newsrc += '" width="%scm" height="%scm' % (width, height)
        return full_tag.replace(src, newsrc)

    def insert_content(self, content):
        for kw in ["replace", "wikiversion", "wikiname", "timestamp",
                   "cut_start", "cut_stop"]:
            self.options[kw+"_keyword"] = str(self.options[kw+"_keyword"])

        for k, v in {'wikiversion': str(self.page_version),
                     'wikiname': str(self.page_name),
                     'timestamp': str(datetime.datetime.now())}.iteritems():
            for xmltype in self.xml.keys():
                #self.env.log.debug("Key %s, Value %s, xml %s\n"%(k,v,xmltype))
                if self.options[k+"_keyword"] and self.xml[xmltype].count(
                    self.options[k+"_keyword"]) > 0:
                    self.xml[xmltype] = re.sub(
                        re.escape(self.options[k+"_keyword"]),
                        v, self.xml[xmltype])


        if self.options["replace_keyword"] and self.xml["content"].count(
                self.options["replace_keyword"]) > 0:
            self.xml["content"] = re.sub(
                    "<text:p[^>]*>" +
                    re.escape(self.options["replace_keyword"])
                    +"</text:p>", content, self.xml["content"])
        else:
            self.xml["content"] = self.xml["content"].replace(
                '</office:text>',
                content + '</office:text>')
        # Cut unwanted text
        if self.xml["content"].count(self.options["cut_start_keyword"]) > 0 \
                and self.xml["content"].count(
                    self.options["cut_stop_keyword"]) > 0:
            self.xml["content"] = re.sub(
                    re.escape(self.options["cut_start_keyword"])
                    + ".*" +
                    re.escape(self.options["cut_stop_keyword"]),
                    "", self.xml["content"])

    def add_styles(self):
        """
        Add missing styles and fonts using the dedicated stylesheet from
        xhtml2odt
        """
        xsl_dir = resource_filename(__name__, 'xsl')
        xslt_doc = etree.parse(os.path.join(xsl_dir, "styles.xsl"))
        transform = etree.XSLT(xslt_doc)
        contentxml = etree.fromstring(self.xml["content"])
        stylesxml = etree.fromstring(self.xml["styles"])
        self.xml["content"] = str(transform(contentxml))
        self.xml["styles"] = str(transform(stylesxml))

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
        # main styles
        if self.styles:
            styles = "\n".join(self.styles.values())
            self.xml["styles"] = self.xml["styles"].replace(
                "</office:styles>", "%s</office:styles>" % styles)
        # fonts
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
            for cur_file in files:
                realpath = os.path.join(root, cur_file)
                internalpath = os.path.join(root.replace(self.tmpdir, ""), cur_file)
                newzf.write(realpath, internalpath)
        newzf.close()
        shutil.rmtree(self.tmpdir)
        # Return the StringIO
        return document.getvalue()

