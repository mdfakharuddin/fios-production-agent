import json
from sqlalchemy.future import select
from typing import Dict, Any, List

from FIOS.database.connection import async_session_maker
from FIOS.database.models.pricing_history import PricingHistory
from FIOS.database.models.conversations import Conversation

async def get_patterns(project_type: str = "") -> Dict[str, Any]:
    """Retrieve historical pricing patterns."""
    async with async_session_maker() as session:
        # Simplistic match for demo layering
        # Retrieve Won projects or recorded pricing
        # We assume outcome 'won' indicates a successful price
        stmt = select(Conversation).where(Conversation.analytics.isnot(None))
        result = await session.execute(stmt)
        records = result.scalars().all()

        won_prices = []
        all_prices = []
        
        for r in records:
            if not r.analytics:
                continue
                
            amount = r.analytics.get("final_amount", 0)
            if amount > 0:
                all_prices.append(amount)
                if r.outcome == "won":
                    won_prices.append(amount)
        
        avg_price = sum(won_prices) / len(won_prices) if won_prices else 0
        win_rate = (len(won_prices) / len(all_prices)) * 100 if all_prices else 0
        
        highest_price = max(won_prices) if won_prices else 0

        # Constructing the exact pattern response
        return {
            "avg_price": round(avg_price, 2),
            "highest_winning_price": highest_price,
            "win_rate": round(win_rate, 1),
            "historical_prices": sorted(won_prices, reverse=True)[:5]
        }
