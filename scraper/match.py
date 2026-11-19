"""Filtering and strict requirement matching against the candidate profile.

The profile comes from the PROFILE_JSON secret. It is sent to the Claude API
and never written to logs or to the repository.
"""
from __future__ import annotations

import json
import os
import re

from datetime import date

from common import Job, log

TODAY = date.today().isoformat()

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["phd", "job", "other"],
                 "description": "phd = doctoral position or PhD programme; job = paid position; other = not a position (course, event, list page)"},
        "requirements": {
            "type": "array",
            "description": "Every requirement the posting states, one per item.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The requirement, short, in German"},
                    "mandatory": {"type": "boolean", "description": "true if required (vorausgesetzt, erforderlich, required, must); false if only desirable (wünschenswert, von Vorteil, nice to have, ideally)"},
                    "status": {"type": "string", "enum": ["met", "unmet", "unclear"]},
                },
                "required": ["text", "mandatory", "status"],
                "additionalProperties": False,
            },
        },
        "needs_medical_license": {"type": "boolean", "description": "true if a German Approbation, Berufserlaubnis or specialist title is required"},
        "part_time_possible": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "languages": {
            "type": "array",
            "description": "Every language the posting asks for, with the level it states.",
            "items": {
                "type": "object",
                "properties": {
                    "lang": {"type": "string", "enum": ["de", "en", "es", "fr", "other"]},
                    "level": {"type": "string", "enum": ["A1", "A2", "B1", "B2", "C1", "C2", "native", "unspecified"],
                              "description": "CEFR level. Map words: Grundkenntnisse=A2, gute=B2, sehr gute/fließend/verhandlungssicher/fluent=C1, Muttersprache/native=native; unspecified if no level is given"},
                    "mandatory": {"type": "boolean"},
                },
                "required": ["lang", "level", "mandatory"],
                "additionalProperties": False,
            },
        },
        "role_type": {"type": "string",
                      "enum": ["phd", "study_assistant", "research_assistant", "physician", "medical_writing_info",
                               "monitoring_management", "lab_technical", "lab_assistant", "care_assistant",
                               "patient_service", "admin_documentation", "health_startup", "other"],
                      "description": "phd = doctoral position or PhD programme; study_assistant = Studienassistenz, Clinical Trial Assistant, study coordinator, clinical research coordinator; research_assistant = research assistant, wissenschaftliche Hilfskraft, junior wissenschaftliche Mitarbeiterin in a research project; physician = treats patients as a doctor; medical_writing_info = medical writing, information, affairs, pharmacovigilance; monitoring_management = CRA/monitor, project or study manager, lead roles; lab_technical = skilled bench lab work for trained technicians or scientists; lab_assistant = simple lab help (Laborhilfe, Laborassistenz, Probenannahme, sample logistics); care_assistant = care help without completed nursing training (Pflegehilfe, Pflegeassistenz for career changers, Betreuung); patient_service = patient reception, admission, patient guidance, call centre for patients; admin_documentation = medical documentation, coding, medical office or study administration; health_startup = non-clinical role at a health or medtech company that uses medical knowledge (medical content, support, operations, data annotation); other = anything else"},
        "needs_vocational_qualification": {"type": "boolean",
                                           "description": "true if a completed vocational training or state exam other than medicine is mandatory (e.g. Pflegefachkraft, MFA, MTA/MTL, Laborant, PTA, Rettungssanitäter)"},
        "paid": {"type": "string", "enum": ["yes", "no", "unclear"],
                 "description": "no = internship, volunteer work, or a student job that requires university enrolment"},
        "transition_score": {"type": "integer",
                             "description": "0-100: as a paid job until her medical licence, how much medical knowledge it uses and how realistic it is for the candidate to get it"},
        "min_years_experience": {"type": "number",
                                 "description": "Minimum years of professional experience the posting explicitly REQUIRES. 0 if no number of years is required, or if it only asks for first experience or calls experience desirable."},
        "advanced_lab_skills_required": {"type": "boolean",
                                         "description": "true if mandatory: cell culture, PCR, molecular biology or other wet-lab methods, animal experiments, or similar advanced lab work"},
        "closed": {"type": "boolean",
                   "description": "true if the posting says it is no longer accepting applications, is filled or expired, or its application deadline is before {today}"},
        "deadline": {"type": "string", "description": "Application deadline as YYYY-MM-DD, empty if none is stated"},
        "work_location": {"type": "string", "description": "City and country where the work takes place, e.g. 'Berlin, Deutschland'; empty if not stated"},
        "fully_remote": {"type": "boolean", "description": "true if the role can be done fully remotely from Germany"},
        "field_fit": {"type": "string", "enum": ["core", "related", "distant"],
                      "description": "core = women's health (gynaecology, obstetrics, maternal health, menopause), epidemiology, public health or preventive medicine; related = other clinical or health research that builds on the candidate's research or clinical experience (e.g. clinical trials in general, nutrition, neurology, ophthalmology, imaging); distant = a field far from the candidate's experience (e.g. basic molecular biology, engineering, veterinary)"},
        "topic": {"type": "string", "description": "Main medical field, in German, 1-3 words"},
        "fit_score": {"type": "integer", "description": "0-100: how well field and tasks match the candidate's interests and goals, ignoring requirements"},
        "summary": {"type": "string", "description": "One German sentence: what the role is and why it fits or not. Do not repeat personal details of the candidate."},
    },
    "required": ["kind", "role_type", "requirements", "languages", "needs_medical_license", "min_years_experience",
                 "advanced_lab_skills_required", "needs_vocational_qualification", "paid", "transition_score", "closed", "deadline", "work_location", "fully_remote", "field_fit",
                 "part_time_possible", "topic", "fit_score", "summary"],
    "additionalProperties": False,
}

SYSTEM = """You screen job postings for one candidate. You get the candidate profile below and one posting.

Extract every requirement the posting states and judge each one strictly against the profile:
- met: the profile clearly shows it (same skill, degree, language level or more).
- unmet: the profile clearly does not have it (e.g. a licence, a specialist title, years of experience, a programming language, a certificate, a language level above the profile's).
- unclear: the posting is vague ("gute Deutschkenntnisse", "erste Erfahrung") or the profile does not say.
Never assume skills that are not in the profile. A requirement for a degree in medicine is met by the profile's M.D.
Mark a requirement mandatory unless the posting calls it desirable, an advantage, or optional.
German: a requirement of German up to B2 ("gute Deutschkenntnisse", "Deutsch B2") counts as met, because the candidate
will hold B2 soon. C1 or higher ("sehr gute", "fließend", "verhandlungssicher", C1, C2, Muttersprache) is unmet.
Today is {today}.
Write requirement texts and the summary in German.

<candidate_profile>
{profile}
</candidate_profile>"""


def all_queries(cfg: dict) -> list[str]:
    """Search terms of every stream, for the job boards."""
    extra = [q for st in (cfg.get("streams") or {}).values() for q in st.get("queries", [])]
    return list(dict.fromkeys(cfg.get("queries", []) + extra))


def all_jobspy_queries(cfg: dict) -> list[str]:
    extra = [q for st in (cfg.get("streams") or {}).values() for q in st.get("jobspy_queries", [])]
    return list(dict.fromkeys(cfg["jobspy"].get("queries", []) + extra))


class Matcher:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.mcfg = cfg["matching"]
        self.excl_title = [w.lower() for w in cfg.get("exclude_title", [])]
        self.excl_text = [w.lower() for w in cfg.get("exclude_text", [])]
        self.topics = cfg["topics"]
        self.queries = [q.lower() for q in all_queries(cfg)]
        self.loc_aliases = [a.lower() for loc in cfg["locations"] for a in loc["aliases"]]
        self.remote_words = [w.lower() for w in cfg.get("remote_words", [])]
        profile = os.environ.get("PROFILE_JSON", "")
        self.profile = json.dumps(json.loads(profile), ensure_ascii=False, indent=1) if profile else ""
        self.client = None
        self.exhausted = False
        self.provider = os.environ.get("LLM_PROVIDER") or self.mcfg.get("provider", "gemini")
        if not self.profile:
            return
        self.claude = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic
            self.claude = anthropic.Anthropic()
        if self.provider == "gemini" and os.environ.get("GEMINI_API_KEY"):
            from google import genai
            from google.genai import types
            self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                                       http_options=types.HttpOptions(timeout=90_000))
        elif self.claude:
            self.provider = "claude"
            self.client = self.claude

    def system(self) -> str:
        return SYSTEM.replace("{profile}", self.profile).replace("{today}", TODAY)

    def schema(self) -> dict:
        return json.loads(json.dumps(SCHEMA).replace("{today}", TODAY))

    # --- cheap rules -------------------------------------------------------
    def title_ok(self, job: Job) -> bool:
        t = job.title.lower()
        return bool(t) and not any(w in t for w in self.excl_title)

    def title_reason(self, job: Job) -> str:
        t = job.title.lower()
        if not t:
            return "kein Titel"
        w = next((w for w in self.excl_title if w in t), "")
        return f"Titel enthält „{w}“"

    def text_reason(self, job: Job) -> str:
        d = job.description.lower()
        w = next((w for w in self.excl_text if w in d), "")
        return f"Anzeige verlangt „{w}“"

    def has_place(self, text: str) -> bool:
        """True if one of the configured places appears as a whole word ("langen" must not match "Erlangen")."""
        t = re.sub(r"frankfurt\s*(an der oder|\(oder\)|/oder|oder)", " ", text.lower())  # not Frankfurt am Main
        return any(re.search(rf"(?<![a-zäöüß]){re.escape(a)}(?![a-zäöüß])", t) for a in self.loc_aliases)

    def location_ok(self, job: Job) -> bool:
        loc = f"{job.location} {job.title}".lower()
        if job.remote or any(w in loc for w in self.remote_words):
            # Remote only counts when it is not tied to another country ("USA-Remote", "Remote Australia").
            where = job.location.lower()
            return not where or bool(re.search(HOME_COUNTRIES, where)) or self.has_place(where) \
                or not re.search(r"[a-z]{3,}", re.sub(r"remote|homeoffice|home office|mobiles arbeiten|[-,/()]", " ", where))
        if not job.location:
            return True  # unknown: let the requirement check decide, flagged later
        return self.has_place(loc)

    def text_ok(self, job: Job) -> bool:
        d = job.description.lower()
        return not any(w in d for w in self.excl_text)

    def topic_hits(self, job: Job) -> dict[str, int]:
        text = f"{job.title} {job.title} {job.description}".lower()
        hits = {}
        for key, t in self.topics.items():
            n = sum(1 for w in t["words"] if w in text)
            if n:
                hits[key] = n
        return hits

    def prefilter_score(self, job: Job) -> int:
        hits = self.topic_hits(job)
        score = sum(self.topics[k]["weight"] for k in hits)
        if any(q in job.title.lower() for q in self.queries):
            score += 5
        return score

    def is_wanted(self, job: Job) -> bool:
        """Used before reading a posting's details (title only)."""
        return self.title_ok(job)

    # --- strict check with Claude -----------------------------------------
    def check(self, job: Job) -> dict | None:
        if not self.client:
            return None
        posting = (f"Titel: {job.title}\nArbeitgeber: {job.org}\nOrt: {job.location}\n"
                   f"Remote: {'ja' if job.remote else 'unbekannt'}\n\n{job.description[:14000]}")
        if self.provider == "gemini":
            result = self._check_gemini(posting)
            if result is None and self.exhausted and self.claude:
                # Free Gemini quota used up: continue with the cheap Claude fallback model.
                log("  switching to Claude fallback for the rest of this run")
                self.provider, self.client, self.exhausted = "claude", self.claude, False
                self.mcfg = {**self.mcfg, "model": self.mcfg.get("fallback_model", self.mcfg["model"])}
                return self._check_claude(posting)
            return result
        return self._check_claude(posting)

    def _check_gemini(self, posting: str) -> dict | None:
        import time
        from google.genai import types

        gcfg = self.mcfg.get("gemini", {})
        if not hasattr(self, "gemini_models"):
            self.gemini_models = self._gemini_candidates(gcfg.get("model", ""))
        while self.gemini_models:
            model = self.gemini_models[0]
            last = ""
            for attempt in range(3):
                try:
                    resp = self.client.models.generate_content(
                        model=model,
                        contents=f"<posting>\n{posting}\n</posting>",
                        config=types.GenerateContentConfig(
                            system_instruction=self.system(),
                            response_mime_type="application/json",
                            response_json_schema=self.schema(),
                            temperature=0,
                        ),
                    )
                    time.sleep(gcfg.get("pause_seconds", 4))  # stay under the free-tier per-minute limit
                    self.fails = 0
                    self.used_models = getattr(self, "used_models", [])
                    if model not in self.used_models:
                        self.used_models.append(model)
                    try:
                        return json.loads(resp.text)
                    except (ValueError, TypeError):
                        return None
                except Exception as e:  # noqa: BLE001
                    msg = str(e)
                    last = f"{type(e).__name__}: {msg[:160]}"
                    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                        if "per day" in msg.lower() or "PerDay" in msg or attempt >= 1:
                            log(f"  Gemini quota reached for {model}, trying next model")
                            break
                        time.sleep(20)
                        continue
                    if "503" in msg or "UNAVAILABLE" in msg or "500" in msg or "timed out" in msg.lower():
                        time.sleep(8 * (attempt + 1))
                        continue
                    log(f"  Gemini check failed ({last})")
                    return None
            else:
                # Two postings in a row failing on one model: stop waiting on it, use the next one.
                self.fails = getattr(self, "fails", 0) + 1
                log(f"  Gemini {model} keeps failing ({last}), skipping posting")
                if self.fails < 2:
                    return None
                self.fails = 0
                log(f"  giving up on {model}")
            self.gemini_models.pop(0)
            if self.gemini_models:
                log(f"  Gemini model: {self.gemini_models[0]}")
        self.exhausted = True
        return None

    def _gemini_candidates(self, wanted: str) -> list[str]:
        """Configured model first (if available), then Flash models newest first, each has its own free quota."""
        import re as _re
        try:
            names = [m.name.removeprefix("models/") for m in self.client.models.list()
                     if "generateContent" in (getattr(m, "supported_actions", None) or ["generateContent"])]
        except Exception as e:  # noqa: BLE001
            log(f"  Gemini model list failed ({type(e).__name__}: {str(e)[:120]})")
            return [wanted] if wanted else []

        def rank(n: str):
            v = _re.search(r"gemini-(\d+(?:\.\d+)?)", n)
            stable = "preview" not in n and "exp" not in n
            return (stable, float(v.group(1)) if v else 0, "lite" not in n)

        flash = [n for n in names if "flash" in n and not any(
            x in n for x in ("image", "tts", "audio", "live", "embedding", "thinking"))]
        ordered = sorted(set(flash), key=rank, reverse=True)
        if wanted and wanted in names:
            ordered = [wanted] + [n for n in ordered if n != wanted]
        ordered = ordered[:8]
        log(f"  Gemini models in order: {ordered}")
        return ordered

    def _check_claude(self, posting: str) -> dict | None:
        try:
            extra = {} if "haiku" in self.mcfg["model"] else {
                "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
            resp = self.client.beta.messages.create(
                model=self.mcfg["model"],
                max_tokens=4000,
                **extra,
                cache_control={"type": "ephemeral"},
                system=self.system(),
                messages=[{"role": "user", "content": f"<posting>\n{posting}\n</posting>"}],
                output_config={"effort": self.mcfg.get("effort", "low"),
                               "format": {"type": "json_schema", "schema": self.schema()}},
            )
        except Exception as e:  # noqa: BLE001
            log(f"  Claude check failed ({type(e).__name__}: {str(e)[:200]})")
            return None
        if resp.stop_reason in ("refusal", "max_tokens"):
            return None
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            return json.loads(text)
        except ValueError:
            return None


_LANG_WORDS = {"de": r"deutsch|german", "en": r"englisch|english", "es": r"spanisch|spanish|español|espanol",
               "fr": r"französisch|franzoesisch|french"}
_LEVEL_WORDS = [(r"\b(c2)\b", "C2"), (r"\b(c1)\b", "C1"), (r"\b(b2)\b", "B2"), (r"\b(b1)\b", "B1"),
                (r"\b(a2)\b", "A2"), (r"\b(a1)\b", "A1"),
                (r"mutterspra|native", "native"),
                (r"verhandlungssicher|fließend|fliessend|sehr gut|exzellent|excellent|fluent|business", "C1"),
                (r"\bgut|good|solide", "B2"), (r"grundkenntnis|basic", "A2")]


def languages_from_text(text: str) -> list[dict]:
    """Rough level per language from the posting text, used when no LLM result has it."""
    clauses = re.split(r"[.;\n•,]|(?<!- )\bund\b|\band\b|\bsowie\b|\bor\b|\boder\b", (text or "").lower())
    out = []
    for lang, pat in _LANG_WORDS.items():
        found = None
        for c in clauses:
            if not re.search(rf"({pat})(\w*)\s*(kenntnisse|sprachkenntnisse|skills|language|sprache|\b)", c) \
                    or not re.search(r"kenntnis|sprach|skill|language|spricht|speak|fluent|fließend|niveau|level|"
                                     r"\b[abc][12]\b|mutterspra|native|verhandlungssicher|in wort", c):
                continue
            level = next((lvl for lp, lvl in _LEVEL_WORDS if re.search(lp, c)), "unspecified")
            optional = bool(re.search(r"plus|wünschenswert|von vorteil|vorteilhaft|advantage|desirable|ideally|nice", c))
            found = {"lang": lang, "level": level, "mandatory": not optional}
            if level != "unspecified":
                break
        if found:
            out.append(found)
    return out


HOME_COUNTRIES = r"\b(germany|deutschland|deu|de|austria|österreich|aut|switzerland|schweiz|che|dach|europe|europa|emea|eu)\b"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]
ROLE_LABELS = {"phd": "Promotion / PhD", "study_assistant": "Studienassistenz / Studienkoordination",
               "research_assistant": "Research Assistant / wiss. Hilfskraft", "physician": "ärztliche Tätigkeit",
               "medical_writing_info": "Medical Writing / Information", "monitoring_management": "Monitoring / Management",
               "lab_technical": "Labor / Technik", "lab_assistant": "Laborassistenz / Laborhilfe",
               "care_assistant": "Pflegehilfe / Betreuung", "patient_service": "Patientenservice / Aufnahme",
               "admin_documentation": "Medizinische Dokumentation / Verwaltung",
               "health_startup": "Health-Startup / MedTech", "other": "andere Rolle"}


def decide(job: Job, result: dict | None, matcher: Matcher) -> dict:
    """Turn the Claude result into board status: match / check / reject."""
    hits = matcher.topic_hits(job)
    topics = [matcher.topics[k]["label"] for k in sorted(hits, key=lambda k: -matcher.topics[k]["weight"])
              if k not in ("medical", "bridge")]  # broad catch-all topics only feed the prefilter
    if result is None:
        return {"status": "check", "score": min(60, matcher.prefilter_score(job)), "topics": topics,
                "summary": "Nicht automatisch geprüft (keine Beschreibung oder Prüfung fehlgeschlagen).",
                "requirements": [], "kind": "job", "languages": languages_from_text(job.description)}
    reqs = result.get("requirements") or []
    mandatory = [r for r in reqs if r.get("mandatory")]
    unmet = [r for r in mandatory if r.get("status") == "unmet"]
    unclear = [r for r in mandatory if r.get("status") == "unclear"]
    score = int(result.get("fit_score") or 0)
    kind = result.get("kind", "job")
    role = result.get("role_type", "other")
    rules = matcher.mcfg.get("rules", {})
    languages = result.get("languages") or languages_from_text(job.description)
    german = max((LEVELS.index(lg["level"]) for lg in languages
                  if lg.get("lang") == "de" and lg.get("mandatory") and lg.get("level") in LEVELS), default=-1)
    max_german = LEVELS.index(rules.get("max_german", "B2"))
    years = float(result.get("min_years_experience") or 0)
    deadline = (result.get("deadline") or "")[:10]
    place = result.get("work_location") or job.location
    remote = bool(result.get("fully_remote"))  # from the text; board "remote" flags are unreliable
    reasons = []
    common = []  # rules out a posting for every stream
    if kind == "other":
        common.append("keine Stellenanzeige (z. B. Kurs, Veranstaltung, Übersicht)")
    if result.get("closed") or (re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline) and deadline < TODAY):
        common.append("Bewerbung nicht mehr möglich" + (f" (Frist {deadline})" if deadline else ""))
    if result.get("needs_medical_license"):
        common.append("Approbation oder Facharzttitel nötig")
    if german > max_german:
        common.append(f"Deutsch {LEVELS[german]} verlangt (höchstens {LEVELS[max_german]})")
    if result.get("advanced_lab_skills_required"):
        common.append("Laborarbeit wie Zellkultur oder Molekularbiologie verlangt")
    if place and not remote and not matcher.has_place(place):
        common.append(f"Ort passt nicht: {place[:60]}")
    common += [f"Nicht erfüllt: {r.get('text', '')}" for r in unmet if r.get("text")]

    def stream_rules(srules: dict, research: bool) -> list[str]:
        out = []
        if years > srules.get("max_years_experience", 0):
            out.append(f"{years:g} Jahre Berufserfahrung verlangt")
        if role not in (srules.get("allowed_roles") or list(ROLE_LABELS)):
            out.append(f"Rolle passt nicht: {ROLE_LABELS.get(role, role)}")
        if research and result.get("field_fit") == "distant":
            out.append("Fachgebiet zu weit von ihrer Erfahrung entfernt")
        if not research and result.get("needs_vocational_qualification"):
            out.append("abgeschlossene Ausbildung verlangt (z. B. Pflegefachkraft, MFA, MTA)")
        if not research and result.get("paid") == "no":
            out.append("unbezahlt, Praktikum oder nur für Studierende")
        return out

    research_hard = stream_rules(rules, True)
    bridge_rules = matcher.cfg.get("streams", {}).get("bridge", {}).get("rules")
    bridge_hard = stream_rules(bridge_rules, False) if bridge_rules else ["Stream aus"]
    stream = "research"
    if research_hard and not bridge_hard:
        stream = "bridge"
        score = int(result.get("transition_score") or score)
    hard = common + (research_hard if stream == "research" else [])
    if research_hard and bridge_hard:
        hard = common + research_hard + [f"Übergangsjob: {x}" for x in bridge_hard if x not in research_hard]
    reject_reason = "; ".join(hard)
    if hard:
        status = "reject"
    elif unclear:
        status = "check"
        reasons.append("Pflichtanforderung unklar")
    else:
        status = "match"
    if kind == "job" and result.get("part_time_possible") == "no" and status == "match":
        status = "check"
        reasons.append("keine Teilzeit")
    if result.get("part_time_possible") == "yes":
        score = min(100, score + 5)
    if result.get("field_fit") == "core":
        score = min(100, score + 10)
    if not place and not remote and status == "match":
        status = "check"
        reasons.append("Ort unbekannt")
    return {
        "status": status,
        "score": score,
        "kind": kind,
        "topic": result.get("topic", ""),
        "topics": topics,
        "summary": result.get("summary", ""),
        "part_time": result.get("part_time_possible", "unclear"),
        "requirements": reqs,
        "languages": languages,
        "role": role,
        "stream": stream,
        "fully_remote": remote,
        "field_fit": result.get("field_fit", ""),
        "years": years,
        "deadline": deadline,
        "notes": reasons,
        **({"reject_reason": reject_reason} if reject_reason else {}),
    }


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
