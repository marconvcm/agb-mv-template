# See AGENTS.md for why the layout is split this way.
ROM   := game.gba
BIN   := gba/target/thumbv4t-none-eabi/release/game-gba
TITLE := GAME
SHOTS := $(shell pwd)/docs

.PHONY: all test run build release shots gen-art fonts font-probe font-preview check fmt clippy clean

all: release

# Game logic on the host. Fast, and the gate for any rule change.
test:
	cargo test -p game-core

build:
	cd gba && cargo build

run:
	cd gba && cargo run --release

release: $(ROM)

$(ROM): FORCE
	cd gba && cargo build --release
	agb-gbafix $(BIN) --title $(TITLE) --padding --output $(ROM)
	@cargo run -q -p game-tools --bin romcheck -- $(ROM)

# Headless screenshots straight from the ROM. Needs agb's
# screenshot-generator on PATH -- see AGENTS.md section 7.
shots:
	cd gba && cargo build --release --features capture
	agb-gbafix $(BIN) --title $(TITLE) --padding --output /tmp/$(TITLE)-capture.gba
	@mkdir -p $(SHOTS)
	screenshot-generator --rom /tmp/$(TITLE)-capture.gba --frames 60 --output $(SHOTS)/shot-boot.png
	@ls -l $(SHOTS)/shot-*.png

# Regenerate the committed art. Needs Pillow and the fonts in assets-src/.
gen-art: fonts
	python3 tools/gbagfx.py

# Every font in assets-src/fonts.toml -> gba/gfx/fonts/ and gba/src/gfx/fonts.rs.
fonts:
	python3 tools/gbafont.py build

# Which sizes of a font render crisply?   make font-probe FONT='Saira ExtraCondensed Thin'
font-probe:
	python3 tools/gbafont.py probe "$(FONT)"

# Sample text as the GBA would draw it, scaled up, into target/font-preview.png.
#   make font-preview FONT=assets-src/font.ttf SIZE=8 TEXT='PRESS START|SCORE 100'
SIZE ?= 8
TEXT ?= PRESS START|Score 0123456789
font-preview:
	python3 tools/gbafont.py preview "$(FONT)" --size $(SIZE) --text "$(TEXT)"

check: test
	cargo clippy -p game-core -- -D warnings
	cd gba && cargo clippy --release -- -D warnings

fmt:
	cargo fmt --all
	cd gba && cargo fmt --all

clean:
	cargo clean
	cd gba && cargo clean
	rm -f $(ROM)

FORCE:
