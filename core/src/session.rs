//! The command/event shape that keeps game rules testable.
//!
//! The UI never mutates game state directly: it sends a [`Cmd`] and reads
//! back [`Event`]s. A test is then a script of commands with assertions on
//! the events, and rejected input carries a reason you can show the player
//! instead of leaving a button silently dead.
//!
//! Replace the placeholder command set with your game's.

use crate::rng::Rng;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Cmd {
    Step,
    Reset,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Reason {
    NothingToDo,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    Stepped { value: u32 },
    Reset,
    Rejected(Reason),
}

/// Commands produce a handful of events at most, so a fixed buffer keeps the
/// whole crate allocation-free.
const MAX_EVENTS: usize = 4;

#[derive(Debug, Clone, Copy, Default)]
pub struct Events {
    items: [Option<Event>; MAX_EVENTS],
    len: usize,
}

impl Events {
    pub fn push(&mut self, event: Event) {
        if self.len < MAX_EVENTS {
            self.items[self.len] = Some(event);
            self.len += 1;
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = Event> + '_ {
        self.items[..self.len].iter().flatten().copied()
    }

    pub fn contains(&self, event: Event) -> bool {
        self.iter().any(|e| e == event)
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }
}

#[derive(Debug, Clone)]
pub struct Session {
    pub score: u32,
    pub rng: Rng,
}

impl Session {
    pub fn new(seed: u32) -> Session {
        Session {
            score: 0,
            rng: Rng::new(seed),
        }
    }

    pub fn apply(&mut self, cmd: Cmd) -> Events {
        let mut events = Events::default();
        match cmd {
            Cmd::Step => {
                self.score = self.score.saturating_add(self.rng.below(10) + 1);
                events.push(Event::Stepped { value: self.score });
            }
            Cmd::Reset if self.score == 0 => events.push(Event::Rejected(Reason::NothingToDo)),
            Cmd::Reset => {
                self.score = 0;
                events.push(Event::Reset);
            }
        }
        events
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stepping_reports_the_new_score() {
        let mut s = Session::new(1);
        assert!(s.apply(Cmd::Step).iter().any(|e| matches!(e, Event::Stepped { .. })));
        assert!(s.score > 0);
    }

    #[test]
    fn resetting_an_untouched_session_is_rejected() {
        let mut s = Session::new(1);
        assert!(s.apply(Cmd::Reset).contains(Event::Rejected(Reason::NothingToDo)));
    }

    #[test]
    fn a_scripted_run_is_reproducible() {
        let run = |seed| {
            let mut s = Session::new(seed);
            for _ in 0..20 {
                s.apply(Cmd::Step);
            }
            s.score
        };
        assert_eq!(run(0xABCD), run(0xABCD));
    }
}
