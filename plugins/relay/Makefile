# relay integration-test harness entry point (spec 2026-09-08). Local, on demand.
# NOT wired into CI. Sets RELAY_ITEST=1, the second gate the conftest requires.
SHELL := /bin/bash

TIER   ?=
CMD    ?=
ENGINE ?=
AGENT  ?=
ROUNDS ?=
KEEP   ?=

OPTS :=
ifneq ($(CMD),)
OPTS += --relay-cmd $(CMD)
endif
ifneq ($(ENGINE),)
OPTS += --relay-engine $(ENGINE)
endif
ifneq ($(AGENT),)
OPTS += --relay-agent $(AGENT)
endif
ifneq ($(ROUNDS),)
OPTS += --relay-rounds $(ROUNDS)
endif
ifeq ($(KEEP),1)
OPTS += --relay-keep
endif

PYTEST := RELAY_ITEST=1 python3 -m pytest -m integration -q -rs $(OPTS)

.PHONY: itest
itest:
	@test -n "$(TIER)" || { echo "TIER is required: make itest TIER=gates|e2e|acpx|all"; exit 2; }
ifeq ($(TIER),all)
	$(PYTEST) tests/integration/test_gates.py
	$(PYTEST) tests/integration/test_acpx_live.py
	$(PYTEST) tests/integration/test_e2e.py
else ifeq ($(TIER),gates)
	$(PYTEST) tests/integration/test_gates.py
else ifeq ($(TIER),acpx)
	$(PYTEST) tests/integration/test_acpx_live.py
else ifeq ($(TIER),e2e)
	$(PYTEST) tests/integration/test_e2e.py
else
	@echo "unknown TIER '$(TIER)': use gates|e2e|acpx|all"; exit 2
endif
