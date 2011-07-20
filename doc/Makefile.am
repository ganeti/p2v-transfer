docrst = \
	design.rst

dochtml = $(docrst:.rst=.html)

docstatic = \
	../COPYING \
	../NEWS \
	../README

if RST2HTML
  nodist_doc_DATA = $(dochtml)
endif

dist_doc_DATA = $(docrst) $(docstatic)

%.html: %.rst
	@if test -n "$(RST2HTML)"; then\
	    $(RST2HTML) $< > $@;\
	else\
	    echo "'rst2html' not found, docs will not be built";\
	fi

CLEANFILES = $(dochtml)
