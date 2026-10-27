"""Skills taxonomy: canonical name, aliases, category.

Format per entry: "Canonical|alias|alias". A leading "=" makes the whole entry
case-sensitive, for names that are also everyday words ("Go", "R", "Excel",
"Spring"). Matching also accepts space/hyphen variants and simple plurals, so
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
        Retrieval-Augmented Generation|RAG
        Prompt Engineering
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
        Fraud Detection
        Embeddings|vector embeddings
        Vector Database|vector DB|vector store
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
        Security|cybersecurity
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


class Skill:
    __slots__ = ("name", "aliases", "category", "pattern")

    def __init__(self, name, aliases, category, case_sensitive):
        self.name, self.aliases, self.category = name, aliases, category
        self.pattern = re.compile(
            "|".join(_alias_regex(a, case_sensitive) for a in sorted([name, *aliases], key=len, reverse=True)),
            0 if case_sensitive else re.I,
        )

    def finditer(self, text):
        return self.pattern.finditer(text)


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
