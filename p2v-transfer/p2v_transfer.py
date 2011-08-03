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


"""Performs a physical to virtual transfer.

This script is run from the transfer OS to establish an SSH connection
with the bootstrap OS, mount the source filesystem(s), and copy
the data over to the target. It will prompt the user for credentials as
necessary to gain access to the bootstrap OS.

"""


import re
import stat
import sys
import optparse
import os
import paramiko
import subprocess
import time


TARGET_MOUNT = "/target"
SOURCE_MOUNT = "/source"


class P2VError(Exception):
  """Generic error class for problems with the transfer."""
  pass


def ParseOptions(argv):
  usage = "Usage: %prog [options] root_dev target_host private_key"

  parser = optparse.OptionParser(usage=usage)

  parser.add_option("--skip-kernel-check", action="store_true",
                    dest="skip_kernel_check", default=False,
                    help=("Transfer even if modules for instance kernel are"
                          " not installed on source machine. Useful if you are"
                          " feeling adventurous, or your instance kernel does"
                          " not use modules."))

  options, args = parser.parse_args(argv[1:])

  if len(args) != 3:
    parser.print_help()
    sys.exit(1)

  try:
    stats = os.stat(args[0])
    if not stat.S_ISBLK(stats.st_mode):
      raise P2VError("%s is not a device file" % args[0])
  except OSError, e:
    raise P2VError(str(e))

  if not re.match("[-a-zA-Z0-9.]+$", args[1]):
    raise P2VError("Invalid hostname %s" % args[1])
  if not os.path.isfile(args[2]):
    raise P2VError("Private key file %s not found" % args[2])

  return options, args


def LoadSSHKey(keyfile):
  """Loads private key into paramiko.

  @type keyfile: str
  @param keyfile: Filename of private key to load.
  @rtype: paramiko.PKey
  @returns: Paramiko object representing the private key.
  @raise P2VError: Keyfile is missing, invalid, or encrypted.

  """
  DisplayCommandStart("Loading SSH keys...")

  try:
    key = paramiko.DSSKey.from_private_key_file(keyfile)
  except paramiko.PasswordRequiredException:
    raise P2VError("Why is the private key file encrypted?")
  except (IOError, paramiko.SSHException):
    raise P2VError("Key file is missing or invalid")

  DisplayCommandEnd("done")
  return key


def EstablishConnection(user, host, key):
  """Creates a connection to the specified host.

  Uses a private key to establish an SSH connection to the bootstrap OS, and
  return an SSHClient instance.

  @type user: str
  @param user: Username to use for connection.
  @type host: str
  @param host: Hostname of machine to connect to.
  @type key: paramiko.PKey
  @param key: Private key to use for authentication.

  @rtype: paramiko.SSHClient
  @returns: SSHClient object connected to a root shell on the target instance.

  """
  DisplayCommandStart("Connecting to instance...")

  client = paramiko.SSHClient()
  client.set_missing_host_key_policy(paramiko.WarningPolicy())
  client.load_system_host_keys()
  try:
    client.connect(host, username=user, pkey=key,
                   allow_agent=False, look_for_keys=False)
  except IOError, e:
    raise P2VError("Problem connecting to instance: %s" % e)

  DisplayCommandEnd("done")
  return client


def VerifyKernelMatches(client):
  """Make sure the bootstrap kernel is installed on the source OS.

  In order for the source OS to boot when transferred to the instance, it must
  have kernel modules to support the kernel that ganeti will use to boot it.
  For the time being, we ensure this by enforcing that the kernel running on
  the bootstrap OS is also installed on the source OS before the transfer. We
  check that the bootstrap OS's 'uname -r' is the name of a directory in
  /source/lib/modules.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.
  @rtype: bool
  @returns: True if the proper kernel is installed, else False.

  """
  DisplayCommandStart("Checking kernel compatibility...")

  stdin, stdout, stderr = client.exec_command("uname -r")
  kernel = stdout.read().strip()

  if os.path.exists(os.path.join(SOURCE_MOUNT, "lib", "modules", kernel)):
    DisplayCommandEnd("Kernel matches")
    return True
  else:
    DisplayCommandEnd("Kernel does not match")
    return False


def MountSourceFilesystems(root_dev):
  """Mounts the filesystems of the source (physical) machine in /source.

  Reads /etc/fstab and mounts all of the real filesystems it can, so
  that the contents can be transferred to the target machine with one
  rsync command.  Creates the /source dir if necessary, and checks to
  make sure it"s empty (though it really should be, since we"re probably
  running off LiveCD/PXE)

  @type root_dev: str
  @param root_dev: Name of the device holding the root filesystem of the
    source OS

  """
  DisplayCommandStart("Mounting filesystems to copy...")

  if not os.path.isdir(SOURCE_MOUNT):
    os.mkdir(SOURCE_MOUNT)
  errcode = subprocess.call(["mount", root_dev, SOURCE_MOUNT])
    # TODO(benlipton): mount other filesystems, if any
  if errcode:
    print "Error mounting %s" % root_dev
    sys.exit(1)

  DisplayCommandEnd("done")


def ShutDownTarget(client):
  """Shut down the target instance.

  Sends an ssh command to shut down the instance.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.

  """
  DisplayCommandStart("Transfer complete! Shutting down the instance...")
  _RunCommandAndWait(client, "poweroff")
  DisplayCommandEnd("done")


def _RunCommandAndWait(client, command):
  """Send an SSH command and wait until it completes.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.
  @type command: str
  @param command: Command to send to the instance.
  @raises P2VError: remote command returned nonzero exit status

  """
  stdin, stdout, stderr = client.exec_command(command)

  _WaitForCompletion(stdout.channel)

  if stdout.channel.recv_exit_status() != 0:
    raise P2VError("Remote command returned nonzero exit status: %s" % command)


def _WaitForCompletion(channel):
  """Wait for a remote command to complete.

  Helper function that sleeps until the last command run by the channel has
  completed.

  @type channel: paramiko.Channel
  @param channel: The channel to wait for. If the command was run with
    stdin, stdout, stderr = exec_command(), use stdout.channel.

  """
  start = time.time()
  gave_warning = False

  while not channel.exit_status_ready():
    time.sleep(.01)
    if time.time() - start > 60 and not gave_warning:
      gave_warning = True
      print ("\nThe current command is taking a while to complete. Please make"
             " sure the instance is still pingable. If so, try waiting another"
             " few minutes.")

  if gave_warning:
    print "The command has completed."


def GetDiskSize(client):
  """Determine how much disk is available, how much swap space to include.

  For swap size, returns the minimum of:
  - amount of swap space on the source machine
  - 10% of the target drive

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.
  @rtype: (int, int)
  @return: Total size in megabytes, swap size in megabytes

  """
  DisplayCommandStart("Determining partition sizes...")

   # Find out how many MB are available on target
  stdin, stdout, stderr = client.exec_command("blockdev --getsize64 /dev/xvda")
  for line in stdout:
    if line.strip():
      total_megs = int(line.strip()) / (1024 * 1024)
      break
  stdout.close()

  swap_output = subprocess.Popen(["swapon", "-s"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE).communicate()[0]
  swap_megs = 0
  for line in swap_output.splitlines()[1:]:
    words = line.split()
    try:
      size_kb = int(words[2])
      swap_megs += size_kb / 1024
    except ValueError:
      pass  # This line doesn't have data on it

  swap_size = min(swap_megs, int(total_megs * 0.1))

  DisplayCommandEnd("%d MB disk, %d MB reserved for swap" % (total_megs,
                                                             swap_size))
  return total_megs, swap_size


def PartitionTargetDisks(client, total_megs, swap_megs):
  """Partition and format the disks on the target machine.

  Sends commands over the SSH connection to partition and format the
  disk of the target instance.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.
  @type total_megs: int
  @param total_megs: Total size of disk, in megabytes
  @type swap_megs: int
  @param swap_megs: Desired size of swap space, in megabytes

  """
  DisplayCommandStart("Partitioning disks...")

  nonswap_megs = total_megs - swap_megs
  sfdisk_command = """sfdisk -uM /dev/xvda <<EOF
0,%d,83
,,82
EOF
""" % nonswap_megs

  other_commands = [
    "mkfs.ext3 /dev/xvda1",
    "mkswap /dev/xvda2",
    "mkdir -p %s" % TARGET_MOUNT,
    "mount /dev/xvda1 %s" % TARGET_MOUNT,
    ]

  try:
    _RunCommandAndWait(client, sfdisk_command)
    _RunCommandAndWait(client, " && ".join(other_commands))
  except P2VError, e:
    print e
    print "Retrying..."
    # Make sure target is unmounted, then try again
    CleanUpTarget(client)
    _RunCommandAndWait(client, sfdisk_command)
    _RunCommandAndWait(client, " && ".join(other_commands))

  DisplayCommandEnd("done")


def TransferFiles(user, host, keyfile):
  """Transfer files to the bootstrap OS.

  Runs rsync to copy all files from the source filesystem to the target
  filesystem.

  @type user: str
  @param user: Username to use for connection.
  @type host: str
  @param host: Hostname of instance to connect to.

  """
  DisplayCommandStart("Transferring files. This will take a while...")

  errcode = subprocess.call(["rsync", "-aHAXz", "-e", "ssh -i %s" % keyfile,
                             "%s/" % SOURCE_MOUNT,
                             "%s@%s:%s" % (user, host, TARGET_MOUNT)])
  if errcode:
    print "Error using rsync to transfer files"
    sys.exit(1)

  DisplayCommandEnd("done")


def RunFixScripts(client):
  """Runs the post-transfer scripts on the bootstrap OS.

  Sends a command to the instance to run the post-transfer scripts appropriate
  to the target OS.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.

  """
  DisplayCommandStart("Running fix scripts...")
  _RunCommandAndWait(client, "run-parts /usr/lib/ganeti/fixes")
  DisplayCommandEnd("done")


def UnmountSourceFilesystems():
  """Undo mounts performed by MountSourceFilesystems.

  Unmounts all filesystems mounted by MountSourceFilesystems. Currently, since
  only the root filesystem ever gets mounted, this only unmounts the root
  filesystem. Retries a couple of times in case the filesystem is busy the
  first time.

  """
  for trynum in range(3):
    if not os.path.exists(SOURCE_MOUNT) or not os.path.ismount(SOURCE_MOUNT):
      return
    errcode = subprocess.call(["umount", SOURCE_MOUNT])
    if not errcode:
      return
    time.sleep(0.5)
  print "Error unmounting %s" % SOURCE_MOUNT
  sys.exit(1)


def CleanUpTarget(client):
  """Unmount target filesystem, remove /target directory.

  Cleans up the target to make it look like the p2v_transfer was never run.
  This means that if it doesn't complete successfully, we should be able to do
  it again.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.

  """
  try:
    _RunCommandAndWait(client, "umount %s ; rmdir %s" % (TARGET_MOUNT,
                                                         TARGET_MOUNT))
  except P2VError, e:
    # many things can make this complain, so don't crash because everything
    # might actually be ok
    print e


def DisplayCommandStart(message):
  """Display a message that an action is beginning."""
  print message,
  sys.stdout.flush()


def DisplayCommandEnd(message):
  """Display a message that an action has completed."""
  print message


def main(argv):
  client = None
  uid = None

  try:
    try:
      options, args = ParseOptions(argv)
      user = "root"
      root_dev, host, keyfile = args

      uid = os.getuid()
      if uid != 0:
        raise P2VError("Must be run as root")

      key = LoadSSHKey(keyfile)
      client = EstablishConnection(user, host, key)
      MountSourceFilesystems(root_dev)
      if options.skip_kernel_check or VerifyKernelMatches(client):
        total_megs, swap_megs = GetDiskSize(client)
        PartitionTargetDisks(client, total_megs, swap_megs)
        TransferFiles(user, host, keyfile)
        RunFixScripts(client)
        ShutDownTarget(client)
      else:
        raise P2VError("Modules matching instance kernel not present on source"
                       " OS. If your kernel does not use modules, you may want"
                       " the --skip-kernel-check option.")
    except Exception, e:  # Make sure any error gets printed out
      print e
      sys.exit(1)
  finally:
    if uid == 0:
      UnmountSourceFilesystems()
    if client:
      CleanUpTarget(client)


if __name__ == "__main__":
  main(sys.argv)
