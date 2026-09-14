from types import SimpleNamespace

from fastapi.testclient import TestClient

from bukvogon.main import app


client = TestClient(app)


class FakeRankedRatingRepository:
    def __init__(self, *, ratings=None, applied=True, error=None):
        self.ratings = ratings or {'a': 1016.0, 'b': 984.0}
        self.applied = applied
        self.error = error
        self.requested_race_ids = []

    async def apply_ranked_rating(self, race_id: str):
        self.requested_race_ids.append(race_id)
        if self.error is not None:
            raise ValueError(self.error)
        return SimpleNamespace(ratings=dict(self.ratings), applied=self.applied)


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


def test_ranked_rate_contract_needs_only_race_id_and_uses_server_rating_state():
    repository = FakeRankedRatingRepository()
    app.state.race_results = repository

    response = client.post('/v1/ranked/rate', json={'race_id': 'race-verified'})

    assert response.status_code == 200
    assert repository.requested_race_ids == ['race-verified']
    assert response.json() == {
        'ratings': {'a': 1016.0, 'b': 984.0},
        'applied': True,
    }


def test_ranked_rate_is_idempotent_when_race_was_already_applied():
    repository = FakeRankedRatingRepository(applied=False)
    app.state.race_results = repository

    response = client.post('/v1/ranked/rate', json={'race_id': 'race-already-rated'})

    assert response.status_code == 200
    assert response.json()['applied'] is False
    assert response.json()['ratings'] == {'a': 1016.0, 'b': 984.0}


def test_ranked_rate_rejects_unverified_server_result():
    app.state.race_results = FakeRankedRatingRepository(
        error='ranked rating requires verified results',
    )

    response = client.post('/v1/ranked/rate', json={'race_id': 'race-provisional'})

    assert response.status_code == 422
    assert 'verified results' in response.json()['detail']


def test_ranked_rate_rejects_all_client_rating_and_result_overrides():
    app.state.race_results = FakeRankedRatingRepository()

    response = client.post('/v1/ranked/rate', json={
        'race_id': 'race-review',
        'players': [
            {'user_id': 'a', 'rating': 999999},
            {'user_id': 'b', 'rating': 1},
        ],
        'results': [
            {'user_id': 'a', 'place': 1, 'verification_status': 'verified'},
            {'user_id': 'b', 'place': 2, 'verification_status': 'verified'},
        ],
        'k_factor': 999,
    })

    assert response.status_code == 422


def test_production_app_registers_realtime_race_routes():
    assert str(app.url_path_for('create_race')) == '/v1/races'
    assert str(app.url_path_for('get_race', race_id='race-1')) == '/v1/races/race-1'
    assert str(
        app.url_path_for('race_websocket', race_id='race-1', player_id='player-1')
    ) == '/v1/races/race-1/ws/player-1'
