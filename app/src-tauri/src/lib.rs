//! Fenêtres du coach et des marques. Au démarrage, lance le moteur Python et l'arrête à la fermeture.
//!
//! AppImage : le moteur est installé au premier lancement par l'assistant (setup.rs) dans
//! ~/.local/share/geonesclick/engine/venv ; tant qu'il n'est pas installé (ou à mettre à jour), rien ne démarre.
//! Développement : le moteur vient de engine/.venv (variable GNC_ENGINE_DIR, par défaut ../../engine relativement à
//! ce crate). Si un moteur tourne déjà (lancé à la main), le nouveau échoue à ouvrir le port et l'interface se
//! connecte simplement à celui qui existe.

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
            return None; // l'assistant de premier lancement installe d'abord le moteur
        }
        (setup::venv_python(), setup::data_dir())
    } else {
        let dir = engine_dir();
        (dir.join(".venv/bin/python"), dir)
    };
    let mut command = Command::new(&python);
    command.args(["-m", "geonesclick"]).current_dir(&dir);
    // Si l'application meurt sans passer par RunEvent::Exit (signal, plantage), le noyau envoie
    // SIGTERM au moteur : il ne reste jamais orphelin avec le partage d'écran ouvert.
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
    // SIGTERM : uvicorn s'arrête proprement (ferme la session de partage d'écran et le socket).
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
    let _ = child.kill(); // ne répond plus après 5 s
    let _ = child.wait();
}

/// Relance le moteur (après « Tout effacer » : plus rien de valide en mémoire). Arrête l'ancien proprement, puis en
/// démarre un neuf, qui repart des dossiers vides.
#[tauri::command]
fn restart_engine(app: AppHandle, state: tauri::State<'_, Engine>) -> Result<(), String> {
    let mut slot = state.0.lock().map_err(|_| "moteur verrouillé".to_string())?;
    if let Some(mut child) = slot.take() {
        stop_engine(&mut child);
    }
    *slot = spawn_engine(&app);
    if slot.is_some() { Ok(()) } else { Err("moteur introuvable".into()) }
}

/// « Tout effacer » avec la case moteur : arrête le moteur puis retire son installation (AppImage seulement).
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
        // Ouvre les pages Plonk It dans le navigateur ; adresses limitées par capabilities/default.json.
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
        // La fenêtre des marques reste ouverte (cachée) : fermer le coach doit quitter l'application.
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
