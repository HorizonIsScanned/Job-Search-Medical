'use client';

import { useMemo, useState } from 'react';
import type { Outcome, Run } from '../types';

const OUTCOME: Record<Outcome, string> = {
  match: 'Passt',
  check: 'Prüfen',
  reject: 'Abgelehnt',
  deferred: 'Verschoben',
  over_limit: 'Später geprüft',
  no_topic: 'Kein Thema',
  text: 'Ausschluss im Text',
  title: 'Titel aussortiert',
  location: 'Ort passt nicht',
  duplicate: 'Doppelt',
  known: 'Schon bekannt',
};
const GROUPS: { key: string; label: string; outcomes: Outcome[] }[] = [
  { key: 'checked', label: 'Geprüft', outcomes: ['match', 'check', 'reject'] },
  { key: 'match', label: 'Passt', outcomes: ['match'] },
  { key: 'check', label: 'Prüfen', outcomes: ['check'] },
  { key: 'reject', label: 'Abgelehnt', outcomes: ['reject'] },
  { key: 'rules', label: 'Regeln', outcomes: ['title', 'location', 'text', 'no_topic'] },
  { key: 'later', label: 'Später', outcomes: ['deferred', 'over_limit'] },
  { key: 'known', label: 'Bekannt', outcomes: ['known', 'duplicate'] },
  { key: 'all', label: 'Alle', outcomes: Object.keys(OUTCOME) as Outcome[] },
];
const PAGE = 60;

const minutes = (s: number) => (s < 90 ? `${s} s` : `${Math.round(s / 60)} min`);

export default function RunView({ run, startedLabel }: { run: Run; startedLabel: string }) {
  const [group, setGroup] = useState('checked');
  const [q, setQ] = useState('');
  const [limit, setLimit] = useState(PAGE);
  const c = run.counts;

  const bySource = useMemo(() => {
    const m = new Map<string, Run['sources']>();
    for (const s of run.sources) m.set(s.group, [...(m.get(s.group) ?? []), s]);
    return [...m.entries()];
  }, [run]);

  const g = GROUPS.find((x) => x.key === group)!;
  const countFor = (outs: Outcome[]) => run.postings.filter((p) => outs.includes(p.outcome)).length;
  const shown = run.postings
    .filter((p) => g.outcomes.includes(p.outcome))
    .filter((p) => !q || `${p.title} ${p.org} ${p.location} ${p.source} ${p.reason}`.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1));

  const funnel = [
    { label: 'Gelesen', n: c.collected },
    { label: 'Neu', n: c.new },
    { label: 'Nach den Regeln', n: c.candidates },
    { label: 'Anforderungen geprüft', n: c.match + c.check + c.reject },
    { label: 'Passt oder Prüfen', n: c.match + c.check },
  ];
  const max = Math.max(1, c.collected);
  const failed = run.sources.filter((s) => s.status === 'failed').length;

  return (
    <>
      <h2>{startedLabel}</h2>
      <p className="section-lede">
        Dauer {minutes(run.seconds)} · {run.sources.length} Quellen, davon {failed} fehlgeschlagen ·
        Prüfung mit {run.llm.provider === 'gemini' ? 'Gemini' : 'Claude'}
        {run.llm.models.length ? ` (${run.llm.models.join(', ')})` : ''}
        {run.run_url ? (
          <>
            {' · '}
            <a href={run.run_url} target="_blank" rel="noopener noreferrer">Technisches Protokoll</a>
          </>
        ) : null}
      </p>

      <div className="tiles">
        <div className="tile"><div className="label">Anzeigen gelesen</div><div className="value">{c.collected}</div></div>
        <div className="tile"><div className="label">Davon neu</div><div className="value">{c.new}</div></div>
        <div className="tile ok"><div className="label">Passt</div><div className="value">{c.match}</div></div>
        <div className="tile warn"><div className="label">Prüfen</div><div className="value">{c.check}</div></div>
        <div className="tile bad"><div className="label">Abgelehnt</div><div className="value">{c.reject}</div></div>
      </div>
      <div className="funnel" aria-label="Trichter">
        {funnel.map((f) => (
          <div className="funnel-row" key={f.label}>
            <span>{f.label}</span>
            <span className="bar"><i style={{ width: `${(f.n / max) * 100}%` }} /></span>
            <span className="n">{f.n}</span>
          </div>
        ))}
      </div>

      <h2>Quellen</h2>
      <p className="section-lede">Was gelesen wurde und wie viele Anzeigen jede Quelle geliefert hat.</p>
      {bySource.map(([name, list]) => (
        <div key={name}>
          <div className="group-title">{name}</div>
          <div className="group">
            {list.map((s, i) => (
              <div className="row" key={i}>
                <span className={`dot s-${s.status}`} title={s.status === 'failed' ? 'fehlgeschlagen' : s.status === 'empty' ? 'leer' : 'ok'} />
                <div className="main">
                  <div className="name">
                    {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a> : s.name}
                  </div>
                  <div className="sub">{s.status === 'failed' ? `Fehlgeschlagen: ${s.note}` : s.note}</div>
                </div>
                <span className="num">{s.count}</span>
              </div>
            ))}
          </div>
        </div>
      ))}

      <h2>Anzeigen</h2>
      <p className="section-lede">Jede Anzeige dieses Laufs mit dem Ergebnis und dem Grund.</p>
      <div className="segmented" role="tablist" aria-label="Ergebnis">
        {GROUPS.map((x) => (
          <button key={x.key} role="tab" aria-selected={group === x.key} onClick={() => { setGroup(x.key); setLimit(PAGE); }}>
            {x.label}<span className="count">{countFor(x.outcomes)}</span>
          </button>
        ))}
      </div>
      <div className="filters">
        <input type="search" placeholder="Titel, Arbeitgeber, Ort oder Grund suchen" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {shown.length === 0 ? (
        <p className="empty">Keine Anzeigen in dieser Auswahl.</p>
      ) : (
        <div className="group">
          {shown.slice(0, limit).map((p, i) => (
            <div className="row" key={i}>
              <div className="main">
                <div className="name">
                  <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || 'Ohne Titel'}</a>
                </div>
                <div className="sub">
                  {[p.org, p.location, p.source].filter(Boolean).join(' · ')}
                  {typeof p.score === 'number' ? ` · Passung ${p.score}` : ''}
                </div>
                {p.reason ? <div className="sub">{p.reason}</div> : null}
              </div>
              <span className={`pill ${p.outcome}`}>{OUTCOME[p.outcome] ?? p.outcome}</span>
            </div>
          ))}
          {shown.length > limit ? (
            <button className="more" onClick={() => setLimit(limit + PAGE)}>
              Weitere {Math.min(PAGE, shown.length - limit)} von {shown.length - limit} anzeigen
            </button>
          ) : null}
        </div>
      )}
    </>
  );
}
