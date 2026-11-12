use std::path::Path;

/// The translation catalogs (engine/src/geonesclick/locales/<lang>.json), compiled into the installer: adding a
/// language is adding its file, with no code to change (src/i18n.rs).
fn catalogs() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../engine/src/geonesclick/locales");
    println!("cargo:rerun-if-changed={}", dir.display());
    let mut entries: Vec<_> = std::fs::read_dir(&dir)
        .expect("locales directory")
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    entries.sort();
    let mut code = String::from("pub static CATALOGS: &[(&str, &str)] = &[\n");
    for path in entries {
        let lang = path.file_stem().and_then(|s| s.to_str()).expect("catalog file name");
        let abs = path.canonicalize().expect("catalog path");
        code += &format!("    ({lang:?}, include_str!({:?})),\n", abs.display().to_string());
        println!("cargo:rerun-if-changed={}", abs.display());
    }
    code += "];\n";
    let out = Path::new(&std::env::var("OUT_DIR").expect("OUT_DIR")).join("catalogs.rs");
    std::fs::write(out, code).expect("write catalogs.rs");
}

fn main() {
    catalogs();
    tauri_build::build()
}
