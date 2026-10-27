"""Skills taxonomy: canonical name, aliases, category.

Format per entry: "Canonical|alias|alias". A leading "=" makes the whole entry
case-sensitive, for names that are also everyday words ("Go", "R", "Excel",
"Spring"). An alias starting with "~" only counts on a line that also talks
about AI ("evaluations" next to "LLMs", not "performance evaluations"). Matching also accepts space/hyphen variants and simple plurals, so
"scikit learn" and "APIs" need no alias of their own.
"""

import re

_RAW = {
    "language": """
        Python|py
        Java
        JavaScript|JS|ECMAScript|ES6
        TypeScript|TS
        =C
        C++|cpp
        C#|csharp|C Sharp
        =Go|Golang
        Rust
        Kotlin
        =Swift
        Ruby
        PHP
        Scala
        =R
        MATLAB
        SQL
        Bash|shell scripting
        HTML|HTML5
        CSS|CSS3
        Dart
        Elixir
        Haskell
        Perl
        Julia
        Solidity
        SAS
        VBA
        Objective-C
        Lua
    """,
    "web": """
        React|React.js|ReactJS
        Next.js|NextJS
        Vue|Vue.js|VueJS
        Angular|AngularJS
        Svelte|SvelteKit
        Node.js|NodeJS
        =Express|Express.js
        Django
        Flask
        FastAPI
        =Spring|Spring Framework
        Spring Boot
        .NET|dotnet|ASP.NET
        Ruby on Rails|Rails
        Laravel
        GraphQL
        REST|RESTful|REST API
        gRPC
        Tailwind|Tailwind CSS|TailwindCSS
        Redux
        jQuery
        Streamlit
        Gradio
        WebSockets|WebSocket
        OAuth|OAuth2
        Microservices|microservice architecture
        API design|API development
    """,
    "ml": """
        Machine Learning|ML
        Deep Learning|DL
        Natural Language Processing|NLP
        Computer Vision|CV
        Large Language Models|LLM|LLMs
        Generative AI|GenAI|Gen AI
        Retrieval-Augmented Generation|RAG|~retrieval
        Prompt Engineering|prompt design|prompting|prompt tuning
        AI Agents|AI agent|LLM agents|agentic|agentic workflows|autonomous agents|multi-agent
        Tool Calling|function calling|tool use
        LLM Evaluation|LLM evals|evals|eval harness|~evaluation|~evaluations
        Guardrails|AI guardrails|LLM guardrails
        Hallucination Mitigation|hallucination|hallucinations
        AI Copilots|copilot|copilots|AI assistant|AI assistants
        Fine-tuning|fine tuning|finetuning|LoRA|PEFT
        Semantic Search|vector search
        Model Context Protocol|=MCP
        OpenAI API|OpenAI
        Anthropic API|Claude API|Anthropic
        LangGraph
        CrewAI
        AutoGen
        Pinecone
        pgvector
        FAISS
        Chroma|ChromaDB
        Weaviate
        Qdrant
        Document Processing|document handling|document understanding|intelligent document processing|IDP
        OCR|optical character recognition
        Reinforcement Learning|RL
        PyTorch|Torch
        PyTorch Geometric|PyG
        TensorFlow|TF
        Keras
        JAX
        scikit-learn|sklearn|scikit
        XGBoost
        LightGBM
        CatBoost
        Hugging Face|HuggingFace|Transformers
        LangChain
        LlamaIndex
        DSPy
        OpenCV
        ONNX
        MLflow
        Kubeflow
        SHAP
        Graph Neural Networks|GNN|GNNs
        Time Series|time-series forecasting|forecasting
        Recommender Systems|recommendation systems
        Feature Engineering
        Model Deployment|model serving
        MLOps
        A/B Testing|A/B test|AB testing|experimentation
        Statistics|statistical analysis|statistical modelling|statistical modeling
        Regression|linear regression|logistic regression
        Classification
        Clustering
        Anomaly Detection|outlier detection
        Fraud Detection|fraud prevention|anti-fraud
        Embeddings|vector embeddings
        Vector Database|vector DB|vector store
    """,
    "automation": """
        Workflow Automation|automation workflows|automated workflows|process automation|business process automation|automate workflows
        Support Automation|customer support automation
        Operations Automation|ops automation
        Robotic Process Automation|RPA
        n8n
        Zapier
        UiPath
    """,
    "domain": """
        Fintech|financial technology
        Banking|digital banking|neobank
        Payments|payment systems|payment processing
        Insurance|insurtech
        KYC|know your customer|eKYC
        AML|anti-money laundering|anti money laundering
        =CRM|customer relationship management
        Salesforce
        Risk Management|risk review|risk assessment|risk modelling|risk modeling|credit risk
        Regulatory Compliance|compliance requirements|regulatory requirements
        Onboarding|customer onboarding|user onboarding
    """,
    "data": """
        Pandas
        NumPy
        SciPy
        Matplotlib
        Seaborn
        Plotly
        Polars
        Jupyter|Jupyter Notebook
        Apache Spark|Spark
        PySpark
        Hadoop
        Hive
        Apache Kafka|Kafka
        Apache Airflow|Airflow
        dbt
        Databricks
        Snowflake
        BigQuery
        Redshift
        ETL|ELT|data pipelines|data pipeline
        Data Warehousing|data warehouse
        Data Modeling|data modelling
        Data Analysis|data analytics
        Data Visualization|data visualisation|dashboards|dashboarding
        Data Engineering
        Data Science
        Tableau
        Power BI|PowerBI
        Looker
        =Excel|Microsoft Excel|MS Excel
        Google Sheets
        Power Query
        DAX
        Neo4j|Cypher
        Big Data
    """,
    "database": """
        PostgreSQL|Postgres|psql
        MySQL
        SQLite
        SQL Server|MSSQL|T-SQL
        =Oracle|Oracle DB
        MongoDB|Mongo
        Redis
        DynamoDB
        Cassandra
        Elasticsearch|Elastic|OpenSearch
        Firebase|Firestore
        Supabase
        NoSQL
    """,
    "cloud": """
        AWS|Amazon Web Services
        GCP|Google Cloud|Google Cloud Platform
        Azure|Microsoft Azure
        Docker|containers|containerization
        Kubernetes|K8s
        Terraform
        Ansible
        Jenkins
        GitHub Actions
        GitLab CI
        CI/CD|CI CD|continuous integration|continuous deployment
        Linux|Unix
        Nginx
        Git
        GitHub
        Prometheus
        Grafana
        Serverless
        =Lambda|AWS Lambda
        EC2
        S3
        SageMaker
        Vertex AI
        Cloudflare
        Vercel
        Infrastructure as Code|IaC
        Observability|monitoring
    """,
    "mobile": """
        Android
        iOS
        React Native
        Flutter
        SwiftUI
    """,
    "practice": """
        Agile
        Scrum
        Kanban
        Jira
        Confluence
        Figma
        Unit Testing|unit tests
        Test-Driven Development|TDD
        Pytest
        Jest
        Selenium
        Playwright
        System Design
        Distributed Systems
        Data Structures
        Algorithms
        Object-Oriented Programming|OOP|object oriented
        Code Review|code reviews
        Cybersecurity|cyber security|information security|InfoSec|application security|AppSec|network security|cloud security|security engineering|secure coding
        Product Analytics
        SQL Optimization|query optimization
    """,
    "soft": """
        Communication|communication skills|communicate
        Collaboration|collaborate|collaborative
        Leadership|lead a team
        Problem Solving|problem-solving|solve problems
        Stakeholder Management|stakeholders
        Teamwork|team player
        Mentoring|mentor|mentorship
        Presentation|presenting|presentations
        Critical Thinking
        Attention to Detail|detail-oriented
        Ownership
        Cross-functional|cross functional teams
    """,
}


AI_CONTEXT = re.compile(r"\b(?:LLMs?|AI|GenAI|GPT|agents?|agentic|RAG|prompts?|chatbots?|copilots?|"
                        r"models?|machine learning|ML|NLP|guardrails)\b")


class Skill:
    __slots__ = ("name", "aliases", "category", "pattern", "context_pattern")

    def __init__(self, name, aliases, category, case_sensitive):
        self.name, self.category = name, category
        plain = [a for a in [name, *aliases] if not a.startswith("~")]
        context = [a[1:] for a in aliases if a.startswith("~")]
        self.aliases = [a for a in plain if a != name] + context
        flags = 0 if case_sensitive else re.I
        self.pattern = _compile(plain, case_sensitive, flags)
        self.context_pattern = _compile(context, case_sensitive, flags) if context else None

    def finditer(self, text):
        """Matches of the plain aliases, plus "~" aliases on lines that talk about AI."""
        hits = list(self.pattern.finditer(text))
        if self.context_pattern:
            for m in self.context_pattern.finditer(text):
                start = text.rfind("\n", 0, m.start()) + 1
                end = text.find("\n", m.end())
                line = text[start:] if end < 0 else text[start:end]
                if AI_CONTEXT.search(line) and not any(h.start() <= m.start() < h.end() for h in hits):
                    hits.append(m)
            hits.sort(key=lambda m: m.start())
        return iter(hits)

    def search(self, text):
        return next(self.finditer(text), None)


def _compile(aliases, case_sensitive, flags):
    # "=MCP" inside an otherwise case-insensitive entry is matched case-sensitively.
    parts = []
    for a in sorted(aliases, key=lambda a: len(a.lstrip("=")), reverse=True):
        if a.startswith("="):
            parts.append("(?-i:" + _alias_regex(a[1:], True) + ")")
        else:
            parts.append(_alias_regex(a, case_sensitive))
    return re.compile("|".join(parts), flags)


def _alias_regex(alias: str, case_sensitive: bool) -> str:
    body = re.escape(alias)
    body = body.replace(r"\ ", r"[\s\-]?").replace(r"\-", r"[\s\-]?")
    # Plurals: "API" matches "APIs", "dashboard" matches "dashboards".
    if alias[-1].isalpha() and len(alias) > 2 and not case_sensitive:
        body += "(?:e?s)?"
    # "C" must not match inside "C++", "C#", "CI/CD", "C-level"; "R" not in "R&D";
    # "JS" not inside "Node.js".
    tail = r"(?![\w+#&]|-(?:level|suite)\b)"
    if alias in SEASONS:
        tail += r"(?!\s*'?\d{2,4}\b)"  # "Spring 2024" is a date, not the framework
    return rf"(?<![\w.+#]){body}{tail}"


SEASONS = {"Spring"}


def _parse() -> list[Skill]:
    skills = []
    for category, block in _RAW.items():
        for line in block.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            case_sensitive = line.startswith("=")
            name, *aliases = line.lstrip("=").split("|")
            skills.append(Skill(name, aliases, category, case_sensitive))
    return skills


SKILLS: list[Skill] = _parse()

# Having the specific skill is partial evidence for the general one. A literal
# ATS search for "SQL" still won't find "PostgreSQL", so this only earns
# partial credit and a suggestion to write the general term out.
IMPLIES = {
    "SQL": ["PostgreSQL", "MySQL", "SQLite", "SQL Server", "BigQuery", "Snowflake", "Redshift"],
    "Machine Learning": ["scikit-learn", "XGBoost", "LightGBM", "PyTorch", "TensorFlow", "Deep Learning"],
    "Deep Learning": ["PyTorch", "TensorFlow", "Keras", "JAX"],
    "Data Visualization": ["Tableau", "Power BI", "Looker", "Matplotlib", "Plotly"],
    "Apache Spark": ["PySpark", "Databricks"],
    "CI/CD": ["GitHub Actions", "GitLab CI", "Jenkins"],
    "Large Language Models": ["Retrieval-Augmented Generation", "LangChain", "LlamaIndex", "DSPy"],
    "Statistics": ["Regression", "A/B Testing"],
}
