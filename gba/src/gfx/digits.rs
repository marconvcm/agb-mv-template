//! Numbers drawn as objects.
//!
//! For values that change as often as every frame, where rewriting tiles
//! would be wasteful. Anything that changes once a turn belongs in the
//! background instead.

use agb::display::GraphicsFrame;
use agb::display::object::Object;

use super::assets::{ADVANCE, DIGITS_ALT, digit_frame, sprites};

/// A fixed-width, zero-padded, right-aligned number at a fixed position.
#[derive(Clone, Copy)]
pub struct NumberField {
    pub x: i32,
    pub y: i32,
    pub width: usize,
    /// Draw in the second colour, e.g. to highlight a value that matters.
    pub alt: bool,
}

impl NumberField {
    pub const fn new(x: i32, y: i32, width: usize) -> NumberField {
        NumberField {
            x,
            y,
            width,
            alt: false,
        }
    }

    pub const fn alt(self) -> NumberField {
        NumberField { alt: true, ..self }
    }

    /// Values too large are clamped to all-nines rather than spilling into
    /// whatever is next to them.
    pub fn show(&self, frame: &mut GraphicsFrame, value: u32) {
        let mut digits = [0u8; 10];
        let mut v = value.min(pow10(self.width) - 1);
        for i in (0..self.width.min(digits.len())).rev() {
            digits[i] = b'0' + (v % 10) as u8;
            v /= 10;
        }
        let offset = if self.alt { DIGITS_ALT } else { 0 };
        for (i, &ch) in digits[..self.width.min(digits.len())].iter().enumerate() {
            Object::new(sprites::DIGITS.sprite(digit_frame(ch) + offset))
                .set_pos((self.x + i as i32 * ADVANCE, self.y))
                .show(frame);
        }
    }
}

fn pow10(n: usize) -> u32 {
    let mut out: u32 = 1;
    for _ in 0..n.min(9) {
        out *= 10;
    }
    out
}
