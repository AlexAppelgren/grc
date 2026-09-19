import { AdminGate } from '@/components/admin/AdminGate';
import { VocabularyScreen } from '@/components/admin/VocabularyScreen';

export default async function VocabularyPage({ params }: { params: Promise<{ list: string }> }) {
  const { list } = await params;
  return (
    <AdminGate id="admin-vocabularies">
      <VocabularyScreen list={decodeURIComponent(list)} />
    </AdminGate>
  );
}
