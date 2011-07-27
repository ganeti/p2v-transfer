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
import unittest

import p2v_transfer


class _MockChannelFile:
  def __init__(self, mox_obj):
    self.mox = mox_obj
    self.channel = self.mox.CreateMock(paramiko.Channel)

  def _SetOutput(self, outlist):
    if isinstance(outlist, str):
      outlist = [outlist]
    self.outlist = outlist

  def __getitem__(self, idx):
    return self.outlist[idx]

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
    self.test_argv = [
      "p2v_transfer.py",
      self.root_dev,
      self.host,
      self.pkeyfile,
      ]

  def _MockRunCommandAndWait(self, command, exit_status=0):
    stdin = _MockChannelFile(self.mox)
    stdout = _MockChannelFile(self.mox)
    stderr = _MockChannelFile(self.mox)
    self.client.exec_command(command).AndReturn((stdin, stdout, stderr))

    stdout.channel.recv_exit_status().AndReturn(exit_status)

    # return stdout in case we want to do something else with it
    return stdout

  def _MockSubprocessCallSuccess(self, command_list):
    self.mox.StubOutWithMock(self.module.subprocess, "call")
    self.module.subprocess.call(command_list).AndReturn(0)

  def _MockSubprocessCallFailure(self, command_list):
    self.mox.StubOutWithMock(self.module.subprocess, "call")
    self.module.subprocess.call(command_list).AndReturn(1)

  def _StubOutAllModuleFunctions(self):
    self.module_functions = [
      "EstablishConnection",
      "PartitionTargetDisks",
      "MountSourceFilesystems",
      "TransferFiles",
      "UnmountSourceFilesystems",
      "RunFixScripts",
      "ShutDownTarget",
      "VerifyKernelMatches",
      "LoadSSHKey",
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

  def testPartitionTargetDisksSendsCommands(self):
    swap_cyls = 10
    tot_cyls = 600

    sfdisk_output = "Disk /dev/xvda: %d cylinders, 255 heads, etc." % tot_cyls
    stdout = _MockChannelFile(self.mox)
    stdout._SetOutput(sfdisk_output)

    self.client.exec_command("sfdisk -l /dev/xvda").AndReturn((None, stdout,
                                                               None))

    sfdisk_command = """sfdisk /dev/xvda <<EOF
0,%d,83
,,82
EOF
""" % (tot_cyls - swap_cyls)

    self._MockRunCommandAndWait(sfdisk_command)

    commands = ("mkfs.ext3 /dev/xvda1"
                " && mkswap /dev/xvda2"
                " && mkdir %s"
                " && mount /dev/xvda1 %s") % (self.module.TARGET_MOUNT,
                                              self.module.TARGET_MOUNT)
    self._MockRunCommandAndWait(commands)

    self.mox.ReplayAll()
    self.module.PartitionTargetDisks(self.client, swap_cyls)
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
    command_list = ["umount", self.module.SOURCE_MOUNT]
    self._MockSubprocessCallFailure(command_list)
    self.mox.ReplayAll()
    self.assertRaises(SystemExit, self.module.UnmountSourceFilesystems)
    self.mox.VerifyAll()

  def testUnmountSourceFilesystemsCallsUmount(self):
    command_list = ["umount", self.module.SOURCE_MOUNT]
    self._MockSubprocessCallSuccess(command_list)
    self.mox.ReplayAll()
    self.module.UnmountSourceFilesystems()
    self.mox.VerifyAll()

  def testMainRunsAllFunctions(self):
    self.mox.StubOutWithMock(self.module.os, "getuid")
    self._StubOutAllModuleFunctions()

    self.module.os.getuid().AndReturn(0)  # Wants to run as root
    self.module.LoadSSHKey(self.pkeyfile).AndReturn(self.pkey)
    self.module.EstablishConnection("root",
                                    self.host,
                                    self.pkey).AndReturn(self.client)
    self.module.MountSourceFilesystems(self.root_dev)
    self.module.VerifyKernelMatches(self.client).AndReturn(True)
    self.module.PartitionTargetDisks(self.client, 10)
    self.module.TransferFiles("root", self.host, self.pkeyfile)
    self.module.RunFixScripts(self.client)
    self.module.ShutDownTarget(self.client)
    self.module.UnmountSourceFilesystems()

    self.mox.ReplayAll()
    self.module.main(self.test_argv)
    self.mox.VerifyAll()

  def testMainQuitsIfNotRunAsRoot(self):
    self.mox.StubOutWithMock(self.module.os, "getuid")
    self._StubOutAllModuleFunctions()

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

    self.module.os.getuid().AndReturn(0)  # Wants to run as root
    self.module.LoadSSHKey(self.pkeyfile).AndReturn(self.pkey)
    self.module.EstablishConnection("root",
                                    self.host,
                                    self.pkey).AndReturn(self.client)
    self.module.MountSourceFilesystems(self.root_dev)
    self.module.VerifyKernelMatches(self.client).AndReturn(True)
    call = self.module.PartitionTargetDisks(self.client, 10)
    call.AndRaise(self.module.P2VError("meep"))
    # Transfer is cancelled because of the error, but still we have:
    self.module.UnmountSourceFilesystems()

    self.mox.ReplayAll()
    self.assertRaises(SystemExit, self.module.main, self.test_argv)
    self.mox.VerifyAll()


if __name__ == "__main__":
  unittest.main()
