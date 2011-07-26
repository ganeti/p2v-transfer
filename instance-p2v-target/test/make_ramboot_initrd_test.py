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

"""Tests for make_ramboot_initrd."""

import os
import platform
import shutil
import tempfile
import unittest
import mox

import make_ramboot_initrd as mkinitrd

class MakeRambootInitrdTest(unittest.TestCase):
  SRCDIR = os.environ.get("SRCDIR", ".")
  MOVETORAM = os.path.join(SRCDIR, "test", "testdata", "movetoram")

  def setUp(self):
    self.mox = mox.Mox()

    self.conf_dir = tempfile.mkdtemp()
    self.install_dir = tempfile.mkdtemp()
    self.test_filename = "test"
    self.test_file_contents = "test"
    self.test_filepath = os.path.join(self.conf_dir, self.test_filename)
    self.dirs_to_remove = [self.conf_dir, self.install_dir]
    os.makedirs(os.path.join(self.conf_dir, "scripts", "local-bottom"))

    test_file = open(self.test_filepath, "w")
    test_file.write(self.test_file_contents)
    test_file.close()
    os.chmod(self.conf_dir, 0755)
    os.chmod(self.test_filepath, 0644)

    self.temp_dir, self.new_conf_dir = mkinitrd.CreateTempDir(self.conf_dir)
    self.dirs_to_remove.append(self.temp_dir)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.ResetAll()
    for d in self.dirs_to_remove:
      if d and os.path.isdir(d):
        shutil.rmtree(d)

  def testCreateTempDirCopiesFiles(self):
    self.assertTrue(os.path.isdir(self.temp_dir))
    self.assertTrue(os.path.isdir(self.new_conf_dir))

    filename = os.path.join(self.new_conf_dir, self.test_filename)
    self.assertTrue(os.path.isfile(filename))

    f = open(filename, "r")
    contents = f.read(5)
    self.assertEqual(self.test_file_contents, contents)
    f.close()

  def testCreateTempDirPermissions(self):
    # Ensure that only the user running the script can see into the directory
    # from which the initrd is being built

    # No one but the user should see into the temp dir
    tdmode = os.stat(self.temp_dir).st_mode & 0777
    self.assertEqual(0700, tdmode)

    # The user must be able to access the subdirectory, but it doesn't matter
    # if others can as they can't get into the parent directory
    ncdmode = os.stat(self.new_conf_dir).st_mode & 0700
    self.assertEqual(0700, ncdmode)

    filename = os.path.join(self.new_conf_dir, self.test_filename)
    filemode = os.stat(filename).st_mode & 0777
    self.assertEqual(0644, filemode)

  def testCreateTempDirHandlesPermissionDenied(self):
    self.mox.StubOutWithMock(mkinitrd.tempfile, "mkdtemp")
    self.mox.StubOutWithMock(mkinitrd.shutil, "copytree")

    tempdirname = "/tmp/12345"
    confdirname = os.path.join(tempdirname, "initramfs-tools")
    mkinitrd.tempfile.mkdtemp().AndReturn(tempdirname)
    mkinitrd.shutil.copytree(self.conf_dir,
                             confdirname).AndRaise(OSError("Permission denied"))

    self.mox.ReplayAll()

    # Make sure we fail if user can't read conf_dir
    self.assertRaises(mkinitrd.Error, mkinitrd.CreateTempDir, self.conf_dir)

    self.mox.VerifyAll()

  def testInstallInitrdHandlesPermissionDenied(self):
    self.mox.StubOutWithMock(mkinitrd.shutil, "copy")
    mkinitrd.shutil.copy(self.test_filepath,
                         self.install_dir).AndRaise(OSError("Denied"))

    self.mox.ReplayAll()

    # Make sure we fail if user can't write boot_dir
    try:
      self.assertRaises(mkinitrd.Error, mkinitrd.InstallInitrd,
                        self.test_filepath,  # file to copy
                        self.install_dir,  # where to put it
                        self.test_filename)  # name of file
    except (OSError, IOError):
      self.fail()

    self.mox.VerifyAll()

  def testInstallInitrdHandlesExistingFile(self):
    # Make sure that we ask for confirmation if boot_dir/file_name exists
    dest_filename = os.path.join(self.install_dir, self.test_filename)
    open(dest_filename, "a").close()  # Create file
    self.assertRaises(mkinitrd.Error, mkinitrd.InstallInitrd,
                      self.test_filepath,  # file to copy (would be the initrd)
                      self.install_dir,  # where to put it
                      self.test_filename)  # name of file

  def testInstallInitrdInstallsFile(self):
    mkinitrd.InstallInitrd(self.test_filepath,  # file to copy
                           self.install_dir,  # where to put it
                           self.test_filename)  # name of file
    dest_filename = os.path.join(self.install_dir, self.test_filename)
    self.assertTrue(os.path.isfile(dest_filename))
    filemode = os.stat(dest_filename).st_mode & 0777
    self.assertEqual(0644, filemode)

  def testCleanUpRemovesFiles(self):
    mkinitrd.CleanUp(self.temp_dir)
    self.assertFalse(os.path.exists(self.temp_dir))

  def testCleanUpHandlesMissingDir(self):
    mkinitrd.CleanUp(self.temp_dir)
    try:
      mkinitrd.CleanUp(self.temp_dir)  # should be no error even doing it twice
    except (OSError, IOError):
      self.fail()

  def testCleanUpQuitsCleanlyOnError(self):
    self.mox.StubOutWithMock(mkinitrd.shutil, "rmtree")
    mkinitrd.shutil.rmtree(self.temp_dir).AndRaise(OSError("Permission denied"))

    self.mox.ReplayAll()

    self.assertRaises(SystemExit, mkinitrd.CleanUp, self.temp_dir)

    self.mox.VerifyAll()

  def testAddScriptCreatesCorrectScript(self):
    dest_filename = os.path.join(self.new_conf_dir, "scripts",
                                 "local-bottom", "movetoram")

    try:
      mkinitrd.AddScript(self.new_conf_dir)
    except mkinitrd.Error:
      self.fail()  # should not produce error on normal conf dir

    self.assertTrue(os.path.isfile(dest_filename))
    src_file = open(self.MOVETORAM, "r")
    dst_file = open(dest_filename, "r")
    src_contents = src_file.read(500)
    dst_contents = dst_file.read(500)
    self.assertEqual(src_contents, dst_contents)

  def testAddScriptDetectsImproperConfigDir(self):
    os.rmdir(os.path.join(self.new_conf_dir, "scripts", "local-bottom"))

    self.assertRaises(mkinitrd.Error, mkinitrd.AddScript, self.new_conf_dir)

  def testBuildInitrdRunsCommand(self):
    self.mox.StubOutWithMock(mkinitrd.subprocess, "call")
    test_name = "testinitrd"
    test_tmp = os.path.join("/tmp", "test_makeinitrd")
    test_out = os.path.join(test_tmp, test_name)
    test_conf = os.path.join(test_tmp, "conf")
    test_version = "2.6-test"
    mkinitrd.subprocess.call(["mkinitramfs", "-d", test_conf,
                              "-o", test_out, test_version]).AndReturn(0)
    self.mox.ReplayAll()

    try:
      try:
        mkinitrd.BuildInitrd(test_tmp, test_conf, test_name, test_version)
      except mkinitrd.Error:
        self.fail()
    finally:
      self.mox.VerifyAll()

  def testBuildInitrdRaisesErrorOnFailure(self):
    self.mox.StubOutWithMock(mkinitrd.subprocess, "call")
    test_name = "testinitrd"
    test_tmp = os.path.join("/tmp", "test_makeinitrd")
    test_out = os.path.join(test_tmp, test_name)
    test_conf = os.path.join(test_tmp, "conf")
    test_version = "2.6-test"
    mkinitrd.subprocess.call(["mkinitramfs", "-d", test_conf,
                              "-o", test_out, test_version]).AndReturn(1)
    self.mox.ReplayAll()

    self.assertRaises(mkinitrd.Error, mkinitrd.BuildInitrd, test_tmp,
                      test_conf, test_name, test_version)

    self.mox.VerifyAll()

  def testParseArgsHandlesArgsCorrectly(self):
    old_conf_dir = "/etc/new-initramfs-tools"
    boot_dir = "/boot/subdir"
    file_name = "testinitrd.img"
    version = "2.6-test"
    argv = ["make_ramboot_initrd_test.py", "-d", old_conf_dir, "-v",
            "-n", file_name, "-b", boot_dir, "-V", version]

    options = mkinitrd.ParseOptions(argv)

    self.assertEqual(file_name, options.file_name)
    self.assertEqual(boot_dir, options.boot_dir)
    self.assertTrue(options.verbose)
    self.assertEqual(old_conf_dir, options.conf_dir)
    self.assertFalse(options.keep_temp)
    self.assertFalse(options.overwrite)
    self.assertEqual(version, options.version)

  def testParseArgsHandlesNoArgsCorrectly(self):
    argv = ["make_ramboot_initrd_test.py"]

    options = mkinitrd.ParseOptions(argv)

    expected_version = platform.release()
    self.assertEqual(expected_version, options.version)
    self.assertEqual("initrd.img-%s-ramboot" % expected_version,
                     options.file_name)
    self.assertEqual("/boot", options.boot_dir)
    self.assertFalse(options.verbose)
    self.assertEqual("/etc/initramfs-tools", options.conf_dir)
    self.assertFalse(options.keep_temp)
    self.assertFalse(options.overwrite)

  def testParseArgsHandlesWeirdScriptName(self):
    # make sure it doesn't get thrown off by being called with a strange name
    argv = ["-v"]  # called with -v as script name

    options = mkinitrd.ParseOptions(argv)
    self.assertFalse(options.verbose)

  def testMainHandlesOptions(self):
    old_conf_dir = "/etc/new-initramfs-tools"
    temp_dir = "/tmp/abcde"
    new_conf_dir = os.path.join(temp_dir, "confdir")
    temp_out = os.path.join(temp_dir, "initrd")
    boot_dir = self.install_dir
    file_name = "testinitrd.img"
    version = "2.6-test"

    self.mox.StubOutWithMock(mkinitrd, "CreateTempDir")
    self.mox.StubOutWithMock(mkinitrd, "AddScript")
    self.mox.StubOutWithMock(mkinitrd, "BuildInitrd")
    self.mox.StubOutWithMock(mkinitrd, "InstallInitrd")
    self.mox.StubOutWithMock(mkinitrd, "CleanUp")

    mkinitrd.CreateTempDir(old_conf_dir).AndReturn((temp_dir, new_conf_dir))
    mkinitrd.AddScript(new_conf_dir)
    mkinitrd.BuildInitrd(temp_dir, new_conf_dir, file_name,
                         version).AndReturn(temp_out)
    mkinitrd.InstallInitrd(temp_out, boot_dir, file_name, False)
    mkinitrd.CleanUp(temp_dir)

    self.mox.ReplayAll()

    argv = ["make_ramboot_initrd_test.py", "-d", old_conf_dir, "-v",
            "-n", file_name, "-b", boot_dir, "-V", version]

    mkinitrd.main(argv)

    self.mox.VerifyAll()

  def testMainHandlesNoOptions(self):
    old_conf_dir = "/etc/initramfs-tools"
    temp_dir = "/tmp/abcde"
    new_conf_dir = os.path.join(temp_dir, "confdir")
    temp_out = os.path.join(temp_dir, "initrd")
    boot_dir = self.install_dir  # specify this because it must be writable
    version = platform.release()
    file_name = "initrd.img-%s-ramboot" % version

    self.mox.StubOutWithMock(mkinitrd, "CreateTempDir")
    self.mox.StubOutWithMock(mkinitrd, "AddScript")
    self.mox.StubOutWithMock(mkinitrd, "BuildInitrd")
    self.mox.StubOutWithMock(mkinitrd, "InstallInitrd")
    self.mox.StubOutWithMock(mkinitrd, "CleanUp")

    mkinitrd.CreateTempDir(old_conf_dir).AndReturn((temp_dir, new_conf_dir))
    mkinitrd.AddScript(new_conf_dir)
    mkinitrd.BuildInitrd(temp_dir, new_conf_dir, file_name,
                         version).AndReturn(temp_out)
    mkinitrd.InstallInitrd(temp_out, boot_dir, file_name, False)
    mkinitrd.CleanUp(temp_dir)

    self.mox.ReplayAll()

    argv = ["make_ramboot_initrd_test.py", "-b", boot_dir]

    mkinitrd.main(argv)

    self.mox.VerifyAll()

  def testMainHandlesError(self):
    old_conf_dir = "/etc/initramfs-tools"
    temp_dir = "/tmp/abcde"
    new_conf_dir = os.path.join(temp_dir, "confdir")
    boot_dir = self.install_dir
    version = platform.release()
    file_name = "initrd.img-%s-ramboot" % version

    self.mox.StubOutWithMock(mkinitrd, "CreateTempDir")
    self.mox.StubOutWithMock(mkinitrd, "AddScript")
    self.mox.StubOutWithMock(mkinitrd, "BuildInitrd")
    self.mox.StubOutWithMock(mkinitrd, "InstallInitrd")
    self.mox.StubOutWithMock(mkinitrd, "CleanUp")

    mkinitrd.CreateTempDir(old_conf_dir).AndReturn((temp_dir, new_conf_dir))
    mkinitrd.AddScript(new_conf_dir)
    mkinitrd.BuildInitrd(temp_dir, new_conf_dir, file_name,
                         version).AndRaise(mkinitrd.Error("test!"))
    mkinitrd.CleanUp(temp_dir)

    self.mox.ReplayAll()

    argv = ["make_ramboot_initrd_test.py", "-b", boot_dir]

    self.assertRaises(SystemExit, mkinitrd.main, argv)

    self.mox.VerifyAll()

  def testMainExitsEarlyIfInstallDirUnwritable(self):
    # none of these should be called, because there's no point in doing
    # the work if you're going to discard it later
    self.mox.StubOutWithMock(mkinitrd, "CreateTempDir")
    self.mox.StubOutWithMock(mkinitrd, "AddScript")
    self.mox.StubOutWithMock(mkinitrd, "BuildInitrd")
    self.mox.StubOutWithMock(mkinitrd, "InstallInitrd")
    self.mox.StubOutWithMock(mkinitrd, "CleanUp")

    self.mox.StubOutWithMock(mkinitrd.os, "access")

    mkinitrd.os.access(self.install_dir, mkinitrd.os.W_OK).AndReturn(False)
    mkinitrd.CleanUp(None)

    self.mox.ReplayAll()

    argv = ["make_ramboot_initrd_test.py", "-b", self.install_dir]

    self.assertRaises(SystemExit, mkinitrd.main, argv)

    self.mox.VerifyAll()

  def testMainExitsEarlyIfFileExists(self):
    # none of these should be called, because there's no point in doing
    # the work if you're going to discard it later
    self.mox.StubOutWithMock(mkinitrd, "CreateTempDir")
    self.mox.StubOutWithMock(mkinitrd, "AddScript")
    self.mox.StubOutWithMock(mkinitrd, "BuildInitrd")
    self.mox.StubOutWithMock(mkinitrd, "InstallInitrd")

    self.mox.StubOutWithMock(mkinitrd, "CleanUp")
    mkinitrd.CleanUp(None)

    self.mox.ReplayAll()

    dest_filename = os.path.join(self.install_dir, self.test_filename)
    open(dest_filename, "a").close()  # Create file

    argv = ["make_ramboot_initrd_test.py", "-b", self.install_dir,
            "-n", self.test_filename]

    self.assertRaises(SystemExit, mkinitrd.main, argv)

    self.mox.VerifyAll()


if __name__ == "__main__":
  unittest.main()
