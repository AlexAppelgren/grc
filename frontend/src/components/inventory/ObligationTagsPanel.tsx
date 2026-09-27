'use client';

import { Button } from '@/components/ui/Button';
import { Panel } from '@/components/ui/Panel';
import { Pill } from '@/components/ui/Pill';
import { ProblemAlert } from '@/components/ui/States';
import { VocabularyPicker } from '@/components/vocabularies/VocabularyPicker';
import { useChangeObligationTag, useObligation } from '@/features/library/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { presentVocabularyValue } from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { problemFrom } from '@/shared/utils/problem';

// "Our tags" on the obligation card (VOC-03, VOC-08, VOC-S6; design/screens/
// tenant-obligation.html, "Our tags 1" to "Our tags 6"). The bank's own tags
// come with the obligation read and sit apart from the library's tags. A holder
// of vocab.manage takes one off with its remove control and puts one on with
// the picker, which offers an existing tag first and Create last; each is one
// write, stored at once, because either is undone by the other. Everyone else
// reads the tags, and the same picker offers only Suggest for a tag that does
// not exist yet: it cannot put an existing tag on the record.

const LIST = 'tenant_tag';
const VOCAB_MANAGE = 'vocab.manage';
/** The refusals said in the panel's own words; anything else offers Try again. */
const KNOWN_REFUSALS: ReadonlySet<string> = new Set(['unknown_key', 'permission_denied']);

export function ObligationTagsPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const permissions = usePermissions();
  const obligation = useObligation(obligationId);
  const values = useVocabularyValues(LIST);
  const change = useChangeObligationTag(obligationId);

  if (obligation.data === undefined || permissions === null) return null;
  const tags = obligation.data.tenantTags;
  const manages = permissions.includes(VOCAB_MANAGE);
  const keys = tags.map((tag) => tag.key);

  const onChange = (next: string[]) => {
    const added = next.find((key) => !keys.includes(key));
    const removed = keys.find((key) => !next.includes(key));
    if (added !== undefined) change.mutate({ tagKey: added, on: true });
    else if (removed !== undefined) change.mutate({ tagKey: removed, on: false });
  };

  const tried = change.variables?.tagKey;
  const triedLabel = values.data?.find((row) => row.key === tried)?.label ?? tags.find((tag) => tag.key === tried)?.label ?? tried ?? '';

  return (
    <Panel title={t('obligationTags.heading')} className="bg-subtle" data-obligation-tags="">
      {tags.length === 0 ? (
        <p className="mb-2 text-meta text-muted">{t('obligationTags.none')}</p>
      ) : (
        <ul className="m-0 mb-2 flex list-none flex-wrap items-center gap-1.5 p-0">
          {tags.map((tag) => {
            const pill = presentVocabularyValue(LIST, { key: tag.key, kind: tag.kind, label: tag.label, extra: {} });
            return (
              <li key={tag.key} className="inline-flex items-center gap-0.5" data-obligation-tag={tag.key}>
                <Pill tone={pill.tone} outlined={pill.outlined}>
                  {pill.label}
                </Pill>
                {manages ? (
                  <button
                    type="button"
                    className="rounded-full px-1 text-muted hover:text-fg"
                    aria-label={t('obligationTags.remove', { label: tag.label })}
                    disabled={change.isPending}
                    onClick={() => onChange(keys.filter((key) => key !== tag.key))}
                  >
                    {REMOVE_GLYPH}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <VocabularyPicker
        list={LIST}
        tier="tenant"
        label={manages ? t('obligationTags.add') : t('obligationTags.suggest')}
        value={keys}
        onChange={onChange}
        showSelected={false}
        canPick={manages}
      />

      {change.isError ? (
        KNOWN_REFUSALS.has(problemFrom(change.error)?.code ?? '') ? (
          <ProblemAlert
            error={change.error}
            codes={{
              unknown_key: t('obligationTags.retired', { label: triedLabel }),
              permission_denied: t('obligationTags.denied'),
            }}
          />
        ) : (
          <div role="alert" className="flex flex-wrap items-center gap-2" data-obligation-tags-failed="">
            <span className="text-meta text-negative">{t('obligationTags.failed')}</span>
            {change.variables !== undefined ? (
              <Button variant="outline" size="small" onClick={() => change.variables !== undefined && change.mutate(change.variables)}>
                {t('common.tryAgain')}
              </Button>
            ) : null}
          </div>
        )
      ) : null}
    </Panel>
  );
}

/** The remove control's glyph: an icon, not copy; its name comes from the catalog. */
const REMOVE_GLYPH = '×';
