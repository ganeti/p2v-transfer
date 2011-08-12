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


import binascii
import errno
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


class AskAddPolicy(paramiko.AutoAddPolicy):
  """Policy that asks the user to confirm a key before adding it."""
  def missing_host_key(self, client, hostname, key):
    print "Target has ssh host key fingerprint ",
    print binascii.hexlify(key.get_fingerprint())
    response = raw_input("Is this correct? y/N: ")
    if response.lower() == "y":
      super(AskAddPolicy, self).missing_host_key(client, hostname, key)
    else:
      raise paramiko.SSHException("Incorrect host key for %s" % hostname)


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
  client.set_missing_host_key_policy(AskAddPolicy())
  known_hosts_filename = os.path.expanduser("~/.ssh/known_hosts")
  try:
    # Load from the known_hosts file. Additional keys will be saved back there.
    client.load_host_keys(known_hosts_filename)
  except IOError:
    # Error is ok, file will be created as long as parent directory exists.
    # So, make sure it exists:
    try:
      os.mkdir(os.path.dirname(known_hosts_filename))
    except OSError, e:
      if e.errno != errno.EEXIST:  # already exists
        raise P2VError("Unexpected error editing known_hosts file: %s. Please"
                       " make sure that %s exists and is"
                       " writable" % (e, known_hosts_filename))

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


def MountSourceFilesystems(root_dev, fstab_data=None):
  """Mounts the filesystems of the source (physical) machine on /source.

  Reads /etc/fstab and mounts all of the real filesystems it can, so
  that the contents can be transferred to the target machine with one
  rsync command.  Creates the /source dir if necessary, and checks to
  make sure it's empty (though it really should be, since we're probably
  running off LiveCD/PXE)

  @type root_dev: str
  @param root_dev: Name of the device holding the root filesystem of the
    source OS
  @type fstab_data: str
  @param fstab_data: Contents of an fstab file. If specified, will not try to
    read /etc/fstab off of root FS.
  @rtype: (list, list)
  @return: List of (device, mount point) tuples, list of swap partitions

  """

  DisplayCommandStart("Mounting root filesystem...")
  if not os.path.isdir(SOURCE_MOUNT):
    os.mkdir(SOURCE_MOUNT)
  errcode = subprocess.call(["mount", root_dev, SOURCE_MOUNT])
  if errcode:
    print "Error mounting %s" % root_dev
    sys.exit(1)
  DisplayCommandEnd("done")

  # Now that the root device is mounted, we can read the fstab
  try:
    if not fstab_data:
      fstab = open(os.path.join(SOURCE_MOUNT, "etc", "fstab"), "r")
      fstab_data = fstab.read()
      fstab.close()
  except IOError, e:
    raise P2VError("Error reading /etc/fstab to find filesystems: %s" % str(e))

  fs_devs, swap_devs = ParseFstab(fstab_data)

  DisplayCommandStart("Mounting filesystems to copy...")

  for dev, mount_point in fs_devs:
    if mount_point == "/":
      continue

    # Ok, we've decided to actually try mounting this filesystem
    if mount_point[0] == os.sep:
      mount_point = SOURCE_MOUNT + mount_point
    else:
      mount_point = SOURCE_MOUNT + os.sep + mount_point
    errcode = subprocess.call(["mount", dev, mount_point])
    if errcode:
      print "Could not mount %s on %s, continuing..." % (dev, mount_point)

  DisplayCommandEnd("done")
  return fs_devs, swap_devs


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
    raise P2VError("Remote command returned nonzero exit status: %s\n"
                   "stdout:\n%s\nstderr:\n%s\n" % (command, stdout.read(),
                                                   stderr.read()))


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


def _GetDeviceFile(dev):
  """Get the device file associated with a block device.

  Accepts input of the form /dev/<device>, UUID=<uuid>, and LABEL=<label>, and
  returns the /dev/<device> file for the disk.

  @type dev: str
  @param dev: specification of the block device

  """
  if dev.startswith("UUID=") or dev.startswith("LABEL="):
    popen = subprocess.Popen(["findfs", dev], stdout=subprocess.PIPE)
    devname = popen.communicate()[0].strip()
    if popen.returncode == 0:
      return devname
    else:
      raise P2VError("Swap device %s not found" % dev)
  else:
    return dev


def GetDiskSize(client, swap_devs, target_hd):
  """Determine how much disk is available, how much swap space to include.

  For swap size, returns the minimum of:
  - amount of swap space on the source machine
  - 10% of the target drive

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.
  @type swap_devs: list
  @param swap_devs: List of swap partitions on the source machine.
  @type target_hd: str
  @param target_hd: Device file for the instance hard drive.
  @rtype: (int, int)
  @return: Total size in megabytes, swap size in megabytes

  """
  DisplayCommandStart("Determining partition sizes...")

   # Find out how many MB are available on target
  stdin, stdout, stderr = client.exec_command("blockdev --getsize64 %s" %
                                              target_hd)
  for line in stdout:
    if line.strip():
      total_megs = int(line.strip()) / (1024 * 1024)
      break
  stdout.close()

  swap_megs = 0
  for dev in swap_devs:
    dev = _GetDeviceFile(dev)
    size_output = subprocess.Popen(["blockdev", "--getsize64", dev],
                                   stdout=subprocess.PIPE).communicate()[0]
    try:
      swap_megs += int(size_output.strip()) / (1024 * 1024)
    except ValueError:
      pass  # Dev has gone missing, so just ignore it.

  if swap_megs == 0:
    raise P2VError("No swap devices found, so swap size could not be"
                   " determined.")

  swap_size = min(swap_megs, int(total_megs * 0.1))

  DisplayCommandEnd("%d MB disk, %d MB reserved for swap" % (total_megs,
                                                             swap_size))
  return total_megs, swap_size


def ParseFstab(fstab_data):
  """Grab the useful information from the fstab.

  Parses the fstab, and returns the information it contains, in two objects.
  One is a dictionary of the information needed to mount the real filesystems
  on the machine, and the other is a list of the names of the swap partitions.

  @type fstab_data: str
  @param fstab_data: Contents of an fstab file
  @rtype: (list, list)
  @return: List of (device, mount point) tuples, list of swap partitions

  """
  accepted_filesystems = ["ext2", "ext3", "ext4"]
  DisplayCommandStart("Interpreting /etc/fstab...")

  fs_devs = []
  swap_devs = []

  for line in fstab_data.splitlines():
    if not line or line[0] == "#":
      continue
    words = line.split()
    if len(words) != 6:
      continue  # wrong format

    if words[2] in accepted_filesystems:
      fs_devs.append((words[0], words[1]))
    if words[2] == "swap":
      swap_devs.append(words[0])

  fslist = ", ".join([ item[0] for item in fs_devs ])
  swaplist = ", ".join(swap_devs)
  DisplayCommandEnd("Found filesystems on %s; swap on %s" % (fslist, swaplist))
  return fs_devs, swap_devs


def PartitionTargetDisks(client, total_megs, swap_megs, target_hd):
  """Partition and format the disks on the target machine.

  Sends commands over the SSH connection to partition and format the
  disk of the target instance.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance.
  @type total_megs: int
  @param total_megs: Total size of disk, in megabytes
  @type swap_megs: int
  @param swap_megs: Desired size of swap space, in megabytes
  @type target_hd: str
  @param target_hd: Device file for the instance hard drive.

  """
  DisplayCommandStart("Partitioning disks...")

  nonswap_megs = total_megs - swap_megs
  sfdisk_command = """sfdisk -uM %s <<EOF
0,%d,83
,,82
EOF
""" % (target_hd, nonswap_megs)

  other_commands = [
    "mkfs.ext3 %s1" % target_hd,
    "mkswap %s2" % target_hd,
    "mkdir -p %s" % TARGET_MOUNT,
    "mount %s1 %s" % (target_hd, TARGET_MOUNT),
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


def UnmountSourceFilesystems(fs_devs):
  """Undo mounts performed by MountSourceFilesystems.

  Unmounts all filesystems mounted by MountSourceFilesystems. Retries a couple
  of times in case the filesystem is busy the first time.

  @type fs_devs: list
  @param fs_devs: List of (device, mount point) tuples.

  """
  for _, mount in reversed(fs_devs):
    if mount == "/":
      mount = SOURCE_MOUNT
    elif mount[0] == os.sep:
      mount = SOURCE_MOUNT + mount
    else:
      mount = SOURCE_MOUNT + os.sep + mount

    if os.path.exists(mount) and os.path.ismount(mount):
      succeeded = False
      for trynum in range(3):
        errcode = subprocess.call(["umount", mount])
        if not errcode:
          succeeded = True
          break
        time.sleep(0.5)
      if not succeeded:
        print "Error unmounting %s" % mount
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


def FindTargetHardDrive(client):
  """Find the name of the first hard drive on the target machine.

  Tries, in order, /dev/{xvda,vda,sda} and returns the first one that exists on
  the target machine.

  @type client: paramiko.SSHClient
  @param client: SSH client object used to connect to the instance
  @rtype: str
  @return: name of the hard drive device to install onto

  """
  for hd in ["/dev/xvda", "/dev/vda", "/dev/sda"]:
    stdin, stdout, stderr = client.exec_command("test -b %s" % hd)
    _WaitForCompletion(stdout.channel)
    if stdout.channel.recv_exit_status() == 0:
      return hd
  raise P2VError("Could not locate a hard drive on the target.")


def main(argv):
  client = None
  uid = None
  fs_devs = []

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
      fs_devs, swap_devs = MountSourceFilesystems(root_dev)
      target_hd = FindTargetHardDrive(client)
      if options.skip_kernel_check or VerifyKernelMatches(client):
        total_megs, swap_megs = GetDiskSize(client, swap_devs, target_hd)
        PartitionTargetDisks(client, total_megs, swap_megs, target_hd)
        TransferFiles(user, host, keyfile)
        RunFixScripts(client)
        ShutDownTarget(client)
      else:
        raise P2VError("Modules matching instance kernel not present on source"
                       " OS. If your kernel does not use modules, you may want"
                       " the --skip-kernel-check option.")
    except P2VError, e:  # Print error message
      print e
      sys.exit(1)
  finally:
    if uid == 0:
      UnmountSourceFilesystems(fs_devs)
    if client:
      CleanUpTarget(client)


if __name__ == "__main__":
  main(sys.argv)
