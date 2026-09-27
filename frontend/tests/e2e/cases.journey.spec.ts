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
    await panel.getByLabel('Owner').selectOption('');
    await panel.getByRole('button', { name: 'Confirm and assign' }).click();
    // Then the request answers 422 naming the owner field, and the case has not moved
    await expect(panel.getByText('Choose who owns this case.')).toBeVisible();
    await expect(panel.getByLabel('Owner')).toHaveAttribute('aria-invalid', 'true');
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

  test.fixme("CAS-S8: Sign-off is refused while actions are open or evidence is missing", async () => {
    // pending: CAS-S8 (CAS-06, AC-CAS1)
  });

  test.fixme("CAS-S9: The requester cannot sign off their own case", async () => {
    // pending: CAS-S9 (CAS-06, AC-CAS1)
  });

  test.fixme("CAS-S10: A second person signs off with step-up and the inventory is untouched", async () => {
    // pending: CAS-S10 (CAS-06)
  });

  test.fixme("CAS-S11: The case file stands alone as text and as an export", async () => {
    // pending: CAS-S11 (CAS-07)
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

  test.fixme("CAS-S15 J-3 @smoke: assessment to sign-off and the case file", async () => {
    // pending: CAS-S15 (CAS-03, CAS-04, CAS-05, CAS-06, CAS-07, AC-CAS1, J-3)
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
