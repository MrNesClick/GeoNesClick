// The update check as the coach shows it: the banner (closed once per version), the one-time note, the Settings block.
import { expect, test } from "@playwright/test";
import en from "../../engine/src/geonesclick/locales/en.json" with { type: "json" };
import { fakeEngine, tauri, tauriArgs } from "./fake";

const NEWER = { enabled: true, current: "0.5.0", latest: "0.6.0", url: "https://github.com/MrNesClick/GeoNesClick/releases/tag/v0.6.0",
                dismissed: false, checked: "2026-11-20T09:00:00", error: "" };
const told = () => localStorage.setItem("geonesclick.updates_told", "1");

test.beforeEach(async ({ page }) => {
  await tauri(page, { setup_status: { bundled: false, needed: false }, integration_status: { appimage: true, shortcuts: true, menu: true } });
});

test("a newer version shows a banner that opens its page, and Later closes it for that version", async ({ page }) => {
  await page.addInitScript(told);
  const engine = await fakeEngine(page, { state: { updates: NEWER } });
  await page.goto("/e2e/harness.html");
  const banner = page.getByRole("status").filter({ hasText: "GeoNesClick 0.6.0 is available." });
  await banner.getByRole("button", { name: en["updates.open"] }).click();
  await expect.poll(() => tauriArgs(page, "plugin:opener|open_url")).toEqual([{ url: NEWER.url }]);
  await banner.getByRole("button", { name: en["app.update.later"] }).click();
  await expect(banner).toHaveCount(0);
  expect(engine.posts).toContainEqual({ path: "/updates/dismiss", body: { version: "0.6.0" } });
});

test("a version whose banner was closed shows only in the Settings", async ({ page }) => {
  await page.addInitScript(told);
  await fakeEngine(page, { state: { updates: { ...NEWER, dismissed: true } } });
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: en["app.tab.settings"], exact: true }).click();
  const block = page.getByRole("region", { name: en["updates.title"] });
  await expect(block).toContainText("Version 0.6.0 is available.");
  await expect(page.getByText("GeoNesClick 0.6.0 is available.")).toHaveCount(0);
});

test("the Settings block checks on demand and turns the automatic check off", async ({ page }) => {
  await page.addInitScript(told);
  const engine = await fakeEngine(page, { state: { updates: { ...NEWER, latest: "", url: "" } } });
  engine.post["/updates/check"] = NEWER;
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: en["app.tab.settings"], exact: true }).click();
  const block = page.getByRole("region", { name: en["updates.title"] });
  await expect(block).toContainText("Up to date");
  await block.getByRole("button", { name: en["updates.check_now"] }).click();
  await expect(block).toContainText("Version 0.6.0 is available.");
  await block.getByRole("checkbox", { name: en["setting.updates.check"] }).uncheck();
  await expect.poll(() => engine.posts.map((p) => p.path)).toContain("/settings");
  expect(engine.posts.find((p) => p.path === "/settings")?.body).toEqual({ updates: { check: false } });
});

test("whoever did not choose the check in the installer is told once", async ({ page }) => {
  await fakeEngine(page, { state: { updates: { ...NEWER, latest: "", url: "" } } });
  await page.goto("/e2e/harness.html");
  const note = page.getByRole("status").filter({ hasText: en["app.notice.updates_on"] });
  await note.getByRole("button", { name: en["app.notice.close"] }).click();
  await expect(note).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("geonesclick.updates_told"))).toBe("1");
});
