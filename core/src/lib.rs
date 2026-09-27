//! Game logic.
//!
//! Nothing in here may depend on `agb` or on any platform detail. That is
//! what lets the whole rule set be tested natively in milliseconds:
//!
//!     cargo test -p game-core
//!
//! `no_std` in the real build; the test harness gets `std`.
#![cfg_attr(not(test), no_std)]

pub mod rng;
pub mod session;

pub use rng::Rng;
pub use session::{Cmd, Event, Session};
