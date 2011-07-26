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

"""Construct initrd capable of booting operating system entirely from RAM.

This script is meant to be run on a ganeti node to construct an initrd
that will be used to run the bootstrap operating system for a
physical-to-virtual (P2V) transfer.

This script uses the program mkinitramfs from initramfs-tools to
generate an initrd that is compatible with the currently running
kernel but copies the contents of $ROOT into a tmpfs and mounts the
tmpfs instead of the real disk.  This allows the operating system to
do whatever it likes to the disk (partition, format, copy files)
without interfering with its own operation.

Caveats:
  - The operating system booted with this initrd must not try to mount
    the disk itself in its init scripts. This usually means replacing
    the root filesystem listed in /etc/fstab with the line::
        tmpfs         /         tmpfs       defaults    0     0
  - Because the disk is not mounted, rebooting the os will erase any
    changes that have been made to the root filesystem like installing
    packages or network configuration. If possible, these should be done
    by the OS template.
  - The boot process still depends on the contents of $ROOT. Thus, if
    the P2V process repartitions the disk and then fails, the bootstrap
    OS will need to be reinstalled before it can be booted again.

"""

import optparse
import os
import os.path
import platform
import shutil
import subprocess
import sys
import tempfile

MOVETORAM_SCRIPT = """#!/bin/sh

# movetoram: copies the contents of \$rootmnt to a tmpfs volume, then
# replaces the mounted disk with the tmpfs so that the system will run
# entirely from RAM

case $1 in
  prereqs)
    exit 0 ;;
esac

mkdir /tmproot
mount -t tmpfs -o size=500M,mode=0777 tmpfs /tmproot
cp -r ${rootmnt}/* /tmproot
umount ${rootmnt}
mount -o move /tmproot ${rootmnt}

exit 0
"""


class Error(Exception):
  pass


def ParseOptions(argv):
  """Parse any options on the command line.

  @param argv: the argv the program received on the command line

  @returns: options dictionary

  """
  parser = optparse.OptionParser()
  parser.add_option("-n", "--file-name", dest="file_name",
                    help="file name for initrd [initrd.img-<VERSION>-ramboot]",
                    default=None)
  parser.add_option("-d", "--config-dir", dest="conf_dir",
                    help=("original initramfs-tools configuration directory "
                          "[%default]"),
                    default="/etc/initramfs-tools")
  parser.add_option("-b", "--boot-dir", dest="boot_dir",
                    help="install generated initrd to BOOT_DIR [%default]",
                    default="/boot")
  parser.add_option("-v", "--verbose", action="store_true", dest="verbose",
                    default=False, help="output status messages [%default]")
  parser.add_option("-k", "--keep-temp", action="store_true", dest="keep_temp",
                    default=False, help="keep temporary config dir")
  parser.add_option("-f", "--force", action="store_true", dest="overwrite",
                    default=False, help="overwrite existing file")
  parser.add_option("-V", "--version", dest="version",
                    help=("generate initrd for kernel named VERSION "
                          "[currently running kernel]"),
                    default=None)

  (options, _) = parser.parse_args(argv[1:])

  if not options.version:
    options.version = platform.release()

  if not options.file_name:
    if options.version:
      options.file_name = "initrd.img-%s-ramboot" % options.version
    else:
      options.file_name = "initrd-modified.img"

  return options


def CreateTempDir(conf_dir):
  """Creates temporary configuration dir.

  Securely creates a temporary directory and copies the files from
  conf_dir into it. This directory will be used to the configure the
  creation of the initrd.

  @param conf_dir: path to the original initramfs-tools configuration dir

  @return: path to the temporary directory

  """
  temp_dir = tempfile.mkdtemp()
  new_conf_dir = os.path.join(temp_dir, "initramfs-tools")
  try:
    shutil.copytree(conf_dir, new_conf_dir)
  except (IOError, OSError):
    CleanUp(temp_dir)
    raise Error("Error copying config files. Please ensure you have read"
                " access to the %s directory." % conf_dir)
  return temp_dir, new_conf_dir


def CleanUp(temp_dir):
  """Try to clean up the temporary files.

  Removes the temporary files, but doesn't raise an Error if it
  doesn't work, because that would cause an infinite loop. Just gives
  up and informs the user.

  @param temp_dir: directory to remove

  """
  if temp_dir and os.path.isdir(temp_dir):
    try:
      shutil.rmtree(temp_dir)
    except (OSError, IOError):
      print ("Unexpected error removing temp directory %s. "
             "Not cleaning up.") % temp_dir
      sys.exit(1)


def AddScript(conf_dir):
  """Add the script to be run at boot time.

  Adds a script that copies the root filesystem from disk to memory,
  putting it in a location where it will be picked up and run by the
  initrd

  @param conf_dir: temporary configuration directory

  @raises Error: layout of conf_dir is not as expected

  """
  script_dir = os.path.join(conf_dir, "scripts", "local-bottom")
  if not os.path.isdir(script_dir):
    raise Error("Script does not understand config directory layout. "
                "It should contain a scripts/local-bottom directory.")

  movetoram_name = os.path.join(script_dir, "movetoram")
  movetoram_file = open(movetoram_name, "w")
  movetoram_file.write(MOVETORAM_SCRIPT)
  movetoram_file.close()
  os.chmod(movetoram_name, 0755)


def BuildInitrd(temp_dir, conf_dir, file_name, version):
  """Build the initrd using mkinitramfs.

  Runs the program mkinitramfs to create an initrd for the specified
  kernel version

  @param temp_dir: temporary directory to hold initrd
  @param conf_dir: temporary configuration directory with added script
  @param file_name: what to call the initrd file
  @param version: the kernel version to use

  @return: the location of the generated initrd in the temp_dir

  @raises Error: call to mkinitramfs failed

  """
  temp_out = os.path.join(temp_dir, file_name)
  ret = subprocess.call(["mkinitramfs", "-d", conf_dir,
                         "-o", temp_out, version])
  if ret != 0:
    raise Error("Failed building initramfs")

  return temp_out


def InstallInitrd(temp_out, install_dir, file_name, overwrite=False):
  """Install the initrd to the specified location.

  Moves the initrd to the specified install_dir, and sets the
  permissions securely.


  @param temp_out: full path to the generated initrd
  @param install_dir: where to install it to
  @param file_name: filename of the initrd
  @param overwrite: whether to overwrite one that's there already

  @raises Error: Install directory not writeable or already contains initrd

  """
  dest_filename = os.path.join(install_dir, file_name)
  if os.path.exists(dest_filename) and not overwrite:
    raise Error("A file named %s already exists in the directory %s. If you "
                "wish to overwrite it, please pass the -f "
                "option" % (file_name, install_dir))
  try:
    shutil.copy(temp_out, install_dir)
    os.chmod(dest_filename, 0644)
  except (IOError, OSError):
    raise Error("Error installing the new initrd. Please make sure you can"
                " write to the selected boot directory (%s) or select a new"
                " one with the -b option." % install_dir)


def main(argv):
  options = ParseOptions(argv)
  conf_dir = options.conf_dir
  version = options.version
  file_name = options.file_name
  install_dir = options.boot_dir
  verbose = options.verbose
  temp_dir = None
  dest_filename = os.path.join(install_dir, file_name)

  try:
    # Catch some errors early
    if not os.access(install_dir, os.W_OK):
      raise Error("Can not write to boot directory. Not generating initrd.")
    if os.path.exists(dest_filename) and not options.overwrite:
      raise Error("A file named %s already exists in the directory %s."
                  " If you wish to overwrite it, please pass the -f option" %
                  (file_name, install_dir))

    if verbose:
      print "Configuring..."
    temp_dir, new_conf_dir = CreateTempDir(conf_dir)
    if verbose:
      print "Adding script..."
    AddScript(new_conf_dir)

    if verbose:
      print "Building..."
    temp_out = BuildInitrd(temp_dir, new_conf_dir, file_name, version)

    if verbose:
      print "Installing..."
    InstallInitrd(temp_out, install_dir, file_name, options.overwrite)

  except Error, e:
    print e
    sys.exit(1)
  finally:
    if verbose:
      print "Cleaning up..."

    if options.keep_temp:
      print temp_dir
    else:
      CleanUp(temp_dir)

if __name__ == "__main__":
  main(sys.argv)
