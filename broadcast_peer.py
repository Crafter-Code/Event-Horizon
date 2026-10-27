                                                                 

                                                                               
                                                                                
   

import asyncio
import json
import os
from urllib.parse import urlsplit

from foundry_narrative import parse_object, validate_draft


def review_payload(packet, draft):
    validate_draft(draft, packet)
    if not packet.get('fact_fingerprint') or not packet.get('id'):
        raise ValueError('Episode identity is missing')
    return {'schema': 'eh-broadcast-review-1', 'episode_id': packet['id'],
            'fact_fingerprint': packet['fact_fingerprint'], 'draft': draft,
            'source': packet}


def validate_review(review, request):
    if (set(review) != {'approved', 'episode_id', 'fact_fingerprint', 'reason'} or
            type(review['approved']) is not bool or
            review['episode_id'] != request['episode_id'] or
            review['fact_fingerprint'] != request['fact_fingerprint'] or
            not isinstance(review['reason'], str) or len(review['reason']) > 160):
        raise ValueError('Invalid A2A review')
    if not review['approved']:
        raise ValueError('Broadcast peer held the episode')
    return review


class BroadcastPeer:
    def __init__(self, url):
        parsed = urlsplit(url)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or
            (parsed.scheme != 'https' and not (parsed.scheme == 'http' and
            parsed.hostname in ('127.0.0.1', 'localhost')))):
            raise ValueError('A2A endpoint must use HTTPS or local loopback')
        self.url = url

    async def review(self, packet, draft):
        request = review_payload(packet, draft)
        from agent_framework.a2a import A2AAgent
        async with A2AAgent(url=self.url, timeout=5) as agent:
            response = await asyncio.wait_for(agent.run(json.dumps(request, ensure_ascii=False)), timeout=6)
        return validate_review(parse_object(response), request)


def from_environment():
    url = os.getenv('EVENT_HORIZON_BROADCAST_A2A_URL')
    return BroadcastPeer(url) if url else None
