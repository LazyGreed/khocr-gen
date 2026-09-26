# Preserve OCR ground truth

paths: src/khocr_gen/**, rust/**

Rendering, effects, and augmentation must not silently make the stored OCR label disagree with the intended text. Any intentional label transformation must be explicit and tested.

# Keep configuration behavior compatible

paths: src/khocr_gen/config.py, src/khocr_gen/config_loader.py, src/khocr_gen/cli.py, configs/**

Don't silently rename, remove, or reinterpret CLI flags or YAML keys. CLI values must continue to override YAML, and YAML must continue to override built-in defaults.

# Keep Rust acceleration optional

paths: src/khocr_gen/_rust_accel.py, src/khocr_gen/augmentation.py, src/khocr_gen/fonts.py, rust/**

Changes to accelerated behavior must preserve a usable Python fallback unless removal of that fallback is explicitly part of the task.

# Preserve reproducibility

paths: src/khocr_gen/**

Don't introduce uncontrolled randomness into seeded generation. New random behavior must use the pipeline's seeded randomness and have regression coverage where practical.

# Protect dataset semantics

paths: src/khocr_gen/corpus.py, src/khocr_gen/data_generator.py, src/khocr_gen/lmdb_pack.py, src/khocr_gen/combine.py

Don't silently change split membership, labels, metadata, ordering guarantees, or storage formats relied on by existing datasets and training pipelines.

# Don't hide incomplete work

Don't make failures disappear with skipped tests, broad exception swallowing, fake success paths, placeholder implementations, or untracked TODOs.

# Verify behavioral changes

paths: src/**, rust/**

Add or update focused tests for changed behavior. Run the relevant lint, tests, type checks, and Rust checks before claiming the change is complete.

# Keep documentation tied to reality

paths: README.md, docs/**, wiki/**, configs/**, AGENTS.md, pi-warden.md

Document behavior that exists in the code. Keep examples, commands, config names, and links synchronized with the implementation.

# Keep edits scoped

Avoid unrelated refactors, formatting churn, dependency changes, or documentation rewrites outside the task being solved.
