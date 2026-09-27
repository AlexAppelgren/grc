import { readFile } from 'node:fs/promises';

import { expect, test } from './support/api-guard';
import {
  assignedTo,
  attemptOf,
  backToTriage,
  CASE_JOURNEYS,
  casePanels,
  headerPill,
  LABELS,
  openCase,
  PEOPLE,
  recordHistory,
  shownDate,
  tenantDay,
  triage,
  writeAsSignedIn,
} from './support/cases-work';
import {
  CASES,
  NAMES,
  caseFileLines,
  downloadedLines,
  evidencePdf,
  obligationFacts,
  openCase as openSignoffCase,
  passStepUp,
  showCaseFile,
  signOffAndClose,
  tenantDate,
} from './support/cases-signoff';
import { allowFreshContext, LOGINS, signInAs, signOut } from './support/passkeys';

// cases: the @e2e scenarios from backend/apps/cases/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('cases journeys', () => {
  // c9-e2e-triage-work: each journey below spends its own seeded case and first brings it
  // back to the category the seed left it in (support/cases-work.ts), so a retry starts
  // where the first attempt did. What a journey adds carries the attempt in its name.

  test("CAS-S2: Triage needs an urgency and an owner", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/changes\/[^/]+\/triage$/, 422, 'a triage without an owner is refused, naming the owner field');
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASE_JOURNEYS.triage);
    await backToTriage(page);

    // Given a case in "Needs triage", when the officer confirms without an owner
    const panel = page.locator('[data-case-panel="triage"]');
    await panel.getByLabel('Owner', { exact: true }).selectOption('');
    await panel.getByRole('button', { name: 'Confirm and assign' }).click();
    // Then the request answers 422 naming the owner field, and the case has not moved
    await expect(panel.getByText('Choose who owns this case.')).toBeVisible();
    await expect(panel.getByLabel('Owner', { exact: true })).toHaveAttribute('aria-invalid', 'true');
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');

    // When they set "Within 3 months" and an owner and confirm
    await triage(page, PEOPLE.owner, 'Within 3 months');
    // Then the case is assigned to the owner, and the urgency pill's tone is warning
    await expect(headerPill(page, 'Assigned')).toBeVisible();
    await expect(page.locator('[data-case-panel="next-step"]').getByText(`Assigned to ${PEOPLE.owner} by ${PEOPLE.officer} on `)).toBeVisible();
    const urgency = page.locator('[data-change-classification] [data-pill]').filter({ hasText: /^Within 3 months$/ });
    await expect(urgency).toHaveAttribute('data-pill', 'warning');
  });

  test("CAS-S3: Dismissal needs a reason and can be restored", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/changes\/[^/]+\/dismiss$/, 422, 'a dismissal without a reason is refused');
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASE_JOURNEYS.dismiss);
    await backToTriage(page);
    const title = await page.getByRole('heading', { level: 1 }).innerText();

    // When the officer chooses "Dismiss" without a reason, the request answers 422
    await page.locator('[data-case-panel="triage"]').getByRole('button', { name: 'Dismiss' }).click();
    const dialog = page.getByRole('dialog', { name: 'Dismiss this change?' });
    await dialog.getByRole('button', { name: 'Dismiss' }).click();
    await expect(dialog.getByText('Choose a reason for dismissing it.')).toBeVisible();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');

    // When they dismiss with "Out of scope", the case shows "Dismissed" with the reason
    await dialog.getByRole('radio', { name: LABELS.outOfScope }).check();
    await dialog.getByRole('button', { name: 'Dismiss' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'dismissed');
    await expect(headerPill(page, 'Dismissed')).toBeVisible();
    const dismissed = page.locator('[data-case-panel="dismissed"]');
    await expect(dismissed.getByText(LABELS.outOfScope, { exact: true })).toBeVisible();
    await expect(dismissed.getByText(new RegExp(`^${PEOPLE.officer}, `))).toBeVisible();
    const changeUrl = page.url();

    // And it is absent from the open list, and listed under Dismissed
    await page.goto('/watch?scope=all');
    await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.locator(`a[data-change="${CASE_JOURNEYS.dismiss}"]`)).toHaveCount(0);
    await page.goto('/watch?scope=all&tab=dismissed');
    await expect(page.locator(`a[data-change="${CASE_JOURNEYS.dismiss}"]`)).toBeVisible();

    // When they choose "Move back to triage", the case needs triage again
    await page.goto(changeUrl);
    await page.getByRole('button', { name: 'Move back to triage' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');
    await expect(headerPill(page, 'Needs triage')).toBeVisible();

    // And the audit trail shows both moves
    const history = await recordHistory(page, 'change_case', 'case.moved', title);
    const moveTo = (status: string) => history.and(page.locator('[data-action="case.moved"]')).filter({ has: page.locator('[data-field="status"] [data-after]', { hasText: status }) });
    await expect(moveTo('dismissed').first()).toContainText(`By ${PEOPLE.officer}`);
    await expect(moveTo('dismissed').first().locator('[data-field="reasonKey"] [data-after]')).toContainText('out_of_scope');
    await expect(moveTo('new').first()).toContainText(`By ${PEOPLE.officer}`);
  });

  test("CAS-S4: The impact assessment records what applies and what must change", async ({ page, apiGuard }, testInfo) => {
    test.slow();
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/changes\/[^/]+\/assessment$/, 422, 'an assessment saved without a why is refused');
    const why = `We distribute the affected funds to retail clients (attempt ${attemptOf(testInfo)}).`;

    // Given an assigned case and its owner, as the seed left it
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASE_JOURNEYS.assess);
    await assignedTo(page, PEOPLE.owner);
    await signOut(page);

    // When the owner chooses "Start assessment", the case moves to assessing
    await signInAs(page, LOGINS.owner);
    await openCase(page, CASE_JOURNEYS.assess);
    await page.locator('[data-case-panel="next-step"]').getByRole('button', { name: 'Start assessment' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'assessing');
    await expect(headerPill(page, 'Being assessed')).toBeVisible();
    const form = page.locator('[data-case-panel="assessment"]');
    await expect(form.getByText(/^Version \d+$/)).toBeVisible();

    // When they save applies, why, what must change, a deadline and an effort
    const deadline = tenantDay(45);
    await form.getByRole('radio', { name: 'Yes' }).check();
    await form.getByLabel('Why').fill(why);
    await form.getByLabel('What must change').fill('The product governance process and the distribution agreements.');
    await form.getByLabel('Internal deadline').fill(deadline);
    await form.getByLabel('Effort').selectOption({ label: 'M' });
    await form.getByRole('button', { name: 'Save assessment' }).click();
    // Then it is stored, and the case stays in assessing
    await expect(form.getByText(/^Assessment saved\. It is now version \d+\.$/)).toBeVisible();
    await page.reload();
    await expect(page.locator('[data-case-panel="assessment"]').getByLabel('Why')).toHaveValue(why);
    await expect(page.locator('[data-case-panel="assessment"]').getByLabel('Internal deadline')).toHaveValue(deadline);
    await expect(page.locator('[data-case-panel="assessment"]').getByLabel('Effort')).toHaveValue('m');
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'assessing');

    // When they save without a why, the request answers 422 under the field
    await form.getByLabel('Why').fill('');
    await form.getByRole('button', { name: 'Save assessment' }).click();
    await expect(form.getByText('Say why it applies, or why it does not.')).toBeVisible();
    await signOut(page);

    // A contributor without cases.work is never offered "No", which closes the case: the
    // server's 403 naming cases.work is proved in apps/cases/tests_scenarios.py (CAS-S4)
    await signInAs(page, LOGINS.contributor);
    await openCase(page, CASE_JOURNEYS.assess);
    const theirs = page.locator('[data-case-panel="assessment"]');
    await expect(theirs.getByRole('radio', { name: 'Yes' })).toBeVisible();
    await expect(theirs.getByRole('radio', { name: 'No' })).toHaveCount(0);
    await expect(theirs.getByText('Saying it does not apply closes the case. Ask the case owner.')).toBeVisible();
    await signOut(page);

    // When the owner saves applies "No", the case closes as not applicable
    await signInAs(page, LOGINS.owner);
    await openCase(page, CASE_JOURNEYS.assess);
    await form.getByRole('radio', { name: 'No' }).check();
    await form.getByRole('button', { name: 'Save assessment' }).click();
    await page.getByRole('dialog', { name: 'Close as not applicable?' }).getByRole('button', { name: 'Save and close' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'closed');
    const closed = page.locator('[data-case-panel="closed"]');
    await expect(closed.getByText(LABELS.notApplicableReason, { exact: true })).toBeVisible();
    await expect(closed.getByText(why, { exact: true })).toBeVisible();
    await signOut(page);

    // And it can be restored to triage
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASE_JOURNEYS.assess);
    await page.getByRole('button', { name: 'Move back to triage' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');
  });

  test("CAS-S6: Actions have an owner and due date, lock during sign-off and export as tickets", async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/changes\/[^/]+\/actions$/, 422, 'an action without a title is refused');
    apiGuard.allow(/\/changes\/[^/]+\/actions$/, 409, 'a case waiting for sign-off refuses a new action: actions_locked');
    apiGuard.allow(/\/actions\/[^/]+$/, 409, 'a case waiting for sign-off refuses a change or a removal: actions_locked');
    const title = `Update the settlement cut-off runbook (attempt ${attemptOf(testInfo)})`;
    const due = tenantDay(30);

    // Given a case in assessing with its why saved (the first attempt; a retry finds it
    // implementing, where an action is added the same way)
    await signInAs(page, LOGINS.owner);
    await openCase(page, CASE_JOURNEYS.actions);
    const panel = page.locator('[data-case-panel="actions"]');
    const add = panel.locator('[data-add-action]');

    // An action without a title is refused under the field
    await add.getByLabel('Due').fill(due);
    await add.getByRole('button', { name: 'Add action' }).click();
    await expect(add.getByText('Give the action a title.')).toBeVisible();

    // When the owner adds one with a title and a due date and no owner
    await expect(add.getByText(`${PEOPLE.owner} owns it, as the case's owner.`)).toBeVisible();
    await add.getByLabel('New action').fill(title);
    await add.getByRole('button', { name: 'Add action' }).click();
    // Then it is listed with its due date, the case's owner owns it and the case is implementing
    const row = panel.locator('[data-action]').filter({ hasText: title });
    await expect(row).toBeVisible();
    await expect(row.getByText(PEOPLE.owner, { exact: true })).toBeVisible();
    await expect(row.getByText(`Due ${shownDate(due)}`)).toBeVisible();
    await expect(row.getByText('30 days left')).toBeVisible();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'implementing');
    await expect(headerPill(page, 'Being implemented')).toBeVisible();

    // When the owner removes it, it leaves the list
    await row.getByRole('button', { name: 'Remove' }).click();
    await page.getByRole('dialog', { name: `Remove "${title}"?` }).getByRole('button', { name: 'Remove' }).click();
    await expect(row).toHaveCount(0);

    // When the case waits for sign-off, its actions read but offer no control
    const changeId = await openCase(page, CASE_JOURNEYS.actionsLocked);
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'signoff');
    await expect(panel.getByText('Actions are locked while this case waits for sign-off. Sending it back unlocks them.')).toBeVisible();
    const locked = panel.locator('[data-action]');
    await expect(locked).toHaveCount(2);
    await expect(panel.locator('[data-add-action]')).toHaveCount(0);
    await expect(panel.getByRole('button', { name: 'Remove' })).toHaveCount(0);
    for (const box of await locked.getByRole('checkbox').all()) await expect(box).toBeDisabled();

    // And adding, editing or removing one answers 409 actions_locked from the API itself
    const actionId = (await locked.first().getAttribute('data-action')) ?? '';
    expect(await writeAsSignedIn(page, 'PATCH', `/actions/${actionId}`, { done: false })).toEqual({ status: 409, code: 'actions_locked' });
    expect(await writeAsSignedIn(page, 'DELETE', `/actions/${actionId}`)).toEqual({ status: 409, code: 'actions_locked' });
    expect(await writeAsSignedIn(page, 'POST', `/changes/${changeId}/actions`, { title, dueDate: due })).toEqual({ status: 409, code: 'actions_locked' });
    // And the list still reads as it was
    await page.reload();
    await expect(locked).toHaveCount(2);
    await expect(panel.locator('[data-action][data-done]')).toHaveCount(2);
  });

  test("CAS-S7: Evidence is scanned, hashed and streamed through permission checks", async ({ page, apiGuard }, testInfo) => {
    test.slow();
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/changes\/[^/]+\/evidence$/, 422, 'a file outside the type allow-list is refused');
    const attempt = attemptOf(testInfo);
    const pdfName = `AMLR onboarding test results ${attempt}.pdf`;
    const pdf = Buffer.from(`%PDF-1.4\n% CAS-S7 evidence, attempt ${attempt}\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n`);
    const linkName = `FI guidance on customer due diligence ${attempt}`;
    const referenceName = `KYC procedure v4, compliance share ${attempt}`;

    // Given a case in implementing, with the seed's pieces in every scan state
    await signInAs(page, LOGINS.owner);
    await openCase(page, CASE_JOURNEYS.evidence);
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'implementing');
    const panel = page.locator('[data-case-panel="evidence"]');
    const piece = (name: string) => panel.locator('[data-evidence]').filter({ hasText: name });
    await expect(piece('Customer due diligence checklist.pdf').getByText('Being checked', { exact: true })).toBeVisible();
    await expect(piece('Customer due diligence checklist.pdf').getByRole('button', { name: 'Download' })).toHaveCount(0);
    await expect(piece('Vendor questionnaire.pdf').getByText('Refused, malware found', { exact: true })).toBeVisible();
    await expect(piece('Vendor questionnaire.pdf').getByRole('button', { name: 'Download' })).toHaveCount(0);

    const dialog = page.getByRole('dialog', { name: 'Attach evidence' });
    // A file outside the type allow-list answers 422, in the server's words
    await panel.getByRole('button', { name: 'Attach evidence' }).click();
    await dialog.locator('#evidence-file').setInputFiles({ name: 'payroll.exe', mimeType: 'application/x-msdownload', buffer: Buffer.from('MZ not a document') });
    await dialog.getByRole('button', { name: 'Attach evidence' }).click();
    await expect(dialog.getByRole('alert')).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();

    // When the owner attaches a PDF, it is stored with a content hash and is not yet checked
    await panel.getByRole('button', { name: 'Attach evidence' }).click();
    await dialog.locator('#evidence-file').setInputFiles({ name: pdfName, mimeType: 'application/pdf', buffer: pdf });
    const stored = page.waitForResponse((response) => response.request().method() === 'POST' && /\/changes\/[^/]+\/evidence$/.test(new URL(response.url()).pathname));
    await dialog.getByRole('button', { name: 'Attach evidence' }).click();
    const created = (await (await stored).json()) as { evidence: { id: string; scanState: string; contentHash: string } };
    expect(created.evidence.scanState).toBe('pending');
    expect(created.evidence.contentHash).toMatch(/^sha256:[0-9a-f]{64}$/);
    await expect(panel.getByText('Attached. It can be opened once it has been checked for malware.')).toBeVisible();
    await expect(piece(pdfName)).toBeVisible();

    // And a link and a reference to an internal document
    await panel.getByRole('button', { name: 'Attach evidence' }).click();
    await dialog.getByRole('radio', { name: /^A link/ }).check();
    await dialog.getByRole('textbox', { name: 'Name' }).fill(linkName);
    await dialog.getByRole('textbox', { name: 'Web address' }).fill('https://www.fi.se/en/our-registers/');
    await dialog.getByRole('button', { name: 'Attach evidence' }).click();
    await expect(piece(linkName).getByRole('link', { name: linkName })).toHaveAttribute('href', 'https://www.fi.se/en/our-registers/');
    await panel.getByRole('button', { name: 'Attach evidence' }).click();
    await dialog.getByRole('radio', { name: /^A reference/ }).check();
    await dialog.getByRole('textbox', { name: 'Document' }).fill(referenceName);
    await dialog.getByRole('button', { name: 'Attach evidence' }).click();
    await expect(piece(referenceName).getByText('Reference', { exact: true })).toBeVisible();
    await signOut(page);

    // When a reader downloads the file once the worker has scanned it
    await signInAs(page, LOGINS.reader);
    await openCase(page, CASE_JOURNEYS.evidence);
    await expect(panel.getByRole('button', { name: 'Attach evidence' })).toHaveCount(0);
    await expect(async () => {
      await page.reload();
      await expect(piece(pdfName).getByText('Checked', { exact: true })).toBeVisible({ timeout: 1_000 });
    }).toPass({ timeout: 20_000 });
    const downloaded = page.waitForEvent('download');
    await piece(pdfName).getByRole('button', { name: 'Download' }).click();
    const download = await downloaded;
    // Then it streams through the API, byte for byte what was attached
    expect(download.suggestedFilename()).toBe(pdfName);
    expect(Buffer.compare(await readFile(await download.path()), pdf)).toBe(0);

    // And the audit log records the download, by the reader
    const history = await recordHistory(page, 'evidence', 'case.evidence_downloaded', created.evidence.id);
    await expect(history.and(page.locator('[data-action="case.evidence_downloaded"]')).first()).toContainText(`By ${PEOPLE.reader}`);
    await expect(history.and(page.locator('[data-action="case.evidence_attached"]')).first()).toContainText(`By ${PEOPLE.owner}`);
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
    await openSignoffCase(page, CASES.s8);
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
    await openSignoffCase(page, CASES.s9);
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
    await openSignoffCase(page, CASES.s10);
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
    await openSignoffCase(page, CASES.s11);
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
    await openSignoffCase(page, CASES.s11);
    const readerView = await showCaseFile(page);
    await expect(readerView.locator('[data-case-file-text]')).toContainText(`Case file: ${CASES.s11.title}`);
    await expect(readerView.getByRole('button', { name: 'Export', exact: true })).toHaveCount(0);
  });

  test("CAS-S14 J-2 @smoke: from Today to a triaged case", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // Tenant B's own compliance officer, on tenant B's week lead, whose So what is still the
    // library's draft (a retry finds this bank's wording already confirmed: it never goes back).
    await signInAs(page, LOGINS.secondBankComplianceOfficer);
    await openCase(page, CASE_JOURNEYS.secondBankLead);
    await backToTriage(page);
    const title = await page.getByRole('heading', { level: 1 }).innerText();

    // When they open Today and the lead change
    await page.goto('/');
    const lead = page.locator('[data-lead-card]');
    await lead.getByRole('link', { name: title }).click();
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');

    // And choose "Confirm wording" on the So what
    const soWhat = page.locator('[data-so-what]');
    const confirm = soWhat.getByRole('button', { name: 'Confirm wording' });
    await expect(confirm.or(soWhat.getByRole('button', { name: 'Rewrite' })).first()).toBeVisible();
    if (await confirm.isVisible()) await confirm.click();
    await expect(soWhat).toHaveAttribute('data-so-what-confirmed', '');

    // And triage with "Act now" and an owner
    await triage(page, PEOPLE.secondBankOfficer, 'Act now');
    // Then the case is assigned, "Act now" is a negative pill and the owner is named
    await expect(headerPill(page, 'Assigned')).toBeVisible();
    await expect(page.locator('[data-change-classification] [data-pill]').filter({ hasText: /^Act now$/ })).toHaveAttribute('data-pill', 'negative');
    await expect(page.locator('[data-case-panel="next-step"]').getByText(`Assigned to ${PEOPLE.secondBankOfficer} by ${PEOPLE.secondBankOfficer} on `)).toBeVisible();
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
    await openSignoffCase(page, CASES.j3);
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
      await openSignoffCase(page, CASES.j3);
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

  test("CAS-S19: One person closes a case that needs no work, audited, and can restore it", async ({ page, apiGuard }, testInfo) => {
    test.slow();
    allowFreshContext(apiGuard);
    const note = `Our large exposures reporting already follows the amended rules (attempt ${attemptOf(testInfo)}).`;

    // Given an assigned case and its owner, who holds cases.work
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASE_JOURNEYS.noAction);
    await assignedTo(page, PEOPLE.owner);
    const title = await page.getByRole('heading', { level: 1 }).innerText();
    // A case waiting for sign-off is never offered a close without action: that edge is the
    // sign-off's (its 409 invalid_transition, and a signed_off reason's four_eyes_violation,
    // are proved in apps/cases/tests_scenarios.py, CAS-S19)
    await openCase(page, CASE_JOURNEYS.actionsLocked);
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'signoff');
    await expect(page.getByRole('button', { name: 'No action' })).toHaveCount(0);
    await signOut(page);

    // When they choose "No action" with the reason "No action needed" and a note
    await signInAs(page, LOGINS.owner);
    await openCase(page, CASE_JOURNEYS.noAction);
    await page.locator('[data-case-panel="next-step"]').getByRole('button', { name: 'No action' }).click();
    const dialog = page.getByRole('dialog', { name: 'Close without action?' });
    // Only reasons of the no_action kind are offered: a sign-off is a second person's
    await expect(dialog.getByRole('radio')).toHaveCount(1);
    await dialog.getByRole('radio', { name: LABELS.noActionReason }).check();
    await dialog.getByLabel('Note (optional)').fill(note);
    await dialog.getByRole('button', { name: 'Close the case' }).click();
    // Then the case is closed on their word alone and the note stays on the case
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'closed');
    const closed = page.locator('[data-case-panel="closed"]');
    await expect(closed.getByText(LABELS.noActionReason, { exact: true })).toBeVisible();
    await expect(closed.getByText(note, { exact: true })).toBeVisible();

    // And the audit trail names them and the reason key, never the note
    const history = await recordHistory(page, 'change_case', 'case.moved', title);
    const close = history.and(page.locator('[data-action="case.moved"]')).filter({ has: page.locator('[data-field="status"] [data-after]', { hasText: 'closed' }) }).first();
    await expect(close).toContainText(`By ${PEOPLE.owner}`);
    await expect(close.locator('[data-field="reasonKey"] [data-after]')).toContainText('no_action');
    await expect(history.filter({ hasText: note })).toHaveCount(0);
    await signOut(page);

    // When "Move back to triage" is chosen, the case needs triage again
    await signInAs(page, LOGINS.complianceOfficer);
    await openCase(page, CASE_JOURNEYS.noAction);
    await page.getByRole('button', { name: 'Move back to triage' }).click();
    await expect(casePanels(page)).toHaveAttribute('data-case-panels', 'new');
    // And both moves stay in its history
    const moves = await recordHistory(page, 'change_case', 'case.moved', title);
    await expect(moves.filter({ has: page.locator('[data-field="status"] [data-after]', { hasText: 'closed' }) }).first()).toBeVisible();
    await expect(moves.filter({ has: page.locator('[data-field="status"] [data-after]', { hasText: 'new' }) }).first()).toContainText(`By ${PEOPLE.officer}`);
  });
});
