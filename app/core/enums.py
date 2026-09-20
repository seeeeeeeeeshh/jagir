"""Single source of truth for every enum-driven field in the app.

Used directly by NiceGUI dropdowns and by the Excel data-validation lists,
so there is exactly one place that defines the allowed values.
"""

STATUS_OPTIONS = [
    "Saved",
    "Interested",
    "Preparing",
    "Applied",
    "OA",
    "Recruiter Screen",
    "Interview 1",
    "Interview 2",
    "Final Round",
    "Offer",
    "Accepted",
    "Rejected",
    "Withdrawn",
    "Ghosted",
    "On Hold",
]

# Statuses that count as "not yet applied" for Saved Jobs vs Applications sheet/page splits.
PRE_APPLICATION_STATUSES = {"Saved", "Interested"}
TERMINAL_STATUSES = {"Accepted", "Rejected", "Withdrawn", "Ghosted"}

PRIORITY_OPTIONS = ["Low", "Medium", "High"]

TARGET_REACH_SAFETY_OPTIONS = ["Target", "Reach", "Safety"]

POSITION_TYPE_OPTIONS = ["Internship", "Research", "RA", "FullTime", "PartTime", "Other"]
RESEARCH_POSITION_TYPES = {"Research", "RA"}

ROLE_CATEGORY_OPTIONS = ["SWE", "AI/ML", "Data", "Quant", "Research", "Product", "Other"]

WORKPLACE_TYPE_OPTIONS = ["Remote", "Hybrid", "On-site"]

EMPLOYMENT_TYPE_OPTIONS = ["Full-time", "Part-time", "Internship", "Contract", "Other"]

SOURCE_OPTIONS = [
    "linkedin",
    "company_website",
    "university",
    "referral",
    "email",
    "wellfound",
    "indeed",
    "jobstreet",
    "manual",
    "other",
]

ORIGIN_OPTIONS = ["linkedin_import", "manual", "excel_import"]

NETWORKING_STATUS_OPTIONS = [
    "Not contacted",
    "Connection requested",
    "Connected",
    "Message sent",
    "Replied",
    "Referral offered",
    "Referral submitted",
    "No response",
    "Follow-up needed",
]

INTERVIEW_STAGE_OPTIONS = [
    "Recruiter Screen",
    "OA",
    "Technical",
    "Behavioral",
    "System Design",
    "Final Round",
    "Other",
]

PREP_CATEGORY_OPTIONS = [
    "Company research",
    "Job description",
    "Resume",
    "Behavioral",
    "STAR stories",
    "LeetCode",
    "Python",
    "SQL",
    "ML",
    "System design",
    "Technical concepts",
    "Domain knowledge",
    "Mock interview",
    "Interview experience",
]

DUPLICATE_CANDIDATE_STATUS_OPTIONS = ["pending", "confirmed_merge", "confirmed_distinct"]

URGENCY_TIERS = ["Critical", "Soon", "Normal", "No deadline"]

APPLICATION_HEALTH_OPTIONS = ["Active", "Needs action", "Stale"]
