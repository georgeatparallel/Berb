"""Reasoning method registry and factory.

This module provides a central registry for all reasoning methods,
ensuring each method is implemented once in its own file and can be
reused throughout the codebase via the registry.

Thread-safe singleton creation using double-checked locking pattern.

Usage:
    from berb.reasoning.registry import get_reasoner

    # Get a reasoner by type (singleton pattern)
    multi_perspective = get_reasoner("multi_perspective", llm_client)
    result = await multi_perspective.execute(context)

    # Or use the factory function
    from berb.reasoning.registry import create_reasoner
    reasoner = create_reasoner("debate", llm_client, num_arguments=5)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Type
from enum import Enum

from .base import ReasoningMethod, MethodType, ReasoningContext, ReasoningResult

logger = logging.getLogger(__name__)


# Type alias for reasoner factory functions
ReasonerFactory = Callable[..., ReasoningMethod]


class ReasonerRegistry:
    """Central registry for all reasoning methods.

    Provides singleton access to reasoning method instances, ensuring
    each method is implemented once in its dedicated file and reused
    throughout the codebase.

    Usage:
        # Get singleton instance
        reasoner = ReasonerRegistry.get("multi_perspective", llm_client)

        # Or create new instance
        reasoner = ReasonerRegistry.create("debate", llm_client, num_arguments=5)
    """

    # Registry storage: method_type -> (class, factory_func)
    _registry: dict[MethodType, tuple[Type[ReasoningMethod], ReasonerFactory | None]] = {}

    # Lock for thread-safe singleton creation (BUG-R001 FIX)
    _init_lock: asyncio.Lock | None = None

    # Singleton instances: method_type -> instance
    _singletons: dict[MethodType, ReasoningMethod] = {}
    
    @classmethod
    def register(
        cls,
        method_type: MethodType,
        reasoner_class: Type[ReasoningMethod],
        factory_func: ReasonerFactory | None = None,
    ) -> None:
        """Register a reasoning method.
        
        Args:
            method_type: Type identifier for the method
            reasoner_class: Class implementing the method
            factory_func: Optional factory function for complex initialization
        """
        cls._registry[method_type] = (reasoner_class, factory_func)
        logger.debug(f"Registered reasoning method: {method_type.value}")
    
    @classmethod
    def get(
        cls,
        method_type: MethodType | str,
        llm_client: Any = None,
        **kwargs: Any,
    ) -> ReasoningMethod:
        """Get a reasoning method instance (singleton pattern).

        Returns existing instance if available, otherwise creates new one.

        BUG-R001 FIX: Uses double-checked locking for thread-safe singleton creation.
        BUG-NEW-001 FIX: Warns if called from async context (recommends get_async).

        Args:
            method_type: Type of reasoner to get
            llm_client: LLM client for the reasoner
            **kwargs: Additional arguments for initialization

        Returns:
            ReasoningMethod instance

        Raises:
            ValueError: If method_type is not registered

        Note:
            For async contexts, prefer await ReasonerRegistry.get_async()
            to avoid potential lock contention.
        """
        import threading
        import asyncio

        # BUG-NEW-001 FIX: Detect if called from async context and warn
        try:
            loop = asyncio.get_running_loop()
            if loop is not None and not loop.is_running():
                pass  # Loop exists but not running - ok to use sync
            elif loop is not None:
                # Called from running async context - warn user
                logger.warning(
                    f"get_reasoner('{method_type}') called from async context. "
                    f"Consider using 'await ReasonerRegistry.get_async()' instead "
                    f"to avoid potential lock contention."
                )
        except RuntimeError:
            pass  # No running loop - safe to use sync

        # Convert string to MethodType if needed
        if isinstance(method_type, str):
            try:
                method_type = MethodType(method_type.lower())
            except ValueError:
                raise ValueError(f"Unknown reasoning method: {method_type}")

        # BUG-R001 FIX: Double-checked locking for thread-safe singleton creation
        # Fast path: check without lock (common case after initialization)
        if method_type in cls._singletons:
            return cls._singletons[method_type]

        # Slow path: use threading.Lock for sync safety
        # Note: For pure async contexts, use await cls.get_async() instead
        if not hasattr(cls, '_sync_init_lock') or cls._sync_init_lock is None:
            cls._sync_init_lock = threading.Lock()

        with cls._sync_init_lock:
            # Double-check after acquiring lock
            if method_type in cls._singletons:
                return cls._singletons[method_type]

            # Create new instance (only one thread can reach here)
            instance = cls.create(method_type, llm_client=llm_client, **kwargs)
            cls._singletons[method_type] = instance
            return instance

    @classmethod
    async def get_async(
        cls,
        method_type: MethodType | str,
        llm_client: Any = None,
        **kwargs: Any,
    ) -> ReasoningMethod:
        """Get a reasoning method instance (singleton pattern, async-safe).

        Returns existing instance if available, otherwise creates new one.

        BUG-R001 FIX: Uses asyncio.Lock for async-safe singleton creation.

        Args:
            method_type: Type of reasoner to get
            llm_client: LLM client for the reasoner
            **kwargs: Additional arguments for initialization

        Returns:
            ReasoningMethod instance

        Raises:
            ValueError: If method_type is not registered
        """
        # Convert string to MethodType if needed
        if isinstance(method_type, str):
            try:
                method_type = MethodType(method_type.lower())
            except ValueError:
                raise ValueError(f"Unknown reasoning method: {method_type}")

        # BUG-R001 FIX: Double-checked locking for async-safe singleton creation
        # Fast path: check without lock (common case after initialization)
        if method_type in cls._singletons:
            return cls._singletons[method_type]

        # Slow path: acquire asyncio lock
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            # Double-check after acquiring lock
            if method_type in cls._singletons:
                return cls._singletons[method_type]

            # Create new instance (only one task can reach here)
            instance = cls.create(method_type, llm_client=llm_client, **kwargs)
            cls._singletons[method_type] = instance
            return instance

    @classmethod
    async def initialize(cls) -> None:
        """Initialize the registry (create locks). Call before concurrent access.

        BUG-R001 FIX: Pre-initializes locks to avoid lazy initialization races.
        """
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()
        if not hasattr(cls, '_sync_init_lock') or cls._sync_init_lock is None:
            import threading
            cls._sync_init_lock = threading.Lock()
        logger.debug("Registry initialized")

    @classmethod
    def create(
        cls,
        method_type: MethodType | str,
        llm_client: Any = None,
        **kwargs: Any,
    ) -> ReasoningMethod:
        """Create a new reasoning method instance.
        
        Always creates a new instance (not singleton).
        
        Args:
            method_type: Type of reasoner to create
            llm_client: LLM client for the reasoner
            **kwargs: Additional arguments for initialization
            
        Returns:
            New ReasoningMethod instance
            
        Raises:
            ValueError: If method_type is not registered
        """
        # Convert string to MethodType if needed
        if isinstance(method_type, str):
            try:
                method_type = MethodType(method_type.lower())
            except ValueError:
                raise ValueError(f"Unknown reasoning method: {method_type}")
        
        # Look up in registry
        if method_type not in cls._registry:
            available = ", ".join(mt.value for mt in cls._registry.keys())
            raise ValueError(
                f"Unknown reasoning method: {method_type}. "
                f"Available methods: {available}"
            )
        
        reasoner_class, factory_func = cls._registry[method_type]
        
        # Use factory if provided, otherwise instantiate directly
        if factory_func:
            return factory_func(llm_client=llm_client, **kwargs)
        else:
            return reasoner_class(llm_client=llm_client, **kwargs)
    
    @classmethod
    def clear_singletons(cls) -> None:
        """Clear all singleton instances.

        Also resets the auto_register_all() idempotency flag to allow
        re-registration after clearing the registry.

        Useful for testing or when LLM client needs to be refreshed.
        """
        cls._singletons.clear()
        # BUG-NEW-002 FIX: Reset auto_register_all flag to allow re-registration
        if hasattr(auto_register_all, '_called'):
            delattr(auto_register_all, '_called')
        logger.debug("Cleared all reasoner singletons")
    
    @classmethod
    def list_available(cls) -> list[str]:
        """List all registered reasoning methods.
        
        Returns:
            List of method type names
        """
        return [mt.value for mt in cls._registry.keys()]
    
    @classmethod
    def is_registered(cls, method_type: MethodType | str) -> bool:
        """Check if a reasoning method is registered.
        
        Args:
            method_type: Type to check
            
        Returns:
            True if registered, False otherwise
        """
        if isinstance(method_type, str):
            try:
                method_type = MethodType(method_type.lower())
            except ValueError:
                return False
        return method_type in cls._registry


# Convenience functions for common usage

def get_reasoner(
    method_type: MethodType | str,
    llm_client: Any = None,
    **kwargs: Any,
) -> ReasoningMethod:
    """Get a reasoning method instance (singleton).

    Thread-safe using double-checked locking pattern.

    For async contexts, consider using await ReasonerRegistry.get_async() instead.

    Args:
        method_type: Type of reasoner (e.g., "debate", "bayesian")
        llm_client: LLM client for the reasoner
        **kwargs: Additional initialization arguments

    Returns:
        ReasoningMethod instance

    Example:
        >>> from berb.reasoning.registry import get_reasoner
        >>> reasoner = get_reasoner("multi_perspective", llm_client)
        >>> result = await reasoner.execute(context)
    """
    return ReasonerRegistry.get(method_type, llm_client=llm_client, **kwargs)


def create_reasoner(
    method_type: MethodType | str,
    llm_client: Any = None,
    **kwargs: Any,
) -> ReasoningMethod:
    """Create a new reasoning method instance.
    
    Always creates a new instance (not singleton).
    
    Args:
        method_type: Type of reasoner (e.g., "debate", "bayesian")
        llm_client: LLM client for the reasoner
        **kwargs: Additional initialization arguments
        
    Returns:
        New ReasoningMethod instance
        
    Example:
        >>> from berb.reasoning.registry import create_reasoner
        >>> debate1 = create_reasoner("debate", llm_client, num_arguments=3)
        >>> debate2 = create_reasoner("debate", llm_client, num_arguments=5)
    """
    return ReasonerRegistry.create(method_type, llm_client=llm_client, **kwargs)


def list_reasoners() -> list[str]:
    """List all available reasoning methods.
    
    Returns:
        List of method type names
        
    Example:
        >>> from berb.reasoning.registry import list_reasoners
        >>> print(list_reasoners())
        ['multi_perspective', 'pre_mortem', 'bayesian', ...]
    """
    return ReasonerRegistry.list_available()


# Auto-registration helper

def auto_register_all() -> None:
    """Auto-register all reasoning methods.

    Imports all reasoner modules and registers their classes.
    Called automatically when the reasoner package is imported.

    BUG-R002 FIX: Added error handling and logging for partial failure reporting.
    BUG-NEW-002 FIX: Added idempotency guard to prevent duplicate execution.
    """
    # BUG-NEW-002 FIX: Idempotency guard - skip if already called
    if hasattr(auto_register_all, '_called') and auto_register_all._called:
        logger.debug("auto_register_all() already called, skipping (idempotent)")
        return

    # BUG-R002 FIX: Import with error handling and logging
    modules = [
        "multi_perspective",
        "pre_mortem",
        "bayesian",
        "debate",
        "dialectical",
        "research",
        "socratic",
        "scientific",
        "jury",
    ]

    failed = []
    for module_name in modules:
        try:
            __import__(f"berb.reasoning.{module_name}", fromlist=[""])
            logger.debug(f"Registered reasoning method: {module_name}")
        except Exception as e:
            failed.append((module_name, str(e)))
            logger.error(
                f"Failed to register reasoning method '{module_name}': {e}. "
                f"This method will be unavailable. "
                f"Check dependencies and import path."
            )

    registered_count = len(ReasonerRegistry.list_available())
    if failed:
        logger.warning(
            f"Auto-registration complete with errors: "
            f"{registered_count} methods registered, {len(failed)} failed. "
            f"Failed: {', '.join(name for name, _ in failed)}"
        )
    else:
        logger.info(f"Auto-registered {registered_count} reasoning methods")

    # BUG-NEW-002 FIX: Mark as called
    auto_register_all._called = True
