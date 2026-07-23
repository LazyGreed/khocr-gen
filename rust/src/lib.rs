//! `khocr_gen._rust_accel` — Rust acceleration backend for khocr-gen.
//!
//! Provides fast implementations of image augmentation, text rendering,
//! and font management, exposed to Python via PyO3 with zero-copy numpy
//! array interoperability.

mod augmentation;
mod fonts;
mod rendering;
mod utils;

use numpy::{PyArray1, PyArray2, PyArrayMethods, PyReadonlyArray2, PyReadonlyArrayDyn, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

// ══════════════════════════════════════════════════════════════════════════════
// Augmentation method wrappers
// ══════════════════════════════════════════════════════════════════════════════

/// Extract shape and contiguous slice from a 2D numpy u8 array.
fn extract_2d_slice<'a>(
    arr: &'a PyReadonlyArray2<'a, u8>,
) -> PyResult<(&'a [u8], usize, usize)> {
    let shape = arr.shape();
    let h = shape[0] as usize;
    let w = shape[1] as usize;
    let slice = arr
        .as_slice()
        .map_err(|e| PyValueError::new_err(format!("Array must be C-contiguous: {}", e)))?;
    Ok((slice, w, h))
}

/// Extract shape and contiguous slice from a 3D numpy u8 array.
fn extract_3d_slice<'a>(
    arr: &'a PyReadonlyArrayDyn<'a, u8>,
) -> PyResult<(&'a [u8], usize, usize, usize)> {
    let shape = arr.shape();
    if shape.len() != 3 {
        return Err(PyValueError::new_err("Expected 3D array (HxWx3)"));
    }
    let h = shape[0] as usize;
    let w = shape[1] as usize;
    let c = shape[2] as usize;
    if c != 3 {
        return Err(PyValueError::new_err("Expected 3 channels for RGB image"));
    }
    let slice = arr
        .as_slice()
        .map_err(|e| PyValueError::new_err(format!("Array must be C-contiguous: {}", e)))?;
    Ok((slice, w, h, c))
}

/// Build a 2D numpy array from a flat Vec<u8> and shape (h, w).
fn build_2d_array(py: Python<'_>, data: Vec<u8>, h: usize, w: usize) -> Py<PyArray2<u8>> {
    let arr1d = PyArray1::<u8>::from_vec(py, data);
    arr1d.reshape([h, w]).unwrap().unbind()
}

/// Wrapper: apply an augmentation to a 2D grayscale image, returning a new array.
macro_rules! aug_wrapper_2d {
    ($name:ident, $func:path) => {
        #[pyfunction]
        fn $name(
            py: Python<'_>,
            img: PyReadonlyArray2<'_, u8>,
            intensity: f32,
        ) -> PyResult<Py<PyArray2<u8>>> {
            let (slice, w, h) = extract_2d_slice(&img)?;
            let result = $func(slice, w, h, intensity);
            Ok(build_2d_array(py, result, h, w))
        }
    };
}

macro_rules! gen_aug_wrappers {
    ($($py_name:ident => $rust_fn:path),* $(,)?) => {
        $(
            aug_wrapper_2d!($py_name, $rust_fn);
        )*

        /// Return a Python dict mapping method name -> callable.
        #[pyfunction]
        fn aug_methods_dict(py: Python<'_>) -> PyResult<Py<PyDict>> {
            let dict = PyDict::new(py);
            $(
                dict.set_item(
                    stringify!($py_name),
                    wrap_pyfunction!($py_name, py)?,
                )?;
            )*
            Ok(dict.unbind())
        }
    };
}

gen_aug_wrappers! {
    apply_sauvola_rust => augmentation::apply_sauvola,
    apply_geo_warp_rust => augmentation::apply_geo_warp,
    apply_vertical_crop_rust => augmentation::apply_vertical_crop,
    apply_blur_rust => augmentation::apply_blur,
    apply_salt_pepper_rust => augmentation::apply_salt_pepper,
    apply_background_texture_rust => augmentation::apply_background_texture,
    apply_jpeg_compression_rust => augmentation::apply_jpeg_compression,
    apply_rotation_rust => augmentation::apply_rotation,
    apply_lowdpi_rust => augmentation::apply_lowdpi,
    apply_oversample_rust => augmentation::apply_oversample,
    apply_perspective_rust => augmentation::apply_perspective,
    apply_elastic_rust => augmentation::apply_elastic,
    apply_random_crop_rust => augmentation::apply_random_crop,
    apply_online_blur_rust => augmentation::apply_online_blur,
    apply_online_noise_rust => augmentation::apply_online_noise,
    apply_reverse_rust => augmentation::apply_reverse,
    apply_brightness_contrast_rust => augmentation::apply_brightness_contrast,
    apply_pixelation_rust => augmentation::apply_pixelation,
    apply_gradient_illumination_rust => augmentation::apply_gradient_illumination,
    apply_morphological_rust => augmentation::apply_morphological,
    apply_anisotropic_dilation_rust => augmentation::apply_anisotropic_dilation,
}

// ── RGB-capable methods ──────────────────────────────────────────────────────

#[pyfunction]
fn apply_hsv_rgb_rust(
    py: Python<'_>,
    img: PyReadonlyArrayDyn<'_, u8>,
    intensity: f32,
) -> PyResult<Py<PyArray2<u8>>> {
    let (slice, w, h, _c) = extract_3d_slice(&img)?;
    let result = augmentation::apply_hsv_rgb(slice, w, h, intensity);
    Ok(build_2d_array(py, result, h, w * 3))
}

#[pyfunction]
fn apply_brightness_contrast_rgb_rust(
    py: Python<'_>,
    img: PyReadonlyArrayDyn<'_, u8>,
    intensity: f32,
) -> PyResult<Py<PyArray2<u8>>> {
    let (slice, w, h, _c) = extract_3d_slice(&img)?;
    let result = augmentation::apply_brightness_contrast_rgb(slice, w, h, intensity);
    Ok(build_2d_array(py, result, h, w * 3))
}

// ══════════════════════════════════════════════════════════════════════════════
// Font management
// ══════════════════════════════════════════════════════════════════════════════

#[pyclass]
struct RustFontManager {
    inner: fonts::FontManager,
}

#[pymethods]
impl RustFontManager {
    #[new]
    fn new() -> Self {
        Self {
            inner: fonts::FontManager::new(),
        }
    }

    fn load(&mut self, fonts_dir: &str) -> PyResult<()> {
        self.inner.load(std::path::Path::new(fonts_dir));
        Ok(())
    }

    fn glyph_supported(&mut self, font_path: &str, ch: &str) -> PyResult<bool> {
        let c = ch.chars().next().ok_or_else(|| {
            PyValueError::new_err("Expected a single character string")
        })?;
        Ok(self.inner.char_supported(std::path::Path::new(font_path), c))
    }

    fn text_supported(&mut self, font_path: &str, text: &str) -> PyResult<bool> {
        Ok(self
            .inner
            .text_supported(std::path::Path::new(font_path), text))
    }

    fn text_has_khmer(&mut self, text: &str) -> bool {
        self.inner.text_has_khmer(text)
    }

    fn __len__(&self) -> usize {
        self.inner.all_fonts.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "RustFontManager(khmer={}, english={}, total={})",
            self.inner.khmer_fonts.len(),
            self.inner.english_fonts.len(),
            self.inner.all_fonts.len()
        )
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Fast glyph checking via cmap
// ══════════════════════════════════════════════════════════════════════════════

/// A loaded font face with fast O(1) character-support queries via the
/// TrueType cmap table — no glyph rasterization required.
#[pyclass(name = "FontFace")]
struct RustFontFace {
    inner: fonts::FontFace,
}

#[pymethods]
impl RustFontFace {
    /// Load a font file and parse its cmap table for glyph queries.
    #[staticmethod]
    fn from_file(path: &str) -> PyResult<Self> {
        let face = fonts::FontFace::from_file(std::path::Path::new(path))
            .map_err(|e| PyValueError::new_err(e))?;
        Ok(Self { inner: face })
    }

    /// Check whether *c* has a glyph in this font (O(1) cmap lookup).
    fn glyph_exists(&self, c: char) -> bool {
        self.inner.glyph_exists(c)
    }

    /// Check every character in *text* — returns true only if all chars
    /// are covered. Whitespace and control characters (codepoint < 32) are
    /// always considered supported.
    fn text_supported(&self, text: &str) -> bool {
        for c in text.chars() {
            if c.is_whitespace() || (c as u32) < 32 {
                continue;
            }
            if !self.inner.glyph_exists(c) {
                return false;
            }
        }
        true
    }

    fn __repr__(&self) -> String {
        "FontFace(...)".to_string()
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Text span splitting
// ══════════════════════════════════════════════════════════════════════════════

#[pyfunction]
fn split_text_spans(text: &str) -> PyResult<Vec<(String, String)>> {
    let spans = fonts::split_text_into_spans(text);
    Ok(spans
        .into_iter()
        .map(|s| {
            let script_name = match s.script {
                fonts::Script::Khmer => "khmer",
                fonts::Script::English => "english",
                fonts::Script::Other => "other",
            };
            (s.text, script_name.to_string())
        })
        .collect())
}

// ══════════════════════════════════════════════════════════════════════════════
// Shared utilities
// ══════════════════════════════════════════════════════════════════════════════

#[pyfunction]
fn estimate_bg_rust(img: PyReadonlyArray2<'_, u8>) -> u8 {
    let arr = img.as_array();
    utils::estimate_bg_gray(arr)
}

#[pyfunction]
fn image_is_blank_rust(img: PyReadonlyArray2<'_, u8>, threshold: u8, min_ratio: f32) -> bool {
    let arr = img.as_array();
    utils::image_is_blank(arr, threshold, min_ratio)
}

#[pyfunction]
fn write_image_rust(
    img: PyReadonlyArray2<'_, u8>,
    path: &str,
    format: &str,
    quality: u8,
) -> PyResult<bool> {
    use image::codecs::jpeg::JpegEncoder;
    use image::ImageEncoder;
    use std::io::BufWriter;

    let arr = img.as_array();
    let h = arr.nrows();
    let w = arr.ncols();
    let slice = arr
        .as_slice()
        .ok_or_else(|| PyValueError::new_err("Input array must be contiguous"))?;

    match format.to_lowercase().as_str() {
        "jpg" | "jpeg" => {
            let file = std::fs::File::create(path)
                .map_err(|e| PyValueError::new_err(format!("Cannot create {}: {}", path, e)))?;
            let writer = BufWriter::new(file);
            let encoder = JpegEncoder::new_with_quality(writer, quality);
            encoder
                .write_image(slice, w as u32, h as u32, image::ExtendedColorType::L8)
                .map_err(|e| PyValueError::new_err(format!("JPEG encode error: {}", e)))?;
            Ok(true)
        }
        "png" => {
            image::save_buffer(
                path,
                slice,
                w as u32,
                h as u32,
                image::ExtendedColorType::L8,
            )
            .map_err(|e| PyValueError::new_err(format!("PNG encode error: {}", e)))?;
            Ok(true)
        }
        _ => Err(PyValueError::new_err(format!(
            "Unsupported format: {} (use jpg or png)",
            format
        ))),
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Module registration
// ══════════════════════════════════════════════════════════════════════════════

#[pymodule]
fn _rust_accel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(aug_methods_dict, m)?)?;

    m.add_function(wrap_pyfunction!(apply_sauvola_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_geo_warp_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_vertical_crop_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_blur_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_salt_pepper_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_background_texture_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_jpeg_compression_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_rotation_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_lowdpi_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_oversample_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_perspective_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_elastic_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_random_crop_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_online_blur_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_online_noise_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_reverse_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_brightness_contrast_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_pixelation_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_gradient_illumination_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_morphological_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_anisotropic_dilation_rust, m)?)?;

    m.add_function(wrap_pyfunction!(apply_hsv_rgb_rust, m)?)?;
    m.add_function(wrap_pyfunction!(apply_brightness_contrast_rgb_rust, m)?)?;

    m.add_class::<RustFontManager>()?;
    m.add_class::<RustFontFace>()?;
    m.add_function(wrap_pyfunction!(split_text_spans, m)?)?;

    m.add_function(wrap_pyfunction!(estimate_bg_rust, m)?)?;
    m.add_function(wrap_pyfunction!(image_is_blank_rust, m)?)?;
    m.add_function(wrap_pyfunction!(write_image_rust, m)?)?;

    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add(
        "__doc__",
        "Rust acceleration backend for khocr-gen.",
    )?;

    Ok(())
}
