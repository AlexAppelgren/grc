import { AdminGate } from '@/components/admin/AdminGate';
import { VocabularyScreen } from '@/components/admin/VocabularyScreen';

export default async function ConsoleVocabularyPage({ params }: { params: Promise<{ list: string }> }) {
  const { list } = await params;
  return (
    <AdminGate id="console-vocabularies">
      <VocabularyScreen list={decodeURIComponent(list)} surface="console" />
    </AdminGate>
  );
}
