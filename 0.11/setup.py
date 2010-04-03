from setuptools import setup


setup(name='OdtExportPlugin',
      version='0.4',
      packages=['odtexport'],
      author='Aurelien Bompard',
      author_email='aurelien@bompard.org',
      description='A plugin to export wiki pages as OpenDocument (ODT) files',
      entry_points={'trac.plugins': ['odtexport.odtexport=odtexport.odtexport',
                                     'odtexport.OdtTemplate=odtexport.OdtTemplate']},
      package_data={'odtexport': ['xsl/*.xsl',
                                  'xsl/document-content/*.xsl',
                                  'xsl/specific/*.xsl',
                                  'templates/*.odt',
                                  'templates/*.txt',
                                 ]},
     install_requires = [ 'Trac', 'uTidylib', 'lxml', 'PIL', ],
     )



