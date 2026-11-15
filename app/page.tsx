import { get } from '@vercel/blob';
import Board from './Board';
import type { BoardState } from './types';

export const dynamic = 'force-dynamic';

async function loadState(): Promise<BoardState | null> {
  try {
    const res = await get('board/state.json', { access: 'private' });
    if (!res) return null;
    const text = await new Response(res.stream).text();
    return text ? (JSON.parse(text) as BoardState) : null;
  } catch (e) {
    console.error('could not load state', e);
    return null;
  }
}

export default async function Page() {
  const state = await loadState();
  const title = process.env.BOARD_TITLE || 'Jobboard';
  const jobs = (state?.jobs ?? []).filter((j) => j.match.status !== 'reject');
  return (
    <main>
      <header className="top">
        <h1>{title}</h1>
        <p className="sub">
          {state?.updated
            ? `Zuletzt aktualisiert: ${new Date(state.updated).toLocaleString('de-DE', { timeZone: 'Europe/Berlin', dateStyle: 'medium', timeStyle: 'short' })}`
            : 'Noch kein Suchlauf.'}
          {state?.last_run ? ` · letzter Lauf: ${state.last_run.collected} Anzeigen gelesen, ${state.last_run.match} neue Treffer` : ''}
        </p>
      </header>
      <Board jobs={jobs} updated={state?.updated ?? ''} />
    </main>
  );
}
