"""CLI entrypoint: `python -m app`."""
import argparse
import asyncio
import logging

from app.refresh import main


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run Yandex Music likes backup.')
    parser.add_argument(
        '-u', '--username',
        required=True,
        type=str,
        help='Username of playlist owner',
    )
    parser.add_argument(
        '-x', '--proxy',
        required=False,
        type=str,
        default=None,
        help='Proxy server <example: 127.0.0.1:1080>',
    )
    return parser.parse_args()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s',
    )

    args = _parse_args()
    asyncio.run(main(
        playlist_owner=args.username,
        proxy_server=args.proxy,
    ))
