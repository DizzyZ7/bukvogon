from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from bukvogon.api.auth import require_pro_principal
from bukvogon.domain.auth import AuthenticatedPrincipal


router = APIRouter(tags=['ranked'])


@router.get('/ranked/leaderboard')
async def get_ranked_leaderboard(
    request: Request,
    limit: int = Query(default=100, ge=1, le=100),
    _principal: AuthenticatedPrincipal = Depends(require_pro_principal),
) -> dict[str, object]:
    entries = await request.app.state.race_results.fetch_ranked_leaderboard(limit=limit)
    return {
        'entries': [
            {
                'user_id': entry.user_id,
                'rating': entry.rating,
                'games_played': entry.games_played,
                'position': entry.position,
                'is_top_1000': entry.is_top_1000,
            }
            for entry in entries
        ]
    }
