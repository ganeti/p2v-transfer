all: help
help:
	@echo 'This package has two parts, please select the one to install:'
	@echo '  "make target": Install instance OS (on a ganeti node)'
	@echo '  "make source": Install p2v-transfer script (on source machine)'

target:
	$(MAKE) -C instance-p2v-target
	$(MAKE) -C instance-p2v-target install

source:
	$(MAKE) -C p2v-transfer
	$(MAKE) -C p2v-transfer install
