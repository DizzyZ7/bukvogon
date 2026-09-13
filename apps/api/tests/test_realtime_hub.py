import asyncio

from bukvogon.services.realtime import RaceRealtimeHub


class QueueBroker:
    def __init__(self):
        self.queues = {}
        self.listen_calls = {}

    async def publish(self, race_id, snapshot):
        await self.queues.setdefault(race_id, asyncio.Queue()).put(snapshot)

    async def listen(self, race_id):
        self.listen_calls[race_id] = self.listen_calls.get(race_id, 0) + 1
        queue = self.queues.setdefault(race_id, asyncio.Queue())
        while True:
            yield await queue.get()


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


def test_hub_uses_one_broker_listener_per_race_and_broadcasts_to_all_local_clients():
    async def scenario():
        broker = QueueBroker()
        hub = RaceRealtimeHub(broker)
        first = FakeSocket()
        second = FakeSocket()

        await hub.add('race-1', first)
        await hub.add('race-1', second)
        await asyncio.sleep(0)

        assert broker.listen_calls == {'race-1': 1}

        snapshot = {'type': 'snapshot', 'race_id': 'race-1', 'racers': []}
        await hub.publish('race-1', snapshot)

        for _ in range(20):
            if first.messages and second.messages:
                break
            await asyncio.sleep(0.01)

        assert first.messages == [snapshot]
        assert second.messages == [snapshot]

        await hub.remove('race-1', first)
        await hub.remove('race-1', second)
        assert hub.local_client_count('race-1') == 0

        await hub.close()

    asyncio.run(scenario())
