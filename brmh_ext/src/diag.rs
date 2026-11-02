//! Diagnostics and experiments (`diag:*`). Not used by the harness itself.
//!
//! - `diag:ctx` reports what arma-rs parsed from the call context. On arma-rs 1.13 the steam id and
//!   remote-exec owner come back as pointer values (its `call_context/call.rs` casts the argument
//!   pointers instead of reading through them), so don't rely on them.
//! - `diag:burst` pushes callbacks from a background thread, to observe ExtensionCallback delivery.
//! - `diag:r2t` / `diag:r2t_list` use the documented `RVExtensionGGetR2TTexture` (2.22). On 2.22.154089
//!   it never reported a surface for scripted render-to-texture (UI pictures or object textures):
//!   the engine list it walks stayed empty. Kept to re-test on future builds.

use std::ffi::{CStr, CString, c_char, c_void};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use arma_rs::{CallContext, Context};
use windows::Win32::Graphics::Direct3D11::ID3D11Texture2D;
use windows::core::Interface;

use crate::capture::{finish_async, readback};
use crate::game::{GfxLock, d3d, rv_fn};
use crate::log;

/// `diag:ctx` -> [caller, source, mission, server, remote exec owner]
pub fn ctx(call: CallContext) -> Vec<String> {
    vec![
        call.caller().as_str(),
        call.source().as_str().to_string(),
        call.mission().as_str().to_string(),
        call.server().as_str().to_string(),
        call.remote_exec_owner().to_string(),
    ]
}

/// `diag:burst [count, delay_ms]`: push `count` callbacks ("brmh", "burst", [i, unix time]).
pub fn burst(ctx: Context, count: u32, delay_ms: u32) -> String {
    std::thread::spawn(move || {
        for i in 0..count {
            let sent = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0);
            if let Err(e) = ctx.callback_data("brmh", "burst", vec![i.to_string(), format!("{sent:.4}")]) {
                log::line(&format!("burst: callback failed: {e}"));
                break;
            }
            std::thread::sleep(Duration::from_millis(u64::from(delay_ms)));
        }
    });
    "started".to_string()
}

type R2TResultFn = unsafe extern "system" fn(
    *mut c_void,   // ID3D11Texture2D*
    *mut c_void,   // ID3D11ShaderResourceView*
    *mut c_void,   // ID3D11RenderTargetView*
    u32,           // width
    u32,           // height
    u32,           // last seen frame id
    *const c_char, // name
);
type R2TGetFn = unsafe extern "system" fn(*const c_char, R2TResultFn);

struct Surface {
    name: String,
    texture: Option<ID3D11Texture2D>,
    width: u32,
    height: u32,
    frame: u32,
}
// COM pointers handed over by the engine's callback; access is serialised by the mutex below.
unsafe impl Send for Surface {}

static SURFACES: Mutex<Vec<Surface>> = Mutex::new(Vec::new());

unsafe extern "system" fn on_surface(
    texture: *mut c_void,
    _srv: *mut c_void,
    _rtv: *mut c_void,
    width: u32,
    height: u32,
    frame: u32,
    name: *const c_char,
) {
    let name =
        if name.is_null() { String::new() } else { unsafe { CStr::from_ptr(name) }.to_string_lossy().into_owned() };
    let texture = unsafe { ID3D11Texture2D::from_raw_borrowed(&texture) }.cloned();
    if let Ok(mut surfaces) = SURFACES.lock() {
        surfaces.push(Surface { name, texture, width, height, frame });
    }
}

fn request(name: Option<&str>) -> Result<(), String> {
    let f = rv_fn("RVExtensionGGetR2TTexture").ok_or("RVExtensionGGetR2TTexture missing (needs a 2.22 client)")?;
    let f: R2TGetFn = unsafe { std::mem::transmute(f) };
    SURFACES.lock().map_err(|e| e.to_string())?.clear();
    let cname = name.map(|n| CString::new(n).unwrap_or_default());
    unsafe { f(cname.as_ref().map_or(std::ptr::null(), |c| c.as_ptr()), on_surface) };
    Ok(())
}

/// `diag:r2t_list` -> [[name, width, height, last seen frame], ...] reported synchronously.
pub fn r2t_list() -> Result<Vec<Vec<String>>, String> {
    request(None)?;
    Ok(SURFACES
        .lock()
        .map_err(|e| e.to_string())?
        .iter()
        .map(|s| vec![s.name.clone(), s.width.to_string(), s.height.to_string(), s.frame.to_string()])
        .collect())
}

/// `diag:r2t [name, path]`: read a named render-to-texture surface; result as callback "r2t_done".
pub fn r2t(ctx: Context, name: String, path: String) -> Result<String, String> {
    let t0 = Instant::now();
    request(Some(&name))?;
    std::thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(2);
        let surface = loop {
            let found = SURFACES.lock().ok().and_then(|mut s| s.pop());
            if found.is_some() || Instant::now() > deadline {
                break found;
            }
            std::thread::sleep(Duration::from_millis(5));
        };
        let frame = (|| {
            let surface = surface.ok_or_else(|| format!("no render-to-texture surface named '{name}'"))?;
            let texture = surface.texture.ok_or("null texture")?;
            let _lock = GfxLock::acquire()?;
            let (dev, dctx) = d3d()?;
            readback(&dev, &dctx, &texture)
        })();
        finish_async(ctx, "r2t_done", path, frame, t0, 0);
    });
    Ok("requested".into())
}
