===================
ganeti-p2v-transfer
===================

This is a tool for converting a physical computer into a ganeti
instance. It consists of two parts, a ganeti instance OS template that
allows the instance to be booted to receive the files, and a script that
is run on the source machine to make the transfer.

A design document is available in doc/design.rst that describes the
functioning of the system. This document will focus on getting the
system up and running, and the process for actually performing
physical-to-virtual transfers.

Requirements
============

The following external programs are used by this package:

* `paramiko <http://www.lag.net/paramiko/>`_ is needed on the transfer
  OS (live image booted on the source machine) for making SSH
  connections
* `pymox <http://code.google.com/p/pymox/>`_ is required to run the unit
  tests (`make check`)
* `rst2html, from docutils <http://docutils.sourceforge.net/>`_ is
  needed to build the html documentation (`make doc`)


Installation
============

Installation of Bootstrap OS
----------------------------

The bootstrap OS is a somewhat modified version of the
instance-debootstrap OS definition, whose documentation is located in
``doc/README.debootstrap.rst``. The first step will be to install this
OS definition onto the nodes of the cluster so that instances can be
created.

In order to install this package from source, you need to determine what
options ganeti itself has been configured with. If ganeti was built
directly from source, then the only place it looks for OS definitions is
``/srv/ganeti/os``, and you need to install the OS under it. Distribute
and install the package::

  gnt-cluster copyfile /root/ganeti-p2v-transfer-0.1.tar.gz
  gnt-cluster command "tar xf ganeti-p2v-transfer-0.1.tar.gz &&
    cd ganeti-p2v-transfer-0.1 &&
    ./configure --prefix=/usr --localstatedir=/var \
      --sysconfdir=/etc \
      --with-os-dir=/srv/ganeti/os &&
    make install-target"

If ganeti was installed from a package, its default OS path should
already include /usr/share/ganeti/os, so you can omit
``--with-os-dir``::

  gnt-cluster copyfile /root/ganeti-p2v-transfer-0.1.tar.gz
  gnt-cluster command "tar xf ganeti-p2v-transfer-0.1.tar.gz &&
    cd ganeti-p2v-transfer-0.1 &&
    ./configure --prefix=/usr --localstatedir=/var \
      --sysconfdir=/etc &&
    make install-target"

The actual path that ganeti will search for operating system definitions
can be determined easily in ganeti 2.4.3 by running ``gnt-cluster info``
and looking for the OS search path. In earlier versions, it can be found
by looking for a file named _autoconf.py under a ganeti directory in the
python modules tree (e.g.
``/usr/lib/python2.4/site-packages/ganeti/_autoconf.py``). In this file,
a variable named OS_SEARCH_PATH will list all the directories in which
ganeti will look for OS definitions. On of these should be passed to
``./configure`` as the value of ``--with-os-dir``.


Configuring the Bootstrap OS
----------------------------

Once the package is installed, edit the file
``/etc/ganeti/instance-p2v-target/p2v-target.conf`` to uncomment the
``EXTRA_PKGS`` value that is appropriate to the hypervisor you are using
on this cluster. Then distribute the updated file

Edit ``/etc/ganeti/instance-p2v-target/p2v-target.conf`` to uncomment
the appropriate value of EXTRA_PKGS. Depending on your setup, you may
need to change other values as well. Then, copy the edited file to all
nodes::

  gnt-cluster copyfile /etc/ganeti/instance-p2v-target/p2v-target.conf

Note on Bootstrap OS Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As the bootstrap OS is completely overwritten by the files transferred
from the source, it probably doesn't require much configuration.
However, all the information in ``doc/README.debootstrap.rst`` about
configuring the OS is still valid if you need it.


Generating the Bootstrap Initrd
-------------------------------

The bootstrap OS must be started with a specialized initrd that moves
all files into RAM before finishing the boot. Create this initrd by
running::

  sudo make_ramboot_initrd.py -V $DEB_KERNEL

on the master node, where $DEB_KERNEL is the name of a kernel that can
be used to boot a debootstrap instance. That is, if the filename of the
kernel is /boot/vmlinuz-2.6.32-generic, DEB_KERNEL would be
"2.6.32-generic". This command should create the file
``/boot/initrd.img-$DEB_KERNEL-ramboot``. Copy this file to the other
nodes with::

  gnt-cluster copyfile /boot/initrd.img-$DEB_KERNEL-ramboot

Compatibility Warning
~~~~~~~~~~~~~~~~~~~~~

The generated initrd depends heavily on the version of initramfs-tools
installed on the machine that generates it. As a result, it may not be
compatible with the kernel that is to be used for booting the bootstrap
OS. In this case, the bootstrap OS may not boot, or may not be able to
find the root device. If this happens, a good way to improve
compatibility is to use a machine that is already running the instance
kernel, perhaps a "normal" (non-p2v) instance on the same cluster.
Install and run ``make_ramboot_initrd.py`` on this machine to generate
the desired initrd.

Creating a Keypair
------------------

Users will authenticate to their instances using an SSH keypair
generated in advance by the administrator. The public key will be
installed into root's ``.ssh/authorized_keys`` file on the instance, and
the private key will be provided to the user so that they can make the
transfer. Generate the keys, with no passphrase, using the commands::

  ssh-keygen -t dsa -N "" -f /etc/ganeti/instance-p2v-target/id_dsa
  gnt-cluster copyfile /etc/ganeti/instance-p2v-target/id_dsa.pub

Keep the private key (``/etc/ganeti/instance-p2v-target/id_dsa``)
somewhere safe, and give it to users who wish to use the P2V system.


Workflow
========

Administrator: Creating Target Instance
---------------------------------------

Now that the nodes are set up to install instances with the bootstrap
OS, we can go ahead and perform a P2V transfer. The first step is to
create the instance that will receive the transfer. Create it with
the ``p2v-target+default`` OS and whatever parameters you need. The
default kernel and initrd of the instance should be ones that are both
*compatible with* and *installed on* the source OS. Also pass the
``--no-start`` flag, because we want to use the specially generated
initrd for the boot rather than the default one. The command line will
look something like the following::

  gnt-instance add -t<template> -s<size> -o p2v-target+default \
  -n<nodes> --no-start <hostname>

Now boot the instance using the kernel and initrd that work on the
initrd::

  gnt-instance start -H kernel_path=/boot/vmlinuz-$DEB_KERNEL,\
  initrd_path=/boot/initrd.img-$DEB_KERNEL-ramboot <hostname>

User: Starting the Transfer
---------------------------

Before you begin, you will need the private key corresponding to the
public key installed on the instance. Your administrator will provide
this to you.

Boot the source machine from a LiveCD or PXE image. Extract the
ganeti-p2v-transfer tarball and run::

  ./configure --prefix=/usr --localstatedir=/var \
    --sysconfdir=/etc
  sudo make install-source

This will install the ``p2v_transfer.py`` script. The script requires
the following arguments:

$root_dev
  the device file for the disk on which the root filesystem of the
  source machine is stored

$target_host
  the hostname or IP address of the instance to receive the transfer

$private_key
  the private key obtained from the administrator

Run the script, and your data will be transferred::

  sudo p2v_transfer.py $root_dev $target_host $private_key

When the transfer finishes, the script will shut down the instance. When
the ganeti watcher restarts it, log in and make sure that everything
works.


Troubleshooting
===============

Bootstrap OS does not boot properly
-----------------------------------

These instructions suggest building the initrd on a node, for
convenience.  However, it is possible that there are incompatibilities
between the initramfs-tools installed on the node and the kernel that
will be used for the bootstrap OS. In this case, the bootstrap OS may
not boot, or may not be able to find the root device. If this happens, a
good way to improve compatibility is to use a machine that is already
running the instance kernel, perhaps a "normal" (non-p2v) instance on
the same cluster. Install and run make_ramboot_initrd.py on this machine
to generate the desired initrd.

Another possibility is that the bootstrap OS does not have enough RAM to
complete its boot. Since the bootstrap OS must be copied entirely into
RAM, instances with small memory sizes are not supported. I have had
good luck using 768MB of instance memory.

No such script: ``/usr/share/debootstrap/scripts/squeeze``
----------------------------------------------------------
The version of debootstrap installed on the nodes may not be recent
enough to support installing squeeze. Try changing the SUITE variable in
``/etc/ganeti/instance-p2v-target/p2v-target.conf`` to something older::

  SUITE="lenny"

.. vim: set textwidth=72 :
.. Local Variables:
.. mode: rst
.. fill-column: 72
.. End:
