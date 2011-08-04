===================
instance-p2v-target
===================

This document contains technical details for instance-p2v-target, the
OS definition for the boostrap operating system. The purpose of this
operating system is to allow the instance to be booted without having
the hard disk mounted, so that SSH commands from the source machine can
repartition, format, and image the disk as necessary.

Background
==========

The parts of the Linux boot process that I understand work as follows:

1. The bootloader copies the kernel, which is an executable file, into
   memory, and optionally passes it an initrd (initial ramdisk) file.
2. If passed an initrd, the kernel extracts it, dumping its contents
   into a filesystem in memory called the rootfs.
3. The rootfs contains a program ``/init``, which seems usually to be
   a shell script. The kernel runs this program. The arguments given on
   the kernel command line are passed to this program.
4. ``/init`` sets up various things, including loading kernel modules,
   setting up devices, and mounting the real root filesystem. It does
   some of this work itself, but also calls all of the scripts in the
   ``/scripts`` directory at various points in the process.
5. At the end of this, ``/init`` calls a program called ``run-init``
   from the klibc package, which does three things. It clears all of the
   files out of the rootfs, remounts the real root device on ``/``, and
   calls ``/sbin/init``.
6. ``/sbin/init`` is the program described in ``man init``. It brings
   the system up, starting all necessary services.

The document `ramfs, rootfs and initramfs
<http://www.kernel.org/doc/Documentation/filesystems/
ramfs-rootfs-initramfs.txt>`_ was very helpful in figuring this out.

The instance-p2v-target OS modifies step 4 of this process, after the
physical hard drive has been mounted, but before it is moved to ``/``.
This script creates a tmpfs filesystem and copies everything from the
physical hard drive to this filesystem. Then it unmounts the physical
hard drive and moves the tmpfs to where ``/init`` expects the hard drive
to be. So, at the end of the boot process the tmpfs is mounted on ``/``,
and the physical hard drive is not mounted at all. It is much easier to
do this while inside the initrd, because it's really hard to unmount the
disk when it's already mounted on ``/`` and all the tools you want to
use to unmount it are stored inside it.

Package Contents
================

The instance-p2v-target package contains a few things in addition to
those found in the instance-debootstrap package from which it derives.
The general categories of the additions are:

* Hook scripts, which are run on instance creation and aim to make the
  bootstrap OS bootable and usable as the target of a transfer.
* Fix scripts, which are copied to the instance on creation, and run
  after the transfer to fix hardware-specific configuration.
* Prep scripts, of which there is currently only one:
  ``make_ramboot_initrd.py``, the script that generates the initrd used
  to boot the bootstrap OS.
