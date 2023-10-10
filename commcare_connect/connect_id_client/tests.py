from .main import fetch_users


def test_fetch_users(httpx_mock):
    httpx_mock.add_response(
        json={
            "found_users": [
                {
                    "username": "user_name1",
                    "name": "name1",
                    "phone_number": "phone_number1",
                },
                {
                    "name": "name2",
                    "username": "user_name2",
                    "phone_number": "phone_number2",
                },
            ]
        }
    )

    users = fetch_users(["phone_number1", "phone_number2"])
    assert len(users) == 2
    assert users[0].name == "name1"
    assert users[1].name == "name2"
