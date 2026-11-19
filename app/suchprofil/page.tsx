import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parse } from 'yaml';

// Read once at build time from config/search.yaml, so the page always matches the deployed search.
export const dynamic = 'force-static';

type Topic = { label: string; weight: number; words: string[] };
type Cfg = {
  locations: { name: string; aliases: string[] }[];
  remote_words: string[];
  queries: string[];
  streams?: { bridge?: { label: string; queries: string[]; jobspy_queries?: string[]; rules: { allowed_roles: string[]; max_years_experience: number } } };
  topics: Record<string, Topic>;
  exclude_title: string[];
  exclude_text: string[];
  bundesagentur: { enabled: boolean; radius_km: number; days: number; first_run_days: number; size: number; cities: string[] };
  jobspy: { enabled: boolean; sites: string[]; results_wanted: number; hours_old: number; queries: string[]; places: { location: string; remote?: boolean }[] };
  sites: { name: string; url: string }[];
  ats: { type: string; name: string }[];
  matching: { provider: string; max_llm_checks_per_run: number; min_prefilter_score: number;
    rules?: { allowed_roles: string[]; max_german: string; max_years_experience: number } };
  notify: { min_score: number; high_priority_score: number; max_items: number; max_failed_sources: number };
  keep_days: number;
};

const SITE = { indeed: 'Indeed', google: 'Google Jobs', linkedin: 'LinkedIn' } as Record<string, string>;

const ROLE_NAMES: Record<string, string> = {
  phd: 'Promotion / PhD',
  study_assistant: 'Studienassistenz, Clinical Trial Assistant, Study Coordinator',
  research_assistant: 'Research Assistant und wissenschaftliche Hilfskraft',
};

const BRIDGE_ROLES: Record<string, string> = {
  study_assistant: 'Studienassistenz',
  research_assistant: 'Research Assistant',
  lab_assistant: 'Laborassistenz und Laborhilfe',
  care_assistant: 'Pflegehilfe und Betreuung',
  patient_service: 'Patientenservice und Aufnahme',
  admin_documentation: 'Medizinische Dokumentation und Verwaltung',
  health_startup: 'Health-Startups und MedTech',
  medical_writing_info: 'Medical Writing und Information',
};

export default function Suchprofil() {
  const cfg = parse(readFileSync(join(process.cwd(), 'config', 'search.yaml'), 'utf8')) as Cfg;
  const topics = Object.values(cfg.topics).sort((a, b) => b.weight - a.weight);
  const maxW = Math.max(...topics.map((t) => t.weight));
  const sites = [...new Map(cfg.sites.map((s) => [s.name, s])).values()];
  const euraxess = cfg.sites.filter((s) => s.name === 'EURAXESS').length;

  return (
    <main>
      <section className="hero">
        <h1>Suchprofil</h1>
        <p className="lede">
          Wonach gesucht wird, wo gesucht wird und nach welchen Regeln eine Stelle angezeigt wird. Alle Werte kommen
          direkt aus der Suchkonfiguration.
        </p>
      </section>

      <h2>So entsteht die Liste</h2>
      <p className="section-lede">Jeden Morgen um 6:30 Uhr läuft die Suche in fünf Schritten.</p>
      <ol className="steps">
        <li>
          <h3>Sammeln</h3>
          <p>{cfg.queries.length} Suchbegriffe in der Jobbörse der Bundesagentur, auf Jobbörsen, {sites.length} Karriereseiten und {cfg.ats.length} Bewerbungsportalen.</p>
        </li>
        <li>
          <h3>Doppelte entfernen</h3>
          <p>Gleicher Link oder gleicher Titel beim gleichen Arbeitgeber zählt einmal. Schon bewertete Anzeigen werden übersprungen.</p>
        </li>
        <li>
          <h3>Regeln</h3>
          <p>Titel, Ort und Ausschlüsse im Text. Mindestens ein Themenbegriff muss vorkommen.</p>
        </li>
        <li>
          <h3>Anforderungen prüfen</h3>
          <p>Bis zu {cfg.matching.max_llm_checks_per_run} Anzeigen pro Lauf: jede Pflichtanforderung wird mit dem Lebenslauf verglichen.</p>
        </li>
        <li>
          <h3>Einordnen und melden</h3>
          <p>Passt, Prüfen oder Abgelehnt. Treffer ab {cfg.notify.min_score} Punkten kommen als Push aufs Handy.</p>
        </li>
      </ol>

      <h2>Einordnung</h2>
      <p className="section-lede">Die Regel ist streng: Eine Stelle erscheint nur, wenn keine Pflichtanforderung sicher fehlt.</p>
      <div className="group">
        <div className="rule"><span className="pill match">Passt</span><span>Alle Pflichtanforderungen sind laut Lebenslauf erfüllt, Teilzeit ist möglich oder unklar, der Ort ist bekannt.</span></div>
        <div className="rule"><span className="pill check">Prüfen</span><span>Mindestens eine Pflichtanforderung ist unklar (z. B. „gute Deutschkenntnisse“), oder es gibt keine Teilzeit, oder der Ort fehlt.</span></div>
        <div className="rule"><span className="pill reject">Abgelehnt</span><span>Mindestens eine Pflichtanforderung ist nicht erfüllt, eine Approbation oder ein Facharzttitel ist nötig, oder es ist keine Stellenanzeige. Wird nie angezeigt.</span></div>
      </div>

      <h2>Harte Ausschlüsse</h2>
      <p className="section-lede">Jede dieser Bedingungen führt immer zu „Abgelehnt“, egal wie gut die Stelle sonst passt.</p>
      <div className="group">
        <div className="rule"><span className="pill reject">Rolle</span><span>Nur {(cfg.matching.rules?.allowed_roles ?? []).map((r) => ROLE_NAMES[r] ?? r).join(', ')}.</span></div>
        <div className="rule"><span className="pill reject">Deutsch</span><span>Verlangt die Anzeige mehr als {cfg.matching.rules?.max_german ?? 'B2'} (z. B. „sehr gute“ oder „verhandlungssichere“ Deutschkenntnisse, C1), fällt sie raus. „Gute Deutschkenntnisse“ (B2) sind in Ordnung.</span></div>
        <div className="rule"><span className="pill reject">Erfahrung</span><span>{(cfg.matching.rules?.max_years_experience ?? 0) === 0 ? 'Keine geforderten Berufsjahre. „Erste Erfahrung“ oder „von Vorteil“ ist in Ordnung.' : `Höchstens ${cfg.matching.rules?.max_years_experience} Jahre Berufserfahrung.`}</span></div>
        <div className="rule"><span className="pill reject">Approbation</span><span>Keine Stellen, die eine Approbation, Berufserlaubnis oder einen Facharzttitel verlangen.</span></div>
        <div className="rule"><span className="pill reject">Labor</span><span>Keine Stellen mit Pflicht zu Zellkultur, PCR, Molekularbiologie oder Tierversuchen.</span></div>
        <div className="rule"><span className="pill reject">Fachgebiet</span><span>Schwerpunkt Frauengesundheit, Epidemiologie, Public Health und Prävention. Verwandte klinische Forschung ist erlaubt, weit entfernte Gebiete nicht.</span></div>
        <div className="rule"><span className="pill reject">Ort</span><span>Nur die Orte unten oder remote. Stellen im Ausland außerhalb dieser Orte fallen raus.</span></div>
        <div className="rule"><span className="pill reject">Frist</span><span>Abgelaufene oder geschlossene Ausschreibungen fallen raus, auch nachträglich vom Board.</span></div>
      </div>

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="panel">
          <h3>Passung (0 bis 100)</h3>
          <p>Wie gut Fachgebiet und Aufgaben zu Interessen und Zielen passen, unabhängig von den Anforderungen. Bewertet von {cfg.matching.provider === 'gemini' ? 'Gemini' : 'Claude'}. Teilzeit möglich gibt 5 Punkte dazu.</p>
        </div>
        <div className="panel">
          <h3>Vorfilter-Punkte</h3>
          <p>Summe der Gewichte aller Themen, die in der Anzeige vorkommen, plus 5, wenn ein Suchbegriff im Titel steht. Mindestens {cfg.matching.min_prefilter_score} Punkt nötig. Die höchsten werden zuerst geprüft.</p>
        </div>
        <div className="panel">
          <h3>Benachrichtigung</h3>
          <dl className="kv">
            <dt>Push ab</dt><dd>{cfg.notify.min_score} Punkten</dd>
            <dt>Hohe Priorität ab</dt><dd>{cfg.notify.high_priority_score} Punkten</dd>
            <dt>Höchstens</dt><dd>{cfg.notify.max_items} Stellen pro Push</dd>
            <dt>Warnung ab</dt><dd>{cfg.notify.max_failed_sources + 1} fehlgeschlagenen Quellen</dd>
          </dl>
        </div>
        <div className="panel">
          <h3>Aufbewahrung</h3>
          <dl className="kv">
            <dt>Stellen</dt><dd>{cfg.keep_days} Tage</dd>
            <dt>Prüfungen pro Lauf</dt><dd>bis {cfg.matching.max_llm_checks_per_run}</dd>
            <dt>Rest</dt><dd>im nächsten Lauf</dd>
          </dl>
        </div>
      </div>

      <h2>Themen und Gewichte</h2>
      <p className="section-lede">Bestimmen die Reihenfolge der Prüfung und die Themen-Filter auf der Stellenseite.</p>
      <div className="group">
        {topics.map((t) => (
          <div className="weight" key={t.label}>
            <h3>{t.label}</h3>
            <span className="num">{t.weight}</span>
            <span className="bar"><i style={{ width: `${(t.weight / maxW) * 100}%` }} /></span>
            <span className="words">{t.words.join(', ')}</span>
          </div>
        ))}
      </div>

      <h2>Suchbegriffe</h2>
      <p className="section-lede">
        Alle {cfg.queries.length} Begriffe gehen an die Bundesagentur. Die blau markierten {cfg.jobspy.queries.length} gehen zusätzlich an{' '}
        {cfg.jobspy.sites.map((s) => SITE[s] ?? s).join(', ')} und die Bewerbungsportale.
      </p>
      <div className="chips">
        {[...new Set([...cfg.queries, ...cfg.jobspy.queries])].map((q) => (
          <span key={q} className={`chip${cfg.jobspy.queries.includes(q) ? ' lang' : ''}`}>{q}</span>
        ))}
      </div>

      {cfg.streams?.bridge ? (
        <>
          <h2>Zweiter Stream: {cfg.streams.bridge.label}</h2>
          <p className="section-lede">
            Bezahlte Jobs bis zur Approbation. Jede Anzeige wird einmal geprüft: Erfüllt sie die strengen Regeln oben, steht sie unter Forschung &amp; PhD.
            Sonst kommt sie hierher, wenn diese Regeln passen.
          </p>
          <div className="group">
            <div className="rule"><span className="pill match">Rollen</span><span>{cfg.streams.bridge.rules.allowed_roles.map((r) => BRIDGE_ROLES[r] ?? r).join(', ')}.</span></div>
            <div className="rule"><span className="pill reject">Erfahrung</span><span>Höchstens {cfg.streams.bridge.rules.max_years_experience} Jahr Berufserfahrung gefordert.</span></div>
            <div className="rule"><span className="pill reject">Ausbildung</span><span>Keine Stellen, die eine abgeschlossene Ausbildung verlangen (Pflegefachkraft, MFA, MTA, Laborant).</span></div>
            <div className="rule"><span className="pill reject">Bezahlt</span><span>Keine Praktika, kein Ehrenamt, keine Jobs nur für Eingeschriebene.</span></div>
            <div className="rule"><span className="pill reject">Wie oben</span><span>Deutsch höchstens B2, keine Approbation, keine Zellkultur, Ort aus der Liste, keine abgelaufene Frist.</span></div>
          </div>
          <div className="chips" style={{ marginTop: 14 }}>
            {[...new Set([...cfg.streams.bridge.queries, ...(cfg.streams.bridge.jobspy_queries ?? [])])].map((q) => (
              <span key={q} className="chip">{q}</span>
            ))}
          </div>
        </>
      ) : null}

      <h2>Orte</h2>
      <p className="section-lede">Eine Stelle muss an einem dieser Orte liegen oder remote möglich sein.</p>
      <div className="chips">
        {cfg.locations.map((l) => <span key={l.name} className="chip lang">{l.name}</span>)}
        <span className="chip lang">Remote</span>
      </div>
      <p className="hint">Als remote zählt: {cfg.remote_words.join(', ')}.</p>

      <h2>Quellen</h2>
      <div className="grid2">
        <div className="panel">
          <h3>Bundesagentur für Arbeit</h3>
          <dl className="kv">
            <dt>Städte</dt><dd>{cfg.bundesagentur.cities.join(', ')}</dd>
            <dt>Umkreis</dt><dd>{cfg.bundesagentur.radius_km} km</dd>
            <dt>Zeitraum</dt><dd>letzte {cfg.bundesagentur.days} Tage</dd>
            <dt>Je Anfrage</dt><dd>bis {cfg.bundesagentur.size} Anzeigen</dd>
          </dl>
        </div>
        <div className="panel">
          <h3>Jobbörsen</h3>
          <dl className="kv">
            <dt>Portale</dt><dd>{cfg.jobspy.sites.map((s) => SITE[s] ?? s).join(', ')}</dd>
            <dt>Orte</dt><dd>{cfg.jobspy.places.map((p) => (p.remote ? 'Remote' : p.location)).join(', ')}</dd>
            <dt>Zeitraum</dt><dd>letzte {cfg.jobspy.hours_old} Stunden</dd>
            <dt>Je Anfrage</dt><dd>bis {cfg.jobspy.results_wanted} Anzeigen</dd>
          </dl>
        </div>
        <div className="panel">
          <h3>Karriereseiten</h3>
          <p>
            {sites.map((s, i) => (
              <span key={s.name}>
                {i ? ', ' : ''}
                <a href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a>
                {s.name === 'EURAXESS' && euraxess > 1 ? ` (${euraxess} Suchen)` : ''}
              </span>
            ))}
          </p>
        </div>
        <div className="panel">
          <h3>Bewerbungsportale</h3>
          <p>{cfg.ats.map((a) => `${a.name} (${a.type[0].toUpperCase()}${a.type.slice(1)})`).join(', ')}</p>
        </div>
      </div>

      <h2>Ausschlüsse</h2>
      <p className="section-lede">Diese Anzeigen werden vor der Prüfung aussortiert, weil sie eine Approbation, einen Facharzttitel, einen Studierendenstatus oder keine medizinischen Kenntnisse voraussetzen.</p>
      <div className="group-title">Im Titel</div>
      <div className="chips">{cfg.exclude_title.map((w) => <span key={w} className="chip">{w}</span>)}</div>
      <div className="group-title">Im Anzeigentext</div>
      <div className="chips">{cfg.exclude_text.map((w) => <span key={w} className="chip">{w}</span>)}</div>

      <p className="privacy">
        Der Lebenslauf liegt nur als verschlüsseltes Secret beim Suchlauf und wird nirgends gespeichert oder angezeigt.
        Diese Seite und das öffentliche Repository enthalten keine persönlichen Daten.
      </p>
    </main>
  );
}
