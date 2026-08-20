"""Example plugins for Berb."""

from __future__ import annotations

import logging
from typing import Any

from berb.plugins import Plugin, PluginHook, PluginManifest

logger = logging.getLogger(__name__)


class SecurityScannerPlugin(Plugin):
    """Security scanning plugin using Bandit and Safety."""

    def __init__(
        self, manifest: PluginManifest, config: dict[str, Any] | None = None
    ) -> None:
        """Initialize security scanner plugin."""
        super().__init__(manifest, config)
        self._scan_results: list[dict[str, Any]] = []

    def on_security_scan(self, code: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Scan code for security issues.

        Args:
            code: Python code to scan

        Returns:
            List of security issues found
        """
        issues = []

        # Check for common security issues
        dangerous_patterns = [
            ("eval(", "Use of eval() is dangerous"),
            ("exec(", "Use of exec() is dangerous"),
            ("__import__(", "Dynamic import detected"),
            ("subprocess.Popen", "Subprocess without shell=False"),
            ("os.system(", "Use of os.system() is dangerous"),
            ("pickle.load", "Pickle deserialization is dangerous"),
            ("yaml.load(", "YAML load without safe_load"),
        ]

        for line_num, line in enumerate(code.split("\n"), 1):
            for pattern, message in dangerous_patterns:
                if pattern in line:
                    issues.append(
                        {
                            "type": "security",
                            "severity": "high",
                            "line": line_num,
                            "message": message,
                            "code": line.strip(),
                        }
                    )

        # Check for hardcoded secrets
        import re

        secret_patterns = [
            (r'["\']api[_-]?key["\']\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded API key"),
            (r'["\']password["\']\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded password"),
            (r'["\']secret["\']\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded secret"),
            (r'["\']token["\']\s*[:=]\s*["\'][^"\']+["\']', "Hardcoded token"),
        ]

        for line_num, line in enumerate(code.split("\n"), 1):
            for pattern, message in secret_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append(
                        {
                            "type": "secret",
                            "severity": "critical",
                            "line": line_num,
                            "message": message,
                            "code": line.strip(),
                        }
                    )

        self._scan_results = issues
        logger.info(f"Security scan found {len(issues)} issues")

        return issues

    def on_post_stage(
        self, stage: int, stage_name: str, result: Any, **kwargs: Any
    ) -> None:
        """Scan generated code after code generation stage."""
        if stage_name == "code_generation":
            # Extract code from result if possible
            if hasattr(result, "code"):
                self.on_security_scan(result.code)
            elif isinstance(result, dict) and "code" in result:
                self.on_security_scan(result["code"])


class CitationManagerPlugin(Plugin):
    """Citation management plugin for Zotero/Mendeley integration."""

    def __init__(
        self, manifest: PluginManifest, config: dict[str, Any] | None = None
    ) -> None:
        """Initialize citation manager."""
        super().__init__(manifest, config)
        self._zotero_api_key = config.get("zotero_api_key") if config else None
        self._zotero_user_id = config.get("zotero_user_id") if config else None
        self._citations_exported = 0

    def on_post_search(self, results: list, **kwargs: Any) -> list | None:
        """Export citations to Zotero after literature search.

        Args:
            results: List of literature search results

        Returns:
            Modified results (unchanged)
        """
        if not self._zotero_api_key or not self._zotero_user_id:
            logger.warning("Zotero credentials not configured")
            return results

        # Convert results to Zotero format
        zotero_items = []
        for paper in results:
            item = {
                "itemType": "journalArticle",
                "title": getattr(paper, "title", ""),
                "creators": [],
                "abstractNote": getattr(paper, "abstract", ""),
                "DOI": getattr(paper, "doi", ""),
                "url": getattr(paper, "url", ""),
            }

            # Add authors
            authors = getattr(paper, "authors", [])
            for author in authors:
                if isinstance(author, str):
                    # Parse "Last, First" format
                    parts = author.split(", ")
                    if len(parts) == 2:
                        item["creators"].append(
                            {
                                "creatorType": "author",
                                "firstName": parts[1],
                                "lastName": parts[0],
                            }
                        )

            zotero_items.append(item)

        # Export to Zotero (would use actual API in production)
        logger.info(f"Would export {len(zotero_items)} citations to Zotero")
        self._citations_exported += len(zotero_items)

        return results

    def on_pipeline_end(self, **kwargs: Any) -> None:
        """Report citation statistics at pipeline end."""
        logger.info(f"Total citations exported: {self._citations_exported}")


class DjangoTemplatePlugin(Plugin):
    """Django experiment template plugin."""

    def __init__(
        self, manifest: PluginManifest, config: dict[str, Any] | None = None
    ) -> None:
        """Initialize Django template plugin."""
        super().__init__(manifest, config)
        self._templates_applied = 0

    def on_pre_experiment(self, experiment_config: dict, **kwargs: Any) -> None:
        """Apply Django template if experiment is web-related."""
        experiment_type = experiment_config.get("type", "")

        if "web" in experiment_type.lower() or "django" in experiment_type.lower():
            # Inject Django-specific configuration
            experiment_config.setdefault("framework", "django")
            experiment_config.setdefault("requirements", [])
            experiment_config["requirements"].extend(
                [
                    "django>=4.0",
                    "djangorestframework>=3.14",
                    "pytest-django>=4.5",
                ]
            )

            self._templates_applied += 1
            logger.info("Applied Django template to experiment")

    def on_post_experiment(self, results: dict, **kwargs: Any) -> None:
        """Report template usage."""
        if self._templates_applied > 0:
            logger.info(f"Django templates applied: {self._templates_applied}")


# Plugin manifests (would be in plugin.json in production)
SECURITY_SCANNER_MANIFEST = PluginManifest(
    id="security-scanner",
    name="Security Scanner",
    version="1.0.0",
    description="Scan generated code for security issues using Bandit patterns",
    author="Berb Team",
    hooks=[PluginHook.SECURITY_SCAN, PluginHook.POST_STAGE],
    entry_point="berb.plugins.examples.SecurityScannerPlugin",
    homepage="https://github.com/georgehadji/berb/plugins/security-scanner",
    license="MIT",
)

CITATION_MANAGER_MANIFEST = PluginManifest(
    id="citation-manager",
    name="Citation Manager",
    version="1.0.0",
    description="Export citations to Zotero/Mendeley",
    author="Berb Team",
    hooks=[PluginHook.POST_SEARCH, PluginHook.PIPELINE_END],
    entry_point="berb.plugins.examples.CitationManagerPlugin",
    config_schema={
        "type": "object",
        "properties": {
            "zotero_api_key": {"type": "string"},
            "zotero_user_id": {"type": "string"},
        },
    },
    homepage="https://github.com/georgehadji/berb/plugins/citation-manager",
    license="MIT",
)

DJANGO_TEMPLATE_MANIFEST = PluginManifest(
    id="django-template",
    name="Django Template",
    version="1.0.0",
    description="Django experiment templates for web applications",
    author="Berb Team",
    hooks=[PluginHook.PRE_EXPERIMENT, PluginHook.POST_EXPERIMENT],
    entry_point="berb.plugins.examples.DjangoTemplatePlugin",
    homepage="https://github.com/georgehadji/berb/plugins/django-template",
    license="MIT",
)
