//! First-launch assistant (AppImage).
//!
//! The AppImage is light: the engine (Python, PyTorch, StreetCLIP) is installed on first launch, in
//! ~/.local/share/geonesclick/engine/, AFTER the assistant has shown EVERYTHING that will be downloaded
//! (engine-bundle/downloads.json) and obtained your consent. The work itself is done by
//! engine-bundle/install-engine.sh (testable without a UI); this module checks the system, runs that script, relays
//! its progress to the UI and removes the engine on request ("Erase everything"). The GNOME shortcuts and the
//! applications-menu entry are in integration.rs.
//! In development (no engine-bundle), none of this: the engine comes from engine/.venv.

use std::collections::VecDeque;
use std::ffi::{OsStr, OsString};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex, PoisonError};

use serde::Serialize;
use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager};

use crate::i18n;

/// Variables that the AppImage launcher (AppRun, GTK hook) points into the AppImage. A program of the host
/// system must not inherit them: with PYTHONHOME set, the installed Python cannot find its standard library
/// ("No module named 'encodings'"); with LD_LIBRARY_PATH or GI_TYPELIB_PATH, the engine would load the
/// AppImage's GTK and GStreamer files instead of the system ones.
const APPIMAGE_VARS: [&str; 16] = [
    "PYTHONHOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH",
    "GST_PLUGIN_SYSTEM_PATH", "GST_PLUGIN_SYSTEM_PATH_1_0", "GI_TYPELIB_PATH", "GIO_MODULE_DIR",
    "GSETTINGS_SCHEMA_DIR", "GTK_DATA_PREFIX", "GTK_THEME", "GTK_EXE_PREFIX", "GTK_PATH", "GTK_IM_MODULE_FILE",
    "GDK_PIXBUF_MODULE_FILE",
];

/// A path list without the entries inside the AppImage (PATH, XDG_DATA_DIRS).
fn without_appdir(value: &OsStr, appdir: &Path) -> OsString {
    std::env::join_paths(std::env::split_paths(value).filter(|p| !p.starts_with(appdir))).unwrap_or_default()
}

/// A command for a program of the host system (engine, install script, gsettings), with the environment the
/// session had before the AppImage changed it. Outside an AppImage (development), nothing changes.
pub fn host_command(program: impl AsRef<OsStr>) -> Command {
    let mut command = Command::new(program);
    if let Some(appdir) = std::env::var_os("APPDIR").filter(|d| !d.is_empty()).map(PathBuf::from) {
        for var in APPIMAGE_VARS {
            command.env_remove(var);
        }
        for var in ["PATH", "XDG_DATA_DIRS"] {
            if let Some(value) = std::env::var_os(var) {
                command.env(var, without_appdir(&value, &appdir));
            }
        }
    }
    command
}

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
    /// Catalog key of its name, translated by the UI (a change of language applies to the list already shown).
    label: &'static str,
    ok: bool,
    package: &'static str,
}

const LIB_DIRS: [&str; 4] = ["/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib", "/lib/x86_64-linux-gnu"];

fn in_lib_dirs(rel: &str) -> bool {
    LIB_DIRS.iter().any(|d| Path::new(d).join(rel).exists())
}

/// The system's package manager: the command shown when a component is missing, and the Install button.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum PackageManager {
    Apt,
    Dnf,
    Pacman,
    Zypper,
}

impl PackageManager {
    const ALL: [PackageManager; 4] = [Self::Apt, Self::Dnf, Self::Pacman, Self::Zypper];

    fn binary(self) -> &'static str {
        match self {
            Self::Apt => "/usr/bin/apt-get",
            Self::Dnf => "/usr/bin/dnf",
            Self::Pacman => "/usr/bin/pacman",
            Self::Zypper => "/usr/bin/zypper",
        }
    }

    /// Arguments of an install without questions; the packages follow.
    fn install_args(self) -> &'static [&'static str] {
        match self {
            // A fresh Ubuntu often runs its automatic updates: wait for apt's lock instead of failing at once.
            Self::Apt => &["-o", "DPkg::Lock::Timeout=300", "install", "-y"],
            Self::Dnf => &["install", "-y"],
            Self::Pacman => &["-S", "--needed", "--noconfirm"],
            Self::Zypper => &["--non-interactive", "install"],
        }
    }
}

fn package_manager() -> Option<PackageManager> {
    PackageManager::ALL.into_iter().find(|pm| Path::new(pm.binary()).exists())
}

/// The package that ships a checked file, for each package manager: [apt, dnf, pacman, zypper]. Looked up in each
/// distribution's repositories (Ubuntu 24.04, Fedora 45, Arch, openSUSE Tumbleweed): which package owns the file.
/// Without a known package manager, Debian's name is shown as a hint.
fn package(pm: Option<PackageManager>, names: [&'static str; 4]) -> &'static str {
    match pm {
        Some(PackageManager::Apt) | None => names[0],
        Some(PackageManager::Dnf) => names[1],
        Some(PackageManager::Pacman) => names[2],
        Some(PackageManager::Zypper) => names[3],
    }
}

/// What screen capture needs from the system (present by default with GNOME); the package to install otherwise.
fn system_checks(pm: Option<PackageManager>) -> Vec<Check> {
    let portal = ["/usr/libexec", "/usr/lib", "/usr/lib/xdg-desktop-portal"]
        .iter()
        .any(|d| Path::new(d).join("xdg-desktop-portal").exists());
    let portal_gnome = ["/usr/libexec", "/usr/lib"].iter().any(|d| Path::new(d).join("xdg-desktop-portal-gnome").exists());
    let check = |label, ok, names| Check { label, ok, package: package(pm, names) };
    vec![
        check("setup.check.portal", portal, ["xdg-desktop-portal"; 4]),
        check("setup.check.portal_gnome", portal_gnome, ["xdg-desktop-portal-gnome"; 4]),
        check(
            "setup.check.gst_typelib",
            in_lib_dirs("girepository-1.0/Gst-1.0.typelib"),
            ["gir1.2-gstreamer-1.0", "gstreamer1", "gstreamer", "typelib-1_0-Gst-1_0"],
        ),
        check(
            "setup.check.gst_convert",
            in_lib_dirs("gstreamer-1.0/libgstapp.so")
                && (in_lib_dirs("gstreamer-1.0/libgstvideoconvertscale.so") || in_lib_dirs("gstreamer-1.0/libgstvideoconvert.so")),
            ["gstreamer1.0-plugins-base", "gstreamer1-plugins-base", "gst-plugins-base-libs", "gstreamer-plugins-base"],
        ),
        check(
            "setup.check.gst_pipewire",
            in_lib_dirs("gstreamer-1.0/libgstpipewire.so"),
            ["gstreamer1.0-pipewire", "pipewire-gstreamer", "gst-plugin-pipewire", "gstreamer-plugin-pipewire"],
        ),
        check(
            "setup.check.gobject",
            in_lib_dirs("libgirepository-2.0.so.0"),
            ["libgirepository-2.0-0", "glib2", "glib2", "libgirepository-2_0-0"],
        ),
        check("setup.check.cairo", in_lib_dirs("libcairo.so.2"), ["libcairo2", "cairo", "cairo", "libcairo2"]),
    ]
}

const PKEXEC: &str = "/usr/bin/pkexec";

/// Installs the missing system packages (system_checks) with the system's package manager, as root through pkexec:
/// the system asks for the password in its own window. The list comes from the checks, never from the UI. A clean
/// Ubuntu 24.04 lacks libgirepository-2.0-0. Only apt is tested for real; the command stays shown.
#[tauri::command]
pub async fn setup_system_install() -> Result<(), String> {
    let Some(pm) = package_manager().filter(|_| Path::new(PKEXEC).exists()) else {
        return Err(i18n::tr("setup.system.cannot_install", &[]));
    };
    let packages: Vec<&'static str> = system_checks(Some(pm)).into_iter().filter(|c| !c.ok).map(|c| c.package).collect();
    if packages.is_empty() {
        return Ok(());
    }
    // Waits for the password and for the package manager: off the UI thread.
    let out = tauri::async_runtime::spawn_blocking(move || {
        host_command(PKEXEC)
            .arg(pm.binary())
            .args(pm.install_args())
            .args(&packages)
            .stdin(Stdio::null())
            .output()
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e| i18n::tr("setup.system.install_failed", &[("error", &e.to_string())]))?;
    install_outcome(&i18n::current(), out.status.code(), &String::from_utf8_lossy(&out.stderr))
}

/// What pkexec + the package manager ended with: 126 / 127 are pkexec's (password dialog dismissed, not authorised),
/// any other failure is the package manager's, explained by its last error line (in `lang`).
fn install_outcome(lang: &str, code: Option<i32>, stderr: &str) -> Result<(), String> {
    match code {
        Some(0) => Ok(()),
        Some(126 | 127) => Err(i18n::t(lang, "setup.system.install_cancelled", &[])),
        _ => {
            let last = stderr.lines().rev().map(str::trim).find(|l| !l.is_empty()).unwrap_or("?");
            Err(i18n::t(lang, "setup.system.install_failed", &[("error", last)]))
        }
    }
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
    /// Installed for this version, but the choices are not written yet (window closed before the end).
    engine_ready: bool,
    gpu: bool,
    checks: Vec<Check>,
    package_manager: Option<PackageManager>,
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
        engine_ready: venv_python().is_file()
            && bundle.as_ref().and_then(|b| read_version(&b.join("VERSION"))).is_some_and(|v| {
                read_version(&engine_home().join("INSTALLED")).as_deref() == Some(v.as_str())
            }),
        gpu: has_nvidia(),
        checks: system_checks(package_manager()),
        package_manager: package_manager(),
        downloads: file("downloads.json"),
        packages_cuda: file("packages-cuda.json"),
        packages_cpu: file("packages-cpu.json"),
    }
}

#[derive(Serialize, Clone)]
struct Progress {
    phase: Option<String>,
    line: Option<String>,
    done: bool,
    ok: bool,
    /// On failure, its likely cause in plain words (see diagnose); the log keeps the details.
    reason: Option<String>,
}

impl Progress {
    fn line(line: String, phase: Option<String>) -> Self {
        Progress { phase, line: Some(line), done: false, ok: true, reason: None }
    }
}

/// Error lines kept to explain a failure: uv and geonesclick.fetch write their cause in the last ones.
const ERROR_TAIL: usize = 40;

/// Words of a download that failed (uv, huggingface_hub, geonesclick.fetch), compared in lower case.
const NETWORK_SIGNS: [&str; 12] = [
    "error sending request", "dns error", "request failed after", "failed to download", "failed to fetch",
    "server error", "timed out", "connection", "name or service not known", "temporary failure in name resolution",
    "network is unreachable", "not downloaded from",
];

/// The host of the first https:// URL in a line.
fn url_host(line: &str) -> Option<&str> {
    let rest = &line[line.find("https://")? + "https://".len()..];
    let end = rest
        .find(|c: char| matches!(c, '/' | ':' | ')' | '`' | '\'' | '"') || c.is_whitespace())
        .unwrap_or(rest.len());
    Some(&rest[..end]).filter(|h| !h.is_empty())
}

/// The download site behind a host (the hosts of downloads.json), as the catalog key of its name.
fn service(host: &str) -> Option<&'static str> {
    let is = |domain: &str| host == domain || host.ends_with(&format!(".{domain}"));
    if is("github.com") || is("githubusercontent.com") {
        Some("setup.site.github")
    } else if is("pypi.org") || is("pythonhosted.org") {
        Some("setup.site.pypi")
    } else if is("pytorch.org") {
        Some("setup.site.pytorch")
    } else if is("huggingface.co") || is("hf.co") {
        Some("setup.site.huggingface")
    } else {
        None
    }
}

/// Why install-engine.sh failed, in plain words and in `lang`: disk full, or a download site that does not answer
/// (named from the URL in the error, otherwise from the phase). None when the cause is something else: the log
/// shows it.
fn diagnose(lang: &str, phase: &str, variant: &str, errors: &[String]) -> Option<String> {
    if errors.iter().any(|l| l.contains("No space left on device") || l.contains("os error 28")) {
        return Some(i18n::t(lang, "setup.fail.disk", &[]));
    }
    let network: Vec<&String> = errors
        .iter()
        .filter(|l| {
            let lower = l.to_lowercase();
            NETWORK_SIGNS.iter().any(|s| lower.contains(s))
        })
        .collect();
    if network.is_empty() {
        return None;
    }
    let named = network.iter().rev().filter_map(|l| url_host(l)).find_map(service);
    let site = named.or(match (phase, variant) {
        ("python", _) => Some("setup.site.github"),
        ("packages", "cpu") => Some("setup.site.pypi_or_pytorch"),
        ("packages", _) => Some("setup.site.pypi"),
        ("model", _) => Some("setup.site.huggingface"),
        _ => None,
    });
    Some(match site {
        Some(key) => i18n::t(lang, "setup.fail.site", &[("site", &i18n::t(lang, key, &[]))]),
        None => i18n::t(lang, "setup.fail.some_site", &[]),
    })
}

/// Runs install-engine.sh ("cuda" or "cpu" variant), after your consent to the required block. Your options are
/// chosen meanwhile and applied afterwards by setup_apply, BEFORE the engine's first start.
/// Progress arrives as "setup-progress" events: script phases and output lines.
#[tauri::command]
pub fn setup_install(app: AppHandle, variant: String) -> Result<(), String> {
    let bundle = bundle_dir(&app).ok_or_else(|| i18n::tr("setup.error.no_bundle", &[]))?;
    if variant != "cuda" && variant != "cpu" {
        return Err(i18n::tr("setup.error.variant", &[]));
    }
    std::fs::create_dir_all(engine_home()).map_err(|e| e.to_string())?;

    let mut child = host_command("/bin/sh")
        .arg(bundle.join("install-engine.sh"))
        .arg(&variant)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| i18n::tr("setup.error.launch", &[("error", &e.to_string())]))?;

    // Script errors (stderr) relayed as is, like its output. The last ones of the current phase are kept to explain
    // a failure: a retry that succeeded in an earlier phase (Hugging Face's "Retrying…") must not be blamed for it.
    let tail = Arc::new(Mutex::new(VecDeque::with_capacity(ERROR_TAIL)));
    let reader = child.stderr.take().map(|err| {
        let (app, tail) = (app.clone(), Arc::clone(&tail));
        std::thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                let _ = app.emit("setup-progress", Progress::line(line.clone(), None));
                let mut tail = tail.lock().unwrap_or_else(PoisonError::into_inner);
                if tail.len() == ERROR_TAIL {
                    tail.pop_front();
                }
                tail.push_back(line);
            }
        })
    });
    let stdout = child.stdout.take().ok_or_else(|| i18n::tr("setup.error.no_output", &[]))?;
    let lang = i18n::current(); // the failure is explained in the language of the moment
    std::thread::spawn(move || {
        let mut last_phase = String::new();
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            let phase = line.strip_prefix("PHASE ").map(str::to_string);
            if let Some(p) = &phase {
                last_phase.clone_from(p);
                tail.lock().unwrap_or_else(PoisonError::into_inner).clear();
            }
            let _ = app.emit("setup-progress", Progress::line(line, phase));
        }
        let ok = child.wait().map(|s| s.success()).unwrap_or(false);
        if let Some(reader) = reader {
            let _ = reader.join(); // its last lines hold the cause
        }
        let errors = Vec::from(std::mem::take(&mut *tail.lock().unwrap_or_else(PoisonError::into_inner)));
        let reason = if ok { None } else { diagnose(&lang, &last_phase, &variant, &errors) };
        let _ = app.emit("setup-progress", Progress { phase: None, line: None, done: true, ok, reason });
    });
    Ok(())
}

/// Your options (settings accepted or declined) and your API key, written by the installed engine BEFORE its first
/// start: it will never download a declined option. Same checks as the Settings screen.
#[tauri::command]
pub fn setup_apply(app: AppHandle, choices: Value, api_key: Option<String>) -> Result<(), String> {
    let mut child = host_command(venv_python())
        .args(["-m", "geonesclick.settings"])
        .stdin(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| i18n::tr("setup.error.engine", &[("error", &e.to_string())]))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(&serde_json::to_vec(&choices).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    }
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    if let Some(key) = api_key.filter(|k| !k.trim().is_empty()) {
        if !store_key(&key) {
            return Err(i18n::tr("setup.error.key", &[]));
        }
    }
    // Only now may the engine start: it follows these choices, never the defaults.
    let bundle = bundle_dir(&app).ok_or_else(|| i18n::tr("setup.error.no_bundle", &[]))?;
    std::fs::copy(bundle.join("VERSION"), engine_home().join("VERSION")).map_err(|e| e.to_string())?;
    Ok(())
}

fn store_key(key: &str) -> bool {
    let Ok(mut child) = host_command(venv_python())
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

/// "Erase everything" with the engine box ticked: removes ~/.local/share/geonesclick/engine (AppImage only; never the
/// development engine/.venv). The engine must be stopped first (see lib.rs).
pub fn remove_engine(app: &AppHandle) -> Result<(), String> {
    if bundle_dir(app).is_none() {
        return Err("in development, the engine (engine/.venv) is not removed".into());
    }
    let home = engine_home();
    if home.ends_with("geonesclick/engine") && home.is_dir() {
        std::fs::remove_dir_all(&home).map_err(|e| e.to_string())?;
    }
    // The engine was the last thing in ~/.local/share/geonesclick (the engine erased the rest): the folder goes if
    // it is empty, never with something in it.
    let _ = std::fs::remove_dir(data_dir());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn appimage_entries_are_dropped_from_path_lists() {
        let value = OsString::from("/tmp/.mount_GeoNes/usr/bin:/usr/local/bin:/usr/bin:/tmp/.mount_GeoNes/bin");
        assert_eq!(without_appdir(&value, Path::new("/tmp/.mount_GeoNes")), OsString::from("/usr/local/bin:/usr/bin"));
    }

    #[test]
    fn missing_components_are_named_for_the_system_package_manager() {
        let names = |pm| system_checks(pm).into_iter().map(|c| c.package).collect::<Vec<_>>();
        let common = ["xdg-desktop-portal", "xdg-desktop-portal-gnome"];
        assert_eq!(names(Some(PackageManager::Dnf))[2..], ["gstreamer1", "gstreamer1-plugins-base", "pipewire-gstreamer", "glib2", "cairo"]);
        assert_eq!(names(Some(PackageManager::Pacman))[2..], ["gstreamer", "gst-plugins-base-libs", "gst-plugin-pipewire", "glib2", "cairo"]);
        assert_eq!(
            names(Some(PackageManager::Zypper))[2..],
            ["typelib-1_0-Gst-1_0", "gstreamer-plugins-base", "gstreamer-plugin-pipewire", "libgirepository-2_0-0", "libcairo2"]
        );
        assert_eq!(names(None), names(Some(PackageManager::Apt)));
        for pm in [None, Some(PackageManager::Dnf), Some(PackageManager::Pacman), Some(PackageManager::Zypper)] {
            assert_eq!(names(pm)[..2], common);
        }
    }

    #[test]
    fn the_system_install_tells_a_refused_password_from_an_apt_failure() {
        assert_eq!(install_outcome("en", Some(0), ""), Ok(()));
        let cancelled = i18n::t("en", "setup.system.install_cancelled", &[]);
        assert_eq!(install_outcome("en", Some(126), ""), Err(cancelled.clone()));
        assert_eq!(install_outcome("en", Some(127), "Error executing command as another user"), Err(cancelled));
        let failed = install_outcome("fr", Some(100), "Reading package lists...\nE: Unable to locate package libgirepository-2.0-0\n\n")
            .unwrap_err();
        assert!(failed.ends_with("E: Unable to locate package libgirepository-2.0-0"), "{failed}");
        assert!(failed.starts_with("L'installation des composants a échoué"), "{failed}");
        assert!(install_outcome("en", None, "").unwrap_err().ends_with('?'));
    }

    fn lines(text: &str) -> Vec<String> {
        text.lines().map(str::to_string).collect()
    }

    // Error outputs captured with uv 0.9.17 and huggingface_hub 2.4 with unreachable hosts, then given the
    // real host names; the 504 one is written by hand in reqwest's format (uv's HTTP client).
    const UV_PYTHON: &str = "error: Request failed after 5 retries
  Caused by: Failed to download https://github.com/astral-sh/python-build-standalone/releases/download/20251209/cpython-3.12.12%2B20251209-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz
  Caused by: error sending request for url (https://github.com/astral-sh/python-build-standalone/releases/download/20251209/cpython-3.12.12%2B20251209-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz)
  Caused by: client error (Connect)
  Caused by: dns error
  Caused by: failed to lookup address information: Name or service not known";
    const UV_PYPI: &str = "error: Failed to fetch: `https://pypi.org/simple/idna/`
  Caused by: Request failed after 5 retries
  Caused by: error sending request for url (https://pypi.org/simple/idna/)
  Caused by: client error (Connect)
  Caused by: dns error";
    const UV_PYTORCH_504: &str = "error: Failed to download `torch==2.9.1+cpu`
  Caused by: Request failed after 5 retries
  Caused by: HTTP status server error (504 Gateway Timeout) for url (https://download.pytorch.org/whl/cpu/torch-2.9.1%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl)";
    const HF: &str = "'[Errno -2] Name or service not known' thrown while requesting HEAD https://huggingface.co/geolocal/StreetCLIP/resolve/abc/config.json
Retrying in 8s [Retry 5/5].
error: geolocal/StreetCLIP/config.json not downloaded from https://huggingface.co/: LocalEntryNotFoundError: An error happened while trying to locate the file on the Hub.";

    fn site(reason: Option<String>) -> String {
        let reason = reason.expect("a cause");
        assert!(reason.ends_with("What is already downloaded is kept."), "{reason}");
        reason
    }

    #[test]
    fn an_unreachable_site_is_named_from_the_url_in_the_error() {
        let named = |phase, variant, text: &str| site(diagnose("en", phase, variant, &lines(text)));
        assert!(named("python", "cpu", UV_PYTHON).starts_with("The site GitHub (Python) does not answer."));
        assert!(named("packages", "cuda", UV_PYPI).starts_with("The site PyPI (Python libraries) does not answer."));
        assert!(named("packages", "cpu", UV_PYTORCH_504).starts_with("The site download.pytorch.org (PyTorch)"));
        assert!(named("model", "cpu", HF).starts_with("The site Hugging Face (StreetCLIP model)"));
        // Several sites in the errors: the last one named is the one that made the step fail.
        assert!(named("packages", "cpu", &format!("{UV_PYPI}\n{UV_PYTORCH_504}")).starts_with("The site download.pytorch.org"));
    }

    #[test]
    fn the_cause_is_told_in_the_language_asked() {
        let reason = diagnose("fr", "python", "cpu", &lines(UV_PYTHON)).expect("a cause");
        assert!(reason.starts_with("Le site GitHub (Python) ne répond pas."), "{reason}");
        assert!(reason.ends_with("Ce qui est déjà téléchargé est gardé."), "{reason}");
    }

    #[test]
    fn without_a_known_url_the_phase_names_the_site() {
        // A host that is none of the installation's sites (a mirror, say): download.geonames.org stands for it,
        // because test_downloads.py forbids undeclared addresses in the code.
        let other = lines("error: Failed to fetch: `https://download.geonames.org/simple/idna/`\n  Caused by: dns error");
        assert!(site(diagnose("en", "packages", "cpu", &other)).starts_with("The site PyPI or download.pytorch.org"));
        assert!(site(diagnose("en", "packages", "cuda", &other)).starts_with("The site PyPI (Python libraries)"));
        assert!(site(diagnose("en", "python", "cuda", &lines("Caused by: dns error"))).starts_with("The site GitHub (Python)"));
        assert!(site(diagnose("en", "engine", "cuda", &other)).starts_with("A download site does not answer."));
    }

    #[test]
    fn a_full_disk_is_told_before_anything_else() {
        let full = lines(&format!("{UV_PYPI}\nerror: failed to write to file `/x`: No space left on device (os error 28)"));
        assert!(site(diagnose("en", "packages", "cpu", &full)).starts_with("Not enough disk space"));
    }

    #[test]
    fn other_failures_are_left_to_the_log() {
        assert_eq!(diagnose("en", "choices", "cpu", &lines("ValueError: unknown setting")), None);
        assert_eq!(diagnose("en", "python", "cpu", &[]), None);
    }

    #[test]
    fn hosts_are_read_from_urls_and_matched_by_domain() {
        assert_eq!(url_host("for url (https://pypi.org/simple/idna/)"), Some("pypi.org"));
        assert_eq!(url_host("`https://files.pythonhosted.org`"), Some("files.pythonhosted.org"));
        assert_eq!(url_host("no url here"), None);
        assert_eq!(service("objects.githubusercontent.com"), Some("setup.site.github"));
        assert_eq!(service("cas-bridge.xethub.hf.co"), Some("setup.site.huggingface"));
        assert_eq!(service("evilgithub.com"), None);
    }
}
