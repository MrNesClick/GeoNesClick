// First-launch installer, System step: the missing components, installed from here or named for the system.
import { expect, test } from "@playwright/test";
import en from "../../engine/src/geonesclick/locales/en.json" with { type: "json" };
import { fixture, tauri, tauriCalls } from "./fake";

const CHECKS = ["portal", "portal_gnome", "gst_typelib", "gst_convert", "gst_pipewire", "gobject", "cairo"];

/** setup_status as setup.rs answers it: an AppImage whose engine is not installed yet. */
function status(packageManager: string | null, missing: Record<string, string> = {}) {
  return {
    bundled: true, needed: true, version: "0.2.4", installed: null, engine_ready: false, gpu: false,
    checks: CHECKS.map((id) => ({ label: `setup.check.${id}`, ok: !(id in missing), package: missing[id] ?? id })),
    downloads: fixture("downloads.json"), packages_cuda: [], packages_cpu: [], package_manager: packageManager,
  };
}

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
