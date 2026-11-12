// The coach window, with the Rust side and the engine simulated (an installed engine: no installer).
import { expect, test } from "@playwright/test";
import en from "../../engine/src/geonesclick/locales/en.json" with { type: "json" };
import { fakeEngine, fixture, tauri, tauriArgs, tauriCalls } from "./fake";

const INTEGRATION = { appimage: true, shortcuts: true, menu: true };

test.beforeEach(async ({ page }) => {
  await tauri(page, { setup_status: { bundled: false, needed: false }, erase_engine: null, integration_status: INTEGRATION });
});

const round = () => fixture<object[]>("round-sweden.json");
/** The engine's state with the screen shared (the fixtures come from an engine without a screen to share). */
const sharing = () => ({ capture: { alive: true, starting: false, message: en["app.status.ready_marks"] } });

test("the Settings opened while the engine is still starting load once it answers", async ({ page }) => {
  const engine = await fakeEngine(page, { up: false });
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: en["app.tab.settings"], exact: true }).click();
  await expect(page.getByText(en["settings.loading"])).toBeVisible();
  engine.up = true; // the engine answers: the window reconnects within 1.5 s
  await expect(page.getByRole("button", { name: en["group.general"] })).toBeVisible({ timeout: 10_000 });
});

test("a capture shows the likely countries and the answer", async ({ page }) => {
  const engine = await fakeEngine(page, { state: sharing() });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["app.status.ready_marks"])).toBeVisible();
  round().forEach((message) => engine.send(message));
  const countries = page.getByRole("region", { name: new RegExp(`^${en["app.section.countries"]}`) });
  await expect(countries.getByRole("paragraph").filter({ hasText: "Sweden" })).toBeVisible(); // the leading country
  await expect(countries.getByText("57%", { exact: true })).toBeVisible();
  const answer = page.getByRole("region", { name: new RegExp(`^${en["app.section.answer"]}`) });
  await expect(answer.getByText(en["summary.from_look"])).toBeVisible();
});

test("while the Plonk It tips are prepared, the coach shows the progress", async ({ page }) => {
  const progress = "preparing the tips close to the view: 1200 / 4054 (first launch only)";
  const state = fixture("state.json");
  const engine = await fakeEngine(page, {
    state: { ...sharing(), plonkit: { ...state.plonkit, enabled: true, status: "busy", message: progress } },
  });
  await page.goto("/e2e/harness.html");
  // Tips: from level 3. The radio is visually hidden: its label takes the click, as for the player.
  await page.getByRole("group", { name: en["level.legend"] }).getByText(en["level.3"], { exact: true }).click();
  round().forEach((message) => engine.send(message));
  await expect(page.getByText(progress)).toBeVisible();
});

test("Erase everything with the engine box uninstalls, then only offers to close", async ({ page }) => {
  const engine = await fakeEngine(page);
  const plan = fixture<{ groups: object[] }>("storage-erase.json");
  engine.get["/storage/erase"] = { groups: [...plan.groups, {
    id: "engine", label: en["storage.group.engine"], files: 1, size: 1_100_000_000, precious: false, optional: true,
  }] };
  // Asked when the Settings open, then again after the uninstall, which removed the shortcuts and the menu entry.
  await tauri(page, { setup_status: { bundled: false, needed: false }, erase_engine: null,
                      integration_status: { sequence: [INTEGRATION, { ...INTEGRATION, shortcuts: false, menu: false }] } });
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: en["app.tab.settings"], exact: true }).click();
  await page.getByRole("button", { name: en["group.storage"] }).click();
  await page.getByRole("button", { name: en["storage.see_what"] }).click();
  await page.getByText(en["storage.also.engine"]).click();
  await page.locator("form").getByRole("textbox").fill(en["storage.confirm_word"]);
  await page.getByRole("button", { name: en["storage.erase_all"], exact: true }).click();
  await expect(page.getByText(en["storage.uninstalled"])).toBeVisible();
  const integration = page.getByRole("button", { name: en["group.integration"] });
  await expect(integration).toContainText(`${en["settings.sum.shortcuts_off"]} · ${en["settings.sum.menu_off"]}`);
  await integration.click();
  await expect(page.getByRole("checkbox", { name: en["setup.menu"] })).toBeDisabled();
  expect(engine.posts).toContainEqual({ path: "/storage/erase", body: { confirm: "ERASE", models: false } });
  // The GNOME shortcuts and the menu entry go before the engine.
  expect((await tauriCalls(page)).filter((c) => c === "remove_integration" || c === "erase_engine"))
    .toEqual(["remove_integration", "erase_engine"]);
  await page.getByRole("button", { name: en["storage.close"], exact: true }).click();
  await expect.poll(() => tauriCalls(page)).toContain("plugin:window|close");
});

test("the GNOME integration group shows what is in place and adds the menu entry", async ({ page }) => {
  await fakeEngine(page);
  await tauri(page, {
    setup_status: { bundled: false, needed: false },
    integration_status: { sequence: [{ appimage: true, shortcuts: true, menu: false }, { appimage: true, shortcuts: true, menu: true }] },
  });
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: en["app.tab.settings"], exact: true }).click();
  const group = page.getByRole("button", { name: en["group.integration"] });
  await expect(group).toContainText(`${en["settings.sum.shortcuts_on"]} · ${en["settings.sum.menu_off"]}`);
  await group.click();
  const menu = page.getByRole("checkbox", { name: en["setup.menu"] });
  await expect(menu).not.toBeChecked();
  await menu.check();
  await expect(menu).toBeChecked();
  await expect(group).toContainText(en["settings.sum.menu_on"]);
  expect(await tauriArgs(page, "set_menu_entry")).toEqual([{ on: true }]);
});
