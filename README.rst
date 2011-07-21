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


For Administrators
==================

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
``/srv/ganeti/os``, and you need to install the OS under it. *On each
node of the cluster,* run the following::

  ./configure --prefix=/usr --localstatedir=/var \
    --sysconfdir=/etc \
    --with-os-dir=/srv/ganeti/os
  sudo make install-target

If ganeti was installed from a package, its default OS path should
already include /usr/share/ganeti/os, so you can just run::

  ./configure -prefix=/usr --localstatedir=/var \
    --sysconfdir=/etc
  sudo make install-target

The actual path that ganeti has been installed with can be determined by
looking for a file named _autoconf.py under a ganeti directory in the
python modules tree (e.g.
``/usr/lib/python2.4/site-packages/ganeti/_autoconf.py``). In this file,
a variable named OS_SEARCH_PATH will list all the directories in which
ganeti will look for OS definitions.

.. TODO(benlipton): enable kernel in EXTRA_PKGS


Note: Configuring the Bootstrap OS
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
be used to boot a debootstrap instance. This should create the file
``/boot/initrd.img-$DEB_KERNEL-ramboot``. Copy this file to the other
nodes with::

  gnt-cluster copyfile /boot/initrd.img-$DEB_KERNEL-ramboot


Creating a Keypair
------------------

Users will authenticate to their instances using an SSH keypair
generated in advance by the administrator. The public key will be
installed into root's ``.ssh/authorized_keys`` file on the instance, and
the private key will be provided to the user so that they can make the
transfer. Generate the keys, with no passphrase, using the command::

  ssh-keygen -t dsa -N ""

Place the public key in ``/etc/ganeti/instance-p2v/id_dsa.pub`` and copy
it to all nodes. Keep the private key somewhere safe, and give it to
users who wish to use the P2V system.


Creating a Target Instance
--------------------------

Now that the nodes are set up to install instances with the bootstrap
OS, we can go ahead and perform a P2V transfer. The first step is to
create the instance that will receive the transfer. Create it with
the ``p2v-target+default`` os and whatever parameters you need. The
default kernel and initrd of the instance should be ones that are both
*compatible with* and *installed on* the source OS. Also pass the
``--no-start`` flag, because we want to use the specially generated
initrd for the boot rather than the default one. The command line will
look something like the following::

  gnt-instance add -t<template> -s<size> -o p2v-target+default \
  --no-start <hostname>

Now boot the instance using the kernel and initrd that work on the
initrd::

  gnt-instance start -H kernel_path=/boot/$DEB_KERNEL,\
  initrd_path=/boot/initrd.img-$DEB_KERNEL-ramboot <hostname>


For Users
=========

Starting the Transfer
---------------------

Before you begin, you will need the private key corresponding to the
public key installed on the instance. Your administrator will provide
this to you.

Boot the source machine from a LiveCD or PXE image. Extract the
ganeti-p2v-transfer tarball and run::

  ./configure -prefix=/usr --localstatedir=/var \
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

.. vim: set textwidth=72 :
.. Local Variables:
.. mode: rst
.. fill-column: 72
.. End:
