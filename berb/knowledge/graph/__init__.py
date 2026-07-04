"""Research knowledge graph built on NetworkX.

Extracts entities (Papers, Methods, Datasets, Metrics) and relations
(CITES, EXTENDS, OUTPERFORMS) from literature and experiment results,
enabling research gap discovery and trend analysis.
"""

from berb.knowledge.graph.builder import KnowledgeGraphBuilder
from berb.knowledge.graph.entities import Entity, EntityType
from berb.knowledge.graph.query import KnowledgeGraphQuery
from berb.knowledge.graph.relations import Relation, RelationType

__all__ = [
    "Entity",
    "EntityType",
    "Relation",
    "RelationType",
    "KnowledgeGraphBuilder",
    "KnowledgeGraphQuery",
]
