//! Every piece of art in the ROM, and the glyph tables that index it.
//!
//! Regenerate the images with `make gen-art`; they are committed.
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
    CHARSET_DARK => deduplicate "gfx/charset_dark.png",
    CHARSET_DIM => deduplicate "gfx/charset_dim.png",
);

agb::include_aseprite!(
    pub mod sprites,
    8 "gfx/font.png",
    8 "gfx/digits.png",
);

/// Glyph order in the charset images and in `font.png`. Index is the tile or
/// frame index; keep in sync with `CHARSET` in `tools/gbagfx.py`.
pub const CHARSET: &[u8] = b" 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:$+-./!?";
/// Glyph order in `digits.png`.
pub const DIGIT_GLYPHS: &[u8] = b"0123456789+- ";
/// `font.png` holds the glyphs twice: normal ink, then dimmed.
pub const FONT_DIM: usize = CHARSET.len();
/// `digits.png` holds the glyphs twice: normal, then highlighted.
pub const DIGITS_ALT: usize = DIGIT_GLYPHS.len();

/// The font's advance. Objects sit at this pitch; background tiles are
/// always 8px apart regardless.
pub const ADVANCE: i32 = 6;

/// Tile or frame index for a glyph, falling back to blank.
pub fn charset_index(ch: u8) -> usize {
    let ch = ch.to_ascii_uppercase();
    CHARSET.iter().position(|&g| g == ch).unwrap_or(0)
}

/// Frame index for a digit glyph, falling back to blank.
pub fn digit_frame(ch: u8) -> usize {
    DIGIT_GLYPHS
        .iter()
        .position(|&g| g == ch)
        .unwrap_or(DIGIT_GLYPHS.len() - 1)
}
