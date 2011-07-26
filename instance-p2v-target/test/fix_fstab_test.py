#!/usr/bin/python
#
# Copyright (C) 2011 Google Inc.

"""Tests for fix_fstab."""


import mox
import os
import tempfile
import unittest

from fixlib import fix_fstab


class FixFstabTest(unittest.TestCase):
  SRCDIR = os.environ.get("SRCDIR", ".")
  TESTDATA = os.path.join(SRCDIR, "test", "testdata")

  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.ResetAll()

  def testFixFstabReplacesRootLine(self):
    # stub out blkid call
    mock_popen = self.mox.CreateMock(fix_fstab.subprocess.Popen)

    self.mox.StubOutWithMock(fix_fstab.subprocess, "Popen",
                             use_mock_anything=True)
    call = fix_fstab.subprocess.Popen(["blkid"],
                                       stdout=fix_fstab.subprocess.PIPE)
    call.AndReturn(mock_popen)
    blkid_str = ("/dev/xvda1: UUID=\"11111111-1111-1111-1111-111111111111\""
                 " TYPE=\"ext3\"\n/dev/xvda2: UUID=\"22222222-2222-2222-2222"
                 "-222222222222\" TYPE=\"swap\"\n")
    mock_popen.communicate().AndReturn((blkid_str, ""))

    self.mox.ReplayAll()

    fname_in = os.path.join(self.TESTDATA, "fstab_uuid_in")
    handle_out, fname_out = tempfile.mkstemp()
    os.close(handle_out)
    fix_fstab.FixFstab(fname_in, fname_out)

    out = open(fname_out, "r")
    desired = open(os.path.join(self.TESTDATA, "fstab_uuid_out"), "r")
    out_data = out.read()
    desired_data = desired.read()
    out.close()
    desired.close()

    self.assertEqual(desired_data, out_data)

    self.mox.VerifyAll()


  def testFixFstabHandlesDeviceMissing(self):
    # stub out blkid call
    mock_popen = self.mox.CreateMock(fix_fstab.subprocess.Popen)

    self.mox.StubOutWithMock(fix_fstab.subprocess, "Popen",
                             use_mock_anything=True)
    call = fix_fstab.subprocess.Popen(["blkid"],
                                       stdout=fix_fstab.subprocess.PIPE)
    call.AndReturn(mock_popen)
    mock_popen.communicate().AndReturn(("", ""))

    self.mox.ReplayAll()

    fname_in = os.path.join(self.TESTDATA, "fstab_uuid_in")
    handle_out, fname_out = tempfile.mkstemp()
    os.close(handle_out)

    self.assertRaises(fix_fstab.fixlib.FixError, fix_fstab.FixFstab,
                      fname_in, fname_out)

    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
