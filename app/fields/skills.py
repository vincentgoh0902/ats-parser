"""Skills: what's listed in the Skills section, plus taxonomy hits anywhere.

Commercial parsers (Textkernel, RChilli) match the whole resume against a large
skills taxonomy. This is a small version of that idea, enough to show which
keywords a search would find.
"""

import re

from app.fields.entries import BULLET_RE

TAXONOMY = [
    # languages
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "Golang", "Rust",
    "Kotlin", "Swift", "Ruby", "PHP", "Scala", "R", "MATLAB", "SQL", "Bash", "Shell",
    "HTML", "CSS", "Dart", "Elixir", "Haskell", "Lua", "Perl", "Solidity", "Julia",
    # web / backend
    "React", "Next.js", "Vue", "Angular", "Svelte", "Node.js", "Express", "Django", "Flask",
    "FastAPI", "Spring", "Spring Boot", ".NET", "ASP.NET", "Rails", "Laravel", "GraphQL",
    "REST", "gRPC", "Tailwind", "Redux", "jQuery", "Bootstrap", "WebSockets",
    # data / ML
    "PyTorch", "TensorFlow", "Keras", "scikit-learn", "Pandas", "NumPy", "SciPy", "Matplotlib",
    "Spark", "PySpark", "Hadoop", "Airflow", "dbt", "Kafka", "Tableau", "Power BI", "Excel",
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "LLM", "ONNX",
    "Hugging Face", "OpenCV", "XGBoost", "LangChain", "Jupyter", "Snowflake", "BigQuery",
    "Databricks", "Statistics", "Data Analysis", "Data Visualization", "A/B Testing",
    # databases
    "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "DynamoDB", "Elasticsearch",
    "Cassandra", "Firebase", "Supabase", "Neo4j", "Oracle",
    # cloud / devops
    "AWS", "GCP", "Google Cloud", "Azure", "Docker", "Kubernetes", "Terraform", "Ansible",
    "Jenkins", "GitHub Actions", "CI/CD", "Linux", "Nginx", "Git", "Prometheus", "Grafana",
    "Serverless", "Lambda", "EC2", "S3", "Cloudflare", "Vercel", "Tailscale",
    # mobile
    "Android", "iOS", "React Native", "Flutter", "SwiftUI",
    # practice
    "Agile", "Scrum", "Jira", "Figma", "Unit Testing", "Pytest", "Jest", "Selenium",
    "Microservices", "System Design", "Data Structures", "Algorithms", "OOP",
]
# Single letters and common words only count inside the Skills section.
SECTION_ONLY = {"C", "R", "Go", "REST", "Spring", "Express", "Shell", "Excel", "Oracle", "Lambda",
                "Statistics", "Swift", "Rails", "Agile"}


def _pattern(skill: str):
    return re.compile(rf"(?<![\w+#.]){re.escape(skill)}(?![\w+#])", re.I)


PATTERNS = {s: _pattern(s) for s in TAXONOMY}


def from_section(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        line = BULLET_RE.sub("", line)
        if ":" in line[:40]:
            line = line.split(":", 1)[1]
        for item in re.split(r"[,;|•·]|\s{2,}|\s+and\s+", line):
            item = item.strip(" .()")
            if item and len(item) <= 40 and item.lower() not in (i.lower() for i in items):
                items.append(item)
    return items


def detect(full_text: str, section_text: str) -> list[str]:
    found = []
    for skill, pattern in PATTERNS.items():
        haystack = section_text if skill in SECTION_ONLY else full_text
        if pattern.search(haystack):
            found.append(skill)
    return found
