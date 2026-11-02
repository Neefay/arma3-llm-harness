//! Terrain export via the engine's exported `ExportSVG` (the implementation behind the diag-exe-only
//! `diag_exportTerrainSVG`). Exported by both arma3_x64.exe and arma3server_x64.exe as the MSVC-mangled
//! `?ExportSVG@@YAXPEBD_N11111@Z` = `void ExportSVG(const char*, bool, bool, bool, bool, bool, bool)`.

use std::ffi::CString;

use windows::Win32::System::LibraryLoader::{GetModuleHandleW, GetProcAddress};
use windows::core::PCSTR;

type ExportSvgFn = unsafe extern "C" fn(*const std::ffi::c_char, bool, bool, bool, bool, bool, bool);

const MANGLED: &[u8] = b"?ExportSVG@@YAXPEBD_N11111@Z\0";

/// `map:svg [path, locationNames, grid, contours, trees, heightPoints, simpleRoads]` -> [path, bytes, ms]
pub fn export_svg(
    path: String,
    names: bool,
    grid: bool,
    contours: bool,
    trees: bool,
    heights: bool,
    simple_roads: bool,
) -> Result<Vec<String>, String> {
    let f = unsafe {
        let m = GetModuleHandleW(None).map_err(|e| e.to_string())?;
        GetProcAddress(m, PCSTR(MANGLED.as_ptr())).ok_or("ExportSVG not exported by this exe")?
    };
    let f: ExportSvgFn = unsafe { std::mem::transmute(f) };
    if let Some(dir) = std::path::Path::new(&path).parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let c = CString::new(path.clone()).map_err(|e| e.to_string())?;
    let t0 = std::time::Instant::now();
    unsafe { f(c.as_ptr(), names, grid, contours, trees, heights, simple_roads) };
    let ms = t0.elapsed().as_secs_f64() * 1000.0;
    let bytes = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
    crate::log::line(&format!("map:svg {path} {bytes} bytes {ms:.0} ms"));
    Ok(vec![path, bytes.to_string(), format!("{ms:.0}")])
}
