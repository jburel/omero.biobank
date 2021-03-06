# BEGIN_COPYRIGHT
# END_COPYRIGHT

'''
This module adds support for "runnable" documentation to Sphinx.

To use it, add the following directive to your rst file:

.. lit-prog:: /path/to/python_mod.py

where python_mod is a python module containing code snippets
interspersed with docstrings that start with the """ .. sequence: The
content of python_mod will be added to the docs as follows:

* Python code blocks will be formatted as Sphinx code-blocks;
* Python docstrings will be included as Sphinx markup blocks.
'''

import os, tempfile
from docutils.parsers.rst.directives.misc import Include as BaseInclude


class LiterateProgrammingInclude(BaseInclude):

    def run(self):
        if (self.arguments[0].startswith('/') or
            self.arguments[0].startswith(os.sep)):
            env = self.state.document.settings.env
            self.arguments[0] = os.path.join(env.srcdir, self.arguments[0][1:])
        fo = tempfile.NamedTemporaryFile(delete=False)
        with open(str(self.arguments[0])) as fi:
          self.invert_blocks(fi, fo)
        self.arguments[0] = fo.name
        fo.close()
        res = BaseInclude.run(self)
        os.unlink(fo.name)
        return res

    def invert_blocks(self, fi, fo):
      """
      Change docstrings into Sphinx markup and code into code-blocks.

      Note that Python comments end up into code-blocks as well.  To
      avoid getting copyright info, pylint disables etc. in the docs,
      anything that comes before the first docstring is ignored.
      """
      def write_code_block(lines):
        indent = '  '
        code_block = indent + indent.join(lines)
        if not code_block.strip():
          return
        fo.write('\n.. code-block:: python\n\n')
        fo.write(code_block)
        fo.write('\n')
      in_litblock_block = False
      passed_first_litblock = False
      code_block_lines = []
      for l in fi:
        if l.startswith('""" ..'):
          write_code_block(code_block_lines)
          code_block_lines = []
          in_litblock_block = True
        elif l.startswith('"""') and in_litblock_block:
          in_litblock_block = False
          passed_first_litblock = True
        elif in_litblock_block:
          fo.write(l)
        elif passed_first_litblock:
          code_block_lines.append(l)
      if code_block_lines:
        write_code_block(code_block_lines)


def setup(app):
    app.add_directive('lit-prog', LiterateProgrammingInclude)
