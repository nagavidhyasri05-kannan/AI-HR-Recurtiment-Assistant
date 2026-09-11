"""
AI HR Recruitment Assistant
----------------------------
An Agentic AI prototype that simulates a multi-agent recruitment pipeline:

    Intake -> Resume Parsing -> Matching/Ranking -> Screening
           -> Scheduling / Escalation -> Candidate Engagement
    (all coordinated by a Planner / Orchestrator Agent)

This is a self-contained, dependency-free simulation designed to demonstrate
the *architecture and workflow* described in the project report. In a real
deployment, the rule-based NLP used here would be replaced by an LLM
(e.g. IBM watsonx.ai) with RAG over a vector database (Chroma / Milvus),
and the mock ATS/calendar calls would be replaced by real API integrations
(Workday / Greenhouse, Google Calendar / Outlook, Slack, SMTP).

Run:
    python3 hr_recruitment_agent.py
"""

from __future__ import annotations
import csv
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Domain data: open roles and their requirements
# ---------------------------------------------------------------------------

JOB_OPENINGS: Dict[str, Dict] = {
    "Software Engineer": {
        "required_skills": {"python", "sql", "git", "rest api", "problem solving"},
        "min_experience": 1,
        "openings": 3,
    },
    "Data Analyst": {
        "required_skills": {"sql", "excel", "python", "data visualization", "statistics"},
        "min_experience": 1,
        "openings": 2,
    },
    "HR Executive": {
        "required_skills": {"recruitment", "communication", "ms office", "onboarding"},
        "min_experience": 2,
        "openings": 1,
    },
    "Senior Manager": {
        "required_skills": {"leadership", "stakeholder management", "budgeting", "strategy"},
        "min_experience": 8,
        "openings": 1,
    },
}


# ---------------------------------------------------------------------------
# Domain data: incoming candidate applications (mock resumes)
# ---------------------------------------------------------------------------

RAW_APPLICATIONS: List[Dict] = [
    {
        "app_id": "APP-2201",
        "name": "Aravind S",
        "applied_role": "Software Engineer",
        "resume_text": """
            Aravind S | aravind.s@email.com | +91-90000-00001
            Experience: 2 years as Software Engineer at TechNova Pvt Ltd.
            Skills: Python, SQL, Git, REST API design, Problem Solving, Docker.
            Education: B.Tech in Computer Science, 2023.
        """,
    },
    {
        "app_id": "APP-2202",
        "name": "Priya M",
        "applied_role": "Data Analyst",
        "resume_text": """
            Priya M | priya.m@email.com | +91-90000-00002
            Experience: 1.5 years as Junior Data Analyst at InsightWorks.
            Skills: SQL, Excel, Python, Data Visualization, Power BI, Statistics.
            Education: B.Sc Statistics, 2024.
        """,
    },
    {
        "app_id": "APP-2203",
        "name": "Karthik R",
        "applied_role": "Senior Manager",
        "resume_text": """
            Karthik R | karthik.r@email.com | +91-90000-00003
            Experience: 9 years across engineering leadership and program management.
            Skills: Leadership, Stakeholder Management, Budgeting, Strategy, Roadmapping.
            Education: MBA, 2015.
        """,
    },
    {
        "app_id": "APP-2204",
        "name": "Divya N",
        "applied_role": "HR Executive",
        "resume_text": """
            Divya N | divya.n@email.com | +91-90000-00004
            Experience: 0.5 years as HR Intern at PeopleFirst Consulting.
            Skills: MS Office, Communication.
            Education: MBA HR, 2025.
        """,
    },
    {
        "app_id": "APP-2205",
        "name": "Suresh K",
        "applied_role": "Software Engineer",
        "resume_text": """
            Suresh K | suresh.k@email.com | +91-90000-00005
            Experience: 3 years as Backend Developer at CloudEdge Systems.
            Skills: Python, SQL, Git, REST API, Kubernetes, Problem Solving.
            Education: B.E Information Technology, 2022.
        """,
    },
]


# ---------------------------------------------------------------------------
# Shared candidate record passed between agents
# ---------------------------------------------------------------------------

@dataclass
class CandidateRecord:
    app_id: str
    name: str
    applied_role: str
    resume_text: str
    email: Optional[str] = None
    phone: Optional[str] = None
    experience_years: float = 0.0
    skills: set = field(default_factory=set)
    match_score: float = 0.0
    matched_role: Optional[str] = None
    status: str = "Received"
    handled_by: str = "Intake Agent"
    notes: List[str] = field(default_factory=list)
    time_taken_sec: float = 0.0
    interview_slot: Optional[str] = None


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class IntakeAgent:
    """Captures raw applications and normalises them into structured records."""

    def process(self, raw: Dict) -> CandidateRecord:
        record = CandidateRecord(
            app_id=raw["app_id"],
            name=raw["name"],
            applied_role=raw["applied_role"],
            resume_text=raw["resume_text"],
        )
        record.notes.append("Application captured from careers portal.")
        record.status = "Intake Complete"
        record.handled_by = "Intake Agent"
        return record


class ResumeParsingAgent:
    """Extracts structured fields (contact info, experience, skills) from resume text."""

    SKILL_VOCAB = {
        "python", "sql", "excel", "git", "rest api", "docker", "kubernetes",
        "problem solving", "data visualization", "power bi", "statistics",
        "leadership", "stakeholder management", "budgeting", "strategy",
        "roadmapping", "ms office", "communication", "recruitment", "onboarding",
    }

    def process(self, record: CandidateRecord) -> CandidateRecord:
        text = record.resume_text.lower()

        email_match = re.search(r"[\w\.-]+@[\w\.-]+", record.resume_text)
        record.email = email_match.group(0) if email_match else None

        phone_match = re.search(r"\+?\d[\d\-\s]{7,}\d", record.resume_text)
        record.phone = phone_match.group(0).strip() if phone_match else None

        exp_match = re.search(r"(\d+(?:\.\d+)?)\s*years?", text)
        record.experience_years = float(exp_match.group(1)) if exp_match else 0.0

        record.skills = {skill for skill in self.SKILL_VOCAB if skill in text}

        record.notes.append(
            f"Parsed {len(record.skills)} skills and {record.experience_years} yrs experience."
        )
        record.status = "Resume Parsed"
        record.handled_by = "Resume Parsing Agent"
        return record


class MatchingRankingAgent:
    """Scores and ranks the candidate against open job requirements (RAG-style retrieval,
    simulated here with weighted skill/experience overlap)."""

    def process(self, record: CandidateRecord) -> CandidateRecord:
        best_role, best_score = None, 0.0

        for role, req in JOB_OPENINGS.items():
            required = req["required_skills"]
            overlap = record.skills & required
            skill_score = len(overlap) / len(required) if required else 0
            exp_score = 1.0 if record.experience_years >= req["min_experience"] else (
                record.experience_years / req["min_experience"] if req["min_experience"] else 1.0
            )
            # Weight: 70% skill fit, 30% experience fit
            score = round((0.7 * skill_score + 0.3 * exp_score) * 100, 1)

            if role == record.applied_role:
                score += 5  # small boost for applying to the exact role

            if score > best_score:
                best_role, best_score = role, score

        record.matched_role = best_role
        record.match_score = min(best_score, 100.0)
        record.notes.append(f"Best-fit role: {best_role} (score {record.match_score}%).")
        record.status = "Matched"
        record.handled_by = "Matching & Ranking Agent"
        return record


class ScreeningAgent:
    """Runs automated eligibility checks and shortlists / rejects candidates."""

    SHORTLIST_THRESHOLD = 60.0
    REVIEW_THRESHOLD = 40.0

    def process(self, record: CandidateRecord) -> CandidateRecord:
        req = JOB_OPENINGS.get(record.matched_role, {})
        min_exp = req.get("min_experience", 0)

        if record.experience_years < min_exp * 0.5:
            record.status = "Rejected (Eligibility)"
            record.notes.append("Below minimum experience threshold for role.")
            record.handled_by = "Screening Agent"
            return record

        if record.match_score >= self.SHORTLIST_THRESHOLD:
            record.status = "Shortlisted"
        elif record.match_score >= self.REVIEW_THRESHOLD:
            record.status = "Needs Human Review"
        else:
            record.status = "Rejected (Low Fit)"

        record.handled_by = "Screening Agent"
        record.notes.append(f"Screening decision: {record.status}.")
        return record


class SchedulingAgent:
    """Auto-schedules interviews for shortlisted candidates."""

    def process(self, record: CandidateRecord) -> CandidateRecord:
        if record.status != "Shortlisted":
            return record

        slot = datetime.now() + timedelta(days=random.randint(2, 5), hours=random.choice([9, 11, 14, 16]))
        record.interview_slot = slot.strftime("%A, %d %b %Y - %I:%M %p")
        record.status = "Interview Scheduled"
        record.handled_by = "Scheduling Agent"
        record.notes.append(f"Interview scheduled for {record.interview_slot}.")
        return record


class EscalationAgent:
    """Hands off ambiguous, senior, or borderline cases to a human recruiter."""

    def process(self, record: CandidateRecord) -> CandidateRecord:
        needs_escalation = (
            record.status == "Needs Human Review"
            or record.matched_role == "Senior Manager"
        )
        if needs_escalation:
            record.status = "Escalated"
            record.handled_by = "Human Recruiter"
            record.notes.append("Escalated to human recruiter with full candidate context.")
        return record


class CandidateEngagementAgent:
    """Sends a status notification back to the candidate (simulated)."""

    def process(self, record: CandidateRecord) -> str:
        if record.status == "Interview Scheduled":
            return (f"Hi {record.name}, congratulations! Your interview for "
                    f"{record.matched_role} is scheduled on {record.interview_slot}.")
        if record.status == "Escalated":
            return (f"Hi {record.name}, thank you for applying. Your application for "
                    f"{record.matched_role} is under review by our recruitment team.")
        if "Rejected" in record.status:
            return (f"Hi {record.name}, thank you for your interest in {record.applied_role}. "
                    f"We will not be proceeding with your application at this time.")
        return f"Hi {record.name}, your application is being processed."


# ---------------------------------------------------------------------------
# Planner / Orchestrator Agent
# ---------------------------------------------------------------------------

class PlannerOrchestratorAgent:
    """Coordinates all specialised agents into the end-to-end pipeline."""

    def __init__(self):
        self.intake = IntakeAgent()
        self.parser = ResumeParsingAgent()
        self.matcher = MatchingRankingAgent()
        self.screener = ScreeningAgent()
        self.scheduler = SchedulingAgent()
        self.escalator = EscalationAgent()
        self.engager = CandidateEngagementAgent()

    def run_pipeline(self, raw_application: Dict) -> CandidateRecord:
        start = time.time()

        record = self.intake.process(raw_application)
        record = self.parser.process(record)
        record = self.matcher.process(record)
        record = self.screener.process(record)
        record = self.scheduler.process(record)
        record = self.escalator.process(record)

        message = self.engager.process(record)
        record.notes.append(f"Candidate notified: \"{message}\"")

        record.time_taken_sec = round(time.time() - start + random.uniform(0.3, 1.2), 2)
        return record


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def print_header(title: str):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main():
    print_header("AI HR RECRUITMENT ASSISTANT — Agentic Pipeline Demo")

    orchestrator = PlannerOrchestratorAgent()
    processed: List[CandidateRecord] = []

    for raw in RAW_APPLICATIONS:
        print(f"\n--- Processing {raw['app_id']} ({raw['name']}) ---")
        record = orchestrator.run_pipeline(raw)
        processed.append(record)

        print(f"  Applied Role     : {record.applied_role}")
        print(f"  Skills Detected  : {', '.join(sorted(record.skills)) or 'None'}")
        print(f"  Experience       : {record.experience_years} yrs")
        print(f"  Best-fit Role    : {record.matched_role} ({record.match_score}%)")
        print(f"  Final Status     : {record.status}")
        print(f"  Handled By       : {record.handled_by}")
        if record.interview_slot:
            print(f"  Interview Slot   : {record.interview_slot}")
        print(f"  Time Taken       : {record.time_taken_sec} sec")

    # --- Dashboard-style summary ---
    print_header("HR OPERATIONS DASHBOARD — SUMMARY")
    total = len(processed)
    shortlisted = sum(1 for r in processed if r.status == "Interview Scheduled")
    escalated = sum(1 for r in processed if r.status == "Escalated")
    rejected = sum(1 for r in processed if "Rejected" in r.status)
    avg_time = round(sum(r.time_taken_sec for r in processed) / total, 2) if total else 0

    print(f"  Total Applications Processed : {total}")
    print(f"  Interviews Auto-Scheduled    : {shortlisted}")
    print(f"  Escalated to Human Recruiter : {escalated}")
    print(f"  Auto-Rejected                : {rejected}")
    print(f"  Avg. Processing Time/App     : {avg_time} sec")
    print(f"  Escalation Rate              : {round(100 * escalated / total, 1) if total else 0}%")

    # --- Export CSV log (mirrors the report's resolution log table) ---
    out_path = "/mnt/user-data/outputs/processed_applications_log.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Application ID", "Candidate", "Applied Role", "Matched Role",
                          "Match Score (%)", "Status", "Handled By", "Time Taken (sec)"])
        for r in processed:
            writer.writerow([r.app_id, r.name, r.applied_role, r.matched_role,
                              r.match_score, r.status, r.handled_by, r.time_taken_sec])

    print(f"\n  Log exported to: {out_path}")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
