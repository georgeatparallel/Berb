"""Plugin system for Berb.

This module provides a plugin architecture for extending Berb functionality
through community-developed plugins.

Features:
- Plugin discovery and loading
- Hook system (pre/post stage hooks)
- Plugin manifest validation
- Example plugins included

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.plugins import PluginManager
    
    manager = PluginManager()
    manager.discover_plugins()
    manager.execute_hook("pre_stage", stage=8)
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class PluginHook(str, Enum):
    """Available plugin hooks."""
    # Pipeline lifecycle
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    
    # Stage hooks
    PRE_STAGE = "pre_stage"
    POST_STAGE = "post_stage"
    STAGE_FAILED = "stage_failed"
    
    # LLM hooks
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    
    # Experiment hooks
    PRE_EXPERIMENT = "pre_experiment"
    POST_EXPERIMENT = "post_experiment"
    EXPERIMENT_FAILED = "experiment_failed"
    
    # Literature hooks
    PRE_SEARCH = "pre_search"
    POST_SEARCH = "post_search"
    
    # Paper hooks
    PRE_WRITE = "pre_write"
    POST_WRITE = "post_write"
    
    # Quality hooks
    QUALITY_CHECK = "quality_check"
    SECURITY_SCAN = "security_scan"


@dataclass
class PluginManifest:
    """Plugin manifest/metadata."""
    
    id: str
    name: str
    version: str
    description: str
    author: str
    hooks: list[PluginHook]
    entry_point: str  # module.class
    config_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    homepage: str = ""
    license: str = "MIT"
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Create manifest from dictionary."""
        hooks = [PluginHook(h) for h in data.get("hooks", []) if h in PluginHook.__members__]
        return cls(
            id=data.get("id", "unknown"),
            name=data.get("name", "Unknown Plugin"),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", "Anonymous"),
            hooks=hooks,
            entry_point=data.get("entry_point", ""),
            config_schema=data.get("config_schema", {}),
            dependencies=data.get("dependencies", []),
            homepage=data.get("homepage", ""),
            license=data.get("license", "MIT"),
        )
    
    @classmethod
    def from_file(cls, path: Path) -> PluginManifest | None:
        """Load manifest from JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load manifest from {path}: {e}")
            return None


class Plugin:
    """Base plugin class."""
    
    def __init__(self, manifest: PluginManifest, config: dict[str, Any] | None = None) -> None:
        """Initialize plugin.
        
        Args:
            manifest: Plugin manifest
            config: Plugin configuration
        """
        self.manifest = manifest
        self.config = config or {}
        self.enabled = True
    
    def execute(self, hook: PluginHook, **kwargs: Any) -> Any:
        """Execute plugin hook.
        
        Args:
            hook: Hook being executed
            **kwargs: Hook-specific arguments
            
        Returns:
            Hook result (varies by hook type)
        """
        if not self.enabled:
            return None
        
        method_name = f"on_{hook.value}"
        method = getattr(self, method_name, None)
        
        if method:
            try:
                return method(**kwargs)
            except Exception as e:
                logger.error(f"Plugin {self.manifest.id} hook {hook} failed: {e}")
                return None
        
        return None
    
    # Default hook implementations (override in subclasses)
    
    def on_pipeline_start(self, **kwargs: Any) -> None:
        """Called when pipeline starts."""
        pass
    
    def on_pipeline_end(self, **kwargs: Any) -> None:
        """Called when pipeline ends."""
        pass
    
    def on_pre_stage(self, stage: int, stage_name: str, **kwargs: Any) -> None:
        """Called before stage execution."""
        pass
    
    def on_post_stage(self, stage: int, stage_name: str, result: Any, **kwargs: Any) -> None:
        """Called after stage execution."""
        pass
    
    def on_stage_failed(self, stage: int, stage_name: str, error: Exception, **kwargs: Any) -> None:
        """Called when stage fails."""
        pass
    
    def on_pre_llm_call(self, prompt: str, model: str, **kwargs: Any) -> str | None:
        """Called before LLM call. Can modify prompt."""
        return None
    
    def on_post_llm_call(self, response: str, **kwargs: Any) -> str | None:
        """Called after LLM call. Can modify response."""
        return None
    
    def on_pre_experiment(self, experiment_config: dict, **kwargs: Any) -> None:
        """Called before experiment execution."""
        pass
    
    def on_post_experiment(self, results: dict, **kwargs: Any) -> None:
        """Called after experiment execution."""
        pass
    
    def on_experiment_failed(self, error: Exception, **kwargs: Any) -> None:
        """Called when experiment fails."""
        pass
    
    def on_pre_search(self, query: str, **kwargs: Any) -> str | None:
        """Called before literature search. Can modify query."""
        return None
    
    def on_post_search(self, results: list, **kwargs: Any) -> list | None:
        """Called after literature search. Can modify results."""
        return None
    
    def on_pre_write(self, section: str, content: str, **kwargs: Any) -> str | None:
        """Called before writing section. Can modify content."""
        return None
    
    def on_post_write(self, section: str, content: str, **kwargs: Any) -> str | None:
        """Called after writing section. Can modify content."""
        return None
    
    def on_quality_check(self, content: str, **kwargs: Any) -> dict[str, Any]:
        """Called during quality check. Return quality metrics."""
        return {}
    
    def on_security_scan(self, code: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Called during security scan. Return security issues."""
        return []


class PluginManager:
    """Manage plugin lifecycle and execution."""
    
    def __init__(self, plugin_dirs: list[str | Path] | None = None) -> None:
        """Initialize plugin manager.
        
        Args:
            plugin_dirs: Directories to search for plugins
        """
        self._plugins: dict[str, Plugin] = {}
        self._hooks: dict[PluginHook, list[Plugin]] = {hook: [] for hook in PluginHook}
        self._plugin_dirs = [Path(d) for d in (plugin_dirs or [])]
        
        # Add default plugin directories
        self._plugin_dirs.extend([
            Path(".berb/plugins"),
            Path.home() / ".berb" / "plugins",
        ])
    
    def discover_plugins(self) -> int:
        """Discover and load plugins from plugin directories.
        
        Returns:
            Number of plugins loaded
        """
        loaded = 0
        
        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                continue
            
            # Look for plugin directories
            for plugin_path in plugin_dir.iterdir():
                if not plugin_path.is_dir():
                    continue
                
                manifest_path = plugin_path / "plugin.json"
                if not manifest_path.exists():
                    continue
                
                # Load manifest
                manifest = PluginManifest.from_file(manifest_path)
                if not manifest:
                    continue
                
                # Load plugin
                try:
                    plugin = self._load_plugin(manifest, plugin_path)
                    if plugin:
                        self.register_plugin(plugin)
                        loaded += 1
                        logger.info(f"Loaded plugin: {manifest.name} v{manifest.version}")
                except Exception as e:
                    logger.error(f"Failed to load plugin {plugin_path}: {e}")
        
        logger.info(f"Discovered {loaded} plugins")
        return loaded
    
    def _load_plugin(self, manifest: PluginManifest, plugin_path: Path) -> Plugin | None:
        """Load plugin from entry point.
        
        Args:
            manifest: Plugin manifest
            plugin_path: Plugin directory path
            
        Returns:
            Loaded plugin or None
        """
        try:
            # Parse entry point (module.class)
            module_name, class_name = manifest.entry_point.rsplit(".", 1)
            
            # Add plugin path to sys.path temporarily
            import sys
            sys.path.insert(0, str(plugin_path))
            
            try:
                # Import module
                module = importlib.import_module(module_name)
                plugin_class = getattr(module, class_name)
                
                # Load config if exists
                config_path = plugin_path / "config.json"
                config = None
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                
                # Instantiate plugin
                return plugin_class(manifest, config)
                
            finally:
                sys.path.remove(str(plugin_path))
                
        except Exception as e:
            logger.error(f"Failed to load plugin {manifest.id}: {e}")
            return None
    
    def register_plugin(self, plugin: Plugin) -> None:
        """Register a plugin and its hooks.
        
        Args:
            plugin: Plugin to register
        """
        self._plugins[plugin.manifest.id] = plugin
        
        # Register hooks
        for hook in plugin.manifest.hooks:
            if plugin not in self._hooks[hook]:
                self._hooks[hook].append(plugin)
        
        logger.debug(f"Registered plugin {plugin.manifest.id} with {len(plugin.manifest.hooks)} hooks")
    
    def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin.
        
        Args:
            plugin_id: Plugin ID to unregister
            
        Returns:
            True if plugin was unregistered
        """
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False
        
        # Remove from hooks
        for hook in plugin.manifest.hooks:
            if plugin in self._hooks[hook]:
                self._hooks[hook].remove(plugin)
        
        # Remove from plugins dict
        del self._plugins[plugin_id]
        logger.info(f"Unregistered plugin: {plugin_id}")
        return True
    
    def execute_hook(self, hook: PluginHook, **kwargs: Any) -> list[Any]:
        """Execute all plugins registered for a hook.
        
        Args:
            hook: Hook to execute
            **kwargs: Hook arguments
            
        Returns:
            List of hook results
        """
        results = []
        
        for plugin in self._hooks.get(hook, []):
            if not plugin.enabled:
                continue
            
            try:
                result = plugin.execute(hook, **kwargs)
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(f"Plugin {plugin.manifest.id} hook {hook} failed: {e}")
        
        return results
    
    def execute_hook_first(self, hook: PluginHook, **kwargs: Any) -> Any | None:
        """Execute hook and return first non-None result.
        
        Useful for hooks that can modify values (e.g., pre_llm_call).
        
        Args:
            hook: Hook to execute
            **kwargs: Hook arguments
            
        Returns:
            First non-None result or None
        """
        for plugin in self._hooks.get(hook, []):
            if not plugin.enabled:
                continue
            
            try:
                result = plugin.execute(hook, **kwargs)
                if result is not None:
                    return result
            except Exception as e:
                logger.error(f"Plugin {plugin.manifest.id} hook {hook} failed: {e}")
        
        return None
    
    def list_plugins(self) -> list[PluginManifest]:
        """List all registered plugins.
        
        Returns:
            List of plugin manifests
        """
        return [p.manifest for p in self._plugins.values()]
    
    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """Get plugin by ID.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            Plugin or None
        """
        return self._plugins.get(plugin_id)
    
    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            True if plugin was enabled
        """
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.enabled = True
            logger.info(f"Enabled plugin: {plugin_id}")
            return True
        return False
    
    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            True if plugin was disabled
        """
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.enabled = False
            logger.info(f"Disabled plugin: {plugin_id}")
            return True
        return False
    
    def get_hook_count(self, hook: PluginHook) -> int:
        """Get number of plugins registered for a hook.
        
        Args:
            hook: Hook to check
            
        Returns:
            Number of plugins
        """
        return len(self._hooks.get(hook, []))
    
    def get_summary(self) -> dict[str, Any]:
        """Get plugin manager summary.
        
        Returns:
            Summary dictionary
        """
        return {
            "total_plugins": len(self._plugins),
            "enabled_plugins": sum(1 for p in self._plugins.values() if p.enabled),
            "plugins": [
                {
                    "id": p.manifest.id,
                    "name": p.manifest.name,
                    "version": p.manifest.version,
                    "enabled": p.enabled,
                    "hooks": [h.value for h in p.manifest.hooks],
                }
                for p in self._plugins.values()
            ],
        }


# Global plugin manager instance
_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Get global plugin manager instance."""
    global _manager
    if _manager is None:
        _manager = PluginManager()
        _manager.discover_plugins()
    return _manager
