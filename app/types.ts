export type Requirement = { text: string; mandatory: boolean; status: 'met' | 'unmet' | 'unclear' };
export type Match = {
  status: 'match' | 'check' | 'reject';
  score: number;
  kind: 'phd' | 'job' | 'other';
  topic?: string;
  topics: string[];
  summary: string;
  part_time?: 'yes' | 'no' | 'unclear';
  requirements: Requirement[];
  notes?: string[];
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
