"""Resolve reference_image paths with filesystem fallback.

Mirrors the frontend's checkRefImageStatus logic: if the stored
reference_image is empty, probe the convention path
``{project_dir}/assets/images/{node_id}.png``.  For state nodes,
fall back further to the parent entity's image.
"""

from __future__ import annotations

from pathlib import Path


def resolve_reference_image(
    node_id: str,
    entity_id: str,
    project_dir: str,
    stored_ref: str = "",
) -> str:
    """Return the best available reference image path for a node.

    Parameters
    ----------
    node_id:
        The ID of the node (entity or state).
    entity_id:
        For state nodes, the parent entity ID.  Pass ``""`` for entity nodes.
    project_dir:
        Absolute path to the project directory (parent of ``assets/``).
    stored_ref:
        The ``reference_image`` value stored in story-graph.json.
        If non-empty and the file exists, returned as-is.

    Returns
    -------
    str
        Resolved absolute path, or ``""`` if no image can be found.
    """
    # 1. Stored value
    if stored_ref:
        if not project_dir:
            # No project context — cannot probe, trust stored value as-is
            return stored_ref
        if Path(stored_ref).is_file():
            return stored_ref
        # Stored value points to a missing file — fall through to probing
    if not project_dir:
        return ""
    images_dir = Path(project_dir) / "assets" / "images"
    # 2. Convention path: {node_id}.png
    own = images_dir / f"{node_id}.png"
    if own.is_file():
        return str(own)
    # 3. State nodes fall back to entity image
    if entity_id:
        entity_img = images_dir / f"{entity_id}.png"
        if entity_img.is_file():
            return str(entity_img)
    return ""
