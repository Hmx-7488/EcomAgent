"""M4 integration coverage for the canonical authentication API."""

from __future__ import annotations

import pytest

from .helpers import (
    AUTH_LOGIN_PATH,
    AUTH_ME_PATH,
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_CUSTOMER_SERVICE,
    ROLE_OPERATOR_CONTENT,
    SERVICE_CONVERSATIONS_PATH,
    TEST_PASSWORDS,
    bearer_headers,
    error_detail,
)


@pytest.mark.parametrize(
    "role",
    [ROLE_ADMIN, ROLE_OPERATOR_CONTENT, ROLE_CUSTOMER_SERVICE],
)
def test_canonical_login_and_me_return_each_fixed_role(client, role):
    login = client.post(
        AUTH_LOGIN_PATH,
        json={"username": role, "password": TEST_PASSWORDS[role]},
    )
    assert login.status_code == 200, login.text
    payload = login.json()
    assert payload["user"]["role"] == role

    me = client.get(AUTH_ME_PATH, headers=bearer_headers(payload["access_token"]))
    assert me.status_code == 200, me.text
    assert me.json()["role"] == role


def test_legacy_auth_paths_are_not_the_production_contract(client):
    assert client.post(
        "/auth/login",
        json={"username": ROLE_ADMIN, "password": TEST_PASSWORDS[ROLE_ADMIN]},
    ).status_code == 404
    assert client.get("/auth/me", headers={"Authorization": ""}).status_code == 404


@pytest.mark.parametrize(
    ("path", "method"),
    [
        (AUTH_ME_PATH, "get"),
        (PRODUCTS_PATH, "get"),
        (SERVICE_CONVERSATIONS_PATH, "get"),
    ],
)
def test_backoffice_routes_reject_anonymous_access(client, path, method):
    response = getattr(client, method)(path, headers={"Authorization": ""})
    assert response.status_code == 401
    assert error_detail(response)["code"] == "authentication_required"


def test_real_login_token_enforces_role_routes(client):
    operator_login = client.post(
        AUTH_LOGIN_PATH,
        json={
            "username": ROLE_OPERATOR_CONTENT,
            "password": TEST_PASSWORDS[ROLE_OPERATOR_CONTENT],
        },
    )
    assert operator_login.status_code == 200
    operator_headers = bearer_headers(operator_login.json()["access_token"])
    assert client.get(PRODUCTS_PATH, headers=operator_headers).status_code == 200
    denied = client.get(SERVICE_CONVERSATIONS_PATH, headers=operator_headers)
    assert denied.status_code == 403
    assert error_detail(denied)["code"] == "permission_denied"

    service_login = client.post(
        AUTH_LOGIN_PATH,
        json={
            "username": ROLE_CUSTOMER_SERVICE,
            "password": TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE],
        },
    )
    assert service_login.status_code == 200
    service_headers = bearer_headers(service_login.json()["access_token"])
    assert client.get(SERVICE_CONVERSATIONS_PATH, headers=service_headers).status_code == 200
    denied = client.post(
        PRODUCTS_PATH,
        headers=service_headers,
        json={"name": "forbidden", "category": "Demo", "skus": []},
    )
    assert denied.status_code == 403
    assert error_detail(denied)["code"] == "permission_denied"
