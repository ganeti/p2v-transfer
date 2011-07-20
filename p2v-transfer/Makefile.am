dist_sbin_SCRIPTS = \
	p2v_transfer.py

EXTRA_DIST = \
	$(dist_TESTS) \
	$(test_extras)

# Testing python scripts
dist_TESTS = \
	test/p2v_transfer_test.py
test_extras = # coming soon

srcdir = @abs_srcdir@
TESTS = $(dist_TESTS)
TESTS_ENVIRONMENT = \
	PYTHONPATH=$(srcdir) SRCDIR=$(srcdir)
