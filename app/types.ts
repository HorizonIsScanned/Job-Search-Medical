export type Requirement = { text: string; mandatory: boolean; status: 'met' | 'unmet' | 'unclear' };
export type Language = {
  lang: 'de' | 'en' | 'es' | 'fr' | 'other';
  level: 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2' | 'native' | 'unspecified';
  mandatory: boolean;
};
export type Match = {
  status: 'match' | 'check' | 'reject';
  score: number;
  kind: 'phd' | 'job' | 'other';
  topic?: string;
  topics: string[];
  summary: string;
  part_time?: 'yes' | 'no' | 'unclear';
  requirements: Requirement[];
  languages?: Language[];
  notes?: string[];
  role?: string;
  stream?: 'research' | 'bridge';
  field_fit?: 'core' | 'related' | 'distant' | '';
  years?: number;
  deadline?: string;
};
export type JobEntry = {
  id: string;
  title: string;
  org: string;
  location: string;
  url: string;
  source: string;
  posted: string;
  remote: boolean;
  first_seen: string;
  match: Match;
};
export type BoardState = {
  updated?: string;
  jobs: JobEntry[];
  last_run?: { collected: number; new: number; match: number; check: number; reject: number; failed_sources: number };
};

export type Outcome =
  | 'known' | 'duplicate' | 'title' | 'location' | 'text' | 'no_topic'
  | 'over_limit' | 'deferred' | 'match' | 'check' | 'reject';
export type RunPosting = {
  title: string; org: string; location: string; url: string; source: string;
  outcome: Outcome; reason: string; score?: number;
};
export type RunSource = { group: string; name: string; url: string; count: number; status: 'ok' | 'empty' | 'failed'; note: string };
export type RunCounts = {
  collected: number; new: number; dropped: number; candidates: number; deferred: number;
  match: number; check: number; reject: number; failed_sources: number;
};
export type Run = {
  id: string; started: string; finished: string; seconds: number; trigger: string; run_url: string;
  llm: { provider: string; models: string[]; checked: number; limit: number };
  counts: RunCounts;
  sources: RunSource[];
  postings: RunPosting[];
};
export type RunSummary = Omit<Run, 'sources' | 'postings'>;
