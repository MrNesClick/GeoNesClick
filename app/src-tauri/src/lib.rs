//! Coach and marks windows. On startup, launches the Python engine and stops it on close.
//!
//! AppImage: the engine is installed on first launch by the assistant (setup.rs) in
//! ~/.local/share/geonesclick/engine/venv; while it is not installed (or needs an update), nothing starts.
//! Development: the engine comes from engine/.venv (variable GNC_ENGINE_DIR, by default ../../engine relative to
//! this crate). If an engine is already running (started by hand), the new one fails to open the port and the UI
//! simply connects to the existing one.

mod setup;

use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{AppHandle, Manager, RunEvent, WindowEvent};

struct Engine(Mutex<Option<Child>>);

fn engine_dir() -> PathBuf {
    std::env::var_os("GNC_ENGINE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../engine"))
}

fn spawn_engine(app: &AppHandle) -> Option<Child> {
    let (python, dir) = if setup::bundle_dir(app).is_some() {
        if setup::needed(app) {
            return None; // the first-launch assistant installs the engine first
        }
        (setup::venv_python(), setup::data_dir())
    } else {
        let dir = engine_dir();
        (dir.join(".venv/bin/python"), dir)
    };
    let mut command = Command::new(&python);
    command.args(["-m", "geonesclick"]).current_dir(&dir);
    // If the app dies without going through RunEvent::Exit (signal, crash), the kernel sends
    // SIGTERM to the engine: it is never left orphaned with the screen share still open.
    unsafe {
        command.pre_exec(|| {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    match command.spawn() {
        Ok(child) => Some(child),
        Err(err) => {
            eprintln!("[coach] moteur introuvable ({}) : {err}", python.display());
            None
        }
    }
}

fn stop_engine(child: &mut Child) {
    // SIGTERM: uvicorn shuts down cleanly (closes the screen-sharing session and the socket).
    let pid = child.id() as libc::pid_t;
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }
    for _ in 0..50 {
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    let _ = child.kill(); // no longer responding after 5 s
    let _ = child.wait();
}

/// Restarts the engine (after "Erase everything": nothing valid is left in memory). Stops the old one cleanly, then
/// starts a fresh one, which starts again from empty folders.
#[tauri::command]
fn restart_engine(app: AppHandle, state: tauri::State<'_, Engine>) -> Result<(), String> {
    let mut slot = state.0.lock().map_err(|_| "moteur verrouillé".to_string())?;
    if let Some(mut child) = slot.take() {
        stop_engine(&mut child);
    }
    *slot = spawn_engine(&app);
    if slot.is_some() { Ok(()) } else { Err("moteur introuvable".into()) }
}

/// "Erase everything" with the engine box ticked: stops the engine, then removes its installation (AppImage only).
#[tauri::command]
fn erase_engine(app: AppHandle, state: tauri::State<'_, Engine>) -> Result<(), String> {
    let mut slot = state.0.lock().map_err(|_| "moteur verrouillé".to_string())?;
    if let Some(mut child) = slot.take() {
        stop_engine(&mut child);
    }
    setup::remove_engine(&app)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // Opens Plonk It pages in the browser; addresses restricted by capabilities/default.json.
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            restart_engine,
            erase_engine,
            setup::setup_status,
            setup::setup_install,
            setup::setup_apply,
            setup::setup_shortcuts
        ])
        .setup(|app| {
            let child = spawn_engine(app.handle());
            app.manage(Engine(Mutex::new(child)));
            Ok(())
        })
        // The marks window stays open (hidden): closing the coach must quit the app.
        .on_window_event(|window, event| {
            if window.label() == "main" && matches!(event, WindowEvent::CloseRequested { .. }) {
                window.app_handle().exit(0);
            }
        })
        .build(tauri::generate_context!())
        .expect("échec du démarrage de l'application");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(state) = handle.try_state::<Engine>() {
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    stop_engine(&mut child);
                }
            }
        }
    });
}
