//! Text written as background tiles.
//!
//! Costs no objects, so this is the right choice for anything static on a
//! flat-coloured surface: HUD labels, instructions, menus over a plain
//! panel. A screenful of text is always this, never objects -- thirty
//! characters across a dozen lines is several hundred glyphs and the
//! hardware has 128 objects.
//!
//! Tiles sit on the 8px grid, so a 6px font reads a little airy here. Use
//! `objtext` where that matters.

use agb::display::tiled::RegularBackground;

use super::assets::backgrounds;
use super::fonts::text as font;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Charset {
    /// Normal ink on the dark panel.
    Dark,
    /// Dimmed ink on the dark panel, for unavailable entries.
    Dim,
}

impl Charset {
    fn set_tile(self, bg: &mut RegularBackground, tx: u16, ty: u16, index: usize) {
        macro_rules! place {
            ($src:expr) => {{
                let settings = $src.tile_settings;
                // A bad glyph degrades to a blank rather than panicking.
                let tile = settings.get(index).copied().unwrap_or(settings[0]);
                bg.set_tile((tx, ty), &$src.tiles, tile);
            }};
        }
        match self {
            Charset::Dark => place!(backgrounds::TEXT_DARK),
            Charset::Dim => place!(backgrounds::TEXT_DIM),
        }
    }
}

/// Write ASCII at a tile position. Anything past the right edge is dropped.
pub fn write(bg: &mut RegularBackground, tx: u16, ty: u16, text: &[u8], set: Charset) {
    for (i, &ch) in text.iter().enumerate() {
        let x = tx + i as u16;
        if x >= 32 {
            break;
        }
        set.set_tile(bg, x, ty, font::index(ch));
    }
}

/// Blank `len` cells, for clearing a row before rewriting it.
pub fn clear(bg: &mut RegularBackground, tx: u16, ty: u16, len: u16, set: Charset) {
    for i in 0..len {
        set.set_tile(bg, tx + i, ty, font::index(b' '));
    }
}
