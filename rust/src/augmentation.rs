//! Image augmentation methods — the hot-path acceleration target.
//!
//! Each method takes a grayscale (H×W) or RGB (H×W×3) `u8` image buffer and
//! an `intensity` in [0, 1]. All methods operate in-place or return a new
//! `Vec<u8>` with the same dimensions.
//!
//! The Python-side dispatching is handled in `lib.rs` via PyO3 wrappers.

use rand::Rng;
use rand_distr::Distribution;
use rayon::prelude::*;
use crate::utils::{clamp_f32_to_u8, normalize_odd_kernel_limit};

// ──────────────────────────────────────────────────────────────────────────────
// Sauvola local-threshold degradation
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_sauvola(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let total = w * h;
    if h < 3 || w < 3 {
        return img.to_vec();
    }

    // Determine window size
    let max_win = w.min(h);
    let max_win = if max_win % 2 == 0 { max_win - 1 } else { max_win };
    let window = 25usize.min(max_win).max(3);
    let window = if window % 2 == 0 { window - 1 } else { window };
    let half = window / 2;

    let k = 0.05 + intensity * 0.45;
    let r = 128.0f32;
    let alpha = 0.45 + intensity * 0.35;

    // Convert to f32 for processing
    let img_f32: Vec<f32> = img.iter().map(|&p| p as f32).collect();

    // Box-filtered mean using running sums
    let integral = {
        let mut integ = vec![0u64; (w + 1) * (h + 1)];
        for y in 0..h {
            let mut row_sum: u64 = 0;
            for x in 0..w {
                row_sum += img[y * w + x] as u64;
                integ[(y + 1) * (w + 1) + (x + 1)] =
                    integ[y * (w + 1) + (x + 1)] + row_sum;
            }
        }
        integ
    };

    let box_sum = |y1: usize, x1: usize, y2: usize, x2: usize| -> u64 {
        let a = integral[y1 * (w + 1) + x1];
        let b = integral[y2 * (w + 1) + x2];
        let c = integral[y1 * (w + 1) + x2];
        let d = integral[y2 * (w + 1) + x1];
        b + a - c - d
    };

    let mut mean = vec![0.0f32; total];
    let mut stddev = vec![0.0f32; total];

    // Parallel: each row writes to a distinct, non-overlapping slice.
    mean.par_chunks_mut(w)
        .zip(stddev.par_chunks_mut(w))
        .enumerate()
        .for_each(|(y, (mean_row, stddev_row))| {
            let y1 = y.saturating_sub(half);
            let y2 = (y + half + 1).min(h);
            let area_y = y2 - y1;
            for x in 0..w {
                let x1 = x.saturating_sub(half);
                let x2 = (x + half + 1).min(w);
                let area_x = x2 - x1;
                let area = (area_y * area_x) as f32;
                let sum = box_sum(y1, x1, y2, x2) as f32;
                let m = sum / area;
                mean_row[x] = m;

                // Variance via box filter on squared values
                let mut sq_sum: f64 = 0.0;
                for py in y1..y2 {
                    for px in x1..x2 {
                        let val = img_f32[py * w + px];
                        sq_sum += (val * val) as f64;
                    }
                }
                let sq_mean = sq_sum as f32 / area;
                let var = (sq_mean - m * m).max(0.0);
                stddev_row[x] = var.sqrt();
            }
        });

    let threshold_scale = 1.0 / r;
    let mut result = vec![0u8; total];
    result.par_iter_mut().enumerate().for_each(|(i, r)| {
        let threshold = mean[i] * (1.0 + k * (stddev[i] * threshold_scale - 1.0));
        let binary: f32 = if img_f32[i] > threshold { 255.0 } else { 0.0 };
        let degraded = img_f32[i] * (1.0 - alpha) + binary * alpha;
        *r = clamp_f32_to_u8(degraded);
    });

    result
}

// ──────────────────────────────────────────────────────────────────────────────
// 4-point perspective (geometric) warp
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_geo_warp(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    if h < 8 || w < 8 {
        return img.to_vec();
    }

    let radius = 0.5 + intensity * 11.5;
    let mut rng = rand::thread_rng();

    // Generate random destination corners
    let src: [[f32; 2]; 4] = [
        [0.0, 0.0],
        [w as f32 - 1.0, 0.0],
        [0.0, h as f32 - 1.0],
        [w as f32 - 1.0, h as f32 - 1.0],
    ];

    let mut dst = src;
    for corner in dst.iter_mut() {
        let dx = rng.gen_range(-radius..radius);
        let dy = rng.gen_range(-radius..radius);
        corner[0] = (corner[0] + dx).clamp(0.0, w as f32 - 1.0);
        corner[1] = (corner[1] + dy).clamp(0.0, h as f32 - 1.0);
    }

    // Estimate background from image border
    let bg = estimate_bg_gray_flat(img, w, h);

    // Compute perspective transform matrix using DLT
    let mat = compute_perspective_transform(&src, &dst);
    warp_perspective_gray(img, w, h, &mat, bg)
}

// ──────────────────────────────────────────────────────────────────────────────
// Vertical crop
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_vertical_crop(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    if h < 4 {
        return img.to_vec();
    }

    let crop_px = (1.0 + intensity * 7.0) as usize;
    let crop_px = crop_px.max(1).min(h - 1);
    let bg = estimate_bg_gray_flat(img, w, h);

    // Find rows with foreground content (pixels darker than bg-20)
    let fg_threshold = bg.saturating_sub(20);
    let fg_rows: Vec<usize> = (0..h)
        .filter(|&y| img[y * w..(y + 1) * w].iter().any(|&p| p < fg_threshold.max(1)))
        .collect();

    let mut rng = rand::thread_rng();
    let mut result = Vec::with_capacity(w * h);

    if rng.gen_bool(0.5) {
        // Crop from top
        let shift = if fg_rows.is_empty() {
            crop_px.min(h - 1)
        } else {
            (crop_px + fg_rows[0]).min(h - 1)
        };
        let pad: Vec<u8> = vec![bg; shift * w];
        result.extend_from_slice(&img[shift * w..]);
        result.extend_from_slice(&pad);
    } else {
        // Crop from bottom
        let bottom_margin = fg_rows.last().map_or(0, |&r| h - 1 - r);
        let shift = (crop_px + bottom_margin).min(h - 1);
        let cropped = &img[..(h - shift) * w];
        let pad: Vec<u8> = vec![bg; shift * w];
        result.extend_from_slice(&pad);
        result.extend_from_slice(cropped);
    }

    result
}

// ──────────────────────────────────────────────────────────────────────────────
// Gaussian blur (OpenCV-free fallback)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_blur(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let kernel = normalize_odd_kernel_limit((3.0 + intensity * 12.0) as i32, 3) as usize;
    gaussian_blur_gray(img, w, h, kernel)
}

/// Separable Gaussian blur for grayscale images.
fn gaussian_blur_gray(img: &[u8], w: usize, h: usize, kernel_size: usize) -> Vec<u8> {
    let half = kernel_size / 2;
    let sigma = kernel_size as f32 / 6.0;
    let mut kernel: Vec<f32> = (0..kernel_size)
        .map(|i| {
            let x = i as f32 - half as f32;
            (-x * x / (2.0 * sigma * sigma)).exp()
        })
        .collect();
    let ksum: f32 = kernel.iter().sum();
    for k in kernel.iter_mut() {
        *k /= ksum;
    }

    let mut tmp = vec![0.0f32; w * h];

    // Horizontal pass — parallelize over rows
    tmp.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        for x in 0..w {
            let mut sum = 0.0f32;
            let mut weight = 0.0f32;
            for (ki, kv) in kernel.iter().enumerate() {
                let sx = (x + ki).saturating_sub(half);
                if sx < w {
                    sum += img[y * w + sx] as f32 * kv;
                    weight += kv;
                }
            }
            row[x] = if weight > 0.0 {
                sum / weight
            } else {
                img[y * w + x] as f32
            };
        }
    });

    // Vertical pass — parallelize over columns
    let mut result = vec![0u8; w * h];
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        for x in 0..w {
            let mut sum = 0.0f32;
            let mut weight = 0.0f32;
            for (ki, kv) in kernel.iter().enumerate() {
                let sy = (y + ki).saturating_sub(half);
                if sy < h {
                    sum += tmp[sy * w + x] * kv;
                    weight += kv;
                }
            }
            row[x] = if weight > 0.0 {
                clamp_f32_to_u8(sum / weight)
            } else {
                img[y * w + x]
            };
        }
    });

    result
}

// ──────────────────────────────────────────────────────────────────────────────
// Salt-and-pepper noise
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_salt_pepper(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let density = 0.001 + intensity * 0.039;
    let total_pixels = w * h;
    let n_noise = ((total_pixels as f32 * density) as usize).max(1);

    let mut result = img.to_vec();
    let mut rng = rand::thread_rng();

    let half = n_noise / 2;
    // Salt (white pixels)
    for _ in 0..half {
        let idx = rng.gen_range(0..total_pixels);
        result[idx] = 255;
    }
    // Pepper (black pixels)
    for _ in 0..half {
        let idx = rng.gen_range(0..total_pixels);
        result[idx] = 0;
    }

    result
}

// ──────────────────────────────────────────────────────────────────────────────
// JPEG compression artifacts
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_jpeg_compression(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    use image::codecs::jpeg::JpegEncoder;
    use image::ImageEncoder;
    use std::io::Cursor;

    let quality = (95.0 - intensity * 70.0).max(5.0) as u8;

    let mut jpeg_buf = Vec::new();
    {
        let cursor = Cursor::new(&mut jpeg_buf);
        let encoder = JpegEncoder::new_with_quality(cursor, quality);
        if encoder.write_image(img, w as u32, h as u32, image::ExtendedColorType::L8).is_err() {
            return img.to_vec();
        }
    }

    let decoded = image::load_from_memory(&jpeg_buf);
    match decoded {
        Ok(dynamic) => dynamic.into_luma8().into_raw(),
        Err(_) => img.to_vec(),
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Random rotation
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_rotation(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let mut rng = rand::thread_rng();
    let max_angle = 0.5 + intensity * 7.5;
    let angle: f32 = rng.gen_range(-max_angle..max_angle);

    if angle.abs() < 0.01 {
        return img.to_vec();
    }

    let bg = estimate_bg_gray_flat(img, w, h);
    let angle_rad = angle.to_radians();
    let cx = w as f32 / 2.0;
    let cy = h as f32 / 2.0;

    let cos_a = angle_rad.cos();
    let sin_a = angle_rad.sin();

    let mut result = vec![bg; w * h];
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        for x in 0..w {
            // Inverse transform: find source pixel
            let dx = x as f32 - cx;
            let dy = y as f32 - cy;
            let sx = cos_a * dx + sin_a * dy + cx;
            let sy = -sin_a * dx + cos_a * dy + cy;

            if sx >= 0.0 && sx < w as f32 - 1.0 && sy >= 0.0 && sy < h as f32 - 1.0 {
                let fx = sx.fract();
                let fy = sy.fract();
                let ix = sx as usize;
                let iy = sy as usize;
                let ix1 = (ix + 1).min(w - 1);
                let iy1 = (iy + 1).min(h - 1);

                // Bilinear interpolation
                let a = img[iy * w + ix] as f32;
                let b = img[iy * w + ix1] as f32;
                let c = img[iy1 * w + ix] as f32;
                let d = img[iy1 * w + ix1] as f32;
                let val = (1.0 - fy) * ((1.0 - fx) * a + fx * b)
                    + fy * ((1.0 - fx) * c + fx * d);
                row[x] = clamp_f32_to_u8(val);
            }
        }
    });

    result
}

// ──────────────────────────────────────────────────────────────────────────────
// Background texture overlay
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_background_texture(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let bg = estimate_bg_gray_flat(img, w, h);
    let total = w * h;
    let mut rng = rand::thread_rng();

    let mut out: Vec<f32> = img.iter().map(|&p| p as f32).collect();

    match rng.gen_range(0..3) {
        0 => {
            // Fine Gaussian grain — parallel over pixels
            let sigma = 1.0 + intensity * 10.0;
            let alpha = 0.05 + intensity * 0.25;
            let dist = rand_distr::Normal::new(0.0, sigma).unwrap();
            out.par_iter_mut().for_each_init(
                || rand::thread_rng(),
                |rng, pixel| {
                    let noise: f32 = dist.sample(rng);
                    *pixel += noise * alpha;
                },
            );
        }
        1 => {
            // Coarse texture
            let coarse_h = (h / 4).max(1);
            let coarse_w = (w / 4).max(1);
            let coarse_total = coarse_h * coarse_w;
            let mut coarse: Vec<f32> = Vec::with_capacity(coarse_total);
            let dist = rand_distr::Normal::new(0.0, 20.0).unwrap();
            for _ in 0..coarse_total {
                coarse.push(dist.sample(&mut rng));
            }
            // Upscale coarse to full size with box interpolation
            let upscaled = upscale_nearest_f32(&coarse, coarse_w, coarse_h, w, h);
            // Blur the upscaled texture
            let blur_sigma = (w as f32 * 0.05).max(1.0);
            let blurred = gaussian_blur_f32(&upscaled, w, h, blur_sigma);
            let alpha = 0.03 + intensity * 0.20;
            out.par_iter_mut()
                .zip(blurred.par_iter())
                .for_each(|(p, &b)| {
                    *p += b * alpha;
                });
        }
        _ => {
            // Horizontal streaks
            let streak_count = rng.gen_range(3..=12);
            for _ in 0..streak_count {
                let y = rng.gen_range(0..h);
                let streak_val: f32 = rng.gen_range(-12.0..12.0);
                let angle: f32 = rng.gen_range(-0.05..0.05);
                for dy in 0..rng.gen_range(1..=2) {
                    let row = y + dy;
                    if row >= h {
                        break;
                    }
                    for x in 0..w {
                        let src_y = (row as f32 + x as f32 * angle) as isize;
                        let src_y = src_y.clamp(0, h as isize - 1) as usize;
                        out[src_y * w + x] += streak_val;
                    }
                }
            }
        }
    }

    // Ink preservation: suppress texture over dark pixels
    let bg_f = bg as f32;
    for i in 0..total {
        let ink_strength = (bg_f - img[i] as f32) / bg_f.max(1.0);
        let ink_strength = ink_strength.clamp(0.0, 1.0);
        out[i] = out[i] * (1.0 - ink_strength) + img[i] as f32 * ink_strength;
    }

    out.into_par_iter().map(clamp_f32_to_u8).collect()
}

// ──────────────────────────────────────────────────────────────────────────────
// Low DPI simulation
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_lowdpi(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let ratio = (0.80 - intensity * 0.65).max(0.05);
    let small_h = (h as f32 * ratio).max(2.0) as usize;
    let small_w = (w as f32 * ratio).max(2.0) as usize;
    let down = crate::utils::downscale_gray(img, w, h, small_w, small_h);
    upscale_nearest_u8(&down, small_w, small_h, w, h)
}

// ──────────────────────────────────────────────────────────────────────────────
// Oversample (mild sharpen)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_oversample(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let alpha = 1.0 + intensity * 0.5;
    let kernel: [f32; 9] = [
        -0.5, -0.5, -0.5,
        -0.5, 5.0 * alpha, -0.5,
        -0.5, -0.5, -0.5,
    ];
    convolve_3x3(img, w, h, &kernel)
}

// ──────────────────────────────────────────────────────────────────────────────
// Perspective warp (online)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_perspective(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    if h < 10 || w < 10 {
        return img.to_vec();
    }

    let d = (w.min(h) as f32) * (0.02 + intensity * 0.10);
    let mut rng = rand::thread_rng();

    let src: [[f32; 2]; 4] = [
        [0.0, 0.0],
        [w as f32, 0.0],
        [w as f32, h as f32],
        [0.0, h as f32],
    ];

    let dst: [[f32; 2]; 4] = [
        [rng.gen_range(0.0..d), rng.gen_range(0.0..d)],
        [w as f32 - rng.gen_range(0.0..d), rng.gen_range(0.0..d)],
        [w as f32 - rng.gen_range(0.0..d), h as f32 - rng.gen_range(0.0..d)],
        [rng.gen_range(0.0..d), h as f32 - rng.gen_range(0.0..d)],
    ];

    let mat = compute_perspective_transform(&src, &dst);
    warp_perspective_gray(img, w, h, &mat, 128)
}

// ──────────────────────────────────────────────────────────────────────────────
// Elastic distortion
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_elastic(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    if h < 10 || w < 10 {
        return img.to_vec();
    }

    let sigma = (w.min(h) as f32) * (0.02 + intensity * 0.10);
    let scale = 8;
    let ch = (h / scale).max(2);
    let cw = (w / scale).max(2);

    let dist = rand_distr::Uniform::new(-1.0, 1.0);
    let mut rng = rand::thread_rng();

    // Generate coarse displacement fields
    let mut dx_coarse = vec![0.0f32; ch * cw];
    let mut dy_coarse = vec![0.0f32; ch * cw];
    for i in 0..ch * cw {
        dx_coarse[i] = dist.sample(&mut rng) * sigma;
        dy_coarse[i] = dist.sample(&mut rng) * sigma;
    }

    // Upscale displacement fields
    let dx = upscale_nearest_f32(&dx_coarse, cw, ch, w, h);
    let dy = upscale_nearest_f32(&dy_coarse, cw, ch, w, h);

    let mut result = vec![0u8; w * h];
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        let y_off = y * w;
        for x in 0..w {
            let sx = (x as f32 + dx[y_off + x]).clamp(0.0, w as f32 - 1.0);
            let sy = (y as f32 + dy[y_off + x]).clamp(0.0, h as f32 - 1.0);

            let ix = sx as usize;
            let iy = sy as usize;
            let fx = sx - ix as f32;
            let fy = sy - iy as f32;

            let ix1 = (ix + 1).min(w - 1);
            let iy1 = (iy + 1).min(h - 1);

            let a = img[iy * w + ix] as f32;
            let b = img[iy * w + ix1] as f32;
            let c = img[iy1 * w + ix] as f32;
            let d = img[iy1 * w + ix1] as f32;

            let val = (1.0 - fy) * ((1.0 - fx) * a + fx * b)
                + fy * ((1.0 - fx) * c + fx * d);
            row[x] = val.clamp(0.0, 255.0) as u8;
        }
    });

    result
}

// ──────────────────────────────────────────────────────────────────────────────
// Random height crop
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_random_crop(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    if h < 8 {
        return img.to_vec();
    }

    let max_cut = (h as f32 * (0.01 + intensity * 0.07)).max(1.0) as usize;
    let mut rng = rand::thread_rng();
    let cut = rng.gen_range(1..=max_cut);

    let cropped: &[u8] = if rng.gen_bool(0.5) {
        &img[cut * w..]
    } else {
        &img[..(h - cut) * w]
    };

    let new_h = h - cut;
    upscale_nearest_u8(cropped, w, new_h, w, h)
}

// ──────────────────────────────────────────────────────────────────────────────
// Online blur (Gaussian or Motion via box averaging)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_online_blur(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let kernel = normalize_odd_kernel_limit((3.0 + intensity * 4.0) as i32, 3) as usize;
    gaussian_blur_gray(img, w, h, kernel)
}

// ──────────────────────────────────────────────────────────────────────────────
// Online noise (additive Gaussian)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_online_noise(img: &[u8], _w: usize, _h: usize, intensity: f32) -> Vec<u8> {
    let sigma = 3.0 + intensity * 27.0;
    let dist = rand_distr::Normal::new(0.0, sigma).unwrap();

    img.par_iter()
        .map_init(
            || rand::thread_rng(),
            |rng, &p| {
                let noise: f32 = dist.sample(rng);
                clamp_f32_to_u8(p as f32 + noise)
            },
        )
        .collect()
}

// ──────────────────────────────────────────────────────────────────────────────
// HSV color jitter (grayscale images pass through unchanged)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_hsv(img: &[u8], _w: usize, _h: usize, _intensity: f32) -> Vec<u8> {
    // For grayscale images, HSV jitter is a no-op.
    // RGB handling is done on the Python side by converting to RGB first.
    img.to_vec()
}

pub fn apply_hsv_rgb(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let total = w * h;
    let mut rng = rand::thread_rng();
    let factor = 1.0 - intensity * 0.40;
    let upper = 2.0 - factor;
    // At intensity == 0.0, factor == upper == 1.0: the range is a single
    // point, which rand's gen_range rejects as empty. Fall back to that
    // point directly rather than sampling.
    let s_mult = if factor < upper { rng.gen_range(factor..upper) } else { factor };
    let v_mult = if factor < upper { rng.gen_range(factor..upper) } else { factor };

    let mut result = vec![0u8; total * 3];
    result.par_chunks_mut(3).enumerate().for_each(|(i, rgb)| {
        let r = img[i * 3] as f32 / 255.0;
        let g = img[i * 3 + 1] as f32 / 255.0;
        let b = img[i * 3 + 2] as f32 / 255.0;

        // RGB to HSV
        let max_val = r.max(g).max(b);
        let min_val = r.min(g).min(b);
        let delta = max_val - min_val;

        let h: f32;
        let s = if max_val > 0.0 { delta / max_val } else { 0.0 };
        let v = max_val;

        if delta < 1e-6 {
            h = 0.0;
        } else if (max_val - r).abs() < 1e-6 {
            h = (g - b) / delta + if g < b { 6.0 } else { 0.0 };
        } else if (max_val - g).abs() < 1e-6 {
            h = (b - r) / delta + 2.0;
        } else {
            h = (r - g) / delta + 4.0;
        }

        // Modify S and V
        let s_new = (s * s_mult).clamp(0.0, 1.0);
        let v_new = (v * v_mult).clamp(0.0, 1.0);

        // HSV to RGB
        let (r2, g2, b2) = hsv_to_rgb(h / 6.0, s_new, v_new);
        rgb[0] = (r2 * 255.0).clamp(0.0, 255.0) as u8;
        rgb[1] = (g2 * 255.0).clamp(0.0, 255.0) as u8;
        rgb[2] = (b2 * 255.0).clamp(0.0, 255.0) as u8;
    });

    result
}

#[inline]
fn hsv_to_rgb(h: f32, s: f32, v: f32) -> (f32, f32, f32) {
    if s < 1e-6 {
        return (v, v, v);
    }
    let h6 = h * 6.0;
    let i = h6.floor() as i32;
    let f = h6 - i as f32;
    let p = v * (1.0 - s);
    let q = v * (1.0 - s * f);
    let t = v * (1.0 - s * (1.0 - f));
    match i % 6 {
        0 => (v, t, p),
        1 => (q, v, p),
        2 => (p, v, t),
        3 => (p, q, v),
        4 => (t, p, v),
        _ => (v, p, q),
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Color reversal
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_reverse(img: &[u8], _w: usize, _h: usize, _intensity: f32) -> Vec<u8> {
    img.par_iter().map(|&p| 255u8.saturating_sub(p)).collect()
}

// ──────────────────────────────────────────────────────────────────────────────
// Brightness/contrast jitter
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_brightness_contrast(
    img: &[u8],
    _w: usize,
    _h: usize,
    intensity: f32,
) -> Vec<u8> {
    let spread = 0.02 + intensity * 0.23;
    let mut rng = rand::thread_rng();
    let alpha = rng.gen_range((1.0 - spread)..(1.0 + spread));
    // At intensity == 0.0 the beta range collapses to a single point (0.0),
    // which rand's gen_range rejects as empty; sample only when non-empty.
    let beta_bound = 30.0 * intensity;
    let beta = if beta_bound > 0.0 { rng.gen_range(-beta_bound..beta_bound) } else { 0.0 };

    img.par_iter()
        .map(|&p| clamp_f32_to_u8(p as f32 * alpha + beta))
        .collect()
}

pub fn apply_brightness_contrast_rgb(
    img: &[u8],
    _w: usize,
    _h: usize,
    intensity: f32,
) -> Vec<u8> {
    let spread = 0.02 + intensity * 0.23;
    let mut rng = rand::thread_rng();
    let alpha = rng.gen_range((1.0 - spread)..(1.0 + spread));
    let beta_bound = 30.0 * intensity;
    let beta = if beta_bound > 0.0 { rng.gen_range(-beta_bound..beta_bound) } else { 0.0 };

    img.par_iter()
        .map(|&p| clamp_f32_to_u8(p as f32 * alpha + beta))
        .collect()
}

// ──────────────────────────────────────────────────────────────────────────────
// Pixelation (downscale-then-upscale)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_pixelation(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let scale = (0.9 - intensity * 0.7).max(0.02);
    let small_w = (w as f32 * scale).max(1.0) as usize;
    let small_h = (h as f32 * scale).max(1.0) as usize;
    let down = crate::utils::downscale_gray(img, w, h, small_w, small_h);
    upscale_nearest_u8(&down, small_w, small_h, w, h)
}

// ──────────────────────────────────────────────────────────────────────────────
// Gradient illumination overlay
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_gradient_illumination(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let strength = 0.1 + intensity * 0.5;
    let mut rng = rand::thread_rng();

    let gradient: Vec<f32> = if rng.gen_bool(0.5) {
        // Horizontal gradient
        let mut g: Vec<f32> = (0..w)
            .map(|x| 1.0 - strength + strength * x as f32 / (w.max(2) - 1) as f32)
            .collect();
        if rng.gen_bool(0.5) {
            g.reverse();
        }
        let mut expanded = vec![0.0f32; w * h];
        for y in 0..h {
            expanded[y * w..(y + 1) * w].copy_from_slice(&g);
        }
        expanded
    } else {
        // Vertical gradient
        let mut g: Vec<f32> = (0..h)
            .map(|y| 1.0 - strength + strength * y as f32 / (h.max(2) - 1) as f32)
            .collect();
        if rng.gen_bool(0.5) {
            g.reverse();
        }
        let mut expanded = vec![0.0f32; w * h];
        for y in 0..h {
            for x in 0..w {
                expanded[y * w + x] = g[y];
            }
        }
        expanded
    };

    img.par_iter()
        .enumerate()
        .map(|(i, &p)| clamp_f32_to_u8(p as f32 * gradient[i]))
        .collect()
}

// ──────────────────────────────────────────────────────────────────────────────
// Morphological erode/dilate
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_morphological(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let kernel_size = if intensity < 0.5 { 2 } else { 3 };
    let mut rng = rand::thread_rng();
    let erode = rng.gen_bool(0.5);

    if erode {
        erode_gray(img, w, h, kernel_size)
    } else {
        dilate_gray(img, w, h, kernel_size)
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Anisotropic dilation (dot-matrix spread)
// ──────────────────────────────────────────────────────────────────────────────

pub fn apply_anisotropic_dilation(img: &[u8], w: usize, h: usize, intensity: f32) -> Vec<u8> {
    let mut rng = rand::thread_rng();
    let kernel_size = if intensity < 0.5 {
        2
    } else {
        rng.gen_range(3..=4)
    };

    let horizontal = rng.gen_bool(0.5);
    if horizontal {
        dilate_gray_1d_horizontal(img, w, h, kernel_size)
    } else {
        dilate_gray_1d_vertical(img, w, h, kernel_size)
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Internal helpers
// ══════════════════════════════════════════════════════════════════════════════

fn estimate_bg_gray_flat(img: &[u8], w: usize, h: usize) -> u8 {
    if w == 0 || h == 0 {
        return 255;
    }
    let mut samples: Vec<u8> = Vec::with_capacity((h + w) * 2);
    for &p in &img[..w] {
        samples.push(p);
    }
    for &p in &img[(h - 1) * w..] {
        samples.push(p);
    }
    for row in 1..h.saturating_sub(1) {
        samples.push(img[row * w]);
        samples.push(img[row * w + w - 1]);
    }
    samples.sort_unstable();
    let mid = samples.len() / 2;
    if samples.len() % 2 == 0 {
        ((samples[mid - 1] as u16 + samples[mid] as u16) / 2) as u8
    } else {
        samples[mid]
    }
}

fn erode_gray(img: &[u8], w: usize, h: usize, ksize: usize) -> Vec<u8> {
    let half = ksize / 2;
    let mut result = vec![255u8; w * h];
    let y_end = h.saturating_sub(half);
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        if y >= half && y < y_end {
            for x in half..w.saturating_sub(half) {
                let mut min_val = 255u8;
                for dy in 0..ksize {
                    for dx in 0..ksize {
                        let py = y - half + dy;
                        let px = x - half + dx;
                        min_val = min_val.min(img[py * w + px]);
                    }
                }
                row[x] = min_val;
            }
        }
    });
    result
}

fn dilate_gray(img: &[u8], w: usize, h: usize, ksize: usize) -> Vec<u8> {
    let half = ksize / 2;
    let mut result = vec![0u8; w * h];
    let y_end = h.saturating_sub(half);
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        if y >= half && y < y_end {
            for x in half..w.saturating_sub(half) {
                let mut max_val = 0u8;
                for dy in 0..ksize {
                    for dx in 0..ksize {
                        let py = y - half + dy;
                        let px = x - half + dx;
                        max_val = max_val.max(img[py * w + px]);
                    }
                }
                row[x] = max_val;
            }
        }
    });
    result
}

fn dilate_gray_1d_horizontal(img: &[u8], w: usize, h: usize, ksize: usize) -> Vec<u8> {
    let half = ksize / 2;
    let x_end = w.saturating_sub(half);
    let mut result = vec![0u8; w * h];
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        for x in half..x_end {
            let mut max_val = 0u8;
            for dx in 0..ksize {
                let px = x - half + dx;
                max_val = max_val.max(img[y * w + px]);
            }
            row[x] = max_val;
        }
    });
    result
}

fn dilate_gray_1d_vertical(img: &[u8], w: usize, h: usize, ksize: usize) -> Vec<u8> {
    let half = ksize / 2;
    let y_end = h.saturating_sub(half);
    let mut result = vec![0u8; w * h];
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        if y >= half && y < y_end {
            for x in 0..w {
                let mut max_val = 0u8;
                for dy in 0..ksize {
                    let py = y - half + dy;
                    max_val = max_val.max(img[py * w + x]);
                }
                row[x] = max_val;
            }
        }
    });
    result
}

fn upscale_nearest_f32(src: &[f32], sw: usize, sh: usize, dw: usize, dh: usize) -> Vec<f32> {
    let mut dst = vec![0.0f32; dw * dh];
    let x_ratio = sw as f64 / dw as f64;
    let y_ratio = sh as f64 / dh as f64;
    dst.par_chunks_mut(dw).enumerate().for_each(|(dy, row)| {
        let sy = ((dy as f64) * y_ratio) as usize;
        for dx in 0..dw {
            let sx = ((dx as f64) * x_ratio) as usize;
            row[dx] = src[sy * sw + sx];
        }
    });
    dst
}

fn upscale_nearest_u8(src: &[u8], sw: usize, sh: usize, dw: usize, dh: usize) -> Vec<u8> {
    let mut dst = vec![0u8; dw * dh];
    let x_ratio = sw as f64 / dw as f64;
    let y_ratio = sh as f64 / dh as f64;
    dst.par_chunks_mut(dw).enumerate().for_each(|(dy, row)| {
        let sy = ((dy as f64) * y_ratio) as usize;
        for dx in 0..dw {
            let sx = ((dx as f64) * x_ratio) as usize;
            row[dx] = src[sy * sw + sx];
        }
    });
    dst
}

fn gaussian_blur_f32(img: &[f32], w: usize, h: usize, sigma: f32) -> Vec<f32> {
    let kernel_size = ((sigma * 4.0).ceil() as usize).max(3);
    let kernel_size = if kernel_size % 2 == 0 { kernel_size + 1 } else { kernel_size };
    let half = kernel_size / 2;

    let mut kernel: Vec<f32> = (0..kernel_size)
        .map(|i| {
            let x = i as f32 - half as f32;
            (-x * x / (2.0 * sigma * sigma)).exp()
        })
        .collect();
    let ksum: f32 = kernel.iter().sum();
    for k in kernel.iter_mut() {
        *k /= ksum;
    }

    let mut tmp = vec![0.0f32; w * h];

    // Horizontal — parallelize over rows
    tmp.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        for x in 0..w {
            let mut sum = 0.0;
            let mut weight = 0.0;
            for (ki, kv) in kernel.iter().enumerate() {
                let sx = (x + ki).saturating_sub(half);
                if sx < w {
                    sum += img[y * w + sx] * kv;
                    weight += kv;
                }
            }
            row[x] = if weight > 0.0 { sum / weight } else { img[y * w + x] };
        }
    });

    // Vertical — parallelize over rows
    let mut result = vec![0.0f32; w * h];
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        for x in 0..w {
            let mut sum = 0.0;
            let mut weight = 0.0;
            for (ki, kv) in kernel.iter().enumerate() {
                let sy = (y + ki).saturating_sub(half);
                if sy < h {
                    sum += tmp[sy * w + x] * kv;
                    weight += kv;
                }
            }
            row[x] = if weight > 0.0 { sum / weight } else { tmp[y * w + x] };
        }
    });

    result
}

fn convolve_3x3(img: &[u8], w: usize, h: usize, kernel: &[f32; 9]) -> Vec<u8> {
    let mut result = vec![0u8; w * h];
    let y_end = h.saturating_sub(1);
    let x_end = w.saturating_sub(1);
    result.par_chunks_mut(w).enumerate().for_each(|(y, row)| {
        if y >= 1 && y < y_end {
            for x in 1..x_end {
                let mut sum = 0.0f32;
                for dy in 0..3usize {
                    for dx in 0..3usize {
                        let py = y - 1 + dy;
                        let px = x - 1 + dx;
                        sum += img[py * w + px] as f32 * kernel[dy * 3 + dx];
                    }
                }
                row[x] = clamp_f32_to_u8(sum);
            }
        }
    });
    result
}

fn compute_perspective_transform(src: &[[f32; 2]; 4], dst: &[[f32; 2]; 4]) -> [f32; 9] {
    // Solve for perspective transform matrix via DLT (8-DOF)
    // We want: H * src_i = dst_i (up to scale)
    // That gives 8 equations for 8 unknowns (h33=1)

    let mut a = [[0.0f32; 8]; 8];
    let mut b = [0.0f32; 8];

    for i in 0..4 {
        let (sx, sy) = (src[i][0], src[i][1]);
        let (dx, dy) = (dst[i][0], dst[i][1]);
        // x' = (h11*x + h12*y + h13) / (h31*x + h32*y + 1)
        // y' = (h21*x + h22*y + h23) / (h31*x + h32*y + 1)
        a[i * 2][0] = sx;
        a[i * 2][1] = sy;
        a[i * 2][2] = 1.0;
        a[i * 2][3] = 0.0;
        a[i * 2][4] = 0.0;
        a[i * 2][5] = 0.0;
        a[i * 2][6] = -sx * dx;
        a[i * 2][7] = -sy * dx;
        b[i * 2] = dx;

        a[i * 2 + 1][0] = 0.0;
        a[i * 2 + 1][1] = 0.0;
        a[i * 2 + 1][2] = 0.0;
        a[i * 2 + 1][3] = sx;
        a[i * 2 + 1][4] = sy;
        a[i * 2 + 1][5] = 1.0;
        a[i * 2 + 1][6] = -sx * dy;
        a[i * 2 + 1][7] = -sy * dy;
        b[i * 2 + 1] = dy;
    }

    let h = solve_8x8(&a, &b);
    [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1.0]
}

fn solve_8x8(a: &[[f32; 8]; 8], b: &[f32; 8]) -> [f32; 8] {
    // Gaussian elimination with partial pivoting
    let mut m = [[0.0f32; 9]; 8];
    for i in 0..8 {
        for j in 0..8 {
            m[i][j] = a[i][j];
        }
        m[i][8] = b[i];
    }

    for col in 0..8 {
        // Find pivot
        let mut max_row = col;
        let mut max_val = m[col][col].abs();
        for row in col + 1..8 {
            let val = m[row][col].abs();
            if val > max_val {
                max_val = val;
                max_row = row;
            }
        }
        m.swap(col, max_row);

        // Eliminate below
        let pivot = m[col][col];
        if pivot.abs() < 1e-10 {
            break;
        }
        for row in col + 1..8 {
            let factor = m[row][col] / pivot;
            for j in col..9 {
                m[row][j] -= factor * m[col][j];
            }
        }
    }

    // Back substitution
    let mut x = [0.0f32; 8];
    for row in (0..8).rev() {
        let mut sum = m[row][8];
        for j in row + 1..8 {
            sum -= m[row][j] * x[j];
        }
        x[row] = if m[row][row].abs() > 1e-10 {
            sum / m[row][row]
        } else {
            0.0
        };
    }
    x
}

fn warp_perspective_gray(img: &[u8], w: usize, h: usize, mat: &[f32; 9], fill: u8) -> Vec<u8> {
    let mut result = vec![fill; w * h];
    let inv = if let Some(m) = invert_3x3(mat) {
        m
    } else {
        return img.to_vec();
    };

    result.par_chunks_mut(w).enumerate().for_each(|(dy, row)| {
        for dx in 0..w {
            let w_out = inv[6] * dx as f32 + inv[7] * dy as f32 + inv[8];
            if w_out.abs() < 1e-10 {
                continue;
            }
            let sx = (inv[0] * dx as f32 + inv[1] * dy as f32 + inv[2]) / w_out;
            let sy = (inv[3] * dx as f32 + inv[4] * dy as f32 + inv[5]) / w_out;

            if sx >= 0.0 && sx < w as f32 - 1.0 && sy >= 0.0 && sy < h as f32 - 1.0 {
                let ix = sx as usize;
                let iy = sy as usize;
                let fx = sx - ix as f32;
                let fy = sy - iy as f32;

                let ix1 = (ix + 1).min(w - 1);
                let iy1 = (iy + 1).min(h - 1);

                let a = img[iy * w + ix] as f32;
                let b = img[iy * w + ix1] as f32;
                let c = img[iy1 * w + ix] as f32;
                let d = img[iy1 * w + ix1] as f32;

                let val = (1.0 - fy) * ((1.0 - fx) * a + fx * b)
                    + fy * ((1.0 - fx) * c + fx * d);
                row[dx] = clamp_f32_to_u8(val);
            }
        }
    });

    result
}

fn invert_3x3(m: &[f32; 9]) -> Option<[f32; 9]> {
    let det = m[0] * (m[4] * m[8] - m[5] * m[7])
        - m[1] * (m[3] * m[8] - m[5] * m[6])
        + m[2] * (m[3] * m[7] - m[4] * m[6]);

    if det.abs() < 1e-10 {
        return None;
    }

    let inv_det = 1.0 / det;
    Some([
        (m[4] * m[8] - m[5] * m[7]) * inv_det,
        (m[2] * m[7] - m[1] * m[8]) * inv_det,
        (m[1] * m[5] - m[2] * m[4]) * inv_det,
        (m[5] * m[6] - m[3] * m[8]) * inv_det,
        (m[0] * m[8] - m[2] * m[6]) * inv_det,
        (m[2] * m[3] - m[0] * m[5]) * inv_det,
        (m[3] * m[7] - m[4] * m[6]) * inv_det,
        (m[1] * m[6] - m[0] * m[7]) * inv_det,
        (m[0] * m[4] - m[1] * m[3]) * inv_det,
    ])
}
