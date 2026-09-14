from fastapi.testclient import TestClient

from bukvogon.domain.anti_cheat import VerificationStatus
from bukvogon.domain.ranked import RankedResult
from bukvogon.main import app


client = TestClient(app)


class FakeRaceResultsRepository:
    def __init__(self, results):
        self.results = list(results)
        self.requested_race_ids = []

    async def fetch_ranked_results(self, race_id: str):
        self.requested_race_ids.append(race_id)
        return list(self.results)


def test_health_endpoint():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_free_access_keeps_casual_but_blocks_ranked_and_leaderboard():
    response = client.get('/v1/access/free')
    assert response.status_code == 200
    assert response.json() == {
        'casual': True,
        'ranked': False,
        'leaderboard': False,
        'monthly_price_rub': 300,
    }


def test_active_pro_access_unlocks_ranked_and_leaderboard():
    response = client.get('/v1/access/pro_active')
    assert response.status_code == 200
    payload = response.json()
    assert payload['casual'] is True
    assert payload['ranked'] is True
    assert payload['leaderboard'] is True


def test_typing_validation_uses_mode_specific_yo_rule():
    casual = client.post('/v1/typing/validate', json={
        'target': 'ёлка',
        'typed': 'ел',
        'mode': 'casual',
    })
    ranked = client.post('/v1/typing/validate', json={
        'target': 'ёлка',
        'typed': 'ел',
        'mode': 'ranked',
    })

    assert casual.status_code == 200
    assert casual.json()['valid'] is True
    assert ranked.status_code == 200
    assert ranked.json()['valid'] is False
    assert ranked.json()['error_index'] == 0


def test_ranked_rate_contract_uses_server_results_and_returns_new_ratings():
    repository = FakeRaceResultsRepository([
        RankedResult('a', 1, VerificationStatus.VERIFIED),
        RankedResult('b', 2, VerificationStatus.VERIFIED),
    ])
    app.state.race_results = repository

    response = client.post('/v1/ranked/rate', json={
        'race_id': 'race-verified',
        'players': [
            {'user_id': 'a', 'rating': 1000},
            {'user_id': 'b', 'rating': 1000},
        ],
        'k_factor': 32,
    })

    assert response.status_code == 200
    assert repository.requested_race_ids == ['race-verified']
    ratings = response.json()['ratings']
    assert ratings['a'] > 1000
    assert ratings['b'] < 1000


def test_ranked_rate_rejects_provisional_result_loaded_from_server():
    app.state.race_results = FakeRaceResultsRepository([
        RankedResult('a', 1, VerificationStatus.VERIFIED),
        RankedResult('b', 2, VerificationStatus.PROVISIONAL),
    ])

    response = client.post('/v1/ranked/rate', json={
        'race_id': 'race-provisional',
        'players': [
            {'user_id': 'a', 'rating': 1000},
            {'user_id': 'b', 'rating': 1000},
        ],
    })

    assert response.status_code == 422
    assert 'verified results' in response.json()['detail']


def test_ranked_rate_rejects_client_supplied_result_or_verification_override():
    app.state.race_results = FakeRaceResultsRepository([
        RankedResult('a', 1, VerificationStatus.REVIEW),
        RankedResult('b', 2, VerificationStatus.REVIEW),
    ])

    response = client.post('/v1/ranked/rate', json={
        'race_id': 'race-review',
        'players': [
            {'user_id': 'a', 'rating': 1000},
            {'user_id': 'b', 'rating': 1000},
        ],
        'results': [
            {'user_id': 'a', 'place': 1, 'verification_status': 'verified'},
            {'user_id': 'b', 'place': 2, 'verification_status': 'verified'},
        ],
    })

    assert response.status_code == 422


def test_production_app_registers_realtime_race_routes():
    assert str(app.url_path_for('create_race')) == '/v1/races'
    assert str(app.url_path_for('get_race', race_id='race-1')) == '/v1/races/race-1'
    assert str(
        app.url_path_for('race_websocket', race_id='race-1', player_id='player-1')
    ) == '/v1/races/race-1/ws/player-1'
