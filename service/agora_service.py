import time as time_module
from agora_token_builder import RtcTokenBuilder

from core.config import settings


class AgoraService:

    @staticmethod
    def generate_agora_token(channel_name: str, uid: int):

        expiration_in_seconds = 3600

        current_timestamp = int(time_module.time())

        privilege_expired_ts = current_timestamp + expiration_in_seconds

        token = RtcTokenBuilder.buildTokenWithUid(
            settings.AGORA_APP_ID,
            settings.AGORA_APP_CERTIFICATE,
            channel_name,
            uid,
            1,  # role: publisher
            privilege_expired_ts,
        )

        return token
