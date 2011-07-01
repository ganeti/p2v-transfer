osname=$(subst ganeti-instance-,,$(PACKAGE))

osdir=$(OS_DIR)/$(osname)
variantsdir=$(DESTDIR)$(sysconfdir)/ganeti/instance-debootstrap/variants

dist_os_SCRIPTS = create import export rename
dist_os_DATA = ganeti_api_version variants.list
os_DATA = common.sh

dist_sbin_SCRIPTS = scripts/make_ramboot_initrd.py

dist_doc_DATA = ../COPYING ../NEWS ../README

EXTRA_DIST = common.sh.in defaults \
	examples/hooks/grub \
	examples/hooks/interfaces \
	$(dist_TESTS) \
	$(test_extras)

# Testing python scripts
abs_top_srcdir = @abs_top_srcdir@
srcdir = $(abs_top_srcdir)/instance-p2v-target
dist_TESTS = \
	test/make_ramboot_initrd_test.py
TESTS = $(dist_TESTS)
TESTS_ENVIRONMENT = \
	PYTHONPATH=$(srcdir) SRCDIR=$(srcdir)
test_extras = \
	scripts/__init__.py \
	test/testdata/movetoram

do_subst = sed \
	-e 's,[@]sysconfdir[@],$(sysconfdir),g' \
	-e 's,[@]localstatedir[@],$(localstatedir),g'

common.sh: common.sh.in Makefile
	$(do_subst) < $< > $@
	chmod +x $@

install-exec-local:
	@mkdir_p@ $(variantsdir)
	touch $(variantsdir)/default.conf

install-exec-hook:
	@echo
	@echo *****************************************************************
	@echo To make the instances boot from RAM, a special initrd needs to be
	@echo created. Plase run
	@echo $(sbindir)/make_ramboot_initrd.py -V VERSION
	@echo where VERSION is the name of the instance kernel. Run
	@echo $(sbindir)/make_ramboot_initrd.py --help for more options.
	@echo *****************************************************************
	@echo

CLEANFILES = common.sh
