//! Screen flow and the frame loop.
//!
//! Replace the demo screen with your game. The shape worth keeping: one
//! `Screen` enum, a background rebuilt on entry, a fade between screens, and
//! a render pass that never mutates state.

use agb::Gba;
use agb::display::tiled::{RegularBackground, RegularBackgroundSize};
use agb::display::{GraphicsFrame, Priority};
use agb::fixnum::Num;
use agb::input::Button;
use game_core::{Cmd, Session};

use crate::gfx::assets::backgrounds;
use crate::gfx::digits::NumberField;
use crate::gfx::objtext::{self, Ink};
use crate::gfx::text::{self, Charset};
use crate::platform::input::Input;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Screen {
    Title,
    Demo,
}

/// A three-phase fade. `hold` of `u32::MAX` means "stay until something else
/// changes the screen".
struct Fade {
    frames: u32,
    fade_in: u32,
    hold: u32,
    fade_out: u32,
}

impl Fade {
    fn new(fade_in: u32, hold: u32, fade_out: u32) -> Fade {
        Fade {
            frames: 0,
            fade_in,
            hold,
            fade_out,
        }
    }

    fn tick(&mut self) {
        self.frames += 1;
    }

    /// Part of the Fade API: used by screens that time out on their own,
    /// such as a studio card that fades in, holds and fades out.
    #[allow(dead_code)]
    fn finished(&self) -> bool {
        self.frames >= self.fade_in.saturating_add(self.hold).saturating_add(self.fade_out)
    }

    /// The hardware blend coefficient has four fractional bits, so there are
    /// only seventeen steps. Compute in raw sixteenths and skip the division.
    fn darkness(&self) -> Num<u8, 4> {
        const STEPS: u32 = 16;
        let f = self.frames;
        let raw = if f < self.fade_in {
            STEPS - (f * STEPS / self.fade_in.max(1)).min(STEPS)
        } else if f < self.fade_in.saturating_add(self.hold) {
            0
        } else {
            ((f - self.fade_in - self.hold) * STEPS / self.fade_out.max(1)).min(STEPS)
        };
        Num::from_raw(raw.min(STEPS) as u8)
    }
}

pub struct App {
    session: Session,
    screen: Screen,
    bg: RegularBackground,
    fade: Fade,
    frame_counter: u32,
    seeded: bool,
}

impl App {
    pub fn new() -> App {
        let mut app = App {
            session: Session::new(1),
            screen: Screen::Title,
            bg: fresh_background(),
            fade: Fade::new(30, u32::MAX, 0),
            frame_counter: 0,
            seeded: false,
        };
        app.enter(Screen::Title);
        app
    }

    fn enter(&mut self, screen: Screen) {
        self.screen = screen;
        self.bg = fresh_background();
        self.bg.fill_with(&backgrounds::PANEL);
        self.fade = Fade::new(20, u32::MAX, 0);

        match screen {
            Screen::Title => {
                text::write(&mut self.bg, 8, 6, b"AGB TEMPLATE", Charset::Dark);
                text::write(&mut self.bg, 8, 8, b"PRESS START", Charset::Dim);
            }
            Screen::Demo => {
                text::write(&mut self.bg, 2, 2, b"A    STEP", Charset::Dark);
                text::write(&mut self.bg, 2, 3, b"B    RESET", Charset::Dark);
                text::write(&mut self.bg, 2, 4, b"START  BACK", Charset::Dark);
            }
        }
    }

    pub fn update(&mut self, input: &mut Input) {
        self.frame_counter = self.frame_counter.wrapping_add(1);
        self.fade.tick();

        #[cfg(feature = "capture")]
        self.capture_script();

        // The GBA has no entropy source, so seed from how long the player
        // took to press a button.
        if !self.seeded && input.just_pressed(Button::Start) {
            self.seeded = true;
            self.session = Session::new(self.frame_counter.wrapping_mul(2_654_435_761));
        }

        match self.screen {
            Screen::Title => {
                if input.just_pressed(Button::Start) || input.just_pressed(Button::A) {
                    self.enter(Screen::Demo);
                }
            }
            Screen::Demo => {
                if input.just_pressed(Button::A) {
                    self.session.apply(Cmd::Step);
                }
                if input.just_pressed(Button::B) {
                    self.session.apply(Cmd::Reset);
                }
                if input.just_pressed(Button::Start) {
                    self.enter(Screen::Title);
                }
            }
        }
    }

    pub fn render(&mut self, frame: &mut GraphicsFrame) {
        let bg_id = self.bg.show(frame);

        match self.screen {
            Screen::Title => {
                objtext::write_centred(frame, 120, 120, b"AGB-MV-TEMPLATE", Ink::Dim);
            }
            Screen::Demo => {
                objtext::write(frame, 16, 80, b"SCORE", Ink::Normal);
                NumberField::new(70, 80, 6).alt().show(frame, self.session.score);
            }
        }

        let darkness = self.fade.darkness();
        if darkness.to_raw() > 0 {
            frame.blend().darken(darkness).enable_background(bg_id);
        }
    }
}

impl Default for App {
    fn default() -> Self {
        App::new()
    }
}

/// A tour of every screen at fixed frames, so `make shots` can photograph
/// the game without a human holding the pad.
#[cfg(feature = "capture")]
impl App {
    fn capture_script(&mut self) {
        if self.frame_counter == 90 {
            self.enter(Screen::Demo);
        }
    }
}

fn fresh_background() -> RegularBackground {
    RegularBackground::new(
        Priority::P0,
        RegularBackgroundSize::Background32x32,
        backgrounds::PANEL.tiles.format(),
    )
}

pub fn run(mut gba: Gba) -> ! {
    let mut graphics = gba.graphics.get();
    graphics.set_background_palettes(backgrounds::PALETTES);

    let mut app = App::new();
    let mut input = Input::new();

    loop {
        input.update();
        app.update(&mut input);

        let mut frame = graphics.frame();
        app.render(&mut frame);
        // mixer.frame() goes here once there is audio, every frame or it skips.
        frame.commit();
    }
}
