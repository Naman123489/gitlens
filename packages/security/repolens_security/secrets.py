"""Hardcoded-secret detection.

Two-stage: a high-precision pattern match for well-known credential formats,
then a generic ``KEY = "value"`` rule gated on Shannon entropy so that
``password = "changeme"`` in an example config does not generate noise.

**Detected values are never returned.** :func:`mask` is applied at the point of
detection, so a secret cannot leak into the database, the API or a report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from repolens_shared import Severity
from repolens_shared.textutils import shannon_entropy


@dataclass(frozen=True, slots=True)
class SecretRule:
    id: str
    name: str
    pattern: re.Pattern[str]
    severity: Severity
    confidence: float
    entropy_floor: float = 0.0


#: High-precision provider patterns. These formats are unambiguous enough that a
#: match is reported at high confidence.
PROVIDER_RULES: tuple[SecretRule, ...] = (
    SecretRule("aws_access_key_id", "AWS access key id",
               re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"), Severity.CRITICAL, 0.95),
    SecretRule("github_token", "GitHub token",
               re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), Severity.CRITICAL, 0.95),
    SecretRule("github_fine_grained", "GitHub fine-grained token",
               re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"), Severity.CRITICAL, 0.95),
    SecretRule("slack_token", "Slack token",
               re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), Severity.HIGH, 0.9),
    SecretRule("stripe_key", "Stripe secret key",
               re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b"), Severity.CRITICAL, 0.93),
    SecretRule("google_api_key", "Google API key",
               re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), Severity.HIGH, 0.9),
    SecretRule("openai_key", "OpenAI API key",
               re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_\-]{32,}\b"), Severity.CRITICAL, 0.9),
    SecretRule("anthropic_key", "Anthropic API key",
               re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{24,}\b"), Severity.CRITICAL, 0.93),
    SecretRule("private_key_block", "Private key block",
               re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
               Severity.CRITICAL, 0.97),
    SecretRule("jwt_token", "JSON Web Token",
               re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
               Severity.HIGH, 0.8),
    SecretRule("connection_string", "Credentialed connection string",
               re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://"
                          r"[^\s:@/]+:[^\s:@/]{3,}@[^\s/]+"), Severity.HIGH, 0.85),
    SecretRule("twilio_key", "Twilio key",
               re.compile(r"\bSK[0-9a-fA-F]{32}\b"), Severity.HIGH, 0.8),
    SecretRule("sendgrid_key", "SendGrid key",
               re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"), Severity.HIGH, 0.9),
)

#: Generic assignment rule. Entropy-gated to suppress placeholders.
GENERIC_RULE = SecretRule(
    "generic_credential", "Credential-like assignment",
    re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret[_-]?key|secret|password|passwd|pwd|token|"
        r"access[_-]?token|auth[_-]?token|client[_-]?secret|private[_-]?key|"
        r"encryption[_-]?key|session[_-]?secret)\b\s*[:=]\s*"
        r"['\"]([^'\"\s]{8,120})['\"]"
    ),
    Severity.HIGH, 0.55, entropy_floor=3.2,
)

#: Values that look like secrets but are conventional placeholders.
PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:"
    r"x{3,}|y{3,}|\*{3,}|\.{3,}|<[^>]+>|\$\{[^}]+\}|\{\{[^}]+\}\}|%\([^)]+\)s|"
    r"your[\w.\-]*|my[-_.][\w.\-]*|some[\w.\-]*|dummy[\w.\-]*|sample[\w.\-]*|"
    r"example[\w.\-]*|[\w.\-]*(?:goes[-_]?here|here)|[\w.\-]*placeholder[\w.\-]*|"
    r"changeme|change[-_ ]me|replace[-_ ]?me|todo|tbd|none|null|nil|undefined|empty|"
    r"password|passwd|secret|token|apikey|api[-_]key|key|value|string|test|testing|"
    r"dev|development|local|localhost|admin|root|user|username|default|placeholder|"
    r"insecure|not[-_ ]?a[-_ ]?secret|fake\w*|mock\w*|"
    r"process\.env\.\w+|os\.environ.*|env\.\w+|config\.\w+|settings\.\w+"
    r")$"
)

#: Files where credential-looking strings are expected and not a finding.
EXAMPLE_PATH_RE = re.compile(
    r"(?i)(^|/)(\.env\.(example|sample|template)|.*\.example(\.\w+)?|.*\.sample(\.\w+)?|"
    r".*\.template(\.\w+)?|fixtures?|mocks?|__mocks__|examples?|docs?)(/|$)"
)

_TEST_PATH_RE = re.compile(r"(?i)(^|/)(tests?|spec|__tests__)(/|$)|test_|_test\.")


@dataclass(frozen=True, slots=True)
class SecretFinding:
    rule_id: str
    title: str
    file: str
    line: int
    severity: Severity
    confidence: float
    masked_value: str
    snippet: str
    entropy: float
    note: str | None = None


def mask(value: str) -> str:
    """Mask a detected credential.

    Keeps at most the first two characters so a reviewer can correlate the
    finding with a known key, and never more than that.
    """
    value = value.strip()
    if len(value) <= 6:
        return "[REDACTED]"
    return f"{value[:2]}{'•' * 8}[REDACTED len={len(value)}]"


def _mask_line(line: str, value: str) -> str:
    return line.strip().replace(value, "[REDACTED]")[:200]


def scan_text(path: str, text: str) -> list[SecretFinding]:
    """Scan one file for hardcoded secrets."""
    findings: list[SecretFinding] = []
    is_example = bool(EXAMPLE_PATH_RE.search(path))
    is_test = bool(_TEST_PATH_RE.search(path))
    lines = text.splitlines()

    for index, line in enumerate(lines, start=1):
        if len(line) > 4000:
            continue
        for rule in PROVIDER_RULES:
            for match in rule.pattern.finditer(line):
                value = match.group(0)
                confidence = rule.confidence
                note = None
                if is_example:
                    confidence *= 0.4
                    note = "located in an example/template file; may be an intentional placeholder"
                elif is_test:
                    confidence *= 0.7
                    note = "located in test code; may be a fixture value"
                findings.append(SecretFinding(
                    rule_id=rule.id, title=rule.name, file=path, line=index,
                    severity=rule.severity, confidence=round(confidence, 3),
                    masked_value=mask(value), snippet=_mask_line(line, value),
                    entropy=round(shannon_entropy(value), 3), note=note,
                ))

        for match in GENERIC_RULE.pattern.finditer(line):
            value = match.group(2)
            if PLACEHOLDER_RE.match(value.strip()):
                continue
            if value.startswith(("process.env", "os.environ", "${", "{{", "<%")):
                continue
            entropy = shannon_entropy(value)
            if entropy < GENERIC_RULE.entropy_floor:
                continue
            if any(f.line == index and f.file == path for f in findings):
                continue
            confidence = GENERIC_RULE.confidence + min(0.25, (entropy - 3.2) * 0.12)
            note = None
            if is_example:
                confidence *= 0.35
                note = "located in an example/template file; may be an intentional placeholder"
            elif is_test:
                confidence *= 0.6
                note = "located in test code; may be a fixture value"
            findings.append(SecretFinding(
                rule_id=GENERIC_RULE.id,
                title=f"{GENERIC_RULE.name} ({match.group(1)})",
                file=path, line=index, severity=GENERIC_RULE.severity,
                confidence=round(min(0.9, confidence), 3), masked_value=mask(value),
                snippet=_mask_line(line, value), entropy=round(entropy, 3), note=note,
            ))
    return findings
