//! Font management and glyph support checking.
//!
//! Uses `fontdue` for rasterization and `ttf-parser` for fast glyph-existence
//! lookups directly from the cmap table (no rasterization needed for checking).

use fontdue::Font;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

// ── Font entry ──────────────────────────────────────────────────────────────

/// A loaded font with metadata. Font data is shared via Arc for cheap cloning.
#[derive(Clone)]
pub struct FontEntry {
    pub path: PathBuf,
    pub size: u32,
    pub family_name: String,
    pub font: Arc<Font>,
}

impl FontEntry {
    pub fn from_file(path: &Path, size: u32) -> Result<Self, String> {
        let data = std::fs::read(path).map_err(|e| format!("Cannot read {}: {}", path.display(), e))?;
        let font = Font::from_bytes(data, fontdue::FontSettings::default())
            .map_err(|e| format!("Cannot parse {}: {}", path.display(), e))?;
        let family_name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();
        Ok(Self {
            path: path.to_path_buf(),
            size,
            family_name,
            font: Arc::new(font),
        })
    }
}

// ── Glyph support cache ─────────────────────────────────────────────────────

/// A ttf-parser face stored alongside fontdue data for fast cmap lookups.
pub struct FontFace {
    pub fontdue_font: Arc<Font>,
    pub ttf_data: Arc<Vec<u8>>,
    pub ttf_face: ttf_parser::Face<'static>,
}

// Safety: ttf_parser::Face borrows from ttf_data which is Arc'd and never moved.
// We use unsafe to create a self-referential struct.
impl FontFace {
    pub fn from_file(path: &Path) -> Result<Self, String> {
        let data = std::fs::read(path).map_err(|e| format!("Cannot read {}: {}", path.display(), e))?;
        let fontdue_font = Font::from_bytes(data.clone(), fontdue::FontSettings::default())
            .map_err(|e| format!("Cannot parse {}: {}", path.display(), e))?;

        // Transmute the Vec<u8> into a static reference for ttf_parser::Face.
        // This is safe because the data is Arc'd and never freed while FontFace lives.
        let data_arc = Arc::new(data);
        let data_ptr: &'static [u8] = unsafe { std::mem::transmute(data_arc.as_ref() as &[u8]) };
        let ttf_face = ttf_parser::Face::parse(data_ptr, 0)
            .map_err(|e| format!("Cannot parse TTF {}: {:?}", path.display(), e))?;

        Ok(Self {
            fontdue_font: Arc::new(fontdue_font),
            ttf_data: data_arc,
            ttf_face,
        })
    }

    /// Check if a character is supported via the cmap table. O(1) lookup.
    pub fn glyph_exists(&self, c: char) -> bool {
        self.ttf_face.glyph_index(c).is_some()
    }
}

// ── Font manager ────────────────────────────────────────────────────────────

const FONT_EXTENSIONS: &[&str] = &["ttf", "otf", "ttc", "woff", "woff2"];
const DEFAULT_SIZES: &[u32] = &[28, 32, 36, 40, 44, 48];

pub struct FontManager {
    pub khmer_fonts: Vec<FontEntry>,
    pub english_fonts: Vec<FontEntry>,
    pub all_fonts: Vec<FontEntry>,
    /// Loaded font faces (with cmap) keyed by (path, size)
    pub font_lookup: HashMap<(PathBuf, u32), FontEntry>,
    /// Cached glyph existence checks: (path, char) -> bool
    pub glyph_cache: HashMap<(PathBuf, char), bool>,
    /// Cached script detection: text -> has_khmer
    pub script_cache: HashMap<String, bool>,
}

impl FontManager {
    pub fn new() -> Self {
        Self {
            khmer_fonts: Vec::new(),
            english_fonts: Vec::new(),
            all_fonts: Vec::new(),
            font_lookup: HashMap::new(),
            glyph_cache: HashMap::new(),
            script_cache: HashMap::new(),
        }
    }

    /// Collect font files recursively under a directory.
    pub fn collect_font_files(dir: &Path) -> Vec<PathBuf> {
        let mut files = Vec::new();
        if !dir.exists() {
            return files;
        }
        Self::walk_font_dir(dir, &mut files);
        files.sort();
        files
    }

    fn walk_font_dir(dir: &Path, files: &mut Vec<PathBuf>) {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    Self::walk_font_dir(&path, files);
                } else if path.is_file() {
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        if FONT_EXTENSIONS.contains(&ext.to_lowercase().as_str()) {
                            files.push(path);
                        }
                    }
                }
            }
        }
    }

    /// Load fonts from a directory into the given lists, one entry per size.
    pub fn load_fonts_from(
        &mut self,
        dir: &Path,
        khmer_list: &mut Vec<FontEntry>,
        english_list: &mut Vec<FontEntry>,
    ) -> usize {
        let font_paths = Self::collect_font_files(dir);
        let mut added = 0usize;

        for font_path in &font_paths {
            for &size in DEFAULT_SIZES {
                match FontEntry::from_file(font_path, size) {
                    Ok(entry) => {
                        self.font_lookup
                            .insert((font_path.clone(), size), entry.clone());
                        khmer_list.push(entry.clone());
                        english_list.push(entry.clone());
                        self.all_fonts.push(entry);
                        added += 1;
                    }
                    Err(_) => {}
                }
            }
        }
        added
    }

    /// Load fonts from the standard khmer/ and english/ subdirectory layout.
    pub fn load(&mut self, fonts_dir: &Path) {
        let khmer_dir = fonts_dir.join("khmer");
        let english_dir = fonts_dir.join("english");

        if khmer_dir.exists() {
            let mut k = Vec::new();
            let mut e = Vec::new();
            let _ = self.load_fonts_from(&khmer_dir, &mut k, &mut e);
            self.khmer_fonts.extend(k);
        }

        if english_dir.exists() {
            let mut k = Vec::new();
            let mut e = Vec::new();
            let _ = self.load_fonts_from(&english_dir, &mut k, &mut e);
            self.english_fonts.extend(e);
        }

        // Fallback: fonts directly in fonts_dir go to both pools
        if let Ok(entries) = std::fs::read_dir(fonts_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file() {
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        if !FONT_EXTENSIONS.contains(&ext.to_lowercase().as_str()) {
                            continue;
                        }
                        let mut k = Vec::new();
                        let mut e = Vec::new();
                        self.load_fonts_from(&path.parent().unwrap_or(Path::new(".")), &mut k, &mut e);
                    }
                }
            }
        }
    }

    /// Check if text contains any Khmer Unicode characters (U+1780–U+17FF, U+19E0–U+19FF).
    pub fn text_has_khmer(&mut self, text: &str) -> bool {
        if let Some(&cached) = self.script_cache.get(text) {
            return cached;
        }
        let result = text.chars().any(|c| {
            let cp = c as u32;
            (0x1780..=0x17FF).contains(&cp) || (0x19E0..=0x19FF).contains(&cp)
        });
        if self.script_cache.len() > 100_000 {
            self.script_cache.clear();
        }
        self.script_cache.insert(text.to_string(), result);
        result
    }

    /// Get a random font entry appropriate for the given text.
    pub fn random_font(&self, _text: &str, has_khmer: bool) -> Option<&FontEntry> {
        use rand::seq::SliceRandom;
        let mut rng = rand::thread_rng();

        let pool: &[FontEntry] = if has_khmer && !self.khmer_fonts.is_empty() {
            &self.khmer_fonts
        } else if !has_khmer && !self.english_fonts.is_empty() {
            &self.english_fonts
        } else {
            &self.all_fonts
        };

        pool.choose(&mut rng)
    }

    /// Check if a character is supported by a font using ttf-parser cmap.
    pub fn char_supported(&mut self, font_path: &Path, c: char) -> bool {
        let cache_key = (font_path.to_path_buf(), c);
        if let Some(&supported) = self.glyph_cache.get(&cache_key) {
            return supported;
        }

        let supported = match FontFace::from_file(font_path) {
            Ok(face) => face.glyph_exists(c),
            Err(_) => true, // Assume supported on parse failure
        };

        if self.glyph_cache.len() > 50_000 {
            self.glyph_cache.clear();
        }
        self.glyph_cache.insert(cache_key, supported);
        supported
    }

    /// Check if an entire text string is supported by a font.
    pub fn text_supported(&mut self, font_path: &Path, text: &str) -> bool {
        for c in text.chars() {
            if c.is_whitespace() || (c as u32) < 32 {
                continue;
            }
            if !self.char_supported(font_path, c) {
                return false;
            }
        }
        true
    }
}

// ── Text span splitting ────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Script {
    Khmer,
    English,
    Other,
}

pub struct TextSpan {
    pub text: String,
    pub script: Script,
}

/// Split text into contiguous script spans.
pub fn split_text_into_spans(text: &str) -> Vec<TextSpan> {
    if text.is_empty() {
        return vec![];
    }

    fn char_script(c: char) -> Script {
        let cp = c as u32;
        if (0x1780..=0x17FF).contains(&cp) || (0x19E0..=0x19FF).contains(&cp) {
            Script::Khmer
        } else if (0x41..=0x5A).contains(&cp)
            || (0x61..=0x7A).contains(&cp)
            || (0x30..=0x39).contains(&cp)
        {
            Script::English
        } else {
            Script::Other
        }
    }

    let mut spans: Vec<TextSpan> = Vec::new();
    let mut chars = text.chars();
    let first = chars.next().unwrap();
    let mut cur_script = char_script(first);
    let mut cur_buf = String::from(first);

    for ch in chars {
        let s = char_script(ch);
        if matches!(s, Script::Other) || s == cur_script {
            cur_buf.push(ch);
        } else {
            spans.push(TextSpan {
                text: cur_buf,
                script: cur_script,
            });
            cur_script = s;
            cur_buf = String::from(ch);
        }
    }
    spans.push(TextSpan {
        text: cur_buf,
        script: cur_script,
    });

    spans
}
