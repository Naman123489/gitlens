"""Insecure-code pattern detection.

Language-aware regular expressions for injection, unsafe deserialisation, weak
crypto and authentication mistakes. Each rule carries a confidence reflecting
how often the pattern is a true positive in real code, plus a remediation note.

This is lint-grade static analysis, not taint tracking: it flags *patterns*
worth a human look, and says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from repolens_shared import Severity


@dataclass(frozen=True, slots=True)
class PatternRule:
    id: str
    title: str
    category: str
    pattern: re.Pattern[str]
    severity: Severity
    confidence: float
    languages: tuple[str, ...]
    remediation: str
    cwe: str | None = None


ANY = ("*",)

PATTERN_RULES: tuple[PatternRule, ...] = (
    # --- SQL injection ------------------------------------------------------
    PatternRule(
        "sql_string_concat", "SQL query built by string concatenation", "sql_injection",
        re.compile(r"(?i)(execute|executemany|cursor\.execute|query|raw|db\.run)\s*\(\s*"
                   r"[fr]?['\"](?:[^'\"]*\b(?:select|insert|update|delete|drop)\b[^'\"]*)"
                   r"['\"]\s*(?:\+|%|\.format\()"),
        Severity.HIGH, 0.8, ("python", "javascript", "typescript", "java"),
        "Use parameterised queries or an ORM binding instead of building SQL from strings.",
        "CWE-89",
    ),
    PatternRule(
        "sql_fstring", "SQL query built with an f-string or template literal", "sql_injection",
        re.compile(r"(?i)(?:execute|query|raw)\s*\(\s*(?:f['\"]|`)[^'\"`]*\b"
                   r"(?:select|insert|update|delete)\b[^'\"`]*(?:\{|\$\{)"),
        Severity.HIGH, 0.85, ("python", "javascript", "typescript"),
        "Pass values as query parameters; never interpolate them into the SQL text.",
        "CWE-89",
    ),
    # --- Command injection --------------------------------------------------
    PatternRule(
        "shell_true", "Subprocess invoked with shell=True", "command_injection",
        re.compile(r"subprocess\.(?:run|call|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True"),
        Severity.HIGH, 0.75, ("python",),
        "Pass an argument list and leave shell=False so the shell cannot re-interpret input.",
        "CWE-78",
    ),
    PatternRule(
        "os_system", "os.system / exec with a dynamic command", "command_injection",
        re.compile(r"(?:os\.system|os\.popen)\s*\(\s*(?:f['\"]|[^'\")]*[+%]|.*\.format\()"),
        Severity.HIGH, 0.8, ("python",),
        "Use subprocess with an argument list, or validate against an allow-list.",
        "CWE-78",
    ),
    PatternRule(
        "node_exec", "child_process.exec with interpolated input", "command_injection",
        re.compile(r"(?:child_process\.)?exec(?:Sync)?\s*\(\s*(?:`[^`]*\$\{|['\"][^'\"]*['\"]\s*\+)"),
        Severity.HIGH, 0.8, ("javascript", "typescript"),
        "Use execFile/spawn with an argument array instead of a shell string.",
        "CWE-78",
    ),
    # --- Unsafe evaluation / deserialisation --------------------------------
    PatternRule(
        "python_eval", "eval/exec on non-literal input", "code_injection",
        re.compile(r"\b(?:eval|exec)\s*\(\s*(?!['\"]\s*\))[a-zA-Z_][\w.\[\]]*\s*[,)]"),
        Severity.CRITICAL, 0.7, ("python",),
        "Replace eval/exec with explicit parsing (ast.literal_eval, json.loads, a dispatch table).",
        "CWE-95",
    ),
    PatternRule(
        "pickle_load", "Unsafe deserialisation with pickle", "unsafe_deserialization",
        re.compile(r"\bpickle\.loads?\s*\(|\bcPickle\.loads?\s*\(|\byaml\.load\s*\((?![^)]*Loader\s*=)"),
        Severity.HIGH, 0.85, ("python",),
        "Use json, or yaml.safe_load; pickle executes arbitrary code during load.",
        "CWE-502",
    ),
    PatternRule(
        "js_eval", "eval / new Function on dynamic input", "code_injection",
        re.compile(r"\beval\s*\(\s*[a-zA-Z_$][\w$.]*\s*\)|new\s+Function\s*\("),
        Severity.HIGH, 0.7, ("javascript", "typescript", "tsx"),
        "Avoid eval/new Function; parse data explicitly instead.",
        "CWE-95",
    ),
    PatternRule(
        "java_deserialize", "Java object deserialisation of untrusted data", "unsafe_deserialization",
        re.compile(r"new\s+ObjectInputStream\s*\("),
        Severity.HIGH, 0.6, ("java",),
        "Avoid Java serialisation for untrusted input; use a data format such as JSON.",
        "CWE-502",
    ),
    # --- XSS ----------------------------------------------------------------
    PatternRule(
        "react_dangerous_html", "dangerouslySetInnerHTML with dynamic content", "xss",
        re.compile(r"dangerouslySetInnerHTML\s*=\s*\{\{\s*__html:\s*(?!['\"])"),
        Severity.HIGH, 0.75, ("javascript", "typescript", "tsx"),
        "Render text as children, or sanitise the HTML (for example with DOMPurify) first.",
        "CWE-79",
    ),
    PatternRule(
        "inner_html_assign", "innerHTML assigned from a variable", "xss",
        re.compile(r"\.innerHTML\s*=\s*(?!['\"`]\s*['\"`;])[a-zA-Z_$][\w$.\[\]]*"),
        Severity.MEDIUM, 0.6, ("javascript", "typescript", "tsx"),
        "Use textContent, or sanitise before assigning HTML.",
        "CWE-79",
    ),
    PatternRule(
        "jinja_autoescape_off", "Template auto-escaping disabled", "xss",
        re.compile(r"autoescape\s*=\s*False|\|\s*safe\b|mark_safe\s*\("),
        Severity.MEDIUM, 0.55, ("python",),
        "Keep auto-escaping on; escape deliberately and narrowly where raw HTML is required.",
        "CWE-79",
    ),
    # --- Transport / crypto -------------------------------------------------
    PatternRule(
        "tls_verification_disabled", "TLS certificate verification disabled", "insecure_transport",
        re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|"
                   r"CURLOPT_SSL_VERIFYPEER\s*,\s*(?:0|false)|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0"),
        Severity.HIGH, 0.9, ANY,
        "Keep certificate verification enabled; pin a CA bundle if a private CA is needed.",
        "CWE-295",
    ),
    PatternRule(
        "weak_hash", "Weak hash used for security purposes", "weak_crypto",
        re.compile(r"(?i)\b(?:hashlib\.)?(?:md5|sha1)\s*\(|createHash\s*\(\s*['\"](?:md5|sha1)['\"]"),
        Severity.MEDIUM, 0.5, ANY,
        "Use SHA-256+ for integrity and a password KDF (bcrypt/argon2/scrypt) for passwords.",
        "CWE-327",
    ),
    PatternRule(
        "plaintext_password_store", "Password stored or compared without hashing", "auth",
        re.compile(r"(?i)(?:password|passwd)\s*==\s*(?:request|req|body|data|form|params)"
                   r"|user\.password\s*==\s*"),
        Severity.HIGH, 0.6, ANY,
        "Store a password hash and compare with the KDF's constant-time verify function.",
        "CWE-256",
    ),
    # --- Authentication / access control ------------------------------------
    PatternRule(
        "jwt_verify_disabled", "JWT signature verification disabled", "auth",
        re.compile(r"verify_signature['\"]?\s*:\s*False|verify\s*:\s*false|"
                   r"jwt\.decode\([^)]*options\s*=\s*\{[^}]*verify[^}]*False"),
        Severity.CRITICAL, 0.85, ANY,
        "Always verify the signature and the issuer/audience claims before trusting a token.",
        "CWE-347",
    ),
    PatternRule(
        "debug_enabled", "Debug mode enabled in committed configuration", "misconfiguration",
        re.compile(r"(?i)\b(?:debug|DEBUG)\s*[:=]\s*(?:True|true|1)\b"),
        Severity.LOW, 0.4, ANY,
        "Drive debug from an environment variable that defaults to off.",
        "CWE-489",
    ),
    PatternRule(
        "cors_wildcard_credentials", "CORS allows any origin together with credentials", "misconfiguration",
        re.compile(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\][^)]*allow_credentials\s*=\s*True"
                   r"|origin\s*:\s*['\"]\*['\"][^}]*credentials\s*:\s*true"),
        Severity.HIGH, 0.85, ANY,
        "List explicit origins when credentials are allowed; the wildcard is rejected by browsers.",
        "CWE-942",
    ),
    PatternRule(
        "bind_all_interfaces", "Service bound to all network interfaces", "misconfiguration",
        re.compile(r"0\.0\.0\.0['\"]?\s*[,:)]|host\s*=\s*['\"]0\.0\.0\.0['\"]"),
        Severity.LOW, 0.3, ANY,
        "Binding to 0.0.0.0 is correct inside a container but should not be the default locally.",
        "CWE-1327",
    ),
    PatternRule(
        "path_traversal", "Filesystem path built from request input", "path_traversal",
        re.compile(r"(?:open|readFile|readFileSync|sendFile)\s*\(\s*(?:os\.path\.join\s*\()?"
                   r"[^)]*\b(?:request|req)\.(?:args|params|query|body|GET|POST)\b"),
        Severity.HIGH, 0.7, ANY,
        "Resolve the path and assert it stays within an allow-listed base directory.",
        "CWE-22",
    ),
)


@dataclass(frozen=True, slots=True)
class PatternFinding:
    rule_id: str
    title: str
    category: str
    file: str
    line: int
    severity: Severity
    confidence: float
    snippet: str
    remediation: str
    cwe: str | None


_COMMENT_ONLY = re.compile(r"^\s*(#|//|\*|/\*|--)")


def scan_patterns(path: str, text: str, language: str | None) -> list[PatternFinding]:
    """Apply the pattern rules relevant to ``language`` to one file."""
    findings: list[PatternFinding] = []
    lines = text.splitlines()
    in_test = bool(re.search(r"(?i)(^|/)(tests?|spec|__tests__)(/|$)|test_|_test\.", path))

    for index, line in enumerate(lines, start=1):
        if len(line) > 4000 or _COMMENT_ONLY.match(line):
            continue
        for rule in PATTERN_RULES:
            if rule.languages != ANY and language not in rule.languages:
                continue
            if not rule.pattern.search(line):
                continue
            confidence = rule.confidence * (0.6 if in_test else 1.0)
            findings.append(PatternFinding(
                rule_id=rule.id, title=rule.title, category=rule.category, file=path,
                line=index, severity=rule.severity, confidence=round(confidence, 3),
                snippet=line.strip()[:200], remediation=rule.remediation, cwe=rule.cwe,
            ))
    return findings
