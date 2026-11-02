//! CPU-side image handling: pixel format conversion, area downscaling, brightness, PNG encoding.
//! Pure functions (no GPU), so they are unit-tested.

use windows::Win32::Graphics::Dxgi::Common::*;

/// A tightly packed RGB8 image.
pub struct Frame {
    pub width: u32,
    pub height: u32,
    pub rgb: Vec<u8>,
}

pub fn half_to_f32(h: u16) -> f32 {
    let s = u32::from(h >> 15) << 31;
    let e = (h >> 10) & 0x1F;
    let m = u32::from(h & 0x3FF);
    let bits = match e {
        0 if m == 0 => s,
        0 => {
            // Subnormal: normalise the mantissa.
            let mut e2: i32 = 127 - 15 + 1;
            let mut m2 = m;
            while m2 & 0x400 == 0 {
                m2 <<= 1;
                e2 -= 1;
            }
            s | ((e2 as u32) << 23) | ((m2 & 0x3FF) << 13)
        }
        31 => s | 0x7F80_0000 | (m << 13),
        _ => s | ((u32::from(e) + 127 - 15) << 23) | (m << 13),
    };
    f32::from_bits(bits)
}

pub fn linear_to_srgb8(v: f32) -> u8 {
    let v = v.clamp(0.0, 1.0);
    let s = if v <= 0.003_130_8 { v * 12.92 } else { 1.055 * v.powf(1.0 / 2.4) - 0.055 };
    (s * 255.0 + 0.5) as u8
}

/// Appends one row of `width` pixels in `format` to `out` as RGB8.
pub fn convert_row(format: DXGI_FORMAT, row: &[u8], width: usize, out: &mut Vec<u8>) -> Result<(), String> {
    match format {
        DXGI_FORMAT_R8G8B8A8_UNORM | DXGI_FORMAT_R8G8B8A8_UNORM_SRGB | DXGI_FORMAT_R8G8B8A8_TYPELESS => {
            for px in row[..width * 4].as_chunks::<4>().0 {
                out.extend_from_slice(&px[..3]);
            }
        }
        DXGI_FORMAT_B8G8R8A8_UNORM
        | DXGI_FORMAT_B8G8R8A8_UNORM_SRGB
        | DXGI_FORMAT_B8G8R8X8_UNORM
        | DXGI_FORMAT_B8G8R8A8_TYPELESS => {
            for px in row[..width * 4].as_chunks::<4>().0 {
                out.extend_from_slice(&[px[2], px[1], px[0]]);
            }
        }
        DXGI_FORMAT_R10G10B10A2_UNORM | DXGI_FORMAT_R10G10B10A2_TYPELESS => {
            for px in row[..width * 4].as_chunks::<4>().0 {
                let v = u32::from_le_bytes(*px);
                let c = |shift: u32| (((v >> shift) & 0x3FF) >> 2) as u8;
                out.extend_from_slice(&[c(0), c(10), c(20)]);
            }
        }
        DXGI_FORMAT_R16G16B16A16_FLOAT => {
            for px in row[..width * 8].as_chunks::<8>().0 {
                let ch = |i: usize| linear_to_srgb8(half_to_f32(u16::from_le_bytes([px[i], px[i + 1]])));
                out.extend_from_slice(&[ch(0), ch(2), ch(4)]);
            }
        }
        other => return Err(format!("unsupported back buffer format {}", other.0)),
    }
    Ok(())
}

/// Area-average downscale so the width is at most `max_width` (0 = keep), preserving aspect.
pub fn downscale(frame: Frame, max_width: u32) -> Frame {
    if max_width == 0 || frame.width <= max_width {
        return frame;
    }
    let (sw, sh) = (frame.width as usize, frame.height as usize);
    let w = max_width as usize;
    let h = ((sh * w) / sw).max(1);
    let mut out = Vec::with_capacity(w * h * 3);
    for y in 0..h {
        let (y0, y1) = (y * sh / h, ((y + 1) * sh / h).max(y * sh / h + 1));
        for x in 0..w {
            let (x0, x1) = (x * sw / w, ((x + 1) * sw / w).max(x * sw / w + 1));
            let mut acc = [0u32; 3];
            for sy in y0..y1 {
                let row = &frame.rgb[(sy * sw + x0) * 3..(sy * sw + x1) * 3];
                for px in row.as_chunks::<3>().0 {
                    acc[0] += u32::from(px[0]);
                    acc[1] += u32::from(px[1]);
                    acc[2] += u32::from(px[2]);
                }
            }
            let n = ((y1 - y0) * (x1 - x0)) as u32;
            out.extend(acc.map(|c| (c / n) as u8));
        }
    }
    Frame { width: w as u32, height: h as u32, rgb: out }
}

/// Mean luma (0-255) over a sparse pixel sample. Near 0 means a black frame (loading screen,
/// transition), which callers should report instead of handing a blank image to a model.
pub fn mean_luma(frame: &Frame) -> f64 {
    let (sum, n) = frame.rgb.as_chunks::<3>().0.iter().step_by(97).fold((0.0, 0u32), |(s, n), p| {
        (s + 0.299 * f64::from(p[0]) + 0.587 * f64::from(p[1]) + 0.114 * f64::from(p[2]), n + 1)
    });
    if n == 0 { 0.0 } else { sum / f64::from(n) }
}

pub fn write_png(path: &str, frame: &Frame) -> Result<(), String> {
    if let Some(dir) = std::path::Path::new(path).parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let file = std::fs::File::create(path).map_err(|e| format!("create {path}: {e}"))?;
    let mut enc = png::Encoder::new(std::io::BufWriter::new(file), frame.width, frame.height);
    enc.set_color(png::ColorType::Rgb);
    enc.set_depth(png::BitDepth::Eight);
    enc.set_compression(png::Compression::Fast);
    let mut writer = enc.write_header().map_err(|e| e.to_string())?;
    writer.write_image_data(&frame.rgb).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(w: u32, h: u32, value: u8) -> Frame {
        Frame { width: w, height: h, rgb: vec![value; (w * h * 3) as usize] }
    }

    #[test]
    fn downscale_keeps_small_frames() {
        let f = downscale(frame(100, 50, 10), 200);
        assert_eq!((f.width, f.height), (100, 50));
    }

    #[test]
    fn downscale_hits_the_requested_width_and_averages() {
        let f = downscale(frame(1024, 768, 10), 800);
        assert_eq!((f.width, f.height), (800, 600));
        assert!(f.rgb.iter().all(|&v| v == 10));
        let mut big = frame(4, 2, 0);
        big.rgb[0] = 255;
        let small = downscale(big, 2);
        assert_eq!((small.width, small.height), (2, 1));
        assert_eq!(small.rgb[0], 255 / 4);
    }

    #[test]
    fn luma_detects_black_and_bright_frames() {
        assert!(mean_luma(&frame(64, 64, 0)) < 1.0);
        assert!(mean_luma(&frame(64, 64, 200)) > 150.0);
    }

    #[test]
    fn half_float_and_srgb() {
        assert_eq!(half_to_f32(0x3C00), 1.0);
        assert_eq!(half_to_f32(0xC000), -2.0);
        assert_eq!(linear_to_srgb8(1.0), 255);
        assert_eq!(linear_to_srgb8(0.0), 0);
    }

    #[test]
    fn convert_bgra_and_rgb10() {
        let mut out = Vec::new();
        convert_row(DXGI_FORMAT_B8G8R8A8_UNORM, &[1, 2, 3, 255, 4, 5, 6, 255], 2, &mut out).unwrap();
        assert_eq!(out, [3, 2, 1, 6, 5, 4]);
        out.clear();
        let white = u32::to_le_bytes(0x3FF | (0x3FF << 10) | (0x3FF << 20));
        convert_row(DXGI_FORMAT_R10G10B10A2_UNORM, &white, 1, &mut out).unwrap();
        assert_eq!(out, [255, 255, 255]);
        assert!(convert_row(DXGI_FORMAT_BC1_UNORM, &[0; 8], 1, &mut out).is_err());
    }
}
