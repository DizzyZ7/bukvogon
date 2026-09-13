from fastapi.testclient import TestClient

from bukvogon.main import app


client = TestClient(app)


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


def test_ranked_rate_contract_returns_new_ratings():
    response = client.post('/v1/ranked/rate', json={
        'players': [
            {'user_id': 'a', 'rating': 1000},
            {'user_id': 'b', 'rating': 1000},
        ],
        'results': [
            {'user_id': 'a', 'place': 1},
            {'user_id': 'b', 'place': 2},
        ],
        'k_factor': 32,
    })

    assert response.status_code == 200
    ratings = response.json()['ratings']
    assert ratings['a'] > 1000
    assert ratings['b'] < 1000
