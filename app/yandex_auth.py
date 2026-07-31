"""Helper script to obtain a Yandex Music OAuth token via device auth."""
import asyncio

from yandex_music import ClientAsync
from yandex_music.device_auth.device_code import DeviceCode


async def main() -> None:
    def on_code(code: DeviceCode) -> None:
        print(f'Откройте {code.verification_url} и введите код: {code.user_code}')

    client = ClientAsync()
    token = await client.device_auth(on_code=on_code)

    # Сохраните токен, чтобы не проходить авторизацию заново.
    print(f'access_token:  {token.access_token}')
    print(f'refresh_token: {token.refresh_token}')
    print(f'expires_in:    {token.expires_in}')

    await client.init()
    print(client.me.account.login)

if __name__ == '__main__':
    asyncio.run(main())
