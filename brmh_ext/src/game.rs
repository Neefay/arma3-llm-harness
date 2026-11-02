//! The engine's "Game Functions" (Arma 3 2.18+): exports of the game executable, found with
//! `GetProcAddress(GetModuleHandle(NULL), name)`. The graphics ones exist only in the client exe.
//!
//! `RVExtensionGData` is a DATA export (it lives in `.data`): a pointer to
//! `{ID3D11Device*, ID3D11DeviceContext*}`, not a function.

use std::ffi::{CString, c_void};

use windows::Win32::Graphics::Direct3D11::{ID3D11Device, ID3D11DeviceContext};
use windows::Win32::Graphics::Dxgi::IDXGIDevice;
use windows::Win32::System::LibraryLoader::{GetModuleHandleW, GetProcAddress};
use windows::core::{Interface, PCSTR};

/// Address of a game export, if this executable has it.
pub fn rv_fn(name: &str) -> Option<usize> {
    let c = CString::new(name).ok()?;
    unsafe {
        let module = GetModuleHandleW(None).ok()?;
        GetProcAddress(module, PCSTR(c.as_ptr().cast())).map(|f| f as usize)
    }
}

#[repr(C)]
struct RenderInfo {
    device: *mut c_void,
    context: *mut c_void,
}

#[repr(C)]
struct LockGuardVtbl {
    release_lock: unsafe extern "system" fn(*mut LockGuard),
}

#[repr(C)]
struct LockGuard {
    vtbl: *const LockGuardVtbl,
}

/// RAII wrapper over `RVExtensionGLock`. Forgetting to release it freezes the game.
pub struct GfxLock(*mut LockGuard);

impl GfxLock {
    pub fn acquire() -> Result<Self, String> {
        let f = rv_fn("RVExtensionGLock").ok_or("RVExtensionGLock missing (server exe?)")?;
        let f: unsafe extern "system" fn() -> *mut LockGuard = unsafe { std::mem::transmute(f) };
        let guard = unsafe { f() };
        if guard.is_null() {
            return Err("RVExtensionGLock returned null".into());
        }
        Ok(Self(guard))
    }
}

impl Drop for GfxLock {
    fn drop(&mut self) {
        unsafe { ((*(*self.0).vtbl).release_lock)(self.0) };
    }
}

/// The game's D3D11 device and immediate context (AddRef'd clones).
pub fn d3d() -> Result<(ID3D11Device, ID3D11DeviceContext), String> {
    let addr = rv_fn("RVExtensionGData").ok_or("RVExtensionGData missing (server exe?)")?;
    let info = unsafe { *(addr as *const *const RenderInfo) };
    if info.is_null() {
        return Err("RVExtensionGData not initialised (no renderer?)".into());
    }
    let (dev, ctx) = unsafe { ((*info).device, (*info).context) };
    let dev = unsafe { ID3D11Device::from_raw_borrowed(&dev) }.ok_or("null device")?.clone();
    let ctx = unsafe { ID3D11DeviceContext::from_raw_borrowed(&ctx) }.ok_or("null context")?.clone();
    Ok((dev, ctx))
}

/// `gfx:info`: which game functions this exe exports, plus the device's adapter and feature level.
pub fn info() -> Vec<Vec<String>> {
    let mut out: Vec<Vec<String>> = [
        "RVExtensionGData",
        "RVExtensionGLock",
        "RVExtensionGGetR2TTexture",
        "RVGetProjectionViewTransform",
        "RVExtensionCallback",
        "RVExtensionRequestContext",
    ]
    .into_iter()
    .map(|name| vec![name.to_string(), rv_fn(name).is_some().to_string()])
    .collect();
    match d3d() {
        Ok((dev, _)) => {
            let adapter = dev
                .cast::<IDXGIDevice>()
                .and_then(|d| unsafe { d.GetAdapter() })
                .and_then(|a| unsafe { a.GetDesc() })
                .map(|d| String::from_utf16_lossy(&d.Description).trim_end_matches('\0').to_string())
                .unwrap_or_else(|e| format!("unknown ({e})"));
            out.push(vec!["adapter".into(), adapter]);
            out.push(vec!["feature_level".into(), format!("{:#x}", unsafe { dev.GetFeatureLevel() }.0)]);
        }
        Err(e) => out.push(vec!["d3d".into(), e]),
    }
    out
}
