#
#

# Copyright (C) 2011 Google Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

"""Code for python fix scripts.

Fixlib is a package for the actual code of the python fix scripts, so that they
can be unit tested but also run with run-parts.

"""

import subprocess


class FixError(Exception):
  pass


def FindTargetHardDrive():
  """Find the name of the first hard drive on the target machine.

  Tries, in order, /dev/{xvda,vda,sda} and returns the first one that exists on
  the target machine.

  @rtype: str
  @return: name of the hard drive device to install onto

  """
  for hd in ["/dev/xvda", "/dev/vda", "/dev/sda"]:
    status = subprocess.call(["test", "-b", hd])
    if status == 0:
      return hd
  raise FixError("Could not locate a hard drive.")
