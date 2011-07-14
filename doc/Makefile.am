docrst = \
	design.rst

dochtml = $(docrst:.rst=.html)

nodist_doc_DATA = $(dochtml)
dist_doc_DATA = $(docrst)

%.html: %.rst
	@test -n "$(RST2HTML)" || \
	    { echo 'rst2html' not found, docs will not be built; exit 1; }
	$(RST2HTML) $< > $@

CLEANFILES = $(dochtml)
