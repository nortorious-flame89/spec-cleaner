# vim: set ts=4 sw=4 et: coding=UTF-8

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import sys
import tempfile
import subprocess
import shlex
import os.path

from .rpmsection import Section
from .rpmexception import RpmException
from .rpmcopyright import RpmCopyright
from .rpmdescription import RpmDescription
from .rpmprune import RpmClean
from .rpmprune import RpmChangelog
from .rpmpreamble import RpmPreamble
from .rpmpreamble import RpmPackage
from .rpmprep import RpmPrep
from .rpmbuild import RpmBuild
from .rpmcheck import RpmCheck
from .rpminstall import RpmInstall
from .rpmscriplets import RpmScriptlets
from .rpmfiles import RpmFiles
from .rpmregexp import RegexpSingle


class RpmSpecCleaner(object):
    """
    Class wrapping all section parsers reponsible for ensuring
    that all sections are checked and accounted for.
    If the section is required and not found it is created with
    blank values as fixme for the spec creator.
    """
    specfile = None
    fin = None
    fout = None
    current_section = None
    _previous_line = None
    _previous_nonempty_line = None


    def __init__(self, specfile, output, pkgconfig, inline, diff, diff_prog, minimal):
        self.specfile = specfile
        self.output = output
        self.pkgconfig = pkgconfig
        self.inline = inline
        self.diff = diff
        self.diff_prog = diff_prog
        self.minimal = minimal
        #run gvim(diff) in foreground mode
        if self.diff_prog.startswith("gvim") and " -f" not in self.diff_prog:
            self.diff_prog += " -f"
        self.reg = RegexpSingle(specfile)
        self.fin = open(self.specfile)

        # Section starts detection
        self.section_starts = [
            (self.reg.re_spec_package, RpmPackage),
            (self.reg.re_spec_description, RpmDescription),
            (self.reg.re_spec_prep, RpmPrep),
            (self.reg.re_spec_build, RpmBuild),
            (self.reg.re_spec_install, RpmInstall),
            (self.reg.re_spec_clean, RpmClean),
            (self.reg.re_spec_check, RpmCheck),
            (self.reg.re_spec_scriptlets, RpmScriptlets),
            (self.reg.re_spec_files, RpmFiles),
            (self.reg.re_spec_changelog, RpmChangelog)
        ]

        if self.output:
            self.fout = open(self.output, 'w')
        elif self.inline:
            fifo = StringIO()
            while True:
                string = self.fin.read(500 * 1024)
                if len(string) == 0:
                    break
                fifo.write(string)

            self.fin.close()
            fifo.seek(0)
            self.fin = fifo
            self.fout = open(self.specfile, 'w')
        elif self.diff:
            self.fout = tempfile.NamedTemporaryFile(mode='w+', prefix=os.path.split(self.specfile)[-1]+'.', suffix='.spec')
        else:
            self.fout = sys.stdout


    def _detect_new_section(self, line):
        # Detect if we have multiline value from preamble
        if hasattr(self.current_section, 'multiline') and self.current_section.multiline:
            return None

        # Detect if we match condition and that is from global space
        # Ie like in the optional packages where if is before class definition
        # For the "if" we need to detect it more smartly:
        #   check if the current line is starting new section, and if so
        #   if previous non-empty-uncommented line was starting the condition
        #   we end up the condition section in preamble (if applicable) and proceed to output
        if self.reg.re_else.match(line) or self.reg.re_endif.match(line) or \
             (type(self.current_section) is Section and self.reg.re_if.match(line)):
            if not hasattr(self.current_section, 'condition') or \
                  (hasattr(self.current_section, 'condition') and not self.current_section.condition):
                # If we have to break out we go ahead with small class
                # which just print the one evil line
                return Section

        # try to verify if we start some specific section
        for (regexp, newclass) in self.section_starts:
            if regexp.match(line):
                # check if we are in if conditional and act accordingly if we change sections
                if hasattr(self.current_section, 'condition') and self.current_section.condition:
                    self.current_section.condition = False
                    if hasattr(self.current_section, 'end_subparagraph'):
                        self.current_section.end_subparagraph(True)
                return newclass

        # if we still are here and we are just doing copyright
        # and we are not on commented line anymore, just jump to Preamble
        if isinstance(self.current_section, RpmCopyright):
            if not self.reg.re_comment.match(line):
                return RpmPreamble
            # if we got two whitespaces then the copyright also ended
            if self._previous_line == '' and line == '':
                return RpmPreamble

        # If we actually start matching global content again we need to
        # switch back to preamble, ie %define after %description/etc.
        # This is seriously ugly but can't think of cleaner way
        # WARN: Keep in sync with rpmregexps for rpmpreamble section
        if not isinstance(self.current_section, RpmPreamble) and \
             not isinstance(self.current_section, RpmPackage):
            if self.reg.re_define.match(line) or self.reg.re_global.match(line) or \
                 self.reg.re_bcond_with.match(line) or \
                 self.reg.re_requires.match(line) or self.reg.re_requires_phase.match(line) or \
                 self.reg.re_buildrequires.match(line) or self.reg.re_prereq.match(line) or \
                 self.reg.re_recommends.match(line) or self.reg.re_suggests.match(line) or \
                 self.reg.re_name.match(line) or self.reg.re_version.match(line) or \
                 self.reg.re_release.match(line) or self.reg.re_license.match(line) or \
                 self.reg.re_summary.match(line) or self.reg.re_summary_localized.match(line) or \
                 self.reg.re_url.match(line) or self.reg.re_group.match(line) or \
                 self.reg.re_vendor.match(line) or self.reg.re_source.match(line) or \
                 self.reg.re_patch.match(line) or self.reg.re_enhances.match(line) or \
                 self.reg.re_supplements.match(line) or self.reg.re_conflicts.match(line) or \
                 self.reg.re_provides.match(line) or self.reg.re_obsoletes.match(line) or \
                 self.reg.re_buildroot.match(line) or self.reg.re_buildarch.match(line) or \
                 self.reg.re_epoch.match(line) or self.reg.re_icon.match(line) or \
                 self.reg.re_packager.match(line) or self.reg.re_debugpkg.match(line) or \
                 self.reg.re_requires_eq.match(line):
                return RpmPreamble

        # If we are in clean section and encounter whitespace
        # we need to stop deleting
        # This avoids deleting %if before %files section that could
        # be deleted otherwise
        if isinstance(self.current_section, RpmClean):
            if line.strip() == '':
                return Section

        # we are staying in the section
        return None


    def run(self):
        # We always start with Copyright
        self.current_section = RpmCopyright(self.specfile)

        # FIXME: we need to store the content localy and then reorder
        #        to maintain the specs all the same (eg somebody put
        #        filelist to the top).
        for line in self.fin:
            # Remove \n to make it easier to parse things
            line = line.rstrip('\n')
            line = line.rstrip('\r')

            new_class = self._detect_new_section(line)
            # Following line is debug output with class info
            # USE: 'spec-cleaner file > /dev/null' to see the stderr output
            #sys.stderr.write("class: '{0}' line: '{1}'\n".format(new_class, line))
            if new_class:
                # If we are on minimal approach do not do anything else
                # than trivial whitespacing
                if self.minimal:
                    if isinstance(self.current_section, RpmCopyright):
                        new_class = Section
                        self.current_section.output(self.fout, False)
                        self.current_section = new_class(self.specfile)
                else:
                    # We don't want to print newlines before %else and %endif
                    if (new_class == Section and (self.reg.re_else.match(line) or self.reg.re_endif.match(line))):
                        newline = False
                    else:
                        newline = True
                    self.current_section.output(self.fout, newline)
                    # we need to sent pkgconfig option to preamble and package
                    if new_class == RpmPreamble or new_class == RpmPackage:
                        self.current_section = new_class(self.specfile, self.pkgconfig)
                    else:
                        self.current_section = new_class(self.specfile)
                    # skip empty line adding if we are switching sections
                    if self._previous_line == '' and line == '':
                        continue

            # Do not store data from clean and skip out here
            if isinstance(self.current_section, RpmClean):
                continue

            self.current_section.add(line)
            self._previous_line = line
            if line != '' or not line.startswith('#'):
                self._previous_nonempty_line = line

        self.current_section.output(self.fout)
        self.fout.flush()

        if self.diff:
            cmd = shlex.split(self.diff_prog + " " + self.specfile.replace(" ","\\ ") + " " + self.fout.name.replace(" ","\\ "))
            try:
                subprocess.call(cmd, shell=False)
            except OSError as e:
                raise RpmException('Could not execute %s (%s)' % (self.diff_prog.split()[0], e.strerror))


    def __del__(self):
        """
        We need to close the input and output files
        """

        if self.fin:
            self.fin.close()
            self.fin = None
        if self.fout:
            self.fout.close()
            self.fout = None
