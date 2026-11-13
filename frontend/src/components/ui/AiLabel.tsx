// The label on words a model wrote, until a person stands behind them (CLAUDE.md section 5):
// Ask's answer and a drafted reason say so in the same place and the same voice.
export function AiLabel({ text, id }: { text: string; id?: string }) {
  return (
    <div id={id} className="mb-3 rounded-control bg-surface px-3.5 py-3" data-ai-label="">
      <span className="block text-meta font-semibold text-brass">{text}</span>
    </div>
  );
}
