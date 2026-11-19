'use client';

import { useMemo, useState, type CSSProperties } from 'react';
import type { JobEntry, Language } from './types';

const ROLE: Record<string, string> = {
  phd: 'Promotion / PhD',
  study_assistant: 'Studienassistenz / Koordination',
  research_assistant: 'Research Assistant / Hilfskraft',
  lab_assistant: 'Laborassistenz',
  care_assistant: 'Pflegehilfe / Betreuung',
  patient_service: 'Patientenservice',
  admin_documentation: 'Med. Dokumentation / Verwaltung',
  health_startup: 'Health-Startup / MedTech',
  medical_writing_info: 'Medical Writing / Information',
};
const STREAM = { research: 'Forschung & PhD', bridge: 'Übergangsjobs' } as const;
type Stream = keyof typeof STREAM;
const streamOf = (j: JobEntry): Stream => j.match.stream ?? 'research';
const KIND = { phd: 'Promotion', job: 'Job', other: 'Sonstiges' } as const;
const LANG = { de: 'Deutsch', en: 'Englisch', es: 'Spanisch', fr: 'Französisch', other: 'Andere' } as const;
const RANK: Record<Language['level'], number> = { A1: 1, A2: 2, B1: 3, B2: 4, C1: 5, C2: 6, native: 7, unspecified: 0 };
const LEVEL_LABEL = (l: Language['level']) => (l === 'native' ? 'Muttersprache' : l === 'unspecified' ? 'Niveau offen' : l);

type GermanFilter = 'all' | 'none' | 'B1' | 'B2' | 'C1' | 'open';
const GERMAN: Record<GermanFilter, string> = {
  all: 'Deutsch: alle Niveaus',
  none: 'Kein Deutsch gefordert',
  B1: 'Deutsch bis B1',
  B2: 'Deutsch bis B2',
  C1: 'Deutsch C1 oder höher',
  open: 'Deutsch, Niveau nicht genannt',
};

function germanOk(j: JobEntry, f: GermanFilter): boolean {
  if (f === 'all') return true;
  const de = (j.match.languages ?? []).find((l) => l.lang === 'de' && l.mandatory);
  if (f === 'none') return !de;
  if (f === 'open') return !!de && de.level === 'unspecified';
  if (f === 'C1') return !!de && RANK[de.level] >= 5;
  const max = f === 'B1' ? 3 : 4;
  return !de || (de.level !== 'unspecified' && RANK[de.level] <= max);
}

export default function Board({ jobs: allJobs, updated }: { jobs: JobEntry[]; updated: string }) {
  const [stream, setStream] = useState<Stream>('research');
  const [area, setArea] = useState('all');
  const jobs = allJobs.filter((j) => streamOf(j) === stream);
  const areas = Array.from(new Set(jobs.map((j) => j.match.role ?? '').filter(Boolean)));
  const [tab, setTab] = useState<'match' | 'check' | 'all'>('match');
  const [german, setGerman] = useState<GermanFilter>('all');
  const [kind, setKind] = useState<'all' | 'phd' | 'job'>('all');
  const [topic, setTopic] = useState('all');
  const [q, setQ] = useState('');

  const topics = useMemo(() => Array.from(new Set(jobs.flatMap((j) => j.match.topics))).sort(), [jobs]);
  const lastRun = updated ? new Date(updated).getTime() : 0;

  const shown = jobs
    .filter((j) => tab === 'all' || j.match.status === tab)
    .filter((j) => germanOk(j, german))
    .filter((j) => kind === 'all' || j.match.kind === kind)
    .filter((j) => area === 'all' || j.match.role === area)
    .filter((j) => topic === 'all' || j.match.topics.includes(topic))
    .filter((j) => !q || `${j.title} ${j.org} ${j.location}`.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => b.match.score - a.match.score || b.first_seen.localeCompare(a.first_seen));

  const count = (s: string) => jobs.filter((j) => j.match.status === s).length;

  return (
    <>
      <div className="streams" role="tablist" aria-label="Stream">
        {(Object.keys(STREAM) as Stream[]).map((s) => (
          <button key={s} role="tab" aria-selected={stream === s} onClick={() => { setStream(s); setArea('all'); }}>
            {STREAM[s]} <span className="count">{allJobs.filter((j) => streamOf(j) === s).length}</span>
          </button>
        ))}
      </div>
      <p className="hint">
        {stream === 'research'
          ? 'PhD, wissenschaftliche Mitarbeit und Studienassistenz an Unis, Instituten und CROs. Strenge Regeln.'
          : 'Bezahlte Jobs bis zur Approbation, bei denen ein medizinisches Profil gesucht wird: Labor, Studien, Pflegehilfe, Patientenservice, Dokumentation, Health-Startups.'}
      </p>
      <div className="segmented" role="tablist" aria-label="Ansicht">
        <button role="tab" aria-selected={tab === 'match'} onClick={() => setTab('match')}>
          Passt <span className="count">{count('match')}</span>
        </button>
        <button role="tab" aria-selected={tab === 'check'} onClick={() => setTab('check')}>
          Prüfen <span className="count">{count('check')}</span>
        </button>
        <button role="tab" aria-selected={tab === 'all'} onClick={() => setTab('all')}>
          Alle <span className="count">{jobs.length}</span>
        </button>
      </div>
      <p className="hint">
        {tab === 'match'
          ? 'Alle Pflichtanforderungen sind laut Lebenslauf erfüllt.'
          : tab === 'all'
          ? 'Passt und Prüfen zusammen. Stellen mit einer nicht erfüllten Pflichtanforderung erscheinen nie.'
          : 'Mindestens eine Pflichtanforderung ist unklar (z. B. „gute Deutschkenntnisse“), keine Teilzeit oder Ort unbekannt. Bitte selbst prüfen.'}
      </p>
      <div className="filters">
        {stream === 'research' ? (
          <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="Art">
            <option value="all">Promotion und Job</option>
            <option value="phd">Nur Promotion</option>
            <option value="job">Nur Job</option>
          </select>
        ) : null}
        <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Bereich">
          <option value="all">Alle Bereiche</option>
          {areas.map((a) => (
            <option key={a} value={a}>{ROLE[a] ?? a}</option>
          ))}
        </select>
        <select value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Thema">
          <option value="all">Alle Themen</option>
          {topics.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <select value={german} onChange={(e) => setGerman(e.target.value as GermanFilter)} aria-label="Gefordertes Deutschniveau">
          {(Object.keys(GERMAN) as GermanFilter[]).map((k) => (
            <option key={k} value={k}>{GERMAN[k]}</option>
          ))}
        </select>
        <input type="search" placeholder="Suchen…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {shown.length === 0 && <p className="empty">Keine Stellen in dieser Ansicht.</p>}
      <ul className="list">
        {shown.map((j) => {
          const isNew = lastRun && new Date(j.first_seen).getTime() >= lastRun - 6 * 3600 * 1000;
          const mandatory = j.match.requirements.filter((r) => r.mandatory);
          const optional = j.match.requirements.filter((r) => !r.mandatory);
          return (
            <li key={j.id} className="card">
              <div className="head">
                <span className="ring" style={{ '--p': j.match.score } as CSSProperties} title="Passung von 0 bis 100">
                  <span>{j.match.score}</span>
                </span>
                <div>
                  <a className="title" href={j.url} target="_blank" rel="noopener noreferrer">
                    {j.title}
                  </a>
                  <div className="meta">
                    {j.org} · {j.location || 'Ort unbekannt'}
                    {j.remote ? ' · remote' : ''} · {ROLE[j.match.role ?? ''] ?? KIND[j.match.kind] ?? 'Job'}
                    {j.match.deadline ? ` · Frist ${j.match.deadline.split('-').reverse().join('.')}` : ''}
                    {tab === 'all' ? (j.match.status === 'match' ? ' · passt' : ' · prüfen') : ''}
                    {j.match.part_time === 'yes' ? ' · Teilzeit möglich' : ''} · via {j.source}
                  </div>
                </div>
                {isNew ? <span className="badge new">Neu</span> : null}
              </div>
              <p className="summary">{j.match.summary}</p>
              {j.match.notes && j.match.notes.length > 0 && <p className="notes">Hinweis: {j.match.notes.join(', ')}</p>}
              {(j.match.languages ?? []).length > 0 && (
                <div className="chips">
                  {(j.match.languages ?? []).map((l, i) => (
                    <span key={i} className={`chip lang${l.mandatory ? '' : ' optional'}`}>
                      {LANG[l.lang] ?? l.lang} {LEVEL_LABEL(l.level)}
                      {l.mandatory ? '' : ' (wünschenswert)'}
                    </span>
                  ))}
                </div>
              )}
              {j.match.topics.length > 0 && (
                <div className="chips">
                  {j.match.topics.map((t) => (
                    <span key={t} className="chip">{t}</span>
                  ))}
                </div>
              )}
              {mandatory.length > 0 && (
                <details>
                  <summary>Anforderungen ({mandatory.filter((r) => r.status === 'met').length} von {mandatory.length} Pflicht erfüllt)</summary>
                  <ul className="reqs">
                    {mandatory.map((r, i) => (
                      <li key={i} className={r.status}>
                        <span aria-hidden>{r.status === 'met' ? '✓' : r.status === 'unclear' ? '?' : '✗'}</span> {r.text}
                      </li>
                    ))}
                    {optional.map((r, i) => (
                      <li key={`o${i}`} className={`${r.status} optional`}>
                        <span aria-hidden>{r.status === 'met' ? '✓' : r.status === 'unclear' ? '?' : '–'}</span> {r.text} (wünschenswert)
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
