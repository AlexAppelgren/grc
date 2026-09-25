import { expect, test } from './support/api-guard';
import { allowRegisterEntryPending, openObligation, signInElsewhere } from './support/obligation-page';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// register: the @e2e scenarios from backend/apps/register/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('register journeys', () => {
  test.fixme("REG-S1: One compliance person sets applicability after confirming it", async () => {
    // pending: REG-S1 (REG-01)
  });

  test.fixme("REG-S3: Compliance status and its details are kept per legal entity", async () => {
    // pending: REG-S3 (REG-02)
  });

  test.fixme("REG-S5: A gap has an owner, severity, target date and remediation", async () => {
    // pending: REG-S5 (REG-03)
  });

  test.fixme("REG-S6: Risk acceptance is behind four eyes with step-up", async () => {
    // pending: REG-S6 (REG-03)
  });

  // c8-ui-links-history-participants: the obligation the seed assessed twice over a year and
  // read in two versions (HISTORY_OBLIGATION in apps/shared/e2e_seed.py).
  test("REG-S7: Assessment history and \"How we read this rule\" are kept per obligation", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, 'obl-appropriateness');
    const panel = page.locator('[data-history-panel]');

    // The current reading, with its author and date.
    const current = panel.locator('[data-reading-current]');
    await expect(current).toHaveAttribute('data-reading-current', '2');
    await expect(current.locator('[data-reading-by]')).toHaveText(/^Version 2, written by Sara Lindqvist, \d{1,2} \w{3} \d{4}$/);

    // Each earlier assessment, unchanged, with who and when; newest first.
    const rows = panel.locator('[data-history] [data-assessment-id]');
    await expect(rows.first()).toContainText('Sara Lindqvist');
    await expect(rows.first()).toContainText('Second-line review');
    const older = rows.filter({ hasText: 'Johan Berg' }).filter({ hasText: 'Self-assessment' });
    await expect(older).toHaveCount(1);
    await expect(older.locator('p')).not.toBeEmpty();

    // The earlier reading stays readable.
    await panel.getByRole('button', { name: /^Earlier versions? of how we read this rule, 1$/ }).click();
    await expect(panel.locator('[data-reading-version="1"]')).toContainText('Johan Berg');

    // A new version is written under If-Match and the one before stays readable.
    await panel.getByRole('button', { name: 'Write a new version' }).click();
    const editor = page.getByRole('dialog', { name: 'How we read this rule' });
    const reading = editor.getByLabel('Our reading');
    const seeded = await reading.inputValue();
    let wrote = false;
    try {
      await reading.fill(`${seeded} Structured deposits count as complex too.`);
      const saved = page.waitForResponse((r) => r.url().endsWith('/interpretation') && r.request().method() === 'PUT');
      await editor.getByRole('button', { name: 'Save version' }).click();
      const put = await saved;
      expect(put.status()).toBe(200);
      wrote = true;
      expect(put.request().headers()['if-match']).toBe('"2"');
      await expect(editor).toBeHidden();
      await expect(current).toHaveAttribute('data-reading-current', '3');
      await expect(current.locator('[data-reading-by]')).toContainText('Sara Lindqvist');
      // The earlier versions stay open, now two of them, the one just replaced among them.
      await expect(panel.getByRole('button', { name: /^Earlier versions? of how we read this rule, 2$/ })).toHaveAttribute('aria-expanded', 'true');
      await expect(panel.locator('[data-reading-version="2"]')).toContainText(seeded);
    } finally {
      // Nothing is overwritten, so the seeded reading comes back as the next version.
      if (wrote) {
        await panel.getByRole('button', { name: 'Write a new version' }).click();
        await editor.getByLabel('Our reading').fill(seeded);
        await editor.getByRole('button', { name: 'Save version' }).click();
        await expect(editor).toBeHidden();
      }
    }
  });

  // c8-ui-links-history-participants: the policy and the control the seed leaves unlinked for
  // this journey, picked on the client assets duty, and one item created from the dialog.
  test("REG-S8: Linked internal items carry external references", async ({ page, apiGuard, browser }, testInfo) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, 'obl-client-assets');
    const panel = page.locator('[data-links-panel]');
    await expect(panel.locator('[data-links-empty]').or(panel.locator('[data-link-id]')).first()).toBeVisible();
    const dialog = page.getByRole('dialog', { name: /^(Link an internal item|Create and link an item)$/ });
    const linked: string[] = [];

    async function pick(reference: string, name: RegExp): Promise<string> {
      await panel.getByRole('button', { name: 'Link an item' }).click();
      await dialog.getByRole('searchbox', { name: 'Find an item' }).fill(reference);
      await dialog.getByRole('radio', { name }).click();
      const added = page.waitForResponse((r) => r.url().endsWith('/internal-links') && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: 'Link' }).click();
      const response = await added;
      expect(response.status()).toBe(201);
      await expect(dialog).toBeHidden();
      return ((await response.json()) as { id: string }).id;
    }

    try {
      linked.push(await pick('POL-014', /Client asset policy/));
      linked.push(await pick('CTL-203', /Daily reconciliation/));
      // Both listed with their kind label and external reference.
      const policy = panel.locator(`[data-link-id="${linked[0]}"]`);
      await expect(policy.locator('[data-link-kind]')).toHaveText('Policy');
      await expect(policy.locator('[data-link-ref]')).toHaveText('POL-014');
      const control = panel.locator(`[data-link-id="${linked[1]}"]`);
      await expect(control.locator('[data-link-kind]')).toHaveText('Control');
      await expect(control.locator('[data-link-ref]')).toHaveText('CTL-203');

      // A second link of the same item is refused by its code.
      apiGuard.allow(/\/internal-links$/, 409, 'REG-S8 links the policy a second time on purpose');
      await panel.getByRole('button', { name: 'Link an item' }).click();
      await dialog.getByRole('searchbox', { name: 'Find an item' }).fill('POL-014');
      await dialog.getByRole('radio', { name: /Client asset policy/ }).click();
      await dialog.getByRole('button', { name: 'Link' }).click();
      await expect(dialog.getByText('That item is already linked to this obligation.')).toBeVisible();
      await dialog.getByRole('button', { name: 'Cancel' }).click();

      // An item created from the dialog: one item and one link in one call.
      const name = `Custody break log review ${Date.now()}`;
      await panel.getByRole('button', { name: 'Link an item' }).click();
      await dialog.getByRole('button', { name: 'Create a new item instead' }).click();
      await dialog.getByLabel('Kind').selectOption({ label: 'Control' });
      await dialog.getByLabel('Name').fill(name);
      await dialog.getByLabel('Your reference').fill('CTL-777');
      const created = page.waitForResponse((r) => r.url().endsWith('/internal-links') && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: 'Create and link' }).click();
      const createdResponse = await created;
      expect(createdResponse.status()).toBe(201);
      const link = (await createdResponse.json()) as { id: string; internalItemId: string };
      linked.push(link.id);
      await expect(dialog).toBeHidden();
      await expect(panel.locator(`[data-link-id="${link.id}"] [data-link-ref]`)).toHaveText('CTL-777');

      // The API exposes the links, with the item each points at, so an outside GRC system can read them.
      const reader = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.reader);
      const readerLinks = reader.waitForResponse((r) => r.url().includes('/internal-links') && r.request().method() === 'GET');
      await openObligation(reader, 'obl-client-assets');
      const listed = (await (await readerLinks).json()) as { items: { id: string; externalRef: string | null; kind: { key: string }; internalItemId: string }[] };
      expect(listed.items.find((row) => row.id === linked[0])).toMatchObject({ externalRef: 'POL-014', kind: { key: 'policy' } });
      expect(listed.items.find((row) => row.id === linked[1])).toMatchObject({ externalRef: 'CTL-203', kind: { key: 'control' } });
      expect(listed.items.find((row) => row.id === link.id)).toMatchObject({ internalItemId: link.internalItemId });
      // A reader sees the list and no control.
      const readerPanel = reader.locator('[data-links-panel]');
      await expect(readerPanel.locator(`[data-link-id="${linked[0]}"]`)).toBeVisible();
      await expect(readerPanel.getByRole('button', { name: 'Link an item' })).toHaveCount(0);
      await expect(readerPanel.getByRole('button', { name: 'Remove' })).toHaveCount(0);
      await reader.context().close();
    } finally {
      // Remove every link this journey made; each item stays, as a removal keeps it.
      for (const id of linked) {
        const row = panel.locator(`[data-link-id="${id}"]`);
        if ((await row.count()) === 0) continue;
        await row.getByRole('button', { name: 'Remove' }).click();
        const confirm = page.getByRole('dialog', { name: /^Remove the link to / });
        await expect(confirm.getByText('The item itself stays, with its other links.')).toBeVisible();
        await confirm.getByRole('button', { name: 'Remove link' }).click();
        await expect(row).toHaveCount(0);
      }
    }
  });

  test.fixme("REG-S9: Yearly attestation and waivers", async () => {
    // pending: REG-S9 (REG-06)
  });
});

// PRD 0.3: a legal entity follows a standard and lists its units (REG-01,
// REG-08, J-10). Each stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('standards per legal entity', () => {
  test.fixme("REG-S12: A legal entity follows a standard when its applicability is set to \"Applies\"", async () => {
    // pending: REG-S12 (REG-01, REG-02)
  });

  test.fixme("REG-S13: A tenant lists its clauses and controls as units in its own words", async () => {
    // pending: REG-S13 (REG-08)
  });

  test.fixme("REG-S14: Unit decisions are set from the paste in one confirmed call", async () => {
    // pending: REG-S14 (REG-01, REG-08, AC-REG1)
  });

  test.fixme("REG-S15: The register filtered by standard and entity is the Statement of Applicability", async () => {
    // pending: REG-S15 (REG-08)
  });

  test.fixme("REG-S16 J-10 @smoke: a legal entity follows a standard from regulatory scope to Statement of Applicability", async () => {
    // pending: REG-S16 (FP-02, TEN-02, REG-01, REG-08, J-10)
  });
});
