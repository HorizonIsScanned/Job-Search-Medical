import Link from 'next/link';
import { berlin, loadJson } from '../lib/blob';
import type { Run, RunSummary } from '../types';
import RunView from './RunView';

export const dynamic = 'force-dynamic';


export default async function Runs({ searchParams }: { searchParams: Promise<{ run?: string }> }) {
  const { run: wanted } = await searchParams;
  const runs = (await loadJson<Run[]>('board/runs.json')) ?? [];
  const run = runs.find((r) => r.id === wanted) ?? runs[0];
  const summaries: RunSummary[] = runs.map(({ sources: _s, postings: _p, ...rest }) => rest);

  return (
    <main>
      <section className="hero">
        <h1>Läufe</h1>
        <p className="lede">
          Jeder Suchlauf, nachvollziehbar: welche Quellen gelesen wurden, welche Anzeigen dabei waren und warum
          eine Stelle angezeigt, zur Prüfung gelegt oder aussortiert wurde.
        </p>
      </section>
      {runs.length === 0 ? (
        <p className="empty">Noch kein protokollierter Lauf. Das Protokoll entsteht ab dem nächsten Suchlauf.</p>
      ) : (
        <>
          <div className="runs" role="list">
            {summaries.map((r) => (
              <Link key={r.id} href={`/laeufe?run=${r.id}`} role="listitem" className={r.id === run.id ? 'active' : ''}>
                <div className="when">{berlin(r.started, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                <div className="what">
                  {r.counts.match} passt · {r.counts.check} prüfen · {r.counts.collected} gelesen
                </div>
              </Link>
            ))}
          </div>
          <RunView run={run} startedLabel={berlin(run.started, { dateStyle: 'full', timeStyle: 'short' })} />
        </>
      )}
    </main>
  );
}
