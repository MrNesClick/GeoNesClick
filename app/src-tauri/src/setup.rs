//! First-launch assistant (AppImage): decided with the user on 2026-11-07.
//!
//! The AppImage is light: the engine (Python, PyTorch, StreetCLIP) is installed on first launch, in
//! ~/.local/share/geonesclick/engine/, AFTER the assistant has shown EVERYTHING that will be downloaded
//! (engine-bundle/downloads.json) and obtained your consent. The work itself is done by
//! engine-bundle/install-engine.sh (testable without a UI); this module checks the system, runs that script, relays
//! its progress to the UI, installs the GNOME shortcuts and removes the engine on request ("Erase everything").
//! In development (no engine-bundle), none of this: the engine comes from engine/.venv.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use serde::Serialize;
use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager};

/// Resources bundled in the AppImage (None in development).
pub fn bundle_dir(app: &AppHandle) -> Option<PathBuf> {
    let dir = app.path().resource_dir().ok()?.join("engine-bundle");
    dir.join("VERSION").is_file().then_some(dir)
}

pub fn data_dir() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/share"))
        .join("geonesclick")
}

pub fn engine_home() -> PathBuf {
    data_dir().join("engine")
}

pub fn venv_python() -> PathBuf {
    engine_home().join("venv/bin/python")
}

fn read_version(path: &Path) -> Option<String> {
    std::fs::read_to_string(path).ok().map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

/// Does the engine need installing (first launch) or updating (different AppImage version)?
pub fn needed(app: &AppHandle) -> bool {
    match bundle_dir(app) {
        None => false,
        Some(bundle) => {
            !venv_python().is_file() || read_version(&bundle.join("VERSION")) != read_version(&engine_home().join("VERSION"))
        }
    }
}

#[derive(Serialize)]
struct Check {
    label: &'static str,
    ok: bool,
    package: &'static str,
}

const LIB_DIRS: [&str; 4] = ["/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib", "/lib/x86_64-linux-gnu"];

fn in_lib_dirs(rel: &str) -> bool {
    LIB_DIRS.iter().any(|d| Path::new(d).join(rel).exists())
}

/// What screen capture needs from the system (present by default on Ubuntu GNOME); Ubuntu package to install otherwise.
fn system_checks() -> Vec<Check> {
    let portal = ["/usr/libexec", "/usr/lib", "/usr/lib/xdg-desktop-portal"]
        .iter()
        .any(|d| Path::new(d).join("xdg-desktop-portal").exists());
    let portal_gnome = ["/usr/libexec", "/usr/lib"].iter().any(|d| Path::new(d).join("xdg-desktop-portal-gnome").exists());
    vec![
        Check { label: "Portail de partage d'écran", ok: portal, package: "xdg-desktop-portal" },
        Check { label: "Portail de partage d'écran (GNOME)", ok: portal_gnome, package: "xdg-desktop-portal-gnome" },
        Check { label: "GStreamer (descriptions)", ok: in_lib_dirs("girepository-1.0/Gst-1.0.typelib"), package: "gir1.2-gstreamer-1.0" },
        Check {
            label: "GStreamer (conversion vidéo)",
            ok: in_lib_dirs("gstreamer-1.0/libgstapp.so")
                && (in_lib_dirs("gstreamer-1.0/libgstvideoconvertscale.so") || in_lib_dirs("gstreamer-1.0/libgstvideoconvert.so")),
            package: "gstreamer1.0-plugins-base",
        },
        Check { label: "GStreamer (source PipeWire)", ok: in_lib_dirs("gstreamer-1.0/libgstpipewire.so"), package: "gstreamer1.0-pipewire" },
        Check { label: "GObject Introspection", ok: in_lib_dirs("libgirepository-2.0.so.0"), package: "libgirepository-2.0-0" },
        Check { label: "Cairo", ok: in_lib_dirs("libcairo.so.2"), package: "libcairo2" },
    ]
}

fn has_nvidia() -> bool {
    Path::new("/proc/driver/nvidia/version").exists()
}

fn read_json(path: &Path) -> Value {
    std::fs::read_to_string(path).ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or(Value::Null)
}

#[derive(Serialize)]
pub struct Status {
    bundled: bool,
    needed: bool,
    version: Option<String>,
    installed: Option<String>,
    gpu: bool,
    checks: Vec<Check>,
    downloads: Value,
    packages_cuda: Value,
    packages_cpu: Value,
}

#[tauri::command]
pub fn setup_status(app: AppHandle) -> Status {
    let bundle = bundle_dir(&app);
    let file = |name: &str| bundle.as_ref().map(|b| read_json(&b.join(name))).unwrap_or(Value::Null);
    Status {
        bundled: bundle.is_some(),
        needed: needed(&app),
        version: bundle.as_ref().and_then(|b| read_version(&b.join("VERSION"))),
        installed: read_version(&engine_home().join("VERSION")),
        gpu: has_nvidia(),
        checks: system_checks(),
        downloads: file("downloads.json"),
        packages_cuda: file("packages-cuda.json"),
        packages_cpu: file("packages-cpu.json"),
    }
}

#[derive(Serialize, Clone)]
struct Progress {
    phase: Option<String>,
    line: Option<String>,
    bytes: Option<u64>,
    done: bool,
    ok: bool,
}

fn dir_size(path: &Path) -> u64 {
    let Ok(entries) = std::fs::read_dir(path) else { return 0 };
    entries
        .flatten()
        .map(|e| match e.file_type() {
            Ok(t) if t.is_dir() => dir_size(&e.path()),
            Ok(t) if t.is_file() => e.metadata().map(|m| m.len()).unwrap_or(0),
            _ => 0,
        })
        .sum()
}

/// Runs install-engine.sh ("cuda" or "cpu" variant), after your consent to the required block. Your options are
/// chosen meanwhile and applied afterwards by setup_apply, BEFORE the engine's first start.
/// Progress arrives as "setup-progress" events: script phases, output lines, downloaded bytes
/// (size of the uv and Hugging Face caches).
#[tauri::command]
pub fn setup_install(app: AppHandle, variant: String) -> Result<(), String> {
    let bundle = bundle_dir(&app).ok_or("pas d'AppImage : rien à installer")?;
    if variant != "cuda" && variant != "cpu" {
        return Err("variante inconnue".into());
    }
    std::fs::create_dir_all(engine_home()).map_err(|e| e.to_string())?;

    let mut child = Command::new("/bin/sh")
        .arg(bundle.join("install-engine.sh"))
        .arg(&variant)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("installation impossible à lancer : {e}"))?;

    // Downloaded bytes: uv and Hugging Face caches (packages and the model land there first).
    let running = Arc::new(AtomicBool::new(true));
    {
        let (app, running) = (app.clone(), running.clone());
        let hf = std::env::var_os("HF_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".cache/huggingface"));
        let start = dir_size(&hf);
        std::thread::spawn(move || {
            while running.load(Ordering::Relaxed) {
                let bytes = dir_size(&engine_home().join("cache")) + dir_size(&hf).saturating_sub(start);
                let _ = app.emit("setup-progress", Progress { phase: None, line: None, bytes: Some(bytes), done: false, ok: true });
                std::thread::sleep(Duration::from_secs(1));
            }
        });
    }
    // Script errors (stderr) relayed as is, like its output.
    if let Some(err) = child.stderr.take() {
        let app = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                let _ = app.emit("setup-progress", Progress { phase: None, line: Some(line), bytes: None, done: false, ok: true });
            }
        });
    }
    let stdout = child.stdout.take().ok_or("sortie de l'installation indisponible")?;
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            let phase = line.strip_prefix("PHASE ").map(str::to_string);
            let _ = app.emit("setup-progress", Progress { phase, line: Some(line), bytes: None, done: false, ok: true });
        }
        let ok = child.wait().map(|s| s.success()).unwrap_or(false);
        running.store(false, Ordering::Relaxed);
        let _ = app.emit("setup-progress", Progress { phase: None, line: None, bytes: None, done: true, ok });
    });
    Ok(())
}

/// Your options (settings accepted or declined) and your API key, written by the installed engine BEFORE its first
/// start: it will never download a declined option. Same checks as the Settings screen.
#[tauri::command]
pub fn setup_apply(choices: Value, api_key: Option<String>) -> Result<(), String> {
    let mut child = Command::new(venv_python())
        .args(["-m", "geonesclick.settings"])
        .stdin(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("moteur introuvable : {e}"))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(&serde_json::to_vec(&choices).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    }
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    if let Some(key) = api_key.filter(|k| !k.trim().is_empty()) {
        if !store_key(&key) {
            return Err("clé API refusée (8 à 300 caractères, sans espace) : corrige-la ou passe cette étape".into());
        }
    }
    Ok(())
}

fn store_key(key: &str) -> bool {
    let Ok(mut child) = Command::new(venv_python())
        .args(["-m", "geonesclick.apikey"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    else {
        return false;
    };
    if let Some(mut stdin) = child.stdin.take() {
        let _ = writeln!(stdin, "{}", key.trim());
    }
    child.wait().map(|s| s.success()).unwrap_or(false)
}

const MEDIA_KEYS: &str = "org.gnome.settings-daemon.plugins.media-keys";
const KEY_ROOT: &str = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings";

fn gsettings(args: &[&str]) -> Result<String, String> {
    let out = Command::new("/usr/bin/gsettings").args(args).output().map_err(|e| format!("gsettings : {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// GNOME shortcuts: Super+Shift+G (capture) and Super+Shift+Z (marks), pointing to the installed engine's trigger.
#[tauri::command]
pub fn setup_shortcuts(app: AppHandle) -> Result<(), String> {
    let python = if bundle_dir(&app).is_some() {
        venv_python()
    } else {
        return Err("en développement, utilise scripts/install.sh --setup-shortcut".into());
    };
    let current = gsettings(&["get", MEDIA_KEYS, "custom-keybindings"])?;
    let mut keys: Vec<String> = current.split('\'').skip(1).step_by(2).map(str::to_string).collect();
    for (id, name, action, binding) in [
        ("geonesclick", "GeoNesClick – capture", "capture", "<Super><Shift>g"),
        ("geonesclick-mark", "GeoNesClick – marques", "mark", "<Super><Shift>z"),
    ] {
        let path = format!("{KEY_ROOT}/{id}/");
        if !keys.contains(&path) {
            keys.push(path.clone());
        }
        let schema = format!("{MEDIA_KEYS}.custom-keybinding:{path}");
        gsettings(&["set", &schema, "name", name])?;
        gsettings(&["set", &schema, "command", &format!("{} -m geonesclick.trigger {action}", python.display())])?;
        gsettings(&["set", &schema, "binding", binding])?;
    }
    let list = format!("[{}]", keys.iter().map(|k| format!("'{k}'")).collect::<Vec<_>>().join(", "));
    gsettings(&["set", MEDIA_KEYS, "custom-keybindings", &list])?;
    Ok(())
}

/// "Erase everything" with the engine box ticked: removes ~/.local/share/geonesclick/engine (AppImage only; never the
/// development engine/.venv). The engine must be stopped first (see lib.rs).
pub fn remove_engine(app: &AppHandle) -> Result<(), String> {
    if bundle_dir(app).is_none() {
        return Err("en développement, le moteur (engine/.venv) n'est pas retiré".into());
    }
    let home = engine_home();
    if home.ends_with("geonesclick/engine") && home.is_dir() {
        std::fs::remove_dir_all(&home).map_err(|e| e.to_string())?;
    }
    Ok(())
}
