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
  mounted on / and replacing the device with the string UUID=<new_uuid>. Since
  there may have been more partitions before the transfer, comment out any
  lines that:
  - are not the root or swap partition
  - are not set as "noauto"
  - AND refer to actual block devices.

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
  disk_name = "xvda"
  p = subprocess.Popen(["blkid"], stdout=subprocess.PIPE)

  devregex = re.compile("/dev/(%s[0-9]):" % disk_name)
  uuidregex = re.compile("UUID=\"([-a-z0-9]+)\"")
  typeregex = re.compile("TYPE=\"(.+)\"")

  for line in p.communicate()[0].splitlines():
    devmatch = devregex.search(line)
    uuidmatch = uuidregex.search(line)
    typematch = typeregex.search(line)
    if devmatch and uuidmatch and typematch:
      partname = devmatch.group(1)
      uuids[partname] = uuidmatch.group(1)
      fstypes[partname] = typematch.group(1)

  if "xvda1" not in uuids or "xvda2" not in uuids:
    raise fixlib.FixError("Could not determine UUID of root and swap"
                          " filesystems. Found filesystems were: %s\n"
                          "/etc/fstab may need to be edited by hand." % uuids)

  fstab_file = open(fname_in, "r")
  new_fstab = ""
  for line in fstab_file:
    parts = line.split()
    if len(parts) >= 2 and parts[0][0] != "#":  # Line containing a filesystem
      if parts[1] == "/":  # root partition
        parts[0] = "UUID=%s" % uuids["xvda1"]
        parts[2] = fstypes["xvda1"]
        line = "\t".join(parts) + "\n"
      elif parts[2] == "swap":  # swap partition
        parts[0] = "UUID=%s" % uuids["xvda2"]
        line = "\t".join(parts) + "\n"
      elif IsAutomountedBlockDevice(parts):
        line = "# " + line
    new_fstab += line
  fstab_file.close()
  fstab_file = open(fname_out, "w")
  fstab_file.write(new_fstab)
  fstab_file.close()


def IsAutomountedBlockDevice(fstab_cols):
  """Returns whether a fstab line specifies a block device that is automounted.

  These lines will need to be commented out, unless they are for the / or swap
  partitions, because they will prevent booting if they are missing.

  @type fstab_cols: list
  @param fstab_cols: list of the columns in this fstab line

  """
  for prefix in ["/", "UUID=", "LABEL="]:
    if fstab_cols[0].startswith(prefix):
      if "noauto" not in fstab_cols[3].split(","):
        return True
  return False


def main():
  FixFstab()


if __name__ == "__main__":
  main()
