from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError


@database_sync_to_async
def get_user_from_jwt(token_key: str):
    try:
        jwt_auth = JWTAuthentication()
        validated_token = jwt_auth.get_validated_token(token_key)
        return jwt_auth.get_user(validated_token)
    except TokenError:
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        query_string = parse_qs(scope["query_string"].decode())
        token_key = query_string.get("token", [None])[0]
        scope["user"] = await get_user_from_jwt(token_key) if token_key else AnonymousUser()
        return await super().__call__(scope, receive, send)
