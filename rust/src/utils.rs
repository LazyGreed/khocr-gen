//! Shared utilities for the khocr-gen Rust acceleration backend.
//!
//! Image helpers, border estimation, kernel normalisation, and numpy
//! array conversions used across augmentation, rendering, and font modules.

use numpy::ndarray::ArrayView2;
use rayon::prelude::*;

// ── Background estimation ────────────────────────────────────────────────

/// Estimate the background colour from image border pixels (median of edges).
pub fn estimate_bg_gray(img: ArrayView2<'_, u8>) -> u8 {
    let h = img.nrows();
    let w = img.ncols();
    if h == 0 || w == 0 {
        return 255;
    }

    let mut samples: Vec<u8> = Vec::with_capacity((h + w) * 2);
    // Top and bottom rows
    for &pixel in img.row(0).iter() {
        samples.push(pixel);
    }
    for &pixel in img.row(h.saturating_sub(1)).iter() {
        samples.push(pixel);
    }
    // Left and right columns (excluding corners already sampled)
    for row in 1..h.saturating_sub(1) {
        samples.push(img[(row, 0)]);
        samples.push(img[(row, w.saturating_sub(1))]);
    }

    samples.sort_unstable();
    let mid = samples.len() / 2;
    if samples.len() % 2 == 0 {
        ((samples[mid - 1] as u16 + samples[mid] as u16) / 2) as u8
    } else {
        samples[mid]
    }
}

// ── Kernel normalisation ──────────────────────────────────────────────────

/// Normalise an odd kernel size to the nearest odd value >= `minimum`.
pub fn normalize_odd_kernel_limit(value: i32, minimum: i32) -> u32 {
    let limit = value.max(minimum) as u32;
    if limit % 2 == 0 {
        limit + 1
    } else {
        limit
    }
}

// ── Clamp helpers ─────────────────────────────────────────────────────────

#[inline]
pub fn clamp_f32_to_u8(v: f32) -> u8 {
    if v <= 0.0 {
        0
    } else if v >= 255.0 {
        255
    } else {
        v as u8
    }
}

#[inline]
pub fn clamp_u8(v: i32) -> u8 {
    if v <= 0 {
        0
    } else if v >= 255 {
        255
    } else {
        v as u8
    }
}

// ── Image blank check ─────────────────────────────────────────────────────

/// Check if an image is blank (too few dark pixels).
pub fn image_is_blank(img: ArrayView2<'_, u8>, threshold: u8, min_ratio: f32) -> bool {
    let total = (img.nrows() * img.ncols()) as f32;
    if total < 1.0 {
        return true;
    }
    let dark_count: usize = img.iter().filter(|&&p| p < threshold).count();
    (dark_count as f32 / total) < min_ratio
}

// ── Downscale helper ──────────────────────────────────────────────────────

/// Downscale an 8-bit grayscale image using box (area) filtering.
/// Returns a new buffer of `(new_h, new_w)`.
pub fn downscale_gray(img: &[u8], w: usize, h: usize, new_w: usize, new_h: usize) -> Vec<u8> {
    let mut out = vec![0u8; new_w * new_h];
    let x_ratio = w as f64 / new_w as f64;
    let y_ratio = h as f64 / new_h as f64;

    out.par_chunks_mut(new_w).enumerate().for_each(|(dy, row)| {
        let y_start = (dy as f64 * y_ratio) as usize;
        let y_end = ((dy + 1) as f64 * y_ratio).ceil() as usize;
        let y_end = y_end.min(h);

        for dx in 0..new_w {
            let x_start = (dx as f64 * x_ratio) as usize;
            let x_end = ((dx + 1) as f64 * x_ratio).ceil() as usize;
            let x_end = x_end.min(w);

            let mut sum: u32 = 0;
            let mut count: u32 = 0;
            for py in y_start..y_end {
                for px in x_start..x_end {
                    sum += img[py * w + px] as u32;
                    count += 1;
                }
            }
            row[dx] = if count > 0 {
                (sum / count) as u8
            } else {
                0
            };
        }
    });
    out
}
