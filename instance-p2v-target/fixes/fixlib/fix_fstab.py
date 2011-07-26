#!/usr/bin/python
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

import subprocess
import re

import fixlib

def FixFstab(fname_in="/target/etc/fstab", fname_out="/target/etc/fstab"):
  """Alter the fstab to refer to new filesystems.

  This function edits the fstab file found at fname_in, locating the filesystem
  mounted on / and replacing the device with the string UUID=<new_uuid>.

  @type fname_in: string
  @param fname_in: The fstab file to read.
  @type fname_out: string
  @param fname_out: Where to write the modified file.

  """
  # TODO(benlipton): This is totally xen-specific. Better would be to use the
  # first that exists of /dev/{xvda,vda,sda}.

  # Note: This also assumes a particular partition layout (root partition on
  # /dev/${device}1, swap partition on /dev/${device}2). This is only a problem
  # if we allow configurable partition layouts, so we'll let it stand for now,
  # but for the future, the bootstrap OS's /etc/mtab probably contains enough
  # information to reconstruct the whole partitioning scheme.
  uuids = {}
  fstypes = {}
  p = subprocess.Popen(["blkid"], stdout=subprocess.PIPE)
  for line in p.communicate()[0].split('\n'):
    parts = re.match("/dev/(xvda[0-9]): UUID=\"([-a-z0-9]+)\" TYPE=\"(.+)\"",
                     line)
    if parts:
      partname, uuid, fstype = parts.groups()
      uuids[partname] = uuid
      fstypes[partname] = fstype

  if "xvda1" not in uuids:
    print uuids
    raise fixlib.FixError("Could not determine UUID of root filesystem."
                          " /etc/fstab may need to be edited by hand")

  fstab_file = open(fname_in, "r")
  new_fstab = ""
  for line in fstab_file:
    parts = line.split()
    if len(parts) >= 2 and parts[0][0] != "#":
      if parts[1] == "/":
        parts[0] = "UUID=%s" % uuids["xvda1"]
        parts[2] = fstypes["xvda1"]
        line = "\t".join(parts) + "\n"
      elif parts[2] == "swap":
        parts[0] = "UUID=%s" % uuids["xvda2"]
        line = "\t".join(parts) + "\n"
    new_fstab += line
  fstab_file.close()
  fstab_file = open(fname_out, "w")
  fstab_file.write(new_fstab)
  fstab_file.close()

def main():
  FixFstab()

if __name__ == "__main__":
  main()
