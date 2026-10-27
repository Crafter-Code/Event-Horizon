                                                                       

                                                                             
                                                                              
   

import json
import os

from broadcast_peer import review_payload
from foundry_narrative import validate_draft


def decide(payload):
    try:
        if payload.get('schema') != 'eh-broadcast-review-1':
            raise ValueError('Unsupported review schema')
        request = review_payload(payload['source'], payload['draft'])
        if request != payload:
            raise ValueError('Review request changed in transit')
        validate_draft(payload['draft'], payload['source'])
        approved, reason = True, 'Evidence and delivery contract accepted'
    except (KeyError, TypeError, ValueError):
        approved, reason = False, 'Evidence or delivery contract rejected'
    return {'approved': approved, 'episode_id': payload.get('episode_id'),
            'fact_fingerprint': payload.get('fact_fingerprint'), 'reason': reason}


def build_app(public_url='http://127.0.0.1:9018'):
    from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
    from a2a.server.agent_execution import AgentExecutor
    from a2a.server.events import EventQueue
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
    from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
    from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
    from a2a.types.a2a_pb2 import TaskState
    from starlette.applications import Starlette

    class Broadcaster(AgentExecutor):
        async def execute(self, context, event_queue: EventQueue):
            task = context.current_task or new_task_from_user_message(context.message)
            if context.current_task is None:
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.update_status(state=TaskState.TASK_STATE_WORKING,
                                        message=new_text_message('Reviewing verified episode'))
            try:
                payload = json.loads(get_message_text(context.message))
                result = decide(payload) if isinstance(payload, dict) else decide({})
            except (ValueError, TypeError):
                result = decide({})
            await updater.add_artifact(parts=[new_text_part(text=json.dumps(result), media_type='application/json')])
            await updater.update_status(state=TaskState.TASK_STATE_COMPLETED,
                                        message=new_text_message('Review complete'))

        async def cancel(self, context, event_queue):
            raise NotImplementedError('Review tasks cannot be cancelled')

    card = AgentCard(name='Event Horizon Broadcast Review',
        description='Independently checks the handoff of verified football narratives to broadcast.',
        version='1.0.0', default_input_modes=['text/plain'], default_output_modes=['application/json'],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding='JSONRPC',
            url=public_url.rstrip('/')+'/a2a/broadcast', protocol_version='1.0')],
        skills=[AgentSkill(id='broadcast-review', name='Broadcast review',
            description='Checks evidence identity and delivery contract before editorial review.',
            input_modes=['text/plain'], output_modes=['application/json'], tags=['football','broadcast'])])
    handler = DefaultRequestHandler(agent_executor=Broadcaster(), task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=[*create_agent_card_routes(card),
                             *create_jsonrpc_routes(handler, rpc_url='/a2a/broadcast')])


if __name__ == '__main__':
    import uvicorn
    host = '127.0.0.1'
    port = int(os.getenv('EVENT_HORIZON_A2A_PORT', '9018'))
    uvicorn.run(build_app(f'http://{host}:{port}'), host=host, port=port)
