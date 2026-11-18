# mnkhl — build system (v0.01)
#
# One job: install the script as a command. The symlink keeps the
# repo copy authoritative — edit mnkhl.py, and the installed
# command changes with it.

BIN_DIR := $(HOME)/.local/bin

.PHONY: install uninstall

install:
	@test -d "$(BIN_DIR)" || mkdir -p "$(BIN_DIR)"
	ln -sf "$(CURDIR)/mnkhl.py" "$(BIN_DIR)/mnkhl"
	@echo "installed: $(BIN_DIR)/mnkhl -> $(CURDIR)/mnkhl.py"

# uninstall removes the symlink ONLY if it points into this repo.
uninstall:
	@if [ -L "$(BIN_DIR)/mnkhl" ]; then \
	  if [ "$(BIN_DIR)/mnkhl" -ef "$(CURDIR)/mnkhl.py" ]; then \
	    rm "$(BIN_DIR)/mnkhl"; echo "uninstalled: $(BIN_DIR)/mnkhl"; \
	  else \
	    echo "$(BIN_DIR)/mnkhl is not ours — not touching it."; exit 1; \
	  fi; \
	else \
	  echo "nothing to uninstall."; \
	fi
