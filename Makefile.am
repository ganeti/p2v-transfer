# ganeti-p2v-transfer root Makefile.am
# Goal: make it easy to install the appropriate things for either the
# bootstrap or transfer operating systems, without accidentally installing
# both of them. So, this file defines several convenience targets while making
# sure that a normal 'make' or 'make install' doesn't install everything.

all: help
install: help

help:
	@echo 'Please select what to install:'
	@echo '  "make install-target": Install docs and instance OS'\
	' (on a ganeti node)'
	@echo '  "make install-source": Install docs and transfer script'\
	' (on source machine)'
	@if test -n "$(RST2HTML)"; then \
		echo '  "make doc": Just build html documentation'; \
		echo '  "make install-doc": Build and install'\
	' html documentation'; \
	else \
		echo 'Note: rst2html not found, documentation will'\
		'not be built'; \
	fi


.PHONY: install-target install-source doc install-doc help check all
parts = p2v-transfer instance-p2v-target doc

install-target: install-doc
	$(MAKE) -C instance-p2v-target
	$(MAKE) -C instance-p2v-target install

install-source: install-doc
	$(MAKE) -C p2v-transfer
	$(MAKE) -C p2v-transfer install

doc:
	$(MAKE) -C doc

install-doc: doc
	$(MAKE) -C doc install

check:
	list='$(parts)'; for dir in $$list; do \
	    $(MAKE) -C $$dir check || exit 1; \
	done

DIST_SUBDIRS = $(parts)
