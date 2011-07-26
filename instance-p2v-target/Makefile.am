osname=p2v-target

osdir=$(DESTDIR)$(OS_DIR)/$(osname)
configdir=$(DESTDIR)$(sysconfdir)/ganeti/instance-$(osname)
variantsdir=$(configdir)/variants
hookdir=$(configdir)/hooks
fixesdir=$(configdir)/fixes
fixlibdir=$(fixesdir)/fixlib

dist_os_SCRIPTS = create import export rename
config_DATA = p2v-target.conf
dist_hook_SCRIPTS = hooks/ramboot hooks/interfaces hooks/xen-hvc0 \
		    hooks/clear-root-password
hook_SCRIPTS = hooks/install-fixes

subst_files = hooks/install-fixes common.sh p2v-target.conf

dist_os_DATA = ganeti_api_version variants.list
os_SCRIPTS = common.sh

dist_sbin_SCRIPTS = scripts/make_ramboot_initrd.py
dist_fixes_SCRIPTS = \
	fixes/10_fix_fstab

dist_fixlib_DATA = \
	fixes/fixlib/fix_fstab.py \
	fixes/fixlib/__init__.py

EXTRA_DIST = $(patsubst %,%.in,$(subst_files)) \
	$(dist_TESTS) \
	$(test_extras)

# Testing python scripts
abs_top_srcdir = @abs_top_srcdir@
srcdir = $(abs_top_srcdir)/instance-p2v-target
dist_TESTS = \
	test/make_ramboot_initrd_test.py \
	test/fix_fstab_test.py
TESTS = $(dist_TESTS)
TESTS_ENVIRONMENT = \
	PYTHONPATH=$(srcdir)/scripts:$(srcdir)/fixes SRCDIR=$(srcdir)
test_extras = \
	test/testdata/fstab_uuid_in \
	test/testdata/fstab_uuid_out \
	test/testdata/movetoram

do_subst = sed \
	-e 's,[@]sysconfdir[@],$(sysconfdir),g' \
	-e 's,[@]localstatedir[@],$(localstatedir),g' \
	-e 's,[@]configdir[@],$(configdir),g'

$(subst_files):%: %.in Makefile
	@mkdir_p@ `dirname $@`
	$(do_subst) < $< > $@

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

CLEANFILES = $(subst_files)
