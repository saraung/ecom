# app/api/v1/content.py
"""Public storefront content (no auth — homepage and layout read this)."""
from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.repositories import content as content_repo
from app.schemas.content import ContentBlockRead, PublicBlocksResponse

router = APIRouter(prefix="/content", tags=["Content"])


@router.get("/blocks", response_model=PublicBlocksResponse)
def get_blocks(
    session: SessionDep,
    keys: list[str] | None = Query(default=None, max_length=20),
):
    """Live blocks grouped by slot (sort_order first). Absent slots fall back
    to hardcoded storefront content. Drafts, disabled and expired excluded.

    Omit ``keys`` to fetch every live block (cheap — one indexed query).
    """
    live = content_repo.get_live_blocks(session, keys=keys)
    return PublicBlocksResponse(
        blocks={
            key: [ContentBlockRead.model_validate(block) for block in items]
            for key, items in live.items()
        }
    )
