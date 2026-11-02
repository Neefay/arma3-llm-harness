//! arma-harness game extension (`"brmh" callExtension ...`, loaded as `brmh_x64.dll` from `@brmh`).
//!
//! Commands:
//! - `ping [text]` -> `pong:text` (the probe uses it to report whether the extension is loaded).
//! - `gfx:frame [path, delay_frames, max_width]`: in-engine screenshot, GUI included; result as
//!   ExtensionCallback ("brmh", "frame_done", [ok, path, w, h, ms, luma]). Client exe only.
//! - `gfx:info`, `gfx:status`, `gfx:hook`, `gfx:unhook`: capture plumbing.
//! - `map:svg [path, names, grid, contours, trees, heights, simpleRoads]`: terrain export (any exe).
//! - `diag:*`: diagnostics and experiments, see `diag.rs`.

use arma_rs::{Extension, Group, arma};

pub mod capture;
pub mod diag;
pub mod game;
pub mod image;
pub mod log;
pub mod map;

#[arma]
fn init() -> Extension {
    log::line(concat!("brmh ", env!("CARGO_PKG_VERSION"), " loaded"));
    Extension::build()
        .version(env!("CARGO_PKG_VERSION").to_string())
        .command("ping", ping)
        .group(
            "gfx",
            Group::new()
                .command("frame", capture::frame)
                .command("info", game::info)
                .command("status", capture::status)
                .command("hook", capture::hook)
                .command("unhook", capture::unhook),
        )
        .group("map", Group::new().command("svg", map::export_svg))
        .group(
            "diag",
            Group::new()
                .command("ctx", diag::ctx)
                .command("burst", diag::burst)
                .command("r2t", diag::r2t)
                .command("r2t_list", diag::r2t_list),
        )
        .finish()
}

fn ping(text: String) -> String {
    format!("pong:{text}")
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::time::Duration;

    use super::*;

    #[test]
    fn ping_roundtrip() {
        let ext = init().testing();
        let (out, code) = ext.call("ping", Some(vec!["\"hi\"".to_string()]));
        assert_eq!((out.as_str(), code), ("pong:hi", 0));
    }

    #[test]
    fn burst_pushes_callbacks_from_a_thread() {
        let ext = init().testing();
        let (out, code) = ext.call("diag:burst", Some(vec!["3".into(), "0".into()]));
        assert_eq!((out.as_str(), code), ("started", 0));
        let seen = AtomicU32::new(0);
        let res = ext.callback_handler(
            |name, func, _data| {
                assert_eq!((name, func), ("brmh", "burst"));
                if seen.fetch_add(1, Ordering::Relaxed) + 1 == 3 {
                    arma_rs::Result::Ok(())
                } else {
                    arma_rs::Result::Continue
                }
            },
            Duration::from_secs(2),
        );
        assert!(matches!(res, arma_rs::Result::<(), ()>::Ok(())), "expected 3 callbacks");
    }

    #[test]
    fn unknown_command_is_reported() {
        let ext = init().testing();
        let (_, code) = ext.call("gfx:nope", Some(vec![]));
        assert_ne!(code, 0);
    }
}
