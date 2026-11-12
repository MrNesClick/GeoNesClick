//! Texts the player sees, in their language: the same catalogs as the engine (geonesclick/i18n.py) and the UI
//! (src/i18n.ts), compiled in by build.rs (every locales/<lang>.json). Same rules in the three layers: flat keys,
//! "{name}" placeholders, English when a key or a language is missing.

use std::collections::HashMap;
use std::sync::{LazyLock, PoisonError, RwLock};

include!(concat!(env!("OUT_DIR"), "/catalogs.rs"));

type Catalog = HashMap<String, String>;

static PARSED: LazyLock<HashMap<&'static str, Catalog>> = LazyLock::new(|| {
    CATALOGS
        .iter()
        .map(|(lang, json)| (*lang, serde_json::from_str(json).expect("catalog: JSON object of strings (test_i18n.py)")))
        .collect()
});

/// The text of a key in a language (English if that language has no catalog), its "{name}" placeholders replaced.
/// An unknown key gives the key itself (the installer must never crash on a text); test_i18n.py checks the keys.
pub fn t(lang: &str, key: &str, params: &[(&str, &str)]) -> String {
    let english = PARSED.get("en");
    let mut text = PARSED
        .get(lang)
        .and_then(|c| c.get(key))
        .or_else(|| english.and_then(|c| c.get(key)))
        .cloned()
        .unwrap_or_else(|| key.to_string());
    for (name, value) in params {
        text = text.replace(&format!("{{{name}}}"), value);
    }
    text
}

/// The UI's language, sent by the UI (set_language) as soon as it knows it: English until then.
static CURRENT: RwLock<String> = RwLock::new(String::new());

pub fn current() -> String {
    let lang = CURRENT.read().unwrap_or_else(PoisonError::into_inner).clone();
    if lang.is_empty() { "en".into() } else { lang }
}

/// A text in the UI's language.
pub fn tr(key: &str, params: &[(&str, &str)]) -> String {
    t(&current(), key, params)
}

/// Called by the UI when its language is chosen or changes; a language without a catalog means English.
#[tauri::command]
pub fn set_language(lang: String) {
    let lang = if PARSED.contains_key(lang.as_str()) { lang } else { "en".into() };
    *CURRENT.write().unwrap_or_else(PoisonError::into_inner) = lang;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_key_is_given_in_the_language_asked_english_otherwise() {
        assert_eq!(t("fr", "language.name", &[]), "Français");
        assert_eq!(t("en", "language.name", &[]), "English");
        assert_eq!(t("de", "language.name", &[]), "English"); // no German catalog: English
        assert_eq!(t("fr", "no.such.key", &[]), "no.such.key");
    }

    #[test]
    fn the_ui_language_is_kept_and_an_unknown_one_means_english() {
        set_language("fr".into());
        assert_eq!((current(), tr("language.name", &[])), ("fr".to_string(), "Français".to_string()));
        set_language("../../etc".into());
        assert_eq!(current(), "en");
    }

    #[test]
    fn every_catalog_file_is_compiled_in() {
        let langs: Vec<&str> = CATALOGS.iter().map(|(l, _)| *l).collect();
        assert!(langs.contains(&"en") && langs.contains(&"fr"), "{langs:?}");
    }
}
