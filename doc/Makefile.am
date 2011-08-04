docrst = \
	../README.rst \
	design.rst \
	README.debootstrap.rst \
	instance-p2v-target.rst

dochtml = $(docrst:.rst=.html)

docstatic = \
	../COPYING \
	../NEWS

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
