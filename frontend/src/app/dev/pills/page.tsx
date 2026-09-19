import { Pill, pillToneNames } from '@/components/ui/Pill';
import { PillRow } from '@/components/ui/PillRow';
import { presentRoadmapItem } from '@/features/home/roadmap-presentation';
import { presentObligation, presentScope } from '@/features/library/obligation-presentation';
import { presentGap } from '@/features/register/gap-presentation';
import { presentChange } from '@/features/watch/change-presentation';
import { createT, defaultLocale, type Locale } from '@/shared/i18n';

import { changes, complianceStatuses, gapStatuses, gaps, obligations, roadmapItems, scopeEntities, severities, urgencies } from './samples';

// /dev/pills: every tone, every slot, every record type, light and dark side
// by side (playbook 6.7). A Playwright screenshot pins it in both themes.
// The columns carry their own theme class, so the page looks the same
// whichever theme the visitor uses.

function Record({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 rounded-card border border-line bg-surface px-4 py-3">{children}</div>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="microlabel mb-2.5 text-muted">{title}</h2>
      {children}
    </section>
  );
}

function Meta({ children }: { children: React.ReactNode }) {
  return <span className="text-meta text-muted">{children}</span>;
}

function ThemeColumn({ theme, locale }: { theme: 'light' | 'dark'; locale: Locale }) {
  const t = createT(locale);
  const scope = presentScope(scopeEntities, false, t);
  const allServices = presentScope([], true, t);
  const noClients = presentScope([], false, t);

  return (
    <div className={`${theme} bg-page px-6 pt-7 pb-10 text-fg`} data-theme-column={theme}>
      <h1 className="text-title">{theme === 'light' ? t('dev.pills.light') : t('dev.pills.dark')}</h1>
      <p className="mt-1 max-w-[60ch] text-meta text-muted">{t('dev.pills.lede')}</p>

      <Section title={t('dev.pills.tones')}>
        <span className="flex flex-wrap items-center gap-1.5">
          {pillToneNames.map((tone) => (
            <Pill key={tone} tone={tone}>
              {tone}
            </Pill>
          ))}
          <Pill tone="information" outlined>
            {t('dev.pills.tenantTag')}
          </Pill>
        </span>
      </Section>

      <Section title={t('dev.pills.changeRow')}>
        {changes.map((c) => (
          <Record key={c.title}>
            <PillRow pills={presentChange(c.facts, 'header')}>
              <Meta>{c.authority}</Meta>
            </PillRow>
            <h3 className="mt-1.5 font-semibold">{c.title}</h3>
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.obligationRow')}>
        {obligations.map((o) => (
          <Record key={o.title}>
            <PillRow pills={presentObligation(o.facts, 'row', t)} />
            <h3 className="mt-1.5 font-semibold">{o.title}</h3>
            {o.meta.length > 0 ? (
              <p className="mt-1 flex gap-4">
                {o.meta.map((m) => (
                  <Meta key={m}>{m}</Meta>
                ))}
              </p>
            ) : null}
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.obligationHeader')}>
        {obligations.map((o) => (
          <Record key={o.title}>
            <PillRow pills={presentObligation(o.facts, 'header', t)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.scopeBlock')}>
        <Record>
          <PillRow pills={scope.pills} />
          <div className="mt-1.5">
            <PillRow pills={allServices.pills} />
          </div>
          <div className="mt-1.5">
            <Meta>{noClients.plainText}</Meta>
          </div>
        </Record>
      </Section>

      <Section title={t('dev.pills.gap')}>
        {gaps.map((g) => (
          <Record key={g.status.key}>
            <PillRow pills={presentGap(g)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.roadmapItem')}>
        <Record>
          {roadmapItems.map((item, i) => (
            <div key={i} className={i > 0 ? 'mt-1.5' : undefined}>
              <PillRow pills={presentRoadmapItem(item, t)} />
            </div>
          ))}
        </Record>
      </Section>

      <Section title={t('dev.pills.severityScales')}>
        <PillRow pills={urgencies.flatMap((u) => presentRoadmapItem({ urgency: u, ourDeadline: false }, t))} />
        <div className="mt-1.5">
          <PillRow
            pills={complianceStatuses.flatMap((c) =>
              presentObligation({ instrument: { key: 'x', label: 'x' }, binding: true, complianceStatus: c }, 'row', t).filter(
                (p) => p.key.startsWith('compliance:'),
              ),
            )}
          />
        </div>
        <div className="mt-1.5">
          <PillRow
            pills={gapStatuses.flatMap((g) =>
              presentGap({ status: g, severity: { key: 'low', kind: 'low', label: 'Low' } }).filter((p) => p.key.startsWith('gap-status:')),
            )}
          />
        </div>
        <div className="mt-1.5">
          <PillRow
            pills={severities.flatMap((s) =>
              presentGap({ status: { key: 'open', kind: 'open', label: 'Open' }, severity: s }).filter((p) => p.key.startsWith('severity:')),
            )}
          />
        </div>
      </Section>
    </div>
  );
}

export default function PillsGalleryPage() {
  return (
    <div className="grid min-h-screen md:grid-cols-2" data-pills-gallery="">
      <ThemeColumn theme="light" locale={defaultLocale} />
      <ThemeColumn theme="dark" locale={defaultLocale} />
    </div>
  );
}
