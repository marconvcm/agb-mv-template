//! Every piece of art in the ROM.
//!
//! Regenerate the images with `make gen-art`; they are committed. Font
//! sheets live in `gfx/fonts/` and their glyph tables in `fonts.rs`, both
//! generated from `assets-src/fonts.toml`.
//!
//! Images that share a surface colour belong in the *same*
//! `include_background_gfx!` invocation, because palettes are optimised per
//! invocation.

agb::include_background_gfx!(
    pub mod backgrounds,
    PANEL => deduplicate "gfx/panel.png",
    // One charset per surface the text sits on: background palette index 0
    // is the global backdrop, not per-tile transparency, so a text tile
    // carries the colour of whatever it sits on.
    TEXT_DARK => deduplicate "gfx/fonts/text_dark.png",
    TEXT_DIM => deduplicate "gfx/fonts/text_dim.png",
);

agb::include_aseprite!(
    pub mod sprites,
    8 "gfx/fonts/ui.png",
    8 "gfx/fonts/digits.png",
);
