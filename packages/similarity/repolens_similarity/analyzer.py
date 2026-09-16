"""The similarity analyzer.

Runs three independent mechanisms and reconciles them:

1. **Exact / near-exact** — winnowing fingerprints over normalised source.
2. **Structural** — shared AST shapes.
3. **Lexical-semantic** — embedding cosine over code chunks.

Two guard rails matter here:

* Dependency, generated and configuration files are excluded, so vendored or
  framework code is never reported as the candidate's plagiarism.
* Cross-repository matches are reported as *similarity*, with the caveat that
  shared open-source ancestry is the most common explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repolens_analysis.ast_engine import CodeEntity, FileAST
from repolens_shared import (
    AnalyzerResult,
    Evidence,
    EvidenceDetail,
    OriginalityClassification,
    ScoreCategory,
    Severity,
)
from repolens_shared.textutils import dense_cosine

from .embeddings import EmbeddingProvider, HashingEmbedder
from .fingerprint import containment, fingerprint_set, jaccard
from .structural import identical_shape_groups
from .tutorial import assess_tutorial_signals

ANALYZER_NAME = "similarity"
ANALYZER_VERSION = "1.0.0"

#: Below this, a match is noise for normal code.
INTERNAL_MATCH_THRESHOLD = 0.55
EXTERNAL_MATCH_THRESHOLD = 0.45
MIN_CHUNK_TOKENS = 40


@dataclass(slots=True)
class CorpusChunk:
    """A code chunk from another repository, used as external reference."""

    chunk_id: str
    repository_id: str
    repository_name: str
    file: str
    symbol: str
    fingerprints: set[int] = field(default_factory=set)
    embedding: list[float] = field(default_factory=list)
    structure_signature: str = ""


@dataclass(slots=True)
class SimilarityInput:
    asts: list[FileAST]
    texts: dict[str, str]
    categories: dict[str, str]
    repository_id: str = ""
    corpus: list[CorpusChunk] = field(default_factory=list)
    embedder: EmbeddingProvider | None = None


@dataclass(slots=True)
class ChunkRecord:
    """A chunk produced for this repository; persisted for future comparisons."""

    chunk_id: str
    file: str
    symbol: str
    start_line: int
    end_line: int
    language: str
    structure_signature: str
    fingerprints: list[int]
    embedding: list[float]


def _eligible_entities(data: SimilarityInput) -> list[CodeEntity]:
    """Candidate-authored functions only.

    Generated, dependency and configuration code is excluded so that vendored
    libraries can never be attributed to the candidate.
    """
    allowed = {
        path for path, category in data.categories.items()
        if category in ("CANDIDATE_CODE", "TEST_CODE")
    }
    entities: list[CodeEntity] = []
    for file_ast in data.asts:
        if data.categories and file_ast.path not in allowed:
            continue
        for entity in file_ast.entities:
            if entity.kind == "class" or entity.line_count < 5:
                continue
            entities.append(entity)
    return entities


def build_chunks(
    data: SimilarityInput, embedder: EmbeddingProvider
) -> tuple[list[ChunkRecord], dict[str, CodeEntity]]:
    entities = _eligible_entities(data)
    records: list[ChunkRecord] = []
    by_id: dict[str, CodeEntity] = {}
    for entity in entities:
        source = entity.source or _slice_source(data.texts.get(entity.file, ""), entity)
        if not source:
            continue
        prints = fingerprint_set(source)
        if len(prints) < 2 and len(source.split()) < MIN_CHUNK_TOKENS:
            continue
        chunk_id = f"{entity.file}:{entity.start_line}:{entity.symbol}"
        records.append(ChunkRecord(
            chunk_id=chunk_id, file=entity.file, symbol=entity.symbol,
            start_line=entity.start_line, end_line=entity.end_line, language=entity.language,
            structure_signature=entity.structure_signature, fingerprints=sorted(prints),
            embedding=embedder.embed([source])[0],
        ))
        by_id[chunk_id] = entity
    return records, by_id


def _slice_source(text: str, entity: CodeEntity) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[entity.start_line - 1 : entity.end_line])


def analyze_similarity(data: SimilarityInput) -> tuple[AnalyzerResult, list[ChunkRecord]]:
    """Run all similarity mechanisms. Returns the result and the chunk records
    to persist for future cross-repository comparisons."""
    embedder = data.embedder or HashingEmbedder()
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)
    chunks, entity_by_id = build_chunks(data, embedder)

    if not chunks:
        result.partial = True
        result.confidence = 0.2
        result.metrics = {"chunks": 0, "internal_matches": [], "external_matches": [],
                          "originality": str(OriginalityClassification.UNKNOWN)}
        result.limit("similarity",
                     "No comparable code chunks were extracted, so similarity analysis did not run.")
        result.add(Evidence(
            category=ScoreCategory.OWNERSHIP,
            claim="Similarity analysis could not run on this repository",
            severity=Severity.INFO, confidence=0.9, supports="neutral", tags=("similarity",),
            evidence=(EvidenceDetail(detail="no candidate-authored functions of sufficient size"),),
        ))
        return result, chunks

    # --- 1. internal near-duplicate detection --------------------------------
    internal: list[dict[str, Any]] = []
    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            score = jaccard(set(chunks[i].fingerprints), set(chunks[j].fingerprints))
            if score >= INTERNAL_MATCH_THRESHOLD:
                internal.append({
                    "left": chunks[i].chunk_id, "right": chunks[j].chunk_id,
                    "similarity": round(score, 3), "mechanism": "fingerprint",
                })
    internal.sort(key=lambda m: -m["similarity"])

    # --- 2. structural clone groups ------------------------------------------
    shape_groups = identical_shape_groups(list(entity_by_id.values()))

    # --- 3. external corpus comparison ---------------------------------------
    external: list[dict[str, Any]] = []
    corpus = [c for c in data.corpus if c.repository_id != data.repository_id]
    for chunk in chunks:
        best: dict[str, Any] | None = None
        for reference in corpus:
            exact = jaccard(set(chunk.fingerprints), reference.fingerprints)
            contained = containment(set(chunk.fingerprints), reference.fingerprints)
            structural = 1.0 if (chunk.structure_signature
                                 and chunk.structure_signature == reference.structure_signature) else 0.0
            semantic = dense_cosine(chunk.embedding, reference.embedding) if reference.embedding else 0.0
            combined = max(exact, contained * 0.9, structural * 0.7, semantic * 0.75)
            if combined >= EXTERNAL_MATCH_THRESHOLD and (best is None or combined > best["similarity"]):
                best = {
                    "chunk": chunk.chunk_id,
                    "file": chunk.file,
                    "symbol": chunk.symbol,
                    "matched_repository": reference.repository_name,
                    "matched_repository_id": reference.repository_id,
                    "matched_file": reference.file,
                    "matched_symbol": reference.symbol,
                    "similarity": round(combined, 3),
                    "exact": round(exact, 3),
                    "containment": round(contained, 3),
                    "structural": structural,
                    "semantic": round(semantic, 3),
                }
        if best:
            external.append(best)
    external.sort(key=lambda m: -m["similarity"])

    max_external = max((m["similarity"] for m in external), default=None)
    # Tutorial signals are looked for in candidate-authored code and the root
    # README only. Scanning a project's own documentation would flag any
    # repository that happens to *contain* a tutorial (Flask's docs, for
    # example) as tutorial-derived.
    signal_texts = {
        path: text for path, text in data.texts.items()
        if data.categories.get(path) in ("CANDIDATE_CODE", "TEST_CODE", "CONFIGURATION")
        or (path.lower().startswith("readme") and "/" not in path)
    }
    tutorial = assess_tutorial_signals(
        texts=signal_texts or data.texts,
        all_paths=list(data.texts),
        external_similarity=max_external,
        corpus_size=len({c.repository_id for c in corpus}),
    )

    duplicated_chunks = {m["left"] for m in internal} | {m["right"] for m in internal}
    internal_ratio = len(duplicated_chunks) / len(chunks)
    external_ratio = len(external) / len(chunks)

    result.confidence = 0.75 if corpus else 0.45
    result.metrics = {
        "chunks": len(chunks),
        "embedder": {"name": embedder.name, "kind": embedder.kind,
                     "dimensions": embedder.dimensions},
        "corpus_repositories": len({c.repository_id for c in corpus}),
        "corpus_chunks": len(corpus),
        "internal_matches": internal[:50],
        "internal_duplicate_ratio": round(internal_ratio, 4),
        "structural_clone_groups": [
            [f"{e.file}:{e.start_line} {e.symbol}" for e in group[:6]] for group in shape_groups[:10]
        ],
        "external_matches": external[:50],
        "external_match_ratio": round(external_ratio, 4),
        "max_external_similarity": max_external,
        "originality": str(tutorial.classification),
        "originality_score": tutorial.score,
        "originality_confidence": tutorial.confidence,
        "tutorial_signals": tutorial.matched_signals,
    }

    # --- evidence ------------------------------------------------------------
    if internal:
        result.add(Evidence(
            category=ScoreCategory.TECHNICAL_QUALITY,
            claim=f"{len(internal)} pair(s) of near-duplicate functions within this repository",
            severity=Severity.MEDIUM if internal_ratio > 0.12 else Severity.LOW,
            confidence=0.85, supports="weakness", tags=("similarity", "duplication"),
            evidence=tuple(
                EvidenceDetail(detail=f"{m['left']} ≈ {m['right']} (similarity {m['similarity']})",
                               metric=float(m["similarity"]))
                for m in internal[:5]
            ),
        ))

    if shape_groups:
        result.add(Evidence(
            category=ScoreCategory.TECHNICAL_QUALITY,
            claim=f"{len(shape_groups)} group(s) of functions share an identical control-flow shape",
            severity=Severity.LOW, confidence=0.7, supports="weakness",
            tags=("similarity", "structural"),
            evidence=tuple(
                EvidenceDetail(detail=", ".join(f"{e.symbol} ({e.file}:{e.start_line})" for e in group[:4]))
                for group in shape_groups[:4]
            ),
        ))

    if external:
        result.add(Evidence(
            category=ScoreCategory.OWNERSHIP,
            claim=f"{len(external)} chunk(s) closely match code in {len({m['matched_repository'] for m in external})} "
                  "other analysed repository/repositories",
            severity=Severity.MEDIUM, confidence=0.7, supports="weakness",
            tags=("similarity", "cross_repository", "signal_only"),
            evidence=(
                *(
                    EvidenceDetail(
                        detail=f"`{m['symbol']}` matches `{m['matched_symbol']}` in "
                               f"{m['matched_repository']} ({m['matched_file']}) at {m['similarity']}",
                        file=m["file"], metric=float(m["similarity"]),
                    )
                    for m in external[:5]
                ),
                EvidenceDetail(
                    detail="Shared open-source ancestry, a common framework idiom or a shared "
                           "starter template all produce this pattern. This is a prompt for a "
                           "conversation, not a conclusion.",
                ),
            ),
        ))
    elif corpus:
        result.add(Evidence(
            category=ScoreCategory.OWNERSHIP,
            claim="No close matches were found against other analysed repositories",
            severity=Severity.INFO, confidence=0.6, supports="strength",
            tags=("similarity", "cross_repository"),
            evidence=(EvidenceDetail(
                detail=f"compared against {len(corpus)} chunks from "
                       f"{len({c.repository_id for c in corpus})} repositories"),),
        ))

    if tutorial.matched_signals:
        result.add(Evidence(
            category=ScoreCategory.OWNERSHIP,
            claim=_tutorial_claim(tutorial.classification),
            severity=Severity.MEDIUM
            if tutorial.classification == OriginalityClassification.STRONG_TUTORIAL_SIMILARITY
            else Severity.LOW,
            confidence=tutorial.confidence, supports="weakness",
            tags=("tutorial", "originality", "signal_only"),
            evidence=tuple(
                EvidenceDetail(detail=f"{signal['label']}: {'; '.join(signal['observations'][:2])}")
                for signal in tutorial.matched_signals[:5]
            ),
        ))

    for limitation in tutorial.limitations:
        result.limit("tutorial_detection", limitation)
    result.limit(
        "similarity_scope",
        "Similarity is computed against this deployment's own corpus only. RepoLens does not search "
        "the public internet, so an absence of matches is not proof of originality.",
    )
    if embedder.kind == "lexical":
        result.limit(
            "semantic_similarity",
            f"The '{embedder.name}' embedder is lexical: it compares token distributions, not meaning. "
            "Configure a neural embedding provider for true semantic matching.",
        )
    return result, chunks


def _tutorial_claim(classification: OriginalityClassification) -> str:
    if classification == OriginalityClassification.STRONG_TUTORIAL_SIMILARITY:
        return ("Repository contains strong similarity to publicly available tutorial or scaffold "
                "patterns. A candidate explanation is recommended.")
    if classification == OriginalityClassification.POSSIBLY_TUTORIAL_DERIVED:
        return ("Some scaffold or tutorial-derived material appears to remain unmodified in this "
                "repository.")
    return "Tutorial-derivation signals were evaluated and no strong indication was found."
