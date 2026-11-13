// First-launch installer, System step: the missing components, installed from here or named for the system.
import { expect, test } from "@playwright/test";
import en from "../../engine/src/geonesclick/locales/en.json" with { type: "json" };
import { fakeEngine, fixture, tauri, tauriArgs, tauriCalls } from "./fake";

const CHECKS = ["portal", "portal_gnome", "gst_typelib", "gst_convert", "gst_pipewire", "gobject", "cairo"];

/** setup_status as setup.rs answers it: an AppImage whose engine is not installed yet. */
function status(packageManager: string | null, missing: Record<string, string> = {}) {
  return {
    bundled: true, needed: true, version: "0.2.4", installed: null, engine_ready: false, gpu: false,
    checks: CHECKS.map((id) => ({ label: `setup.check.${id}`, ok: !(id in missing), package: missing[id] ?? id })),
    downloads: fixture("downloads.json"), packages_cuda: [], packages_cpu: [], package_manager: packageManager,
    data_dir: "~/Mes données/geonesclick", models_dir: "~/.cache/huggingface/hub",
    upgrade: false, older: false, installed_variant: null, installed_copy: false, copy_dir: "~/Mes données/geonesclick",
    whats_new: [],
  };
}

/** setup_status for a newer AppImage opened over an installed 0.4.1 (with a processor engine, on an NVIDIA machine). */
function update() {
  return {
    ...status("apt"), version: "0.5.0", installed: "0.4.1", upgrade: true, installed_variant: "cpu", gpu: true,
    whats_new: [{ version: "0.5.0", text: "### Added\n\n- A capture that is nearly a single colour comes with a note.\n\n### Changed\n\n- A [CHANGELOG](https://x) line." }],
  };
}

test("an update runs without a question, keeps the installed engine's variant, and says what changed", async ({ page }) => {
  await tauri(page, { setup_status: update(), place_appimage: "~/Téléchargements/GeoNesClick_0.5.0_amd64.AppImage" });
  await fakeEngine(page);
  await page.goto("/e2e/harness.html");
  await expect(page.getByRole("heading", { name: "Updating GeoNesClick 0.4.1 → 0.5.0" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Updating to 0.5.0…"); // one line, the steps under Details
  await page.evaluate(() => window.__GNC_EMIT__("setup-progress", { phase: "packages", line: "Downloading torch (199.8MiB)", done: false, ok: true, reason: null }));
  await expect(page.getByRole("status")).toHaveText("Downloading torch (200 MB)…"); // why it takes time
  await expect.poll(() => tauriArgs(page, "setup_install")).toEqual([{ variant: "cpu" }]);
  expect(await tauriCalls(page)).not.toContain("setup_apply"); // the choices and the key stay as they are
  await page.evaluate(() => window.__GNC_EMIT__("setup-progress", { phase: null, line: null, done: true, ok: true, reason: null }));
  await expect.poll(() => tauriCalls(page)).toContain("restart_engine");
  const calls = await tauriCalls(page);
  expect(calls.indexOf("setup_finish_update")).toBeLessThan(calls.indexOf("restart_engine"));
  // The coach: one line, whose panel says what changed and that the downloaded file can go.
  const note = page.getByRole("status").filter({ hasText: "Updated to 0.5.0" });
  await note.getByRole("button", { name: en["app.notice.whats_new"] }).click();
  await expect(page.getByRole("dialog")).toContainText("~/Téléchargements/GeoNesClick_0.5.0_amd64.AppImage");
  await page.getByRole("button", { name: en["app.notice.close_panel"] }).click();
  await note.getByRole("button", { name: en["app.notice.close"] }).click();
  await expect(note).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("geonesclick.notice"))).toBeNull(); // never shown again
});

test("an update whose copy could not be made still says once what changed", async ({ page }) => {
  await tauri(page, { setup_status: update(), place_appimage: { error: "No space left on device" } });
  await fakeEngine(page);
  await page.goto("/e2e/harness.html");
  await expect.poll(() => tauriCalls(page)).toContain("setup_install");
  await page.evaluate(() => window.__GNC_EMIT__("setup-progress", { phase: null, line: null, done: true, ok: true, reason: null }));
  const note = page.getByRole("status").filter({ hasText: "Updated to 0.5.0" });
  await note.getByRole("button", { name: en["app.notice.whats_new"] }).click();
  await expect(page.getByRole("dialog")).not.toContainText("You can delete");
});

test("an older AppImage touches nothing and opens the installed version", async ({ page }) => {
  await tauri(page, { setup_status: { ...status("apt"), version: "0.4.1", installed: "0.5.0", older: true, installed_copy: true } });
  await page.goto("/e2e/harness.html");
  await expect(page.getByRole("heading", { name: en["setup.older.title"] })).toBeVisible();
  await page.getByRole("button", { name: "Open GeoNesClick 0.5.0" }).click();
  await expect.poll(() => tauriCalls(page)).toContain("open_installed");
  expect(await tauriCalls(page)).not.toContain("setup_install");
});

test.use({ viewport: { width: 860, height: 980 } }); // the installer's window (main.ts)

test("a missing component is installed with one click, then the installer moves on", async ({ page }) => {
  const missing = status("apt", { gobject: "libgirepository-2.0-0" });
  await tauri(page, {
    // Asked by main.ts then by the installer at start, then again after the install.
    setup_status: { sequence: [missing, missing, status("apt")] },
    setup_system_install: null,
  });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText("sudo apt install libgirepository-2.0-0")).toBeVisible();
  await page.getByRole("button", { name: en["setup.system.install"], exact: true }).click();
  await expect(page.getByRole("heading", { name: en["setup.required.title"] })).toBeVisible();
  expect(await tauriCalls(page)).toContain("setup_system_install");
});

test("a refused password is said, and the installer stays on the system step", async ({ page }) => {
  await tauri(page, {
    setup_status: status("apt", { gobject: "libgirepository-2.0-0" }),
    setup_system_install: { error: en["setup.system.install_cancelled"] },
  });
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: en["setup.system.install"], exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText(en["setup.system.install_cancelled"]);
  await expect(page.getByRole("heading", { name: en["setup.system.title"] })).toBeVisible();
});

test("the components step names the folders the engine and the models actually go to", async ({ page }) => {
  await tauri(page, { setup_status: status("apt") });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText("Engine in ~/Mes données/geonesclick, AI models in ~/.cache/huggingface/hub")).toBeVisible();
  await expect(page.getByText(/copied to ~\/Mes données\/geonesclick as GeoNesClick\.AppImage/)).toBeVisible();
});

test("on Fedora, the command and the button use dnf and Fedora's package names", async ({ page }) => {
  await tauri(page, { setup_status: status("dnf", { gst_pipewire: "pipewire-gstreamer" }) });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText("sudo dnf install pipewire-gstreamer")).toBeVisible();
  await expect(page.getByRole("button", { name: en["setup.system.install"], exact: true })).toBeVisible();
});

test("with an unknown package manager, neither a command nor a button: Debian's names as a hint", async ({ page }) => {
  await tauri(page, { setup_status: status(null, { gobject: "libgirepository-2.0-0" }) });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["setup.system.missing_unknown"])).toBeVisible();
  await expect(page.getByText(/^sudo /)).toHaveCount(0);
  await expect(page.getByRole("button", { name: en["setup.system.install"], exact: true })).toHaveCount(0);
});

test("the menu entry is added only when ticked; the shortcuts are ticked by default", async ({ page }) => {
  // Engine installed earlier, window closed before the end: the installer opens on the options.
  await tauri(page, { setup_status: { ...status("apt"), engine_ready: true } });
  await page.goto("/e2e/harness.html");
  const menu = page.getByRole("checkbox", { name: en["setup.menu"] });
  await expect(menu).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: en["setup.shortcuts"] })).toBeChecked();
  await page.getByRole("checkbox", { name: en["setup.no_key"] }).check();
  await menu.check();
  await page.getByRole("button", { name: en["setup.next"], exact: true }).click();
  await page.getByRole("button", { name: en["setup.launch"], exact: true }).click();
  await expect.poll(() => tauriCalls(page)).toContain("restart_engine");
  expect(await tauriArgs(page, "set_shortcuts")).toEqual([{ on: true }]);
  expect(await tauriArgs(page, "set_menu_entry")).toEqual([{ on: true }]);
  const [apply] = (await tauriArgs(page, "setup_apply")) as { choices: { updates: { check: boolean } } }[];
  expect(apply.choices.updates).toEqual({ check: true }); // the update check, ticked by default
  expect(await page.evaluate(() => localStorage.getItem("geonesclick.updates_told"))).toBe("1"); // chosen: no note
  const calls = await tauriCalls(page);
  expect(calls).toContain("place_appimage");
  expect(calls.indexOf("place_appimage")).toBeLessThan(calls.indexOf("set_menu_entry")); // the entry points to the copy
});

test("a failed shortcut install is shown on the last step, and the coach starts only on demand", async ({ page }) => {
  await tauri(page, {
    setup_status: { ...status("apt"), engine_ready: true },
    set_shortcuts: { error: "expected end of input" },
  });
  await page.goto("/e2e/harness.html");
  await page.getByRole("checkbox", { name: en["setup.no_key"] }).check();
  await page.getByRole("button", { name: en["setup.next"], exact: true }).click();
  await page.getByRole("button", { name: en["setup.launch"], exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("expected end of input");
  expect(await tauriCalls(page)).not.toContain("restart_engine");
  await page.getByRole("button", { name: en["setup.launch_anyway"], exact: true }).click();
  await expect.poll(() => tauriCalls(page)).toContain("restart_engine");
  expect(await tauriArgs(page, "set_shortcuts")).toEqual([{ on: true }]); // not tried a second time
});

test("after a failed shortcut install, going back to the options applies the new choices", async ({ page }) => {
  await tauri(page, {
    setup_status: { ...status("apt"), engine_ready: true },
    set_shortcuts: { error: "expected end of input" },
  });
  await page.goto("/e2e/harness.html");
  await page.getByRole("checkbox", { name: en["setup.no_key"] }).check();
  await page.getByRole("button", { name: en["setup.next"], exact: true }).click();
  await page.getByRole("button", { name: en["setup.launch"], exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: en["setup.back"], exact: true }).click();
  await page.getByRole("checkbox", { name: en["setup.shortcuts"] }).uncheck();
  await page.getByRole("button", { name: en["setup.next"], exact: true }).click();
  await page.getByRole("button", { name: en["setup.launch"], exact: true }).click();
  await expect.poll(() => tauriCalls(page)).toContain("restart_engine");
  expect((await tauriArgs(page, "setup_apply")).length).toBe(2); // the new choices are applied
  expect(await tauriArgs(page, "set_shortcuts")).toEqual([{ on: true }]); // unticked: not tried again
});
