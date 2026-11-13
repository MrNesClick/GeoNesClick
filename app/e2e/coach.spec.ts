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

test("a capture shows the likely countries; below the leader threshold, the answer is a hesitation", async ({ page }) => {
  // Sweden first at 57 %, under leader_min (0.7): no country is given as the answer without written proof.
  const engine = await fakeEngine(page, { state: sharing() });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["app.status.ready_marks"])).toBeVisible();
  round().forEach((message) => engine.send(message));
  const countries = page.getByRole("region", { name: new RegExp(`^${en["app.section.countries"]}`) });
  await expect(countries.getByText("57%", { exact: true })).toBeVisible();
  const answer = page.getByRole("region", { name: new RegExp(`^${en["app.section.answer"]}`) });
  await expect(answer.getByText(en["summary.hesitation"], { exact: true })).toBeVisible();
  await expect(answer.getByRole("list", { name: en["summary.hesitation_aria"] })).toContainText("Sweden");
});

test("a capture cut by a fixed share until the browser's bars are located says so", async ({ page }) => {
  const engine = await fakeEngine(page, { state: sharing() });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["app.status.ready_marks"])).toBeVisible();
  const messages = round() as { type: string; id?: string; guessed_crop?: boolean }[];
  messages.forEach((message) => engine.send(message)); // the first capture of this window size: guessed
  const capture = page.getByRole("region", { name: new RegExp(`^${en["app.section.capture"]}`) });
  await expect(capture).toContainText(en["sum.crop_guessed"]);
  const next = { ...messages.find((m) => m.type === "capture"), id: "cap2", guessed_crop: false };
  engine.send(next); // the edge is learnt: no more note
  await expect(capture).not.toContainText(en["sum.crop_guessed"]);
});

test("a plain capture or the same image as the previous one is analysed with a note", async ({ page }) => {
  const engine = await fakeEngine(page, { state: sharing() });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["app.status.ready_marks"])).toBeVisible();
  const messages = round() as { type: string; id?: string; warnings?: string[] }[];
  messages.forEach((message) => engine.send(message));
  const capture = page.getByRole("region", { name: new RegExp(`^${en["app.section.capture"]}`) });
  await expect(capture).not.toContainText(en["sum.capture_same"]);
  const shot = messages.find((m) => m.type === "capture");
  engine.send({ ...shot, id: "cap2", warnings: ["flat", "same"] });
  await expect(capture).toContainText(en["sum.capture_flat"]);
  await expect(capture).toContainText(en["sum.capture_same"]);
  await capture.getByRole("button").first().click();
  await expect(capture.getByText(en["app.capture_same"])).toBeVisible();
});

test("a country above the leader threshold is given as the answer, from the look of the view", async ({ page }) => {
  const state = { ...sharing(), leader: { min: 0.5, margin: 0.15 } }; // Sweden's 57 % now stands out
  const engine = await fakeEngine(page, { state });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["app.status.ready_marks"])).toBeVisible();
  round().forEach((message) => engine.send(message));
  const answer = page.getByRole("region", { name: new RegExp(`^${en["app.section.answer"]}`) });
  await expect(answer.getByText(en["summary.from_look"])).toBeVisible();
  await expect(answer.getByText(en["summary.hesitation"], { exact: true })).toHaveCount(0);
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

test("a single mark that nothing seconds stays very likely, and the coach asks for a second one", async ({ page }) => {
  const engine = await fakeEngine(page, { state: sharing() });
  await page.goto("/e2e/harness.html");
  await expect(page.getByText(en["app.status.ready_marks"])).toBeVisible();
  const messages = round() as { type: string; id?: string }[];
  messages.forEach((message) => engine.send(message));
  const id = messages.find((m) => m.type === "capture")?.id;
  const verdict = { type: "verdict", id, country: "SE", level: "probable", allowed: null, scripts: [], against: [],
                    cites: [{ n: 1, items: ["Göteborg", "Borås"] }], conflict: "", location: null, ignored: [],
                    unconfirmed: [], unseconded: true };
  engine.send(verdict);
  const answer = page.getByRole("region", { name: new RegExp(`^${en["app.section.answer"]}`) });
  await expect(answer).toContainText(en["proof.marks_likely"]);
  await expect(answer).toContainText(en["summary.second_mark"]);
  engine.send({ ...verdict, cites: [{ n: 1, items: ["Göteborg"] }, { n: 2, items: ["Borås"] }], level: "certain", unseconded: false });
  await expect(answer).toContainText(en["proof.marks_certain"]);
  await expect(answer).not.toContainText(en["summary.second_mark"]);
});

test("nothing is shared at the start: the coach offers to share the game window, then restarting reopens the picker", async ({ page }) => {
  const engine = await fakeEngine(page); // the engine's own state at its start (fixture): not shared, idle
  await page.goto("/e2e/harness.html");
  await expect(page.getByRole("status").first()).toHaveText(en["srv.sharing_off"]);
  await page.getByRole("button", { name: en["app.share"] }).click();
  await expect.poll(() => engine.posts.map((p) => p.path)).toEqual(["/capture/start"]);
  engine.send({ type: "state", ...fixture("state.json"), capture: { alive: false, starting: false, idle: false, message: "cut" } });
  await page.getByRole("button", { name: en["app.restart_sharing"] }).click();
  await expect.poll(() => engine.posts.map((p) => p.path)).toEqual(["/capture/start", "/capture/reselect"]);
});
