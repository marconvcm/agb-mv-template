//! Button handling.
//!
//! Thin wrapper over agb's `ButtonController` that adds the auto-repeat the
//! cursor needs: hold a direction and it steps, rather than needing a press
//! per cell.

use agb::input::{Button, ButtonController, Tri};

/// Frames before a held direction starts repeating, then between repeats.
const REPEAT_DELAY: u8 = 16;
const REPEAT_RATE: u8 = 5;

pub struct Input {
    buttons: ButtonController,
    held: u8,
    countdown: u8,
}

impl Default for Input {
    fn default() -> Self {
        Input::new()
    }
}

impl Input {
    pub fn new() -> Input {
        Input {
            buttons: ButtonController::new(),
            held: 0,
            countdown: 0,
        }
    }

    pub fn update(&mut self) {
        self.buttons.update();

        let moving = self.buttons.x_tri() != Tri::Zero || self.buttons.y_tri() != Tri::Zero;
        if !moving {
            self.held = 0;
            self.countdown = 0;
            return;
        }
        self.held = self.held.saturating_add(1);
        self.countdown = self.countdown.saturating_sub(1);
    }

    pub fn just_pressed(&self, button: Button) -> bool {
        self.buttons.is_just_pressed(button)
    }

    /// Horizontal step this frame, with auto-repeat.
    pub fn step_x(&mut self) -> i32 {
        if self.should_step() {
            tri_to_i32(self.buttons.x_tri())
        } else {
            0
        }
    }

    /// Vertical step this frame, with auto-repeat.
    pub fn step_y(&mut self) -> i32 {
        if self.should_step() {
            tri_to_i32(self.buttons.y_tri())
        } else {
            0
        }
    }

    fn should_step(&mut self) -> bool {
        // The first frame of a press always steps; after that the direction
        // has to be held past the delay before it repeats.
        if self.held == 1 {
            self.countdown = REPEAT_DELAY;
            return true;
        }
        if self.held > 1 && self.countdown == 0 {
            self.countdown = REPEAT_RATE;
            return true;
        }
        false
    }
}

fn tri_to_i32(tri: Tri) -> i32 {
    match tri {
        Tri::Positive => 1,
        Tri::Negative => -1,
        Tri::Zero => 0,
    }
}
