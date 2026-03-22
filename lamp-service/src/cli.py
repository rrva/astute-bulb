"""CLI for controlling lamps via the Local Lamps REST API."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:8000"


def _get_base_url(args: argparse.Namespace) -> str:
    return args.url or os.environ.get("LAMPS_URL", DEFAULT_URL)


def _request(base_url: str, method: str, path: str, body: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail).get("detail", detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        print(f"Error: {e.code} - {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: could not connect to {base_url} - {e.reason}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print(f"Error: request timed out ({url})", file=sys.stderr)
        sys.exit(1)


def _output(data: dict) -> None:
    print(json.dumps(data, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    _output(_request(_get_base_url(args), "GET", "/lamps"))


def cmd_status(args: argparse.Namespace) -> None:
    _output(_request(_get_base_url(args), "GET", f"/lamps/{args.id}/status"))


def cmd_health(args: argparse.Namespace) -> None:
    _output(_request(_get_base_url(args), "GET", "/health"))


def cmd_on(args: argparse.Namespace) -> None:
    _output(_request(_get_base_url(args), "POST", f"/lamps/{args.id}/on"))


def cmd_off(args: argparse.Namespace) -> None:
    _output(_request(_get_base_url(args), "POST", f"/lamps/{args.id}/off"))


def cmd_brightness(args: argparse.Namespace) -> None:
    _output(
        _request(
            _get_base_url(args), "POST", f"/lamps/{args.id}/brightness", {"brightness": args.level}
        )
    )


def cmd_temperature(args: argparse.Namespace) -> None:
    _output(
        _request(
            _get_base_url(args),
            "POST",
            f"/lamps/{args.id}/temperature",
            {"temperature": args.kelvin},
        )
    )


def cmd_color(args: argparse.Namespace) -> None:
    body: dict = {"red": args.red, "green": args.green, "blue": args.blue}
    if args.brightness is not None:
        body["brightness"] = args.brightness
    _output(_request(_get_base_url(args), "POST", f"/lamps/{args.id}/color", body))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lamps", description="Control lamps via REST API")
    parser.add_argument(
        "--url",
        default=None,
        help=f"Base URL of lamp service (env: LAMPS_URL, default: {DEFAULT_URL})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all lamps and their state")
    sub.add_parser("health", help="Show service health")

    p = sub.add_parser("status", help="Get lamp status")
    p.add_argument("id", help="Lamp ID")

    p = sub.add_parser("on", help="Turn lamp on (solar-matched)")
    p.add_argument("id", help="Lamp ID")

    p = sub.add_parser("off", help="Turn lamp off")
    p.add_argument("id", help="Lamp ID")

    p = sub.add_parser("brightness", help="Set brightness (0-100)")
    p.add_argument("id", help="Lamp ID")
    p.add_argument(
        "level", type=int, choices=range(0, 101), metavar="0-100", help="Brightness percentage"
    )

    p = sub.add_parser("temperature", help="Set color temperature in Kelvin")
    p.add_argument("id", help="Lamp ID")
    p.add_argument("kelvin", type=int, metavar="2000-7000", help="Color temperature in Kelvin")

    p = sub.add_parser("color", help="Set RGB color")
    p.add_argument("id", help="Lamp ID")
    p.add_argument("red", type=int, metavar="0-255", help="Red")
    p.add_argument("green", type=int, metavar="0-255", help="Green")
    p.add_argument("blue", type=int, metavar="0-255", help="Blue")
    p.add_argument(
        "--brightness", type=int, default=None, metavar="0-100", help="Brightness override"
    )

    args = parser.parse_args(argv)
    handlers = {
        "list": cmd_list,
        "health": cmd_health,
        "status": cmd_status,
        "on": cmd_on,
        "off": cmd_off,
        "brightness": cmd_brightness,
        "temperature": cmd_temperature,
        "color": cmd_color,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
