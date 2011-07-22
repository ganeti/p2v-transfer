ganeti-instance-debootstrap
===========================

This is a guest OS definition for Ganeti (http://code.google.com/p/ganeti).
It will install a minimal version of Debian or Ubuntu via debootstrap (thus it
requires network access). This only works if you have a Debian-based node or
you have debootstrap installed by hand on another distribution.

Installation
------------

In order to install this package from source, you need to determine what
options ganeti itself has been configured with. If ganeti was built
directly from source, then the only place it looks for OS definitions is
``/srv/ganeti/os``, and you need to install the OS under it::

  ./configure --prefix=/usr --localstatedir=/var \
    --sysconfdir=/etc \
    --with-os-dir=/srv/ganeti/os
  make && make install

If ganeti was installed from a package, its default OS path should
already include /usr/share/ganeti/os, so you can just run::

  ./configure -prefix=/usr --localstatedir=/var \
    --sysconfdir=/etc
  make && make install

Note that you need to repeat this procedure on all nodes of the cluster.

The actual path that ganeti has been installed with can be determined by
looking for a file named _autoconf.py under a ganeti directory in the
python modules tree (e.g.
``/usr/lib/python2.4/site-packages/ganeti/_autoconf.py``). In this file,
a variable named OS_SEARCH_PATH will list all the directories in which
ganeti will look for OS definitions.

Configuration of instance creation
----------------------------------

The kind of instance created can be customized via a settings file. This
file is not installed by default, as the instance creation will work
without it. The creation scripts will look for it in
``$sysconfdir/default/ganeti-instance-debootstrap``, so if you have run
configure with the parameter ``--sysconfdir=/etc``, the final filename
will be ``/etc/default/ganeti-instance-debootstrap``.

The following settings will be examined in this file (see also the file
named 'defaults' in the source distribution for more details):

- PROXY: http proxy to use for non-cached installs
- MIRROR: the mirror to use if not the default one
- ARCH: either i386 or amd64, otherwise your current architecture will
  be used
- SUITE: the actual OS to be installed; the current default is Debian
  *lenny*, and you can choose any of the OSes supported deboostrap (on
  Debian, look into /usr/share/deboostrap/scripts)
- EXTRAPKGS: most OSes will need some extra packages installed to make
  them work nicely under Xen; the example file containts a few
  suggestions
- CUSTOMIZE_DIR: a directory containing customization script for the
  instance.  (by default $sysconfdir/ganeti/instance-debootstrap/hooks)
  See "Customization of the instance" below.
- GENERATE_CACHE: if 'yes' (the default), the installation process will
  save and reuse a cache file to speed reinstalls (located under
  $localstatedir/cache/ganeti-instance-debootstrap)
- CLEAN_CACHE: if empty, the cached files will never be cleaned and thus
  the installation will definitely need to be updated after install;
  otherwise, the value of this variable will be taken as the number of
  days after which to remove the cache file; the default is 14 (two
  weeks)
- PARTITION_STYLE: if 'none' the device will be formatted directly, if 'msdos'
  a partition table will be installed on it. You need to have kpartx installed
  to use the 'msdos' option. The default is 'msdos' from Ganeti 2.0 onwards,
  but still 'none' if installing under Ganeti 1.2

Note that the settings file is important on the node that the instance
is installed on, not the cluster master. This is indeed not a very good
model of using this OS but currently the OS interface in ganeti is
limiting.

Customization of the instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If run-parts is in the os create script, and the CUSTOMIZE_DIR (by
default $sysconfdir/ganeti/instance-debootstrap/hooks,
/etc/ganeti/instance-debootstrap/hooks if you configured the os with
--sysconfdir=/etc) directory exists any executable whose name matches
the run-parts execution rules (quoting run-parts(8): the names must
consist entirely of upper and lower case letters, digits, underscores,
and hyphens) is executed to allow further personalization of the
installation. The following environment variables are passed, in
addition to the ones ganeti passes to the OS scripts:

TARGET: directory in which the filesystem is mounted
SUITE: suite installed by debootstrap (eg: lenny)
ARCH: target architecture
PARTITION_STYLE: style of the disk partitioning (see above)
EXTRA_PKGS: extra packages installed by debootstrap
BLOCKDEV: ganeti block device
FSYSDEV: device in which the filesystem resides (the one mounted in TARGET)

The scripts in CUSTOMIZE_DIR can exit with an error code to signal an error in
the instance creation, should they fail.

The scripts in CUSTOMIZE_DIR should not start any long-term processes or
daemons using this directory, otherwise the installation will fail because it
won't be able to umount the filesystem from the directory, and hand the
instance back to Ganeti.


Caching
~~~~~~~

As described above, the install process uses a cache file in order to
speed up repeated installs. If you only rarely do installs, this will
not matter to you, but if you want to install 10 instances in a row, the
difference will be visible.

The default settings are to generate a cache, and to clean it up after
two weeks.

Note that the cache will use one file per architecture per suite, so if
you install multiple suites there might be a non-trivial amount of space
used in the cache directory. It is safe to remove manually the files.

It is also possible, if done with care, to modify and regenerate the
cache file (which is simply a tar archive) in order to preseed your
installs with site-specific customizations.

Instance notes
--------------

The instance is a minimal install:

 - it has no password for root; simply login at the console
 - it has no network interfaces defined (besides lo); add your own
   definitions to /etc/network/interfaces
 - after configuring the network, it is recommended to run ``apt-get
   update`` so that signatures for the release files are picked up

.. vim: set textwidth=72 :
.. Local Variables:
.. mode: rst
.. fill-column: 72
.. End:
