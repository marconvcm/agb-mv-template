# agb-mv-template

A starting point for Game Boy Advance games in Rust with
[`agb`](https://github.com/agbrs/agb).

**Read [`AGENTS.md`](AGENTS.md) first.** It is the real content of this repo:
the hardware limits that bite, the toolchain traps, how to verify what the
ROM actually draws, and why devices black-screen. It was written from a
finished port, not from the manual.

## Quick start

```sh
rustup toolchain install nightly-2026-07-22 -c rust-src -c clippy -c rustfmt
cargo install agb-gbafix
make test       # game logic, on the host, in milliseconds
make run        # build and launch in mGBA
make release    # padded, header-checked game.gba
```

## Layout

| Path | What |
|---|---|
| `core/` | All game rules. `no_std`, no allocator, **no `agb` dependency**, so it tests natively. |
| `gba/` | The ROM. Its own workspace root, because it targets `thumbv4t-none-eabi`. |
| `tools/` | Host-side codegen and `romcheck`. Never shipped. |
| `assets-src/` | Inputs to the art generator. Not read by the build. |

## What you get

- **A tested-logic split.** `cargo test -p game-core` runs the rules without
  an emulator. This is the point of the layout.
- **Two text systems** — background tiles (free) and an object font (tight) —
  which between them avoid agb's runtime text layout entirely.
- **An art generator that enforces GBA limits** and fails the run rather than
  emitting art the hardware will not take.
- **Every font in one manifest** (`assets-src/fonts.toml`). `make fonts`
  builds the sheets and a generated `fonts.rs` with a module per font, so
  charsets and advances never drift from the art. `tools/gbafont.py probe`
  finds the sizes a new TTF renders crisply at.
- **Headless screenshots** (`make shots`) so you can see what the ROM draws
  without a desktop in the loop.
- **`romcheck`**, run automatically by `make release`: header checksum, magic
  byte, Nintendo logo, power-of-two padding.

## Renaming

The crates are `game-core` and `game-gba`, the ROM is `game.gba`, and the
cartridge title is `GAME`. Change those in `Cargo.toml`, `gba/Cargo.toml` and
the `Makefile` (`TITLE`, `ROM`, `BIN`).

## Before shipping

Check the licence of any font or art you carry over. `assets-src/font.ttf`
here is Kenney Mini Square Mono, chosen because it renders with no
antialiasing at 8px.
