import logging

import click

from godot_wsl_proxy.server import Application


@click.command()
@click.option(
    "-h",
    "--lsp-host",
    "host",
    default="127.0.0.1",
    type=str,
    envvar="GDScript_Host",
)
@click.option(
    "-p",
    "--lsp-port",
    "port",
    default=6005,
    type=int,
    envvar="GDScript_Port",
)
@click.option(
    "-H",
    "--proxy-host",
    "proxy_host",
    default="127.0.0.1",
    type=str,
    envvar="PROXY_HOST",
)
@click.option(
    "-P",
    "--proxy-port",
    "proxy_port",
    default=6004,
    type=int,
    envvar="PROXY_HOST",
)
@click.option(
    "-d",
    "--debug",
    "debug",
    type=bool,
    default=False,
    is_flag=True,
)
def cli(host: str, port: int, proxy_host: str, proxy_port: int, debug: bool) -> None:
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    app = Application(lsp_host=host, lsp_port=port)
    app.serve(host=proxy_host, port=proxy_port)
