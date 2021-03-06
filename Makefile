MAIN_DIR=.
FILENAME=bfu
# Constants for insall directly
SOURCE_DIR=$(MAIN_DIR)/src
PY_REQS=$(SOURCE_DIR)/requirements.txt
MAIN_FILE=$(SOURCE_DIR)/$(FILENAME).py
INSTALL_PATH=/usr/local/bin/$(FILENAME)
# Constants for make bin installer
THIS_FILE=$(MAIN_DIR)/Makefile
BUILDER=$(MAIN_DIR)/builder.py
BUILD_RESULT=$(MAIN_DIR)/bfu_installer

all: install clean

install: $(MAIN_FILE) $(PY_REQS)
	cp -rf $(MAIN_FILE) $(INSTALL_PATH)
	chmod +x $(INSTALL_PATH)

uninstall: $(INSTALL_PATH)
	rm -rf $(INSTALL_PATH)

build: $(MAIN_FILE) $(BUILDER)
	$(BUILDER) --makefile=$(THIS_FILE) --output=$(BUILD_RESULT) $(SOURCE_DIR)

$(PY_REQS):
	python3 -c "import pipreqs" 2>/dev/null || pip3 install pipreqs
	pipreqs $(SOURCE_DIR) --savepath $(PY_REQS)

clean:
	rm -rf $(PY_REQS)
