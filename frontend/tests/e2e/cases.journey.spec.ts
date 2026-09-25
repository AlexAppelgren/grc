import { expect, test } from './support/api-guard';
import { CASES, NAMES, caseFileLines, casePanels, downloadedLines, evidencePdf, obligationFacts, openCase, passStepUp, showCaseFile, signOffAndClose, tenantDate } from './support/cases-signoff';
import { allowFreshContext, LOGINS, signInAs, signOut } from './support/passkeys';

// cases: the @e2e scenarios from backend/apps/cases/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('cases journeys', () => {
  test.fixme("CAS-S2: Triage needs an urgency and an owner", async () => {
    // pending: CAS-S2 (CAS-02)
  });

  test.fixme("CAS-S3: Dismissal needs a reason and can be restored", async () => {
    // pending: CAS-S3 (CAS-02)
  });

  test.fixme("CAS-S4: The impact assessment records what applies and what must change", async () => {
    // pending: CAS-S4 (CAS-03)
  });

  test.fixme("CAS-S6: Actions have an owner and due date, lock during sign-off and export as tickets", async () => {
    // pending: CAS-S6 (CAS-04)
  });

  test.fixme("CAS-S7: Evidence is scanned, hashed and streamed through permission checks", async () => {
    // pending: CAS-S7 (CAS-05)
  });

  // c9-e2e-signoff-j3: CAS-S8. The button asks only once the server says the case is ready,
  // so the two refusals come from a second tab of the owner's that loaded the case while it
  // was ready and still offers the request: the first tab takes the case back to one open
  // action and no evidence, which is the scenario's starting point, and the stale tab asks.
  // The bank's compliance officer works the case (cases.work): the owner's own login is
  // ID-S11's, which counts that person's sessions while other journeys run.
  test("CAS-S8: Sign-off is refused while actions are open or evidence is missing", async ({ page, apiGuard }) => {
    const ACTION = 'Update the ISK and KF tax rate in the statements';
    const MEMO = 'Rate check memo';
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASES.s8);
    const waiting = page.locator('[data-case-panels="signoff"]');
    await expect(page.locator('[data-case-panels="implementing"]').or(waiting).first()).toBeVisible();
    // A retry after the request went through finds the case waiting, and the journey's last step holds.
    if (await waiting.isVisible()) {
      await expect(page.locator('[data-signoff-waiting]')).toHaveText(/^You asked for sign-off on /);
      return;
    }

    const actions = page.locator('[data-case-panel="actions"]');
    const evidence = page.locator('[data-case-panel="evidence"]');
    const signoff = page.locator('[data-signoff-panel="implementing"]');
    const request = signoff.getByRole('button', { name: 'Request sign-off' });
    const done = actions.getByRole('checkbox', { name: ACTION });
    const attachLink = async (on: typeof page) => {
      await on.locator('[data-case-panel="evidence"]').getByRole('button', { name: 'Attach evidence' }).click();
      const dialog = on.getByRole('dialog', { name: 'Attach evidence' });
      await dialog.getByRole('radio', { name: /^A link/ }).check();
      await dialog.getByRole('textbox', { name: 'Name', exact: true }).fill(MEMO);
      await dialog.getByRole('textbox', { name: 'Web address' }).fill('https://intranet.example-bank.test/tax/isk-kf-rate');
      await dialog.getByRole('button', { name: 'Attach evidence' }).click();
      await expect(dialog).toHaveCount(0);
    };

    // The case made ready in this tab: the action done and a link attached, which is checked at once.
    // The box follows the server's answer, so it is clicked and then read back, never `check()`ed.
    if (!(await done.isChecked())) await done.click();
    await expect(done).toBeChecked();
    if ((await evidence.locator('[data-evidence]').count()) === 0) await attachLink(page);
    await expect(request).toBeEnabled();

    // The owner's second tab loads the ready case.
    const stale = await page.context().newPage();
    await stale.goto(page.url());
    const staleRequest = stale.locator('[data-signoff-panel="implementing"]').getByRole('button', { name: 'Request sign-off' });
    await expect(staleRequest).toBeEnabled();

    // Given one open action and no evidence: the action reopened and the link removed, here.
    await done.click();
    await expect(done).not.toBeChecked();
    for (let rows = await evidence.locator('[data-evidence]').count(); rows > 0; rows -= 1) {
      await evidence.locator('[data-evidence]').first().getByRole('button', { name: 'Remove' }).click();
      await page.getByRole('dialog', { name: /^Remove "/ }).getByRole('button', { name: 'Remove' }).click();
      await expect(evidence.locator('[data-evidence]')).toHaveCount(rows - 1);
    }
    await expect(signoff.locator('[data-signoff-reason]')).toHaveText('1 action is still open.');

    apiGuard.allow(/\/api\/v1\/changes\/[^/]+\/signoff\/request$/, 409, 'the stale tab asks while an action is open (open_actions), then while no evidence is checked (evidence_missing)');
    const openActions = stale.waitForResponse((r) => r.url().endsWith('/signoff/request') && r.status() === 409);
    await staleRequest.click();
    expect(((await (await openActions).json()) as { code: string }).code).toBe('open_actions');
    await expect(stale.locator('[data-signoff-panel="implementing"]').getByRole('alert')).toHaveText('1 action is still open. Complete or remove it, then request sign-off.');

    // When the action is completed and sign-off is requested again.
    await done.click();
    await expect(done).toBeChecked();
    const evidenceMissing = stale.waitForResponse((r) => r.url().endsWith('/signoff/request') && r.status() === 409);
    await staleRequest.click();
    expect(((await (await evidenceMissing).json()) as { code: string }).code).toBe('evidence_missing');
    await expect(stale.locator('[data-signoff-panel="implementing"]').getByRole('alert')).toHaveText('Attach at least one piece of evidence, and wait until a file has been checked, then request sign-off.');
    await stale.close();

    // When evidence is attached and sign-off is requested, the case waits for sign-off.
    await attachLink(page);
    await expect(request).toBeEnabled();
    await request.click();
    await expect(waiting).toBeVisible();
    await expect(page.locator('[data-signoff-waiting]')).toHaveText(/^You asked for sign-off on /);
  });

  // c9-e2e-signoff-j3: CAS-S9. A refusal writes nothing, so a retry meets the same case.
  test("CAS-S9: The requester cannot sign off their own case", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.ownerApprover);
    await openCase(page, CASES.s9);
    await expect(page.locator('[data-signoff-waiting]')).toHaveText(/^You asked for sign-off on /);

    apiGuard.allow(/\/api\/v1\/changes\/[^/]+\/signoff\/approve$/, 409, 'the requester cannot sign off: four_eyes_violation');
    const refused = await signOffAndClose(page, apiGuard);
    expect(refused).toMatchObject({ status: 409, body: { code: 'four_eyes_violation' } });
    await expect(page.locator('[data-signoff-panel="signoff"]').getByRole('alert')).toHaveText("You asked for this sign-off, so you can't give it. A second person has to sign off.");
    await expect(page.locator('[data-case-panels="signoff"]')).toBeVisible();
  });

  // c9-e2e-signoff-j3: CAS-S10. The change links one obligation (e2e_seed.py
  // SIGNOFF_SPOT_CHECK_OBLIGATION), read before and after as the spot check that the sign-off
  // changed no library or register row. A closed case is final, so a retry after the approval
  // settles on the closed case and still proves the audit row and the obligation.
  test("CAS-S10: A second person signs off with step-up and the inventory is untouched", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.approver);
    await openCase(page, CASES.s10);
    const obligation = page.locator('[data-change-obligations] [data-obligation] a').first();
    const obligationHref = await obligation.getAttribute('href');
    expect(obligationHref).toMatch(/^\/inventory\/obligations\//);
    const caseUrl = page.url();
    const before = await obligationFacts(page, obligationHref!);

    await page.goto(caseUrl);
    const waiting = page.locator('[data-case-panels="signoff"]');
    const closed = page.locator('[data-case-panels="closed"]');
    await expect(waiting.or(closed).first()).toBeVisible();
    if (await waiting.isVisible()) {
      await expect(page.locator('[data-signoff-waiting]')).toHaveText(new RegExp(`^${NAMES.owner} asked for sign-off on `));
      const approved = await signOffAndClose(page, apiGuard);
      expect(approved.status).toBe(200);
    }
    await expect(closed).toBeVisible();
    const signedOff = page.locator('[data-signoff-panel="signed_off"]');
    await expect(signedOff).toContainText(`Signed off by${NAMES.approver}, `);
    await expect(signedOff).toContainText(`Asked for by${NAMES.owner}, `);

    // The audit log names the move and says it was confirmed with a passkey.
    await page.goto('/admin/audit-log');
    await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible();
    await page.getByLabel('Record kind').selectOption('change_case');
    const event = page.locator('[data-audit-row][data-action="case.moved"]').filter({ hasText: CASES.s10.title });
    await expect(event).toHaveCount(1);
    await expect(event).toContainText(`By ${NAMES.approver}`);
    await expect(event.getByText('Confirmed with a passkey')).toBeVisible();
    await expect(event.locator('[data-audit-diff] [data-field="status"] [data-before]')).toHaveText('signoff');
    await expect(event.locator('[data-audit-diff] [data-field="status"] [data-after]')).toHaveText('closed');

    // The obligation the change links to reads exactly as it did.
    expect(await obligationFacts(page, obligationHref!)).toBe(before);
  });

  // c9-e2e-signoff-j3: CAS-S11. The auditor reads the seeded closed case's file and exports it;
  // a reader, who may read the case but not export, is offered no export. Nothing here
  // changes the case, so a retry meets it as it was.
  test("CAS-S11: The case file stands alone as text and as an export", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.auditor);
    await openCase(page, CASES.s11);
    await expect(page.locator('[data-case-panels="closed"]')).toBeVisible();
    const dialog = await showCaseFile(page);
    const text = dialog.locator('[data-case-file-text]');

    // The change, the So what, the assessment, the actions with completion, the evidence
    // with hashes, the sign-off with both people, the outcome and every move, each dated.
    await expect(text).toContainText(`Case file: ${CASES.s11.title}`);
    for (const heading of ['So what?', 'Assessment', 'Actions', 'Evidence', 'Sign-off', 'Outcome', 'History']) {
      await expect(text.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    }
    const section = (heading: string) => text.locator('section').filter({ has: dialog.page().getByRole('heading', { name: heading, exact: true }) });
    await expect(section('So what?')).toContainText('Confirmed by ');
    await expect(section('Assessment')).toContainText('Does it apply: Yes');
    await expect(section('Actions')).toContainText('- Sample test 40 switch cases');
    await expect(section('Actions')).toContainText(`Done by ${NAMES.owner} on `);
    await expect(section('Evidence')).toContainText('- Best execution report 2026.pdf (file)');
    await expect(section('Evidence').locator('code').first()).toHaveText(/^[0-9a-f]{64}$/);
    await expect(section('Evidence')).toContainText('- FI decision memo (link)');
    await expect(section('Sign-off')).toContainText(`Requested by ${NAMES.owner} on `);
    await expect(section('Sign-off')).toContainText(`Signed off by ${NAMES.approver} on `);
    await expect(section('Outcome')).toContainText('Closed on ');
    for (const move of await section('History').locator('p').allTextContents()) {
      expect(move).toMatch(/^(- .*\d.*: .+|\s*Note: .+)$/);
    }

    // The export produces the same content as a file, through the passkey and the exports job.
    apiGuard.allow(/\/api\/v1\/exports$/, 403, 'exporting answers step_up_required first and opens the passkey prompt');
    await dialog.getByRole('button', { name: 'Export', exact: true }).click();
    await passStepUp(page);
    await expect(dialog.getByText('The file is ready.')).toBeVisible({ timeout: 15_000 });
    const downloading = page.waitForEvent('download');
    await dialog.getByRole('button', { name: 'Download the case file' }).click();
    expect(await downloadedLines(await downloading)).toEqual(await caseFileLines(dialog));
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();

    // A reader may read the file, and is offered no export: the download needs exports.create.
    await signOut(page);
    await signInAs(page, LOGINS.reader);
    await openCase(page, CASES.s11);
    const readerView = await showCaseFile(page);
    await expect(readerView.locator('[data-case-file-text]')).toContainText(`Case file: ${CASES.s11.title}`);
    await expect(readerView.getByRole('button', { name: 'Export', exact: true })).toHaveCount(0);
  });

  test.fixme("CAS-S14 J-2 @smoke: from Today to a triaged case", async () => {
    // pending: CAS-S14 (CAS-01, CAS-02, WAT-05, HOM-01, J-2)
  });

  // c9-e2e-signoff-j3: CAS-S15, J-3. The owner who also holds cases.signoff works the seeded
  // assigned case to sign-off, is refused their own sign-off, and a second person gives it.
  // Every step reads the case first and does only what is still undone, so a retry picks the
  // case up where the first attempt left it; a signed-off case is final.
  test("CAS-S15 J-3 @smoke: assessment to sign-off and the case file", async ({ page, apiGuard }) => {
    const ACTIONS = ['Add the sustainability questions to the suitability test', 'Brief the advisers on the new questions'];
    const EVIDENCE = 'Sustainability preferences review.pdf';
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.ownerApprover);
    await openCase(page, CASES.j3);
    const panels = casePanels(page);
    const category = async () => (await panels.getAttribute('data-case-panels')) ?? '';

    if ((await category()) === 'assigned') {
      await page.getByRole('button', { name: 'Start assessment' }).click();
      await expect(page.locator('[data-case-panels="assessing"]')).toBeVisible();
    }
    if ((await category()) === 'assessing') {
      const form = page.locator('[data-case-panel="assessment"]');
      await form.getByRole('radio', { name: 'Yes' }).check();
      await form.getByLabel('Why').fill('We give investment advice to retail clients, so the suitability test must ask about sustainability preferences.');
      await form.getByLabel('What must change').fill('The suitability questionnaire, the advisers’ script and the client report.');
      await form.getByLabel('Internal deadline').fill(tenantDate(30));
      await form.getByLabel('Effort').selectOption('m');
      await form.getByRole('button', { name: 'Save assessment' }).click();
      await expect(form.getByText(/^Assessment saved\. It is now version \d+\.$/)).toBeVisible();
    }

    // Two actions, the first of which starts the implementation, both then completed.
    const actions = page.locator('[data-case-panel="actions"]');
    if (['assessing', 'implementing'].includes(await category())) {
      for (const title of ACTIONS) {
        if ((await actions.getByRole('checkbox', { name: title }).count()) > 0) continue;
        await actions.getByLabel('New action').fill(title);
        await actions.getByLabel('Due', { exact: true }).fill(tenantDate(14));
        await actions.getByRole('button', { name: 'Add action' }).click();
        await expect(actions.getByRole('checkbox', { name: title })).toBeVisible();
        // The form empties itself once the list is read again; the next title waits for that.
        await expect(actions.getByLabel('New action')).toHaveValue('');
      }
      await expect(page.locator('[data-case-panels="implementing"]')).toBeVisible();
    }

    if ((await category()) === 'implementing') {
      for (const title of ACTIONS) {
        const done = actions.getByRole('checkbox', { name: title });
        if (!(await done.isChecked())) await done.click();
        await expect(done).toBeChecked();
      }

      // A file, scanned by the worker before it counts; the page reads the case again until it does.
      const evidence = page.locator('[data-case-panel="evidence"]');
      if ((await evidence.locator('[data-evidence]').filter({ hasText: EVIDENCE }).count()) === 0) {
        await evidence.getByRole('button', { name: 'Attach evidence' }).click();
        const attach = page.getByRole('dialog', { name: 'Attach evidence' });
        await attach.locator('#evidence-file').setInputFiles(evidencePdf(EVIDENCE));
        await attach.getByRole('button', { name: 'Attach evidence' }).click();
        await expect(attach).toHaveCount(0);
      }
      const request = page.locator('[data-signoff-panel="implementing"]').getByRole('button', { name: 'Request sign-off' });
      await expect(async () => {
        await page.reload();
        await expect(request).toBeEnabled({ timeout: 1_000 });
      }).toPass({ timeout: 10_000 });
      await request.click();
      await expect(page.locator('[data-case-panels="signoff"]')).toBeVisible();
    }

    if ((await category()) === 'signoff') {
      // The owner tries to sign off what they asked for.
      apiGuard.allow(/\/api\/v1\/changes\/[^/]+\/signoff\/approve$/, 409, 'the requester cannot sign off their own case: four_eyes_violation');
      const refused = await signOffAndClose(page, apiGuard);
      expect(refused).toMatchObject({ status: 409, body: { code: 'four_eyes_violation' } });
      await expect(page.locator('[data-signoff-panel="signoff"]').getByRole('alert')).toHaveText("You asked for this sign-off, so you can't give it. A second person has to sign off.");

      // The approver signs off with a passkey step-up.
      await signOut(page);
      await signInAs(page, LOGINS.approver);
      await openCase(page, CASES.j3);
      const approved = await signOffAndClose(page, apiGuard);
      expect(approved.status).toBe(200);
    }

    await expect(page.locator('[data-case-panels="closed"]')).toBeVisible();
    const signedOff = page.locator('[data-signoff-panel="signed_off"]');
    await expect(signedOff).toContainText(`Signed off by${NAMES.approver}, `);
    await expect(signedOff).toContainText(`Asked for by${NAMES.ownerApprover}, `);

    // "Show case file" opens the whole case.
    const file = (await showCaseFile(page)).locator('[data-case-file-text]');
    await expect(file).toContainText(`Case file: ${CASES.j3.title}`);
    await expect(file).toContainText('Does it apply: Yes');
    for (const title of ACTIONS) await expect(file).toContainText(`- ${title}`);
    await expect(file).toContainText(`Done by ${NAMES.ownerApprover} on `);
    await expect(file).toContainText(`- ${EVIDENCE} (file)`);
    await expect(file).toContainText('Content hash (SHA-256): ');
    await expect(file).toContainText(`Requested by ${NAMES.ownerApprover} on `);
    await expect(file).toContainText(`Signed off by ${NAMES.approver} on `);
    await expect(file).toContainText('Confirmed with a passkey, reference ');
  });

  // c9-triage: the API is built; the panel is c9-fe-triage-panel's and the walk c9-e2e-triage-journeys'.
  test.fixme("CAS-S19: One person closes a case that needs no work, audited, and can restore it", async () => {
    // pending: CAS-S19 (CAS-02)
  });
});
