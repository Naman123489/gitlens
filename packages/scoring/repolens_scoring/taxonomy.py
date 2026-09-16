"""Skill taxonomy.

Maps a canonical skill to the things that can *evidence* it in a repository:
dependency names, import statements, file extensions, filename patterns and
free-text aliases. Because every skill declares its own evidence sources, a job
match can always be explained in terms of what was actually found.

The taxonomy is data, not code: adding a skill means adding an entry here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repolens_shared import SkillDimension


@dataclass(frozen=True, slots=True)
class Skill:
    key: str
    label: str
    dimension: SkillDimension
    aliases: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    path_patterns: tuple[str, ...] = ()
    #: Skills implied by this one, used when a job asks for a broad term.
    implies: tuple[str, ...] = ()

    def all_terms(self) -> tuple[str, ...]:
        return (self.key, self.label.lower(), *self.aliases)


def _s(*args, **kwargs) -> Skill:
    return Skill(*args, **kwargs)


D = SkillDimension

SKILLS: tuple[Skill, ...] = (
    # -- languages -----------------------------------------------------------
    _s("python", "Python", D.BACKEND, aliases=("py",), languages=("python",)),
    _s("javascript", "JavaScript", D.FRONTEND, aliases=("js", "ecmascript"), languages=("javascript",)),
    _s("typescript", "TypeScript", D.FRONTEND, aliases=("ts",), languages=("typescript", "tsx")),
    _s("java", "Java", D.BACKEND, languages=("java",)),
    _s("cpp", "C++", D.SYSTEMS, aliases=("c++", "cplusplus"), languages=("cpp",)),
    _s("c", "C", D.SYSTEMS, languages=("c",)),
    _s("go", "Go", D.BACKEND, aliases=("golang",), languages=("go",)),
    _s("rust", "Rust", D.SYSTEMS, languages=("rust",)),
    _s("sql", "SQL", D.BACKEND, languages=("sql",), path_patterns=(r"\.sql$",),
       dependencies=("sqlalchemy", "alembic", "psycopg", "psycopg2", "psycopg2-binary", "asyncpg",
                     "mysqlclient", "pymysql", "prisma", "typeorm", "sequelize", "knex", "drizzle-orm",
                     "pg", "mysql2", "sqlite3", "better-sqlite3")),
    _s("bash", "Shell scripting", D.DEVOPS, aliases=("shell", "bash scripting"), languages=("bash",)),
    # -- AI / ML -------------------------------------------------------------
    _s("pytorch", "PyTorch", D.AI_ML, aliases=("torch",), dependencies=("torch", "pytorch-lightning"),
       imports=("torch",), implies=("machine_learning", "python")),
    _s("tensorflow", "TensorFlow", D.AI_ML, aliases=("tf", "keras"),
       dependencies=("tensorflow", "keras"), imports=("tensorflow", "keras"),
       implies=("machine_learning", "python")),
    _s("machine_learning", "Machine Learning", D.AI_ML, aliases=("ml", "deep learning", "neural network"),
       dependencies=("scikit-learn", "sklearn", "xgboost", "lightgbm", "catboost"),
       imports=("sklearn", "xgboost", "lightgbm")),
    _s("nlp", "Natural Language Processing", D.AI_ML, aliases=("natural language processing",),
       dependencies=("spacy", "nltk", "transformers", "tokenizers"), imports=("spacy", "nltk")),
    _s("llm", "LLM integration", D.AI_ML, aliases=("large language model", "gpt", "generative ai", "genai"),
       dependencies=("openai", "anthropic", "transformers", "litellm", "ollama", "vllm"),
       imports=("openai", "anthropic", "transformers")),
    _s("rag", "Retrieval-Augmented Generation", D.AI_ML, aliases=("retrieval augmented generation",
                                                                  "retrieval-augmented", "vector search"),
       dependencies=("langchain", "llama-index", "llama_index", "haystack-ai"),
       imports=("langchain", "llama_index"), implies=("llm", "vector_database")),
    _s("vector_database", "Vector database", D.AI_ML, aliases=("pgvector", "embeddings store", "vector store"),
       dependencies=("chromadb", "pinecone-client", "qdrant-client", "weaviate-client", "faiss-cpu",
                     "faiss", "pgvector", "milvus")),
    _s("data_science", "Data science", D.AI_ML, aliases=("data analysis", "analytics", "pandas"),
       dependencies=("pandas", "numpy", "scipy", "polars", "matplotlib", "seaborn"),
       imports=("pandas", "numpy")),
    _s("computer_vision", "Computer vision", D.AI_ML, aliases=("cv", "opencv", "image processing"),
       dependencies=("opencv-python", "pillow", "torchvision", "albumentations"),
       imports=("cv2", "torchvision")),
    # -- backend / web -------------------------------------------------------
    _s("fastapi", "FastAPI", D.BACKEND, dependencies=("fastapi", "uvicorn"), imports=("fastapi",),
       implies=("python", "rest_api")),
    _s("flask", "Flask", D.BACKEND, dependencies=("flask",), imports=("flask",), implies=("python", "rest_api")),
    _s("django", "Django", D.BACKEND, dependencies=("django", "djangorestframework"), imports=("django",),
       implies=("python", "rest_api")),
    _s("express", "Express", D.BACKEND, dependencies=("express",), implies=("javascript", "rest_api")),
    _s("nestjs", "NestJS", D.BACKEND, dependencies=("@nestjs/core", "@nestjs/common"),
       implies=("typescript", "rest_api")),
    _s("spring", "Spring Boot", D.BACKEND, aliases=("spring boot", "springboot"),
       dependencies=("spring-boot-starter", "spring-boot-starter-web"), implies=("java", "rest_api")),
    _s("rest_api", "REST API development", D.BACKEND, aliases=("api development", "rest", "restful", "api design"),
       path_patterns=(r"(^|/)(api|routes|routers|controllers|endpoints)(/|$)",)),
    _s("graphql", "GraphQL", D.BACKEND, dependencies=("graphql", "strawberry-graphql", "apollo-server",
                                                      "@apollo/client", "graphene")),
    _s("websockets", "WebSockets", D.BACKEND, aliases=("realtime", "socket.io"),
       dependencies=("websockets", "socket.io", "python-socketio")),
    _s("microservices", "Microservices", D.BACKEND, aliases=("service oriented", "distributed systems")),
    # -- frontend ------------------------------------------------------------
    _s("react", "React", D.FRONTEND, dependencies=("react", "react-dom"), implies=("javascript",)),
    _s("nextjs", "Next.js", D.FRONTEND, aliases=("next.js", "next js"), dependencies=("next",),
       implies=("react",)),
    _s("vue", "Vue", D.FRONTEND, aliases=("vuejs", "vue.js"), dependencies=("vue", "nuxt")),
    _s("angular", "Angular", D.FRONTEND, dependencies=("@angular/core",)),
    _s("tailwind", "Tailwind CSS", D.FRONTEND, dependencies=("tailwindcss",)),
    _s("ui_engineering", "UI engineering", D.FRONTEND, aliases=("frontend", "front-end", "user interface"),
       path_patterns=(r"(^|/)(components|pages|views|screens)(/|$)",)),
    _s("mobile", "Mobile development", D.FRONTEND, aliases=("react native", "android", "ios", "flutter"),
       dependencies=("react-native", "expo", "flutter")),
    # -- data ----------------------------------------------------------------
    _s("postgresql", "PostgreSQL", D.BACKEND, aliases=("postgres", "psql"),
       dependencies=("psycopg", "psycopg2", "psycopg2-binary", "asyncpg", "pg"), implies=("sql",)),
    _s("mysql", "MySQL", D.BACKEND, dependencies=("mysqlclient", "pymysql", "mysql2"), implies=("sql",)),
    _s("mongodb", "MongoDB", D.BACKEND, aliases=("mongo", "nosql"), dependencies=("pymongo", "mongoose", "motor")),
    _s("redis", "Redis", D.BACKEND, aliases=("caching",), dependencies=("redis", "ioredis", "aioredis")),
    _s("orm", "ORM / data modelling", D.BACKEND, aliases=("sqlalchemy", "prisma", "typeorm", "hibernate"),
       dependencies=("sqlalchemy", "prisma", "typeorm", "sequelize", "alembic", "drizzle-orm")),
    _s("data_engineering", "Data engineering", D.AI_ML, aliases=("etl", "data pipeline", "airflow", "spark"),
       dependencies=("apache-airflow", "pyspark", "dbt-core", "prefect", "dagster")),
    # -- devops / infra ------------------------------------------------------
    _s("docker", "Docker", D.DEVOPS, aliases=("containers", "containerization"),
       path_patterns=(r"(^|/)Dockerfile", r"docker-compose\.ya?ml$")),
    _s("kubernetes", "Kubernetes", D.DEVOPS, aliases=("k8s",), path_patterns=(r"(^|/)k8s(/|$)", r"helm")),
    _s("ci_cd", "CI/CD", D.DEVOPS, aliases=("continuous integration", "continuous deployment", "github actions"),
       path_patterns=(r"^\.github/workflows/", r"\.gitlab-ci\.yml$", r"Jenkinsfile$")),
    _s("cloud", "Cloud platforms", D.DEVOPS, aliases=("aws", "gcp", "azure", "cloud infrastructure"),
       dependencies=("boto3", "google-cloud-storage", "azure-identity", "aws-sdk")),
    _s("terraform", "Infrastructure as code", D.DEVOPS, aliases=("terraform", "iac", "pulumi", "ansible"),
       path_patterns=(r"\.tf$",)),
    _s("observability", "Observability", D.DEVOPS, aliases=("monitoring", "logging", "tracing", "prometheus"),
       dependencies=("prometheus-client", "opentelemetry-api", "structlog", "sentry-sdk", "winston")),
    _s("message_queue", "Message queues", D.DEVOPS, aliases=("kafka", "rabbitmq", "celery", "pub/sub"),
       dependencies=("celery", "kafka-python", "pika", "aio-pika", "rq", "bullmq")),
    # -- quality / security --------------------------------------------------
    _s("testing", "Testing", D.TESTING, aliases=("unit testing", "test automation", "tdd", "pytest", "jest"),
       dependencies=("pytest", "jest", "vitest", "mocha", "junit", "playwright", "cypress"),
       path_patterns=(r"(^|/)tests?(/|$)", r"(^|/)__tests__(/|$)")),
    _s("security", "Security engineering", D.SECURITY,
       aliases=("application security", "appsec", "authentication", "authorization", "oauth", "jwt"),
       dependencies=("cryptography", "pyjwt", "passlib", "bcrypt", "authlib", "jsonwebtoken", "helmet")),
    _s("performance", "Performance engineering", D.SYSTEMS,
       aliases=("optimization", "scalability", "profiling", "load testing"),
       dependencies=("locust", "k6", "py-spy")),
    _s("open_source", "Open-source contribution", D.OPEN_SOURCE,
       aliases=("oss", "open source"), path_patterns=(r"(^|/)CONTRIBUTING", r"(^|/)CODE_OF_CONDUCT")),
    _s("research", "Research / experimentation", D.RESEARCH,
       aliases=("paper", "experiment", "benchmark", "reproduction"),
       path_patterns=(r"(^|/)(notebooks?|experiments?|research)(/|$)", r"\.ipynb$")),
    _s("git", "Git / version control", D.DEVOPS, aliases=("version control", "source control")),
)

SKILLS_BY_KEY: dict[str, Skill] = {s.key: s for s in SKILLS}

#: alias -> canonical key, longest alias first so "machine learning" wins over "ml".
_ALIAS_INDEX: list[tuple[str, str]] = sorted(
    ((term, skill.key) for skill in SKILLS for term in skill.all_terms()),
    key=lambda item: -len(item[0]),
)


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s\-_]+")
    boundary_start = r"(?<![\w+#])" if term[0].isalnum() else ""
    # Allow a trailing plural so "vector databases" matches "vector database".
    plural = r"(?:e?s)?" if term[-1].isalpha() else ""
    boundary_end = r"(?![\w+#])" if term[-1].isalnum() else ""
    return re.compile(f"{boundary_start}{escaped}{plural}{boundary_end}", re.IGNORECASE)


_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_term_pattern(term), key) for term, key in _ALIAS_INDEX
]


def extract_skills(text: str) -> dict[str, list[str]]:
    """Find canonical skills mentioned in free text.

    Returns ``{skill_key: [matched surface forms]}``. Overlapping matches are
    resolved by consuming matched spans longest-first, so "machine learning
    engineer" does not also register a stray "learning".
    """
    found: dict[str, list[str]] = {}
    consumed: list[tuple[int, int]] = []
    for pattern, key in _PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in consumed):
                continue
            consumed.append(span)
            found.setdefault(key, [])
            surface = match.group(0)
            if surface not in found[key]:
                found[key].append(surface)
    return found


def expand_implications(keys: set[str]) -> set[str]:
    """Add skills implied by the given ones (PyTorch implies Python + ML)."""
    expanded = set(keys)
    queue = list(keys)
    while queue:
        skill = SKILLS_BY_KEY.get(queue.pop())
        if not skill:
            continue
        for implied in skill.implies:
            if implied not in expanded:
                expanded.add(implied)
                queue.append(implied)
    return expanded
