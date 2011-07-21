docrst = \
	design.rst

dochtml = $(docrst:.rst=.html)

if RST2HTML
  nodist_doc_DATA = $(dochtml)
endif

dist_doc_DATA = $(docrst)

%.html: %.rst
	@if test -n "$(RST2HTML)"; then\
	    $(RST2HTML) $< > $@;\
	else\
	    echo "'rst2html' not found, docs will not be built";\
	fi

CLEANFILES = $(dochtml)
