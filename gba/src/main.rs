//! Game ROM entry point.
//!
//! Rules live in `game-core`, which knows nothing about the hardware and is
//! tested on the host. This crate is presentation only: input, graphics,
//! audio and save media.
#![no_std]
#![no_main]
#![cfg_attr(test, feature(custom_test_frameworks))]
#![cfg_attr(test, reexport_test_harness_main = "test_main")]
#![cfg_attr(test, test_runner(agb::test_runner::test_runner))]

extern crate alloc;

mod app;
// These two are the template's reusable toolkit rather than game code, so
// parts of them are unused until a game uses them. Everywhere else in the
// project, dead code should be deleted rather than silenced -- see
// AGENTS.md section 10.
#[allow(dead_code)]
mod gfx;
#[allow(dead_code)]
mod platform;

#[agb::entry]
fn main(gba: agb::Gba) -> ! {
    app::run(gba)
}
