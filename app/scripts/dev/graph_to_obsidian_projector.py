"""
Simplified Graph-to-Obsidian Projector
=======================================

Minimal projector for neo_adapter compatibility.
Creates simple review files instead of complex template generation.
"""

__version__ = "1.0"


from pathlib import Path
from typing import Any

from services.sync.jupyter_integration import JupyterSyncHook


def project_subgraph(
    subgraph_data: dict[str, Any], vault_path: str, **kwargs: Any
) -> dict[str, Any]:
    """
    Simplified projector function called by neo_adapter.

    Instead of complex template generation, creates a simple review file
    for manual integration.
    """
    try:
        vault = Path(vault_path)
        hook = JupyterSyncHook(vault)

        # Extract basic info from subgraph
        nodes = subgraph_data.get("nodes", [])
        relationships = subgraph_data.get("relationships", [])

        node_ids = [node.get("id") for node in nodes if node.get("id")]

        # Create summary
        summary = f"""
Graph data extraction completed:
- {len(nodes)} nodes retrieved
- {len(relationships)} relationships retrieved
- Node types: {_get_node_types(nodes)}
"""

        # Create review file
        result = hook.after_jupyter_execution(
            notebook_path=kwargs.get("source_notebook", "neo4j_query"),
            modified_nodes=node_ids,
            analysis_summary=summary.strip(),
            custom_metadata={
                "extraction_method": "neo_adapter",
                "total_nodes": len(nodes),
                "total_relationships": len(relationships),
                "node_types": _get_node_types(nodes),
            },
        )

        if result.is_ok:
            return {
                "success": True,
                "files_generated": 1,
                "files_updated": 0,
                "files_deleted": 0,
                "total_changes": 1,
                "errors": [],
                "details": {
                    "review_file": str(result.value),
                    "message": "Review file created for manual integration",
                },
            }
        else:
            return {
                "success": False,
                "files_generated": 0,
                "files_updated": 0,
                "files_deleted": 0,
                "total_changes": 0,
                "errors": [str(result.error)],
                "details": {},
            }

    except Exception as e:
        return {
            "success": False,
            "files_generated": 0,
            "files_updated": 0,
            "files_deleted": 0,
            "total_changes": 0,
            "errors": [str(e)],
            "details": {},
        }


def _get_node_types(nodes) -> Any:
    """Extract unique node types from nodes"""
    types = set()
    for node in nodes:
        labels = node.get("labels", [])
        if labels:
            types.update(labels)
    return sorted(list(types))
