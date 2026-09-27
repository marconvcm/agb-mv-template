//! A deterministic PRNG.
//!
//! The GBA has no entropy source. Seed from something the player influences
//! -- how many frames passed before the first button press is the usual
//! trick -- and store the state in the save file so resetting the console
//! cannot reroll an outcome the player did not like.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rng(u32);

impl Rng {
    /// Zero is the one state xorshift cannot escape, so it is replaced.
    pub fn new(seed: u32) -> Rng {
        Rng(if seed == 0 { 0x2545_F491 } else { seed })
    }

    pub fn state(self) -> u32 {
        self.0
    }

    pub fn next_u32(&mut self) -> u32 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        self.0 = x;
        x
    }

    /// Uniform in `0..n`, by rejection so there is no modulo bias.
    pub fn below(&mut self, n: u32) -> u32 {
        if n <= 1 {
            return 0;
        }
        let zone = u32::MAX - (u32::MAX % n) - 1;
        loop {
            let v = self.next_u32();
            if v <= zone {
                return v % n;
            }
        }
    }
}

impl Default for Rng {
    fn default() -> Self {
        Rng::new(0x2545_F491)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_deterministic_for_a_given_seed() {
        let (mut a, mut b) = (Rng::new(12345), Rng::new(12345));
        for _ in 0..100 {
            assert_eq!(a.next_u32(), b.next_u32());
        }
    }

    #[test]
    fn below_stays_in_range_and_covers_it() {
        let mut r = Rng::new(7);
        let mut seen = [false; 6];
        for _ in 0..10_000 {
            let v = r.below(6);
            assert!(v < 6);
            seen[v as usize] = true;
        }
        assert!(seen.iter().all(|&s| s));
    }

    #[test]
    fn zero_seed_does_not_stick() {
        let mut r = Rng::new(0);
        assert_ne!(r.next_u32(), 0);
    }
}
