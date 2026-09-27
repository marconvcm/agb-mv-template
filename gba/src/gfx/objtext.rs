//! Text drawn as objects.
//!
//! Glyphs sit at the font's natural advance rather than the 8px tile grid,
//! so menus and labels set tight. Use this over uneven art, for text that
//! moves, and for menus; use `text` for static text on a flat panel, which
//! costs no objects at all.
//!
//! Between them these replace agb's `Layout`/`ObjectTextRenderer`, which is
//! correct but slow enough that laying out a line can cost a frame.

use agb::display::GraphicsFrame;
use agb::display::object::Object;

use super::assets::sprites;
use super::fonts::ui;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ink {
    Normal,
    Dim,
}

impl Ink {
    fn offset(self) -> usize {
        match self {
            Ink::Normal => ui::NORMAL,
            Ink::Dim => ui::DIM,
        }
    }
}

/// Pixel width `text` will occupy.
pub fn width(text: &[u8]) -> i32 {
    ui::width(text)
}

pub fn write(frame: &mut GraphicsFrame, x: i32, y: i32, text: &[u8], ink: Ink) {
    for (i, &ch) in text.iter().enumerate() {
        if ch == b' ' {
            continue; // a space costs an object otherwise
        }
        Object::new(sprites::UI.sprite(ui::index(ch) + ink.offset()))
            .set_pos((x + i as i32 * ui::ADVANCE, y))
            .show(frame);
    }
}

pub fn write_centred(frame: &mut GraphicsFrame, centre_x: i32, y: i32, text: &[u8], ink: Ink) {
    write(frame, centre_x - width(text) / 2, y, text, ink);
}

pub fn write_right(frame: &mut GraphicsFrame, right: i32, y: i32, text: &[u8], ink: Ink) {
    write(frame, right - width(text), y, text, ink);
}
