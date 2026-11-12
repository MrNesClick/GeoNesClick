//! GNOME integration, chosen in the installer and changed in the Settings, removed by "Erase everything":
//! - the keyboard shortcuts Super+Shift+G (capture) and Super+Shift+Z (marks), written with gsettings;
//! - the applications-menu entry: a .desktop file in ~/.local/share/applications and the icon in the user's hicolor
//!   theme. GNOME shows the app's icon in the dock only through it: it matches the window to the entry by
//!   StartupWMClass, the program name (GTK's Wayland app id; Tauri's enableGTKAppId stays off, it would forbid a
//!   second instance). The entry points to the AppImage file, rewritten at each launch if the file moved.

use std::path::{Path, PathBuf};

use serde::Serialize;
use tauri::AppHandle;

use crate::i18n;
use crate::setup::{bundle_dir, host_command, venv_python};

const DESKTOP_ID: &str = "fr.mrnesclick.geonesclick";
/// GTK's Wayland app id and X11 WM_CLASS: the program name (the binary is "geonesclick").
const WM_CLASS: &str = "geonesclick";
const ICONS: [(&str, &[u8]); 2] =
    [("128x128", include_bytes!("../icons/128x128.png")), ("256x256", include_bytes!("../icons/128x128@2x.png"))];

const MEDIA_KEYS: &str = "org.gnome.settings-daemon.plugins.media-keys";
const KEY_ROOT: &str = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings";
/// Our shortcuts: id (path under KEY_ROOT), catalog key of the name shown in GNOME's settings, action, keys.
const SHORTCUTS: [(&str, &str, &str, &str); 2] = [
    ("geonesclick", "setup.shortcut.capture", "capture", "<Super><Shift>g"),
    ("geonesclick-mark", "setup.shortcut.mark", "mark", "<Super><Shift>z"),
];

fn data_home() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/share"))
}

fn desktop_file(data: &Path) -> PathBuf {
    data.join("applications").join(format!("{DESKTOP_ID}.desktop"))
}

fn icon_file(data: &Path, size: &str) -> PathBuf {
    data.join("icons/hicolor").join(size).join("apps").join(format!("{DESKTOP_ID}.png"))
}

/// The AppImage file being run (None in development).
fn appimage() -> Option<PathBuf> {
    std::env::var_os("APPIMAGE").filter(|v| !v.is_empty()).map(PathBuf::from).filter(|p| p.is_file())
}

/// A path as one quoted argument of an Exec key (Desktop Entry Specification): `"`, `` ` ``, `$` and `\` escaped
/// inside the quotes, then each `\` doubled again as in any string value, `%` doubled. None for a path that a
/// .desktop line cannot hold (a line break or another control character).
fn exec_arg(path: &Path) -> Option<String> {
    let path = path.to_str()?;
    if path.chars().any(char::is_control) {
        return None;
    }
    let mut out = String::from("\"");
    for c in path.chars() {
        match c {
            '"' | '`' | '$' => {
                out.push_str("\\\\");
                out.push(c);
            }
            '\\' => out.push_str("\\\\\\\\"),
            '%' => out.push_str("%%"),
            _ => out.push(c),
        }
    }
    out.push('"');
    Some(out)
}

fn desktop_entry(exec: &str, comment: &str) -> String {
    format!(
        "[Desktop Entry]\nType=Application\nName=GeoNesClick\nComment={comment}\nExec={exec}\nIcon={DESKTOP_ID}\n\
         StartupWMClass={WM_CLASS}\nCategories=Game;Education;\nTerminal=false\n"
    )
}

fn write_entry(data: &Path, appimage: &Path) -> Result<(), String> {
    let exec = exec_arg(appimage).ok_or_else(|| i18n::tr("integration.error.path", &[]))?;
    let comment = i18n::tr("integration.menu.comment", &[]).replace(['\n', '\r'], " ");
    for (size, bytes) in ICONS {
        let file = icon_file(data, size);
        std::fs::create_dir_all(file.parent().unwrap_or(data)).map_err(|e| e.to_string())?;
        std::fs::write(&file, bytes).map_err(|e| e.to_string())?;
    }
    let file = desktop_file(data);
    std::fs::create_dir_all(file.parent().unwrap_or(data)).map_err(|e| e.to_string())?;
    std::fs::write(&file, desktop_entry(&exec, &comment)).map_err(|e| e.to_string())
}

fn remove_entry(data: &Path) -> Result<(), String> {
    let files = std::iter::once(desktop_file(data)).chain(ICONS.iter().map(|(size, _)| icon_file(data, size)));
    for file in files {
        match std::fs::remove_file(&file) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => return Err(e.to_string()),
            _ => {}
        }
    }
    Ok(())
}

/// At each launch: an existing entry is pointed again at the AppImage being run (moved, or a new version's file).
pub fn refresh_menu_entry() {
    let data = data_home();
    if let (true, Some(appimage)) = (desktop_file(&data).is_file(), appimage()) {
        let _ = write_entry(&data, &appimage);
    }
}

fn gsettings(args: &[&str]) -> Result<String, String> {
    let out = host_command("/usr/bin/gsettings").args(args).output().map_err(|e| format!("gsettings: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn path_of(id: &str) -> String {
    format!("{KEY_ROOT}/{id}/")
}

/// The custom-keybindings list ("['/a/', '/b/']", or "@as []" when empty) as paths.
fn parse_list(value: &str) -> Vec<String> {
    value.split('\'').skip(1).step_by(2).map(str::to_string).collect()
}

fn format_list(keys: &[String]) -> String {
    format!("[{}]", keys.iter().map(|k| format!("'{k}'")).collect::<Vec<_>>().join(", "))
}

/// The list without our two shortcuts: the user's own stay, in their order.
fn without_ours(keys: &[String]) -> Vec<String> {
    let ours: Vec<String> = SHORTCUTS.iter().map(|(id, ..)| path_of(id)).collect();
    keys.iter().filter(|k| !ours.contains(k)).cloned().collect()
}

fn shortcuts_on(keys: &[String]) -> bool {
    SHORTCUTS.iter().all(|(id, ..)| keys.contains(&path_of(id)))
}

fn add_shortcuts(app: &AppHandle) -> Result<(), String> {
    if bundle_dir(app).is_none() {
        return Err("in development, use scripts/install.sh --setup-shortcut".into());
    }
    let python = venv_python();
    let mut keys = parse_list(&gsettings(&["get", MEDIA_KEYS, "custom-keybindings"])?);
    for (id, name, action, binding) in SHORTCUTS {
        let path = path_of(id);
        if !keys.contains(&path) {
            keys.push(path.clone());
        }
        let schema = format!("{MEDIA_KEYS}.custom-keybinding:{path}");
        gsettings(&["set", &schema, "name", &i18n::tr(name, &[])])?;
        gsettings(&["set", &schema, "command", &format!("{} -m geonesclick.trigger {action}", python.display())])?;
        gsettings(&["set", &schema, "binding", binding])?;
    }
    gsettings(&["set", MEDIA_KEYS, "custom-keybindings", &format_list(&keys)])?;
    Ok(())
}

/// Without GNOME's settings (no gsettings, or no GNOME schema), there is nothing to remove.
fn remove_shortcuts() -> Result<(), String> {
    let Ok(current) = gsettings(&["get", MEDIA_KEYS, "custom-keybindings"]) else { return Ok(()) };
    let keys = parse_list(&current);
    let kept = without_ours(&keys);
    if kept.len() != keys.len() {
        gsettings(&["set", MEDIA_KEYS, "custom-keybindings", &format_list(&kept)])?;
    }
    for (id, ..) in SHORTCUTS {
        gsettings(&["reset-recursively", &format!("{MEDIA_KEYS}.custom-keybinding:{}", path_of(id))])?;
    }
    Ok(())
}

#[derive(Serialize)]
pub struct Status {
    /// Running from the AppImage: both can be added (in development, scripts/install.sh adds the shortcuts).
    appimage: bool,
    /// None when GNOME's settings cannot be read (no gsettings).
    shortcuts: Option<bool>,
    menu: bool,
}

#[tauri::command]
pub fn integration_status(app: AppHandle) -> Status {
    let shortcuts = gsettings(&["get", MEDIA_KEYS, "custom-keybindings"]).ok().map(|v| shortcuts_on(&parse_list(&v)));
    Status { appimage: bundle_dir(&app).is_some() && appimage().is_some(), shortcuts, menu: desktop_file(&data_home()).is_file() }
}

#[tauri::command]
pub fn set_shortcuts(app: AppHandle, on: bool) -> Result<(), String> {
    if on { add_shortcuts(&app) } else { remove_shortcuts() }
}

#[tauri::command]
pub fn set_menu_entry(on: bool) -> Result<(), String> {
    let data = data_home();
    if !on {
        return remove_entry(&data);
    }
    let appimage = appimage().ok_or_else(|| i18n::tr("integration.error.appimage", &[]))?;
    write_entry(&data, &appimage)
}

/// "Erase everything": the shortcuts and the menu entry go, whatever was chosen. Both are tried; the errors are joined.
#[tauri::command]
pub fn remove_integration() -> Result<(), String> {
    let errors: Vec<String> = [remove_shortcuts(), remove_entry(&data_home())].into_iter().filter_map(Result::err).collect();
    if errors.is_empty() { Ok(()) } else { Err(errors.join("; ")) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_path_becomes_one_quoted_exec_argument() {
        assert_eq!(exec_arg(Path::new("/home/a/Téléchargements/GeoNesClick 0.3.AppImage")).unwrap(),
                   "\"/home/a/Téléchargements/GeoNesClick 0.3.AppImage\"");
        // Inside the quotes " ` $ \ are escaped by a backslash, which the string value doubles; % is doubled.
        assert_eq!(exec_arg(Path::new(r#"/a "b" `c` $d \e 100%"#)).unwrap(),
                   r#""/a \\"b\\" \\`c\\` \\$d \\\\e 100%%""#);
        assert_eq!(exec_arg(Path::new("/a\nExec=evil")), None);
    }

    #[test]
    fn the_entry_matches_the_window_and_points_to_the_appimage() {
        let entry = desktop_entry("\"/x/GeoNesClick.AppImage\"", "coach");
        assert!(entry.contains("\nExec=\"/x/GeoNesClick.AppImage\"\n"), "{entry}");
        assert!(entry.contains(&format!("\nIcon={DESKTOP_ID}\n")) && entry.contains("\nStartupWMClass=geonesclick\n"), "{entry}");
    }

    #[test]
    fn the_entry_and_its_icons_are_written_then_removed() {
        let data = std::env::temp_dir().join(format!("gnc-integration-{}", std::process::id()));
        let appimage = data.join("GeoNesClick.AppImage");
        std::fs::create_dir_all(&data).unwrap();
        write_entry(&data, &appimage).unwrap();
        assert!(desktop_file(&data).is_file() && icon_file(&data, "256x256").is_file());
        remove_entry(&data).unwrap();
        assert!(!desktop_file(&data).exists() && !icon_file(&data, "128x128").exists());
        remove_entry(&data).unwrap(); // nothing left: not an error
        std::fs::remove_dir_all(&data).unwrap();
    }

    #[test]
    fn only_our_two_shortcuts_count_and_go() {
        let mine = "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']";
        assert_eq!(parse_list("@as []"), Vec::<String>::new());
        assert!(!shortcuts_on(&parse_list(mine)));
        let both = parse_list(&format_list(&[parse_list(mine), vec![path_of("geonesclick"), path_of("geonesclick-mark")]].concat()));
        assert!(shortcuts_on(&both) && both.len() == 3);
        assert!(!shortcuts_on(&both[..2]));
        assert_eq!(without_ours(&both), parse_list(mine)); // the user's own shortcut stays
    }
}
