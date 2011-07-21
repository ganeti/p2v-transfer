AC_PREREQ(2.59)
AC_INIT(ganeti-p2v-transfer, 0.1, ganeti@googlegroups.com)

AC_CONFIG_AUX_DIR(autotools)
AC_CONFIG_SRCDIR(configure)

AM_INIT_AUTOMAKE([1.9 foreign tar-ustar -Wall -Wno-portability])

# --with-os-dir=...
AC_ARG_WITH([os-dir],
  [AS_HELP_STRING([--with-os-dir=DIR],
    [top-level OS directory under which to install]
    [ (default is $datadir/ganeti/os)]
  )],
  [os_dir="$withval"],
  [os_dir="$datadir/ganeti/os"])
AC_SUBST(OS_DIR, $os_dir)

# Check common programs
AC_PROG_INSTALL
AC_PROG_LN_S

AC_PATH_PROG([RST2HTML], [rst2html])
AM_CONDITIONAL([RST2HTML], [test -n "$RST2HTML"])

AC_CONFIG_FILES([ Makefile
        instance-p2v-target/Makefile
        p2v-transfer/Makefile
        doc/Makefile ])

AC_OUTPUT
