import Board from './Board';
import { berlin, loadJson } from './lib/blob';
import type { BoardState } from './types';

export const dynamic = 'force-dynamic';

export default async function Page() {
  const state = await loadJson<BoardState>('board/state.json');
  const jobs = (state?.jobs ?? []).filter((j) => j.match.status !== 'reject');
  return (
    <main>
      <section className="hero">
        <h1>Stellen</h1>
        <p className="lede">
          {state?.updated ? `Aktualisiert am ${berlin(state.updated)}.` : 'Noch kein Suchlauf.'}
          {state?.last_run ? ` Im letzten Lauf ${state.last_run.collected} Anzeigen gelesen, ${state.last_run.match} neue Treffer.` : ''}
        </p>
      </section>
      <Board jobs={jobs} updated={state?.updated ?? ''} />
    </main>
  );
}
