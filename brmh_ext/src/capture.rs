//! In-engine frame capture: the presented back buffer, GUI included.
//!
//! The game's swap chain is not reachable through the extension API, so we hook `Present` and
//! `Present1` in DXGI's swap chain vtable. The vtable is found through a throwaway device and swap
//! chain on a hidden window: every swap chain from dxgi.dll shares it. A capture request is served
//! on the render thread inside the next due `Present`; PNG encoding runs on a worker thread and the
//! result is pushed to SQF through `ExtensionCallback` ("brmh", "frame_done", [...]).

use std::ffi::c_void;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::time::Instant;

use arma_rs::Context;
use windows::Win32::Foundation::HWND;
use windows::Win32::Graphics::Direct3D::{D3D_DRIVER_TYPE_HARDWARE, D3D_FEATURE_LEVEL_11_0};
use windows::Win32::Graphics::Direct3D11::*;
use windows::Win32::Graphics::Dxgi::Common::*;
use windows::Win32::Graphics::Dxgi::*;
use windows::Win32::System::Memory::{PAGE_PROTECTION_FLAGS, PAGE_READWRITE, VirtualProtect};
use windows::Win32::UI::WindowsAndMessaging::{CreateWindowExW, DestroyWindow, WINDOW_EX_STYLE, WS_OVERLAPPED};
use windows::core::{Interface, w};

use crate::game::rv_fn;
use crate::image::{Frame, convert_row, downscale, mean_luma, write_png};
use crate::log;

/// Copies a GPU texture to CPU memory as RGB8. The caller must hold the game's graphics lock or be
/// on the render thread (inside `Present`).
pub(crate) fn readback(dev: &ID3D11Device, ctx: &ID3D11DeviceContext, tex: &ID3D11Texture2D) -> Result<Frame, String> {
    let mut desc = D3D11_TEXTURE2D_DESC::default();
    unsafe { tex.GetDesc(&mut desc) };
    let mut src = tex.clone();
    if desc.SampleDesc.Count > 1 {
        let mut rd = desc;
        rd.SampleDesc = DXGI_SAMPLE_DESC { Count: 1, Quality: 0 };
        rd.BindFlags = 0;
        rd.CPUAccessFlags = 0;
        rd.MiscFlags = 0;
        let mut resolved = None;
        unsafe { dev.CreateTexture2D(&rd, None, Some(&mut resolved)) }.map_err(|e| format!("resolve texture: {e}"))?;
        let resolved: ID3D11Texture2D = resolved.ok_or("resolve texture: null")?;
        unsafe { ctx.ResolveSubresource(&resolved, 0, &src, 0, desc.Format) };
        src = resolved;
    }
    let mut sd = desc;
    sd.SampleDesc = DXGI_SAMPLE_DESC { Count: 1, Quality: 0 };
    sd.Usage = D3D11_USAGE_STAGING;
    sd.BindFlags = 0;
    sd.CPUAccessFlags = D3D11_CPU_ACCESS_READ.0 as u32;
    sd.MiscFlags = 0;
    sd.MipLevels = 1;
    sd.ArraySize = 1;
    let mut staging = None;
    unsafe { dev.CreateTexture2D(&sd, None, Some(&mut staging)) }.map_err(|e| format!("staging texture: {e}"))?;
    let staging: ID3D11Texture2D = staging.ok_or("staging texture: null")?;
    if desc.MipLevels == 1 && desc.ArraySize == 1 {
        unsafe { ctx.CopyResource(&staging, &src) };
    } else {
        unsafe { ctx.CopySubresourceRegion(&staging, 0, 0, 0, 0, &src, 0, None) };
    }
    let mut mapped = D3D11_MAPPED_SUBRESOURCE::default();
    unsafe { ctx.Map(&staging, 0, D3D11_MAP_READ, 0, Some(&mut mapped)) }.map_err(|e| format!("map: {e}"))?;
    let (w, h, pitch) = (desc.Width as usize, desc.Height as usize, mapped.RowPitch as usize);
    let mut rgb = Vec::with_capacity(w * h * 3);
    let converted = (0..h).try_for_each(|y| {
        let row = unsafe { std::slice::from_raw_parts((mapped.pData as *const u8).add(y * pitch), pitch) };
        convert_row(desc.Format, row, w, &mut rgb)
    });
    unsafe { ctx.Unmap(&staging, 0) };
    converted?;
    Ok(Frame { width: desc.Width, height: desc.Height, rgb })
}

/// Downscales and encodes on a worker thread, then reports through ExtensionCallback:
/// `[ok, path_or_error, width, height, ms, mean_luma]`.
pub(crate) fn finish_async(
    ctx: Context,
    func: &'static str,
    path: String,
    frame: Result<Frame, String>,
    t0: Instant,
    max_width: u32,
) {
    std::thread::spawn(move || {
        let encoded = frame.map(|f| downscale(f, max_width)).and_then(|f| write_png(&path, &f).map(|()| f));
        let (ok, msg, w, h, luma) = match encoded {
            Ok(f) => (true, path.clone(), f.width, f.height, mean_luma(&f)),
            Err(e) => {
                set_error(&e);
                (false, e, 0, 0, 0.0)
            }
        };
        let ms = t0.elapsed().as_secs_f64() * 1000.0;
        log::line(&format!("{func}: ok={ok} {msg} {w}x{h} luma={luma:.1} {ms:.1}ms"));
        let data = vec![ok.to_string(), msg, w.to_string(), h.to_string(), format!("{ms:.1}"), format!("{luma:.1}")];
        if let Err(e) = ctx.callback_data("brmh", func, data) {
            log::line(&format!("{func}: callback failed: {e}"));
        }
    });
}

type PresentFn = unsafe extern "system" fn(*mut c_void, u32, u32) -> i32;
type Present1Fn = unsafe extern "system" fn(*mut c_void, u32, u32, *const c_void) -> i32;

const VT_PRESENT: usize = 8;
const VT_PRESENT1: usize = 22;

static VTABLE: AtomicUsize = AtomicUsize::new(0);
static ORIG_PRESENT: AtomicUsize = AtomicUsize::new(0);
static ORIG_PRESENT1: AtomicUsize = AtomicUsize::new(0);
static HOOKED: AtomicBool = AtomicBool::new(false);
static PRESENTS: AtomicU64 = AtomicU64::new(0);
static LAST_ERROR: Mutex<String> = Mutex::new(String::new());

fn set_error(e: &str) {
    if let Ok(mut last) = LAST_ERROR.lock() {
        *last = e.to_string();
    }
}

struct FrameRequest {
    ctx: Context,
    path: String,
    t0: Instant,
    /// Captured at the first `Present` whose ordinal is >= `due` (lets a camera switch render first).
    due: u64,
    max_width: u32,
}

static PENDING: Mutex<Option<FrameRequest>> = Mutex::new(None);

fn on_present(swapchain: *mut c_void, flags: u32) {
    let n = PRESENTS.fetch_add(1, Ordering::Relaxed) + 1;
    if flags & DXGI_PRESENT_TEST.0 != 0 {
        return;
    }
    // try_lock: never block the render thread on a capture request being written.
    let request = match PENDING.try_lock() {
        Ok(mut pending) if pending.as_ref().is_some_and(|r| n >= r.due) => pending.take(),
        _ => None,
    };
    let Some(request) = request else { return };
    let frame = (|| {
        let sc = unsafe { IDXGISwapChain::from_raw_borrowed(&swapchain) }.ok_or("null swap chain")?;
        let tex: ID3D11Texture2D = unsafe { sc.GetBuffer(0) }.map_err(|e| format!("GetBuffer: {e}"))?;
        let dev: ID3D11Device = unsafe { sc.GetDevice() }.map_err(|e| format!("GetDevice: {e}"))?;
        let ctx = unsafe { dev.GetImmediateContext() }.map_err(|e| format!("GetImmediateContext: {e}"))?;
        readback(&dev, &ctx, &tex)
    })();
    finish_async(request.ctx, "frame_done", request.path, frame, request.t0, request.max_width);
}

unsafe extern "system" fn hooked_present(this: *mut c_void, sync: u32, flags: u32) -> i32 {
    let _ = catch_unwind(AssertUnwindSafe(|| on_present(this, flags)));
    let orig: PresentFn = unsafe { std::mem::transmute(ORIG_PRESENT.load(Ordering::Acquire)) };
    unsafe { orig(this, sync, flags) }
}

unsafe extern "system" fn hooked_present1(this: *mut c_void, sync: u32, flags: u32, params: *const c_void) -> i32 {
    let _ = catch_unwind(AssertUnwindSafe(|| on_present(this, flags)));
    let orig: Present1Fn = unsafe { std::mem::transmute(ORIG_PRESENT1.load(Ordering::Acquire)) };
    unsafe { orig(this, sync, flags, params) }
}

/// DXGI's swap chain vtable, read from a throwaway device and swap chain on a hidden window.
fn swapchain_vtable() -> Result<usize, String> {
    unsafe {
        let hwnd: HWND = CreateWindowExW(
            WINDOW_EX_STYLE(0),
            w!("STATIC"),
            w!("brmh-dummy"),
            WS_OVERLAPPED,
            0,
            0,
            8,
            8,
            None,
            None,
            None,
            None,
        )
        .map_err(|e| format!("CreateWindowExW: {e}"))?;
        let desc = DXGI_SWAP_CHAIN_DESC {
            BufferDesc: DXGI_MODE_DESC {
                Width: 8,
                Height: 8,
                Format: DXGI_FORMAT_R8G8B8A8_UNORM,
                ..Default::default()
            },
            SampleDesc: DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
            BufferUsage: DXGI_USAGE_RENDER_TARGET_OUTPUT,
            BufferCount: 1,
            OutputWindow: hwnd,
            Windowed: true.into(),
            SwapEffect: DXGI_SWAP_EFFECT_DISCARD,
            Flags: 0,
        };
        let mut sc: Option<IDXGISwapChain> = None;
        let mut dev: Option<ID3D11Device> = None;
        let created = D3D11CreateDeviceAndSwapChain(
            None,
            D3D_DRIVER_TYPE_HARDWARE,
            Default::default(),
            D3D11_CREATE_DEVICE_FLAG(0),
            Some(&[D3D_FEATURE_LEVEL_11_0]),
            D3D11_SDK_VERSION,
            Some(&desc),
            Some(&mut sc),
            Some(&mut dev),
            None,
            None,
        );
        let vtable = match (&created, &sc) {
            (Ok(()), Some(sc)) => Ok(*(sc.as_raw() as *const usize)),
            _ => Err(format!("dummy swap chain: {created:?}")),
        };
        drop(sc);
        drop(dev);
        let _ = DestroyWindow(hwnd);
        vtable
    }
}

/// Swaps one vtable slot, returning the previous value.
unsafe fn patch_slot(vtable: usize, index: usize, value: usize) -> Result<usize, String> {
    let slot = (vtable + index * size_of::<usize>()) as *mut usize;
    let mut old = PAGE_PROTECTION_FLAGS(0);
    unsafe {
        VirtualProtect(slot.cast(), size_of::<usize>(), PAGE_READWRITE, &mut old)
            .map_err(|e| format!("VirtualProtect: {e}"))?;
        let previous = slot.read();
        slot.write(value);
        let _ = VirtualProtect(slot.cast(), size_of::<usize>(), old, &mut PAGE_PROTECTION_FLAGS(0));
        Ok(previous)
    }
}

/// `gfx:hook`: install the Present/Present1 hook (idempotent; `gfx:frame` does it on demand).
pub fn hook() -> Result<String, String> {
    if HOOKED.load(Ordering::Acquire) {
        return Ok("already hooked".into());
    }
    rv_fn("RVExtensionGData").ok_or("this executable does not render (dedicated server or headless client)")?;
    let vt = swapchain_vtable()?;
    unsafe {
        ORIG_PRESENT.store(patch_slot(vt, VT_PRESENT, hooked_present as PresentFn as usize)?, Ordering::Release);
        ORIG_PRESENT1.store(patch_slot(vt, VT_PRESENT1, hooked_present1 as Present1Fn as usize)?, Ordering::Release);
    }
    VTABLE.store(vt, Ordering::Release);
    HOOKED.store(true, Ordering::Release);
    log::line(&format!("hooked swap chain vtable {vt:#x}"));
    Ok(format!("hooked vtable {vt:#x}"))
}

/// `gfx:unhook`: restore the original vtable entries.
pub fn unhook() -> Result<String, String> {
    if !HOOKED.swap(false, Ordering::AcqRel) {
        return Ok("not hooked".into());
    }
    let vt = VTABLE.load(Ordering::Acquire);
    unsafe {
        patch_slot(vt, VT_PRESENT, ORIG_PRESENT.load(Ordering::Acquire))?;
        patch_slot(vt, VT_PRESENT1, ORIG_PRESENT1.load(Ordering::Acquire))?;
    }
    Ok("unhooked".into())
}

/// `gfx:frame [path, delay_frames, max_width]`: capture a presented frame after `delay_frames`
/// presents, downscaled to `max_width` (0 = native). The result arrives as callback "frame_done".
pub fn frame(ctx: Context, path: String, delay_frames: u32, max_width: u32) -> Result<String, String> {
    hook()?;
    let mut pending = PENDING.lock().map_err(|e| e.to_string())?;
    if pending.is_some() {
        return Err("a frame capture is already pending".into());
    }
    let due = PRESENTS.load(Ordering::Relaxed) + u64::from(delay_frames) + 1;
    *pending = Some(FrameRequest { ctx, path, t0: Instant::now(), due, max_width });
    Ok("queued".into())
}

/// `gfx:status` -> [hooked, presents seen, capture pending, last error]
pub fn status() -> Vec<String> {
    vec![
        HOOKED.load(Ordering::Relaxed).to_string(),
        PRESENTS.load(Ordering::Relaxed).to_string(),
        PENDING.lock().map(|p| p.is_some()).unwrap_or(false).to_string(),
        LAST_ERROR.lock().map(|e| e.clone()).unwrap_or_default(),
    ]
}
