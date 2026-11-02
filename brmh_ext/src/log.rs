//! Tiny append-only file log. The RPT is not reachable from Rust, and a plain file survives crashes.
//! Location: `$BRMH_LOG`, else `%LOCALAPPDATA%\arma-harness\logs\brmh_ext.log` (the harness home).

use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;

static LOCK: Mutex<()> = Mutex::new(());

fn path() -> PathBuf {
    if let Some(p) = std::env::var_os("BRMH_LOG") {
        return PathBuf::from(p);
    }
    let base = std::env::var_os("BRMH_HOME").map(PathBuf::from).unwrap_or_else(|| {
        std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir).join("arma-harness")
    });
    base.join("logs").join("brmh_ext.log")
}

pub fn line(msg: &str) {
    let _guard = LOCK.lock();
    let path = path();
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let t =
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0);
        let _ = writeln!(f, "{t:.3} [{}] {msg}", std::process::id());
    }
}
