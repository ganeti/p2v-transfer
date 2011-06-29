Ganeti p2v-transfer design
==========================

This document describes the design of p2v-transfer, a tool for
converting a physical computer into a ganeti instance.

Objective
---------

p2v-transfer should be a simple tool to move a physical Linux machine
into a ganeti instance. This tool would in its simplest usage be able
to copy all the data from a physical machine and produce an
identically configured, bootable ganeti instance all ready to go. It
should automatically make some changes, such as console and disk
names, that are needed to make the machine function properly as an
instance, and it should be configurable to make more site-specific or
os-specific changes as necessary.

Background
----------

P2V (physical to virtual) systems already exist for various operating
systems and virtualization platforms. Many of them are proprietary,
however, and none are specifically targeted toward ganeti.

* `VMware vCenter Converter
  <http://www.vmware.com/products/converter/>`_ is a free, proprietary
  P2V tool. It can create virtual machines in the Open Virtualization
  Format (OVF, an open image format for virtual machines) as well as
  machines that run on the VMware architecture.
* `Citrix XenServer <http://www.xensource.com>`_ also seems to include
  a P2V tool that creates xen virtual machines (instructions:
  `Physical to Virtual Conversion (P2V)
  <http://docs.vmd.citrix.com/XenServer/4.0.1/guest/ch02s04.html>`_)
  but they say it only works on RHEL, CentOS, and SuSe as source
  distros. I’m also not sure if the process is compatible with ganeti.
* Though not a P2V solution, `Open-OVF
  <http://gitorious.org/open-ovf>`_ is an IBM-sponsored open-source
  python library for dealing with OVF images that might be useful.
* There is an interesting (I think open-source) project called
  virt-p2v that is part of redhat’s virt-v2v package and automates the
  process of virtualizing a physical server booted from a specialized
  liveCD/PXE image (see `Converting, Inspecting, & Modifying Virtual
  Machines with Red Hat Enterprise Linux 6.1
  <http://oirase.annexia.org/booth_w_1020_guest_conversion_in_rhel.pdf>`_).
  However, it requires the data to be transferred to a virt-v2v server
  for conversion to a RHEV instance, so it doesn’t seem to be directly
  applicable.

Requirements and Scale
----------------------

The main use case for the system is transferring a single physical
machine to a single instance. It does not need to be optimized for
transferring many machines at a time, although it should be scriptable
in case the user has a lot of servers they want to move to ganeti. It
should be able to support several users transferring machines, just in
case. How many? P2V won’t be a very common operation so the number of
simultaneous connections shouldn’t be too large. The data transfer,
however, will be fairly large per user, probably on the order of
hundreds of GB. The tool will need to gracefully handle the case where
policy dictates a smaller disk than the one required to store all the
data.

This P2V migration should be possible with a minimum of privileges on
the cluster. For example, the user doing the migration must not need
root privileges on the cluster to make the transfer.

In order for the transferred machine to work as a ganeti instance,
some changes to its filesystem will be required. Some of these can be
automated because they are necessary to work on the virtual
architecture:

* Change default console to /dev/hvc0
* Change disks in /etc/fstab and other places to refer to the new
  UUIDs of the appropriate filesystems.  Actually, filesystems can be
  created to have the same UUID as on the source box, but if fstab
  refers to /dev/sda0 it still needs to change.
* Anything that refers specifically to the MAC address

Others are site-specific and should be specifiable as command-line (or
similar) options:

* Hostname changes
* IP address / networking changes

Because some of these changes must be implemented in a way that is
specific to the operating system, it may be preferable to have a
script or scripts in the OS definition that can handle making these
changes. However, the P2V tool must still be able to request that
these changes be made so that the new instance doesn’t come online
with an invalid hostname, for example.

There is also the possibility of making additional changes to the
machine in addition to simply moving it to the cluster. These should
be considered optional features, which wouldn’t be developed unless
the core functionality was working well. Some possible examples are:

* Changing partitioning scheme of machine / switching partitioning to
  LVM
* Changing kernel (maybe keeping the original kernel is the hard
  problem here, as the kernels have to live on the node...)

Transfer Process
----------------

To maintain the integrity of the copy, the source machine must not be
running when the transfer is taking place. So, the source machine will
be booted from a liveCD/PXE image, and the transfer script run from
that operating system.

Target instances will be created by the administrator with a bootstrap
OS, which unmounts the disk after booting and awaits a connection by
the script running on the source machine. Then the disk can be
partitioned, data copied over rsync, necessary changes made to the
filesystem. Then the instance is rebooted into the new operating
system.

The migration has the following steps:

1. The target instance is created with a modified OS template
   (containing tools required for imaging)
2. The instance is booted with a modified initrd, which copies the
   root filesystem into RAM before running init. This allows the OS to
   run without the disk being mounted. The command looks something
   like::

     gnt-instance start -H initrd_path=/boot/initrd.img-p2v instance17

3. The instance tries to fetch an SSH public key from a predetermined
   location.  When it finds one, it downloads it to its
   /root/.ssh/authorized_keys file, giving the source machine shell
   access to the target.
4. The instance disks are partitioned and formatted as required to
   duplicate the source machine. In the case where the target disks
   are not the same size as the source ones this requires some
   cleverness (or user input, more likely) to ensure that the
   important filesystems (e.g. /usr) have some wiggle room.
5. The newly created filesystems are mounted on the target. Data is
   copied from the source to the target.
6. Modifications are made to the target so that it works in
   ganeti. Some of these modifications may be extremely os-specific,
   so they probably shouldn’t be hard-coded into the p2v script, but
   there isn’t currently a hook in the OS API for this
   operation. However, the instance is still running (from RAM) at
   this point, so there may be other options. See “Unresolved
   Questions,” below.
7. Power the instance off, so ganeti-watcher will restart it using the
   default kernel and initrd. Or, potentially, using pvgrub to use the
   kernel that’s on the transferred image, depending on the setup of
   your cluster.
8. Log in. Hopefully everything is where you left it!

Alternatives Considered
-----------------------

1. The script running on the source machine creates a dump of the
   filesystem that can be imported into the ganeti cluster using
   ``gnt-backup import``.  The disadvantage of this approach is that
   the source system probably does not have enough RAM to store the
   image that is being built, and the image can't be put on the disk
   that is being imaged. So, the image would need to be built off of
   the source box, which forces the administrator to make available a
   staging area where a several-hundered-gigabyte image can be placed.
2. If creating a system image is acceptable, another option is to
   create the image in the OVF format, which is a standard VM export
   format that is understood by VMWare and VirtualBox, among
   others. To make this work with ganeti would mean implementing at
   least sufficient OVF support in ganeti to import the images created
   by the script.  Enabling ganeti to import OVF images would increase
   interoperability with other virtual environments and allow the
   images created by the P2V tool to be used on systems other than
   ganeti, and is in fact a planned feature, but for the reasons
   discussed in option 1 this is a problematic approach to pursue for
   P2V.
3. Boot the source machine (Physical) into a tool that speaks the
   remote import-export API of Ganeti, and coordinate (with a central
   system) the import of the source filesystem into the target ganeti
   cluster. This doesn’t need any OS API changes, and it still keeps
   the streaming/no-copy-needed method.  This requires some work to
   deal with the shared domain secrets that are required by the remote
   import/export, but the real problem is that the remote API only
   supports a 1:1 dump of a filesystem, and changes must be made to
   the filesystem in order for it to boot on ganeti. Either we need a
   staging area like in options 1 and 2, or the migration can be
   destructive and modify the source filesystem, or the remote API
   needs to allow triggering of these filesystem changes (similar to
   how it is possible to trigger a rename).
4. Create the target instance on the cluster, and then connect to the
   node that stores the instance, and partition, mount, copy data to,
   and tweak the instance disks directly by writing to the DRBD
   volumes. This requires the user to be able to ssh to a particular
   node, mount disks on the node and change arbitrary files on those
   disks. These permissions should not be necessary to do this kind of
   transfer; it should be possible even if only the administrator can
   run commands on the node.
