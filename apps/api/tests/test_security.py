"""Security analyzer tests.

The behaviours that matter: real credentials are found, placeholders are not,
detected values never appear in the output, and prose about code is not treated
as code.
"""

from __future__ import annotations

import pytest

from repolens_security import SecurityInput, analyze_security, mask, scan_patterns, scan_text


class TestSecretDetection:
    @pytest.mark.parametrize(
        ("content", "rule"),
        [
            ('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"', "aws_access_key_id"),
            ('token = "ghp_' + "a" * 36 + '"', "github_token"),
            ('key = "sk-ant-' + "x" * 30 + '"', "anthropic_key"),
            ('DB = "postgres://user:s3cretPassw0rd@db.internal/app"', "connection_string"),
            ("-----BEGIN RSA PRIVATE KEY-----", "private_key_block"),
        ],
    )
    def test_detects_provider_credentials(self, content, rule):
        findings = scan_text("src/config.py", content)
        assert rule in {finding.rule_id for finding in findings}

    @pytest.mark.parametrize(
        "content",
        [
            'password = "changeme"',
            'API_KEY = "your-api-key-here"',
            'SECRET = "<your-secret>"',
            'TOKEN = "${GITHUB_TOKEN}"',
            'key = os.environ["API_KEY"]',
            'password = "value-goes-here"',
        ],
    )
    def test_ignores_placeholders(self, content):
        assert scan_text("src/config.py", content) == []

    def test_detected_values_are_never_returned_in_plaintext(self):
        secret = "AKIAIOSFODNN7EXAMPLE"
        findings = scan_text("src/config.py", f'AWS_KEY = "{secret}"')
        assert findings
        for finding in findings:
            assert secret not in finding.masked_value
            assert secret not in finding.snippet
            assert "REDACTED" in finding.masked_value

    def test_mask_keeps_at_most_two_characters(self):
        masked = mask("supersecretvalue123")
        assert masked.startswith("su")
        assert "persecret" not in masked

    def test_example_files_lower_confidence_rather_than_being_ignored(self):
        content = 'GITHUB_TOKEN = "ghp_' + "b" * 36 + '"'
        normal = scan_text("src/config.py", content)[0]
        example = scan_text(".env.example", content)[0]
        assert example.confidence < normal.confidence
        assert example.note and "example" in example.note.lower()


class TestPatternDetection:
    @pytest.mark.parametrize(
        ("path", "language", "content", "rule"),
        [
            ("db.py", "python", 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")', "sql_fstring"),
            ("run.py", "python", "subprocess.run(cmd, shell=True)", "shell_true"),
            ("load.py", "python", "data = pickle.loads(payload)", "pickle_load"),
            ("api.py", "python", "requests.get(url, verify=False)", "tls_verification_disabled"),
            ("view.tsx", "tsx", "<div dangerouslySetInnerHTML={{__html: userInput}} />", "react_dangerous_html"),
        ],
    )
    def test_detects_insecure_patterns(self, path, language, content, rule):
        findings = scan_patterns(path, content, language)
        assert rule in {finding.rule_id for finding in findings}

    def test_comment_lines_are_not_flagged(self):
        assert scan_patterns("a.py", "# subprocess.run(cmd, shell=True)", "python") == []

    def test_every_finding_carries_remediation(self):
        findings = scan_patterns("db.py", 'cursor.execute(f"SELECT {x}")', "python")
        assert findings
        assert all(finding.remediation for finding in findings)


class TestSecurityAnalyzer:
    def test_documentation_is_not_pattern_scanned(self):
        """A changelog describing `verify=False` is prose, not a vulnerability."""
        texts = {
            "HISTORY.md": "- Fixed a bug where verify=False was ignored by the session.\n",
            "src/client.py": "import requests\n",
        }
        result = analyze_security(SecurityInput(
            texts=texts, languages={"src/client.py": "python"}, all_paths=list(texts),
            categories={"HISTORY.md": "DOCUMENTATION", "src/client.py": "CANDIDATE_CODE"},
        ))
        assert result.metrics["pattern_findings"] == 0
        assert result.metrics["files_pattern_scanned"] == 1

    def test_secret_scanning_still_covers_documentation(self):
        """A leaked credential in a README is a real leaked credential."""
        texts = {"README.md": 'Set AWS_KEY = "AKIAIOSFODNN7EXAMPLE" to get started.'}
        result = analyze_security(SecurityInput(
            texts=texts, all_paths=list(texts), categories={"README.md": "DOCUMENTATION"},
        ))
        assert result.metrics["secret_findings"] >= 1

    def test_duplicate_matches_are_counted_once(self):
        """An Anthropic key also matches the generic `sk-` shape; one mistake,
        one finding, one penalty."""
        texts = {"config.py": 'KEY = "sk-ant-' + "y" * 30 + '"'}
        result = analyze_security(SecurityInput(texts=texts, all_paths=list(texts)))
        assert result.metrics["secret_findings"] == 1

    def test_clean_repository_scores_well_and_says_why(self):
        texts = {
            "src/app.py": "def main():\n    return 0\n",
            ".gitignore": ".env\n",
            ".env.example": 'API_KEY="your-api-key-here"\n',
        }
        result = analyze_security(SecurityInput(
            texts=texts, all_paths=list(texts), has_lock_file=True,
            categories={path: "CANDIDATE_CODE" for path in texts},
        ))
        assert result.score >= 90
        assert result.metrics["good_practices"]

    def test_committed_env_file_is_a_critical_finding(self):
        texts = {".env": "SECRET=abc\n"}
        result = analyze_security(SecurityInput(texts=texts, all_paths=[".env"]))
        assert any("environment file" in e.claim.lower() for e in result.evidence)

    def test_limitations_are_always_reported(self):
        result = analyze_security(SecurityInput(texts={"a.py": "x = 1"}, all_paths=["a.py"]))
        scopes = {limitation.scope for limitation in result.limitations}
        assert "security_scope" in scopes
        assert "dependency_cves" in scopes
        assert any("cve database" in l.detail.lower() for l in result.limitations)
