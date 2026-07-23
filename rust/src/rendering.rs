//! Text-to-image rendering using fontdue for font rasterization.
//!
//! Renders text lines to clean grayscale canvases (H×W u8 arrays),
//! with optional mixed-font per-span rendering for Khmer + English text.

use fontdue::layout::{CoordinateSystem, Layout, LayoutSettings, TextStyle};
use fontdue::Font;
use rand::Rng;
use std::sync::Arc;

use crate::fonts::{split_text_into_spans, FontEntry, FontManager, Script};

// ── Render config ──────────────────────────────────────────────────────────

pub struct RenderConfig {
    pub image_height: u32,
    pub image_width: Option<u32>,
    pub color_mode: u8, // 1 = grayscale, 3 = RGB
    pub random_align_when_padded: bool,
    pub mixed_font_prob: f32,
}

impl Default for RenderConfig {
    fn default() -> Self {
        Self {
            image_height: 48,
            image_width: None,
            color_mode: 1,
            random_align_when_padded: false,
            mixed_font_prob: 0.0,
        }
    }
}

// ── Render result ──────────────────────────────────────────────────────────

pub struct RenderResult {
    pub pixels: Vec<u8>,
    pub width: usize,
    pub height: usize,
}

impl RenderResult {
    pub fn new(w: usize, h: usize) -> Self {
        Self {
            pixels: vec![255u8; w * h],
            width: w,
            height: h,
        }
    }

    #[inline]
    pub fn get_mut(&mut self, x: usize, y: usize) -> &mut u8 {
        &mut self.pixels[y * self.width + x]
    }

    #[inline]
    pub fn get(&self, x: usize, y: usize) -> u8 {
        self.pixels[y * self.width + x]
    }

    /// Resize to target height, maintaining aspect ratio.
    pub fn resize_to_height(&self, target_h: u32) -> RenderResult {
        let scale = target_h as f64 / self.height as f64;
        let new_w = (self.width as f64 * scale).round().max(1.0) as usize;
        let new_h = target_h as usize;
        let mut out = vec![0u8; new_w * new_h];

        let x_ratio = self.width as f64 / new_w as f64;
        let y_ratio = self.height as f64 / new_h as f64;

        for dy in 0..new_h {
            let sy = ((dy as f64) * y_ratio) as usize;
            let sy1 = ((dy + 1) as f64 * y_ratio).ceil() as usize;
            let sy1 = sy1.min(self.height);

            for dx in 0..new_w {
                let sx = ((dx as f64) * x_ratio) as usize;
                let sx1 = ((dx + 1) as f64 * x_ratio).ceil() as usize;
                let sx1 = sx1.min(self.width);

                let mut sum: u32 = 0;
                let mut count: u32 = 0;
                for py in sy..sy1 {
                    for px in sx..sx1 {
                        sum += self.get(px, py) as u32;
                        count += 1;
                    }
                }
                out[dy * new_w + dx] = if count > 0 {
                    (sum / count) as u8
                } else {
                    255
                };
            }
        }

        RenderResult {
            pixels: out,
            width: new_w,
            height: new_h,
        }
    }

    /// Pad or resize to target width.
    pub fn adjust_to_width(&self, target_w: u32, bg: u8, random_align: bool) -> RenderResult {
        if self.width as u32 == target_w {
            return RenderResult {
                pixels: self.pixels.clone(),
                width: self.width,
                height: self.height,
            };
        }

        let mut rng = rand::thread_rng();

        if self.width < target_w as usize {
            let remaining = target_w as usize - self.width;
            let x_offset = if random_align {
                match rng.gen_range(0..3) {
                    0 => 0,
                    1 => remaining / 2,
                    _ => remaining,
                }
            } else {
                0
            };

            let mut out = vec![bg; target_w as usize * self.height];
            let left = x_offset;
            for y in 0..self.height {
                let src_row = y * self.width;
                let dst_row = y * target_w as usize + left;
                out[dst_row..dst_row + self.width].copy_from_slice(&self.pixels[src_row..src_row + self.width]);
            }
            RenderResult {
                pixels: out,
                width: target_w as usize,
                height: self.height,
            }
        } else {
            // Shrink
            self.resize_to_width(target_w)
        }
    }

    fn resize_to_width(&self, target_w: u32) -> RenderResult {
        let scale = target_w as f64 / self.width as f64;
        let new_h = (self.height as f64 * scale).round().max(1.0) as usize;
        let new_w = target_w as usize;
        let mut out = vec![0u8; new_w * new_h];

        let x_ratio = self.width as f64 / new_w as f64;
        let y_ratio = self.height as f64 / new_h as f64;

        for dy in 0..new_h {
            let sy = ((dy as f64) * y_ratio) as usize;
            let sy1 = ((dy + 1) as f64 * y_ratio).ceil() as usize;
            let sy1 = sy1.min(self.height);
            for dx in 0..new_w {
                let sx = ((dx as f64) * x_ratio) as usize;
                let sx1 = ((dx + 1) as f64 * x_ratio).ceil() as usize;
                let sx1 = sx1.min(self.width);
                let mut sum: u32 = 0;
                let mut count: u32 = 0;
                for py in sy..sy1 {
                    for px in sx..sx1 {
                        sum += self.get(px, py) as u32;
                        count += 1;
                    }
                }
                out[dy * new_w + dx] = if count > 0 {
                    (sum / count) as u8
                } else {
                    255
                };
            }
        }
        RenderResult {
            pixels: out,
            width: new_w,
            height: new_h,
        }
    }

    /// Estimate background colour from border.
    pub fn estimate_bg(&self) -> u8 {
        let w = self.width;
        let h = self.height;
        if w < 2 || h < 2 {
            return 255;
        }
        let mut samples = Vec::with_capacity((w + h) * 2);
        // Top/bottom rows
        for x in 0..w {
            samples.push(self.get(x, 0));
            samples.push(self.get(x, h - 1));
        }
        // Left/right columns
        for y in 1..h - 1 {
            samples.push(self.get(0, y));
            samples.push(self.get(w - 1, y));
        }
        samples.sort_unstable();
        let mid = samples.len() / 2;
        if samples.len() % 2 == 0 {
            ((samples[mid - 1] as u16 + samples[mid] as u16) / 2) as u8
        } else {
            samples[mid]
        }
    }
}

// ── Renderer ───────────────────────────────────────────────────────────────

pub struct ImageRenderer {
    pub config: RenderConfig,
}

impl ImageRenderer {
    pub fn new(config: RenderConfig) -> Self {
        Self { config }
    }

    /// Render a single text string to a clean canvas using a specific font.
    /// Returns a grayscale image buffer.
    pub fn render_clean_canvas(
        &self,
        text: &str,
        font: &Font,
        font_size: f32,
        augment: bool,
    ) -> Option<RenderResult> {
        let mut rng = rand::thread_rng();

        // Layout the text to get dimensions
        let mut layout = Layout::new(CoordinateSystem::PositiveYDown);
        layout.reset(&LayoutSettings {
            max_width: None,
            max_height: None,
            horizontal_align: fontdue::layout::HorizontalAlign::Left,
            vertical_align: fontdue::layout::VerticalAlign::Top,
            ..LayoutSettings::default()
        });
        layout.append(&[font], &TextStyle::new(text, font_size, 0));

        let glyphs = layout.glyphs();
        if glyphs.is_empty() {
            return None;
        }

        let min_x = glyphs.iter().map(|g| g.x).fold(f32::INFINITY, f32::min);
        let max_x = glyphs
            .iter()
            .map(|g| g.x + g.width as f32)
            .fold(f32::NEG_INFINITY, f32::max);
        let min_y = glyphs.iter().map(|g| g.y).fold(f32::INFINITY, f32::min);
        let max_y = glyphs
            .iter()
            .map(|g| g.y + g.height as f32)
            .fold(f32::NEG_INFINITY, f32::max);

        let text_w = (max_x - min_x).ceil() as usize;
        let text_h = (max_y - min_y).ceil() as usize;

        let offset_x = -min_x;
        let offset_y = -min_y;

        let padding_x = if augment {
            rng.gen_range(10..=30)
        } else {
            20
        };
        let padding_y = if augment {
            rng.gen_range(5..=15)
        } else {
            10
        };

        let img_w = text_w.max(1) + padding_x * 2;
        let img_h = text_h.max(1) + padding_y * 2;

        let bg_color = if augment {
            rng.gen_range(235..=255)
        } else {
            255
        };
        let text_color = if augment {
            rng.gen_range(0..=30) as u8
        } else {
            0u8
        };

        let mut result = RenderResult::new(img_w, img_h);

        // Fill background
        for p in result.pixels.iter_mut() {
            *p = bg_color;
        }

        // Rasterize each glyph
        let base_x = padding_x as f32 + offset_x + if augment { rng.gen_range(-3..=3) as f32 } else { 0.0 };
        let base_y = padding_y as f32 + offset_y + if augment { rng.gen_range(-2..=2) as f32 } else { 0.0 };

        for glyph in glyphs {
            let (metrics, bitmap) = font.rasterize(glyph.parent, font_size);
            if bitmap.is_empty() {
                continue;
            }

            let gx = (base_x + glyph.x + metrics.xmin as f32) as usize;
            let gy = (base_y + glyph.y + metrics.ymin as f32) as usize;

            for (i, &alpha) in bitmap.iter().enumerate() {
                let px = gx + (i % metrics.width);
                let py = gy + (i / metrics.width);
                if px < img_w && py < img_h && alpha > 0 {
                    let existing = result.get(px, py);
                    // Alpha blend: darker text on light background
                    let blended = blend_alpha(existing, text_color, alpha);
                    *result.get_mut(px, py) = blended;
                }
            }
        }

        Some(result)
    }

    /// Render text with per-span font selection for mixed Khmer/English.
    pub fn render_mixed_font(
        &self,
        text: &str,
        font_manager: &mut FontManager,
        augment: bool,
    ) -> Option<RenderResult> {
        let spans = split_text_into_spans(text);
        if spans.len() <= 1 {
            return None;
        }

        let scripts_present: std::collections::HashSet<Script> = spans
            .iter()
            .filter_map(|s| {
                if s.script == Script::Other {
                    None
                } else {
                    Some(s.script.clone())
                }
            })
            .collect();
        if scripts_present.len() <= 1 {
            return None;
        }

        let first_script = spans
            .iter()
            .find(|s| s.script != Script::Other)
            .map(|s| s.script.clone())
            .unwrap_or(Script::Khmer);

        // Pick a base font
        let base_entry = {
            let pool: &[FontEntry] = match &first_script {
                Script::Khmer if !font_manager.khmer_fonts.is_empty() => &font_manager.khmer_fonts,
                Script::English if !font_manager.english_fonts.is_empty() => &font_manager.english_fonts,
                _ => &font_manager.all_fonts,
            };
            if pool.is_empty() {
                return None;
            }
            use rand::seq::SliceRandom;
            pool.choose(&mut rand::thread_rng())?.clone()
        };

        let _base_size = base_entry.size as f32;
        let mut rng = rand::thread_rng();

        let padding_x = if augment {
            rng.gen_range(10..=30)
        } else {
            20
        };
        let padding_y = if augment {
            rng.gen_range(5..=15)
        } else {
            10
        };
        let bg_color = if augment {
            rng.gen_range(235..=255) as u8
        } else {
            255u8
        };
        let text_color = if augment {
            rng.gen_range(0..=30) as u8
        } else {
            0u8
        };

        // Layout each span with appropriate font
        struct SpanLayout {
            span_text: String,
            font: Arc<Font>,
            font_size: f32,
            layout: Layout,
        }

        let mut span_layouts: Vec<SpanLayout> = Vec::new();
        let mut total_w: f32 = 0.0;
        let mut max_h: f32 = 0.0;

        for span in &spans {
            let entry = if span.script == first_script || span.script == Script::Other {
                base_entry.clone()
            } else {
                // Get font for the other script
                let pool: &[FontEntry] = match &span.script {
                    Script::Khmer if !font_manager.khmer_fonts.is_empty() => &font_manager.khmer_fonts,
                    Script::English if !font_manager.english_fonts.is_empty() => &font_manager.english_fonts,
                    _ => &font_manager.all_fonts,
                };
                if pool.is_empty() {
                    return None;
                }
                use rand::seq::SliceRandom;
                pool.choose(&mut rand::thread_rng())?.clone()
            };

            let mut layout = Layout::new(CoordinateSystem::PositiveYDown);
            layout.reset(&LayoutSettings {
                max_width: None,
                max_height: None,
                horizontal_align: fontdue::layout::HorizontalAlign::Left,
                vertical_align: fontdue::layout::VerticalAlign::Top,
                ..LayoutSettings::default()
            });
            layout.append(
                &[entry.font.as_ref()],
                &TextStyle::new(&span.text, entry.size as f32, 0),
            );

            let glyphs = layout.glyphs();
            let span_max_y = glyphs
                .iter()
                .map(|g| g.y + g.height as f32)
                .fold(0.0f32, f32::max);
            let span_min_y = glyphs.iter().map(|g| g.y).fold(f32::INFINITY, f32::min);
            let span_w = glyphs
                .iter()
                .map(|g| g.x + g.width as f32)
                .fold(0.0f32, f32::max)
                - glyphs.iter().map(|g| g.x).fold(f32::INFINITY, f32::min);

            total_w += span_w;
            max_h = max_h.max(span_max_y - span_min_y);

            span_layouts.push(SpanLayout {
                span_text: span.text.clone(),
                font: entry.font.clone(),
                font_size: entry.size as f32,
                layout,
            });
        }

        if total_w <= 0.0 || max_h <= 0.0 {
            return None;
        }

        let img_w = (total_w.ceil() as usize + padding_x * 2).max(1);
        let img_h = (max_h.ceil() as usize + padding_y * 2).max(1);

        let mut result = RenderResult::new(img_w, img_h);
        for p in result.pixels.iter_mut() {
            *p = bg_color;
        }

        let mut x_cursor: f32 = padding_x as f32;
        let y_base: f32 = padding_y as f32;

        for sl in &span_layouts {
            let glyphs = sl.layout.glyphs();
            let span_min_x = glyphs.iter().map(|g| g.x).fold(f32::INFINITY, f32::min);
            let span_min_y = glyphs.iter().map(|g| g.y).fold(f32::INFINITY, f32::min);

            for glyph in glyphs {
                let (metrics, bitmap) = sl.font.rasterize(glyph.parent, sl.font_size);
                if bitmap.is_empty() {
                    continue;
                }

                let gx = (x_cursor + glyph.x - span_min_x + metrics.xmin as f32) as usize;
                let gy = (y_base + glyph.y - span_min_y + metrics.ymin as f32) as usize;

                for (i, &alpha) in bitmap.iter().enumerate() {
                    let px = gx + (i % metrics.width);
                    let py = gy + (i / metrics.width);
                    if px < img_w && py < img_h && alpha > 0 {
                        let existing = result.get(px, py);
                        let blended = blend_alpha(existing, text_color, alpha);
                        *result.get_mut(px, py) = blended;
                    }
                }
            }

            // Advance x cursor
            let span_w = glyphs
                .iter()
                .map(|g| g.x + g.width as f32)
                .fold(0.0f32, f32::max)
                - span_min_x;
            x_cursor += span_w;
        }

        Some(result)
    }
}

// ── Alpha blending ─────────────────────────────────────────────────────────

#[inline]
fn blend_alpha(bg: u8, fg: u8, alpha: u8) -> u8 {
    let a = alpha as u16;
    let result = (bg as u16 * (255 - a) + fg as u16 * a) / 255;
    result as u8
}
