//! Validate a built .gba: header checksum, magic byte and padding.
//!
//!     cargo run -p game-tools --bin romcheck -- game.gba
//!
//! Worth running in CI. A bad header is the difference between "works in my
//! emulator" and "black screen on the device", and it is invisible otherwise.

use std::process::ExitCode;

fn main() -> ExitCode {
    let Some(path) = std::env::args().nth(1) else {
        eprintln!("usage: romcheck <rom.gba>");
        return ExitCode::FAILURE;
    };
    let rom = match std::fs::read(&path) {
        Ok(rom) => rom,
        Err(e) => {
            eprintln!("romcheck: {path}: {e}");
            return ExitCode::FAILURE;
        }
    };
    if rom.len() < 0xC0 {
        eprintln!("romcheck: {path}: too short to hold a header");
        return ExitCode::FAILURE;
    }

    let mut problems = Vec::new();

    // Header checksum: complement check over 0xA0..=0xBC.
    let mut chk: u8 = 0;
    for b in &rom[0xA0..=0xBC] {
        chk = chk.wrapping_sub(*b);
    }
    chk = chk.wrapping_sub(0x19);
    if chk != rom[0xBD] {
        problems.push(format!(
            "header checksum is 0x{:02X}, expected 0x{chk:02X}",
            rom[0xBD]
        ));
    }

    if rom[0xB2] != 0x96 {
        problems.push(format!("fixed byte at 0xB2 is 0x{:02X}, must be 0x96", rom[0xB2]));
    }

    // The logo the hardware checks. Only its bounds are worth asserting here.
    if rom[4..8] != [0x24, 0xFF, 0xAE, 0x51] {
        problems.push("Nintendo logo header data is missing or corrupt".into());
    }

    let padded = rom.len().is_power_of_two();
    if !padded {
        problems.push(format!(
            "size {} is not a power of two -- pass --padding to agb-gbafix",
            rom.len()
        ));
    }

    let title = String::from_utf8_lossy(&rom[0xA0..0xAC]).replace('\0', "");
    println!("{path}: {} KB, title {title:?}", rom.len() / 1024);
    if problems.is_empty() {
        println!("  header ok, padded ok");
        ExitCode::SUCCESS
    } else {
        for p in &problems {
            println!("  PROBLEM: {p}");
        }
        ExitCode::FAILURE
    }
}
