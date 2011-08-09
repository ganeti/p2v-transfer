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

"""Tests for p2v_transfer."""


import mox
import paramiko
import types
import unittest

import p2v_transfer


class _MockChannelFile:
  def __init__(self, mox_obj):
    self.mox = mox_obj
    self.channel = self.mox.CreateMock(paramiko.Channel)
    self.outlist = []

  def _SetOutput(self, outlist):
    if isinstance(outlist, str):
      outlist = [outlist]
    self.outlist = outlist

  def __getitem__(self, idx):
    return self.outlist[idx]

  def read(self):
    return "\n".join(self.outlist)

  def close(self):
    pass


class P2vtransferTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

    self.client = self.mox.CreateMock(paramiko.SSHClient)
    self.module = p2v_transfer

    self.root_dev = "/dev/sda1"
    self.host = "testmachine"
    self.pkeyfile = "/home/testuser/.ssh/id_dsa"
    self.pkey = "thepkey"
    self.user = "testuser"
    self.test_argv = [
      "p2v_transfer.py",
      self.root_dev,
      self.host,
      self.pkeyfile,
      ]
    self.swapsize = 1024
    self.totsize = 102400

    self.fs_devs = [(self.root_dev, "/")]
    self.swap_devs = ["/dev/sda5"]

    self.fstab_data = """
UUID=00000000-0000-0000-0000-000000000000 / ext3 errors=remount-ro 0 1
/dev/sda5 none swap sw 0 0
UUID=55555555-5555-5555-5555-555555555555 /usr ext3 defaults 0 2
"""

    self.opts = self.module.optparse.Values()
    self.opts.skip_kernel_check = False

  def _MockRunCommandAndWait(self, command, exit_status=0):
    stdin = _MockChannelFile(self.mox)
    stdout = _MockChannelFile(self.mox)
    stderr = _MockChannelFile(self.mox)
    self.client.exec_command(command).AndReturn((stdin, stdout, stderr))

    # pretend the command is taking a few cycles
    stdout.channel.exit_status_ready().AndReturn(False)
    stdout.channel.exit_status_ready().AndReturn(False)
    stdout.channel.exit_status_ready().AndReturn(True)
    stdout.channel.recv_exit_status().AndReturn(exit_status)

    # return stdout in case we want to do something else with it
    return stdout

  def _MockSubprocessCallSuccess(self, command_list):
    if type(self.module.subprocess.call) == types.FunctionType:
      self.mox.StubOutWithMock(self.module.subprocess, "call")
    self.module.subprocess.call(command_list).AndReturn(0)

  def _MockSubprocessCallFailure(self, command_list):
    if type(self.module.subprocess.call) == types.FunctionType:
      self.mox.StubOutWithMock(self.module.subprocess, "call")
    self.module.subprocess.call(command_list).AndReturn(1)

  def _StubOutAllModuleFunctions(self):
    self.module_functions = [
      "ParseOptions",
      "EstablishConnection",
      "GetDiskSize",
      "PartitionTargetDisks",
      "MountSourceFilesystems",
      "TransferFiles",
      "UnmountSourceFilesystems",
      "RunFixScripts",
      "ShutDownTarget",
      "VerifyKernelMatches",
      "LoadSSHKey",
      "CleanUpTarget",
      "ParseFstab",
      ]
    for func in self.module_functions:
      self.mox.StubOutWithMock(self.module, func)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.ResetAll()

  def testShutDownTargetSendsPoweroff(self):
    self._MockRunCommandAndWait("poweroff")
    self.mox.ReplayAll()
    self.module.ShutDownTarget(self.client)
    self.mox.VerifyAll()

  def testGetDiskSizeHandlesLargeDisk(self):
    """On large disks, swap size should be the same as the source.

    uses self.totsize and self.swapsize to generate command outputs such that
    the returned values will be approximately self.totsize and self.swapsize.
    """
    popen = self.mox.CreateMock(self.module.subprocess.Popen)
    self.mox.StubOutWithMock(self.module.subprocess, "Popen",
                             use_mock_anything=True)

    tot_bytes = self.totsize * 1024 * 1024
    swap_bytes = self.swapsize * 1024 * 1024

    stdout = _MockChannelFile(self.mox)
    stdout._SetOutput(str(tot_bytes))

    call = self.client.exec_command("blockdev --getsize64 /dev/xvda")
    call.AndReturn((None, stdout, None))

    call = self.module.subprocess.Popen(["blockdev", "--getsize64",
                                         self.swap_devs[0]],
                                        stdout=self.module.subprocess.PIPE)
    call.AndReturn(popen)
    popen.communicate().AndReturn((str(swap_bytes), None))

    self.mox.ReplayAll()
    total, swap = self.module.GetDiskSize(self.client, self.swap_devs)
    self.assertEqual(total, self.totsize)
    # Should return same swap size as source machine
    self.assertEqual(swap, self.swapsize)
    self.mox.VerifyAll()

  def testGetDiskSizeHandlesSmallDisk(self):
    """On small disks, swap size should be 10% of the disk.

    Makes self.totsize small, so that the returned swap size will be smaller
    than self.swapsize.
    """
    self.totsize = self.swapsize * 5

    popen = self.mox.CreateMock(self.module.subprocess.Popen)
    self.mox.StubOutWithMock(self.module.subprocess, "Popen",
                             use_mock_anything=True)

    tot_bytes = self.totsize * 1024 * 1024
    swap_bytes = self.swapsize * 1024 * 1024

    stdout = _MockChannelFile(self.mox)
    stdout._SetOutput(str(tot_bytes))

    call = self.client.exec_command("blockdev --getsize64 /dev/xvda")
    call.AndReturn((None, stdout, None))

    call = self.module.subprocess.Popen(["blockdev", "--getsize64",
                                         self.swap_devs[0]],
                                        stdout=self.module.subprocess.PIPE)
    call.AndReturn(popen)
    popen.communicate().AndReturn((str(swap_bytes), None))

    self.mox.ReplayAll()
    total, swap = self.module.GetDiskSize(self.client, self.swap_devs)
    self.assertEqual(total, self.totsize)
    # swap size should be about 10% of the total
    self.assertEqual(swap, self.totsize/10)
    self.assertNotEqual(swap, self.swapsize)
    self.mox.VerifyAll()

  def testPartitionTargetDisksSendsCommands(self):
    sfdisk_command = """sfdisk -uM /dev/xvda <<EOF
0,%d,83
,,82
EOF
""" % (self.totsize - self.swapsize)

    self._MockRunCommandAndWait(sfdisk_command)

    commands = ("mkfs.ext3 /dev/xvda1"
                " && mkswap /dev/xvda2"
                " && mkdir -p %s"
                " && mount /dev/xvda1 %s") % (self.module.TARGET_MOUNT,
                                              self.module.TARGET_MOUNT)
    self._MockRunCommandAndWait(commands)

    self.mox.ReplayAll()
    self.module.PartitionTargetDisks(self.client, self.totsize, self.swapsize)
    self.mox.VerifyAll()

  def testPartitionTargetDisksRetriesFormatOnError(self):
    self.mox.StubOutWithMock(self.module, "CleanUpTarget")

    sfdisk_command = """sfdisk -uM /dev/xvda <<EOF
0,%d,83
,,82
EOF
""" % (self.totsize - self.swapsize)


    commands = ("mkfs.ext3 /dev/xvda1"
                " && mkswap /dev/xvda2"
                " && mkdir -p %s"
                " && mount /dev/xvda1 %s") % (self.module.TARGET_MOUNT,
                                              self.module.TARGET_MOUNT)

    self._MockRunCommandAndWait(sfdisk_command, 1)  # maybe /target is mounted
    self.module.CleanUpTarget(self.client)  # so, make sure it's unmounted
    self._MockRunCommandAndWait(sfdisk_command)
    self._MockRunCommandAndWait(commands)  # and try both commands again

    self.mox.ReplayAll()
    self.module.PartitionTargetDisks(self.client, self.totsize, self.swapsize)
    self.mox.VerifyAll()

  def testTransferFilesExitsOnError(self):
    user = "root"
    host = "instance"
    pkey = "keyfile"
    command_list = ["rsync", "-aHAXz", "-e", "ssh -i %s" % pkey,
                    "%s/" % self.module.SOURCE_MOUNT,
                    "%s@%s:%s" % (user, host, self.module.TARGET_MOUNT)]
    self._MockSubprocessCallFailure(command_list)
    self.mox.ReplayAll()
    self.assertRaises(SystemExit, self.module.TransferFiles, user, host, pkey)
    self.mox.VerifyAll()

  def testTransferFilesCallsRsync(self):
    user = "root"
    host = "instance"
    pkey = "keyfile"
    command_list = ["rsync", "-aHAXz", "-e", "ssh -i %s" % pkey,
                    "%s/" % self.module.SOURCE_MOUNT,
                    "%s@%s:%s" % (user, host, self.module.TARGET_MOUNT)]
    self._MockSubprocessCallSuccess(command_list)
    self.mox.ReplayAll()
    self.module.TransferFiles(user, host, pkey)
    self.mox.VerifyAll()

  def testUnmountSourceFilesystemsExitsOnError(self):
    self.mox.StubOutWithMock(self.module.os.path, "exists")
    self.mox.StubOutWithMock(self.module.os.path, "ismount")
    self.mox.StubOutWithMock(self.module.time, "sleep")
    command_list = ["umount", self.module.SOURCE_MOUNT]

    self.module.os.path.exists(self.module.SOURCE_MOUNT).AndReturn(True)
    self.module.os.path.ismount(self.module.SOURCE_MOUNT).AndReturn(True)
    for trynum in range(3):
      # Will retry twice before quitting
      self._MockSubprocessCallFailure(command_list)
      self.module.time.sleep(0.5)

    self.mox.ReplayAll()
    self.assertRaises(SystemExit, self.module.UnmountSourceFilesystems,
                      self.fs_devs)
    self.mox.VerifyAll()

  def testUnmountSourceFilesystemsCallsUmount(self):
    self.mox.StubOutWithMock(self.module.os.path, "exists")
    self.mox.StubOutWithMock(self.module.os.path, "ismount")

    self.module.os.path.exists(self.module.SOURCE_MOUNT).AndReturn(True)
    self.module.os.path.ismount(self.module.SOURCE_MOUNT).AndReturn(True)
    command_list = ["umount", self.module.SOURCE_MOUNT]
    self._MockSubprocessCallSuccess(command_list)
    self.mox.ReplayAll()
    self.module.UnmountSourceFilesystems(self.fs_devs)
    self.mox.VerifyAll()

  def testMainRunsAllFunctions(self):
    self.mox.StubOutWithMock(self.module.os, "getuid")
    self._StubOutAllModuleFunctions()

    call = self.module.ParseOptions(self.test_argv)
    call.AndReturn((self.opts, (self.root_dev, self.host, self.pkeyfile)))
    self.module.os.getuid().AndReturn(0)  # Wants to run as root
    self.module.LoadSSHKey(self.pkeyfile).AndReturn(self.pkey)
    self.module.EstablishConnection("root",
                                    self.host,
                                    self.pkey).AndReturn(self.client)
    call = self.module.MountSourceFilesystems(self.root_dev)
    call.AndReturn((self.fs_devs, self.swap_devs))
    self.module.VerifyKernelMatches(self.client).AndReturn(True)
    self.module.GetDiskSize(self.client,
                            self.swap_devs).AndReturn((self.totsize,
                                                       self.swapsize))
    self.module.PartitionTargetDisks(self.client, self.totsize, self.swapsize)
    self.module.TransferFiles("root", self.host, self.pkeyfile)
    self.module.RunFixScripts(self.client)
    self.module.ShutDownTarget(self.client)
    self.module.UnmountSourceFilesystems(self.fs_devs)
    self.module.CleanUpTarget(self.client)

    self.mox.ReplayAll()
    self.module.main(self.test_argv)
    self.mox.VerifyAll()

  def testMainQuitsIfNotRunAsRoot(self):
    self.mox.StubOutWithMock(self.module.os, "getuid")
    self._StubOutAllModuleFunctions()

    call = self.module.ParseOptions(self.test_argv)
    call.AndReturn((self.opts, (self.root_dev, self.host, self.pkeyfile)))
    self.module.os.getuid().AndReturn(500)

    self.mox.ReplayAll()
    self.assertRaises(SystemExit, self.module.main, self.test_argv)
    self.mox.VerifyAll()

  def testRunFixScriptsReportsFailure(self):
    # Run the command, but have it exit with error
    self._MockRunCommandAndWait("run-parts /usr/lib/ganeti/fixes", 1)

    self.mox.ReplayAll()
    self.assertRaises(self.module.P2VError,
                      self.module.RunFixScripts, self.client)
    self.mox.VerifyAll()

  def testMainUnmountsSourceOnTransferFailure(self):
    """Even if some part of the transfer fails, /source should be unmounted."""
    self.mox.StubOutWithMock(self.module.os, "getuid")
    self._StubOutAllModuleFunctions()

    call = self.module.ParseOptions(self.test_argv)
    call.AndReturn((self.opts, (self.root_dev, self.host, self.pkeyfile)))
    self.module.os.getuid().AndReturn(0)  # Wants to run as root
    self.module.LoadSSHKey(self.pkeyfile).AndReturn(self.pkey)
    self.module.EstablishConnection("root",
                                    self.host,
                                    self.pkey).AndReturn(self.client)
    call = self.module.MountSourceFilesystems(self.root_dev)
    call.AndReturn((self.fs_devs, self.swap_devs))
    self.module.VerifyKernelMatches(self.client).AndReturn(True)
    self.module.GetDiskSize(self.client,
                            self.swap_devs).AndReturn((self.totsize,
                                                       self.swapsize))
    call = self.module.PartitionTargetDisks(self.client, self.totsize,
                                            self.swapsize)
    call.AndRaise(self.module.P2VError("meep"))
    # Transfer is cancelled because of the error, but still we have:
    self.module.UnmountSourceFilesystems(self.fs_devs)
    self.module.CleanUpTarget(self.client)

    self.mox.ReplayAll()
    self.assertRaises(SystemExit, self.module.main, self.test_argv)
    self.mox.VerifyAll()

  def _ExecCommandWithOutput(self, command, output):
    stdout = _MockChannelFile(self.mox)
    stdout._SetOutput(output)
    self.client.exec_command(command).AndReturn((None, stdout, None))

  def testVerifyKernelMatchesDetectsMatch(self):
    self.mox.StubOutWithMock(self.module.os.path, "exists")
    kernel = "2.6.32-5-xen-amd64"
    self._ExecCommandWithOutput("uname -r", kernel)

    moduledir = self.module.os.path.join(self.module.SOURCE_MOUNT, "lib",
                                         "modules", kernel)
    self.module.os.path.exists(moduledir).AndReturn(True)

    self.mox.ReplayAll()
    self.assertTrue(self.module.VerifyKernelMatches(self.client))
    self.mox.VerifyAll()

  def testVerifyKernelMatchesDetectsMismatch(self):
    self.mox.StubOutWithMock(self.module.os.path, "exists")
    kernel = "2.6.32-5-xen-amd64"
    self._ExecCommandWithOutput("uname -r", kernel)

    moduledir = self.module.os.path.join(self.module.SOURCE_MOUNT, "lib",
                                         "modules", kernel)
    self.module.os.path.exists(moduledir).AndReturn(False)

    self.mox.ReplayAll()
    self.assertFalse(self.module.VerifyKernelMatches(self.client))
    self.mox.VerifyAll()

  def testEstablishConnectionCreatesClient(self):
    self.mox.StubOutWithMock(self.module.paramiko, "SSHClient",
                             use_mock_anything=True)
    self.module.paramiko.SSHClient().AndReturn(self.client)
    self.client.set_missing_host_key_policy(mox.IsA(paramiko.WarningPolicy))
    self.client.load_system_host_keys()
    self.client.connect(self.host, username=self.user, pkey=self.pkey,
                        allow_agent=False, look_for_keys=False)

    self.mox.ReplayAll()
    res = self.module.EstablishConnection(self.user, self.host, self.pkey)
    self.assertTrue(res is self.client)
    self.mox.VerifyAll()

  def testMountSourceFilesystemsMountsFilesystemsInOrder(self):
    self.mox.StubOutWithMock(self.module.os.path, "isdir")
    self.mox.StubOutWithMock(self.module.os, "mkdir")
    self.mox.StubOutWithMock(self.module, "ParseFstab")

    dev1 = "/dev/sda2"
    dev2 = "/dev/sda5"
    fs_devs1 = [("/dev/sda1", "/"), (dev1, "/usr"), (dev2, "/usr/local")]
    fs_devs2 = [("/dev/sda1", "/"), (dev2, "/usr"), (dev1, "/usr/local")]

    # First call:
    # Mount root filesystem
    self.module.os.path.isdir(self.module.SOURCE_MOUNT).AndReturn(False)
    self.module.os.mkdir(self.module.SOURCE_MOUNT)
    self._MockSubprocessCallSuccess(["mount", self.root_dev,
                                     self.module.SOURCE_MOUNT])
    # Parse
    self.module.ParseFstab(self.fstab_data).AndReturn((fs_devs1,
                                                       self.swap_devs))
    # Mount
    for devpair in fs_devs1[1:]:
      self._MockSubprocessCallSuccess(["mount", devpair[0],
                                       self.module.SOURCE_MOUNT + devpair[1]])

    # Second call:
    # Mount root filesystem
    self.module.os.path.isdir(self.module.SOURCE_MOUNT).AndReturn(False)
    self.module.os.mkdir(self.module.SOURCE_MOUNT)
    self._MockSubprocessCallSuccess(["mount", self.root_dev,
                                     self.module.SOURCE_MOUNT])
    # Parse
    self.module.ParseFstab(self.fstab_data).AndReturn((fs_devs2,
                                                       self.swap_devs))
    # Mount
    for devpair in fs_devs2[1:]:
      self._MockSubprocessCallSuccess(["mount", devpair[0],
                                       self.module.SOURCE_MOUNT + devpair[1]])

    self.mox.ReplayAll()
    self.module.MountSourceFilesystems(self.root_dev,
                                       fstab_data=self.fstab_data)
    self.module.MountSourceFilesystems(self.root_dev,
                                       fstab_data=self.fstab_data)
    self.mox.VerifyAll()

  def testParseFstabReturnsFilesystemsAndSwap(self):
    fs_correct = [("UUID=00000000-0000-0000-0000-000000000000", "/"),
                  ("UUID=55555555-5555-5555-5555-555555555555", "/usr")]

    fs_devs, swap_devs = self.module.ParseFstab(self.fstab_data)

    self.assertEqual(fs_devs, fs_correct)
    self.assertEqual(swap_devs, self.swap_devs)


if __name__ == "__main__":
  unittest.main()
