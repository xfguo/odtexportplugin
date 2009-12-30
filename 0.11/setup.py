from setuptools import setup


setup(name='OdtExportPlugin',
      version='0.1',
      packages=['odtexport'],
      author='Aurelien Bompard',
      author_email='aurelien@bompard.org',
      description='A plugin to export wiki pages as OpenDocument (ODT) files',
      entry_points={'trac.plugins': ['odtexport.odtexport=odtexport.odtexport']},
      package_data={'odtexport': ['xsl/*.xsl',
                                  'xsl/document-content/*.xsl',
                                  'xsl/specific/*.xsl',
                                  'templates/*.odt',
                                  'templates/*.txt',
                                 ]},
     install_requires = [ 'Trac', 'uTidylib', 'lxml', 'PIL', ],
     )



