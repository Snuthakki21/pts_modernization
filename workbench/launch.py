"""One local UI launcher over the existing preflight and single Coordinator."""
import argparse
from pathlib import Path
import sys
import webbrowser

from .domain import ValidationError
from .preflight import check_environment, inspect_workspace


def create_app(root, origin):
    # Dependency checks must also work before FastAPI has been installed.
    from .api import create_app as existing_app
    return existing_app(root, origin)


def start_ui(root, port=8765, open_browser=True):
    """Open the browser after Uvicorn binds, with exactly one existing app/writer."""
    import uvicorn
    url = f'http://127.0.0.1:{port}'
    app = create_app(root, url)

    class ReadyServer(uvicorn.Server):
        browser_attempted = False

        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started and open_browser and not self.browser_attempted:
                self.browser_attempted = True
                try:
                    opened = webbrowser.open(url, new=2)
                except Exception:
                    opened = False
                if not opened:
                    print(f'Open {url} in your browser; automatic browser launch was unavailable.', flush=True)

    try:
        config = uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning')
        print(f'Workbench: {url}\nKeep this window open; Ctrl+C stops the server safely.', flush=True)
        ReadyServer(config).run()
    finally:
        # Includes failed socket binding before the lifespan shutdown hook.
        app.state.coordinator.close()


def _port(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Port must be an integer from 1 to 65535') from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('Port must be an integer from 1 to 65535')
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check local setup and open the existing workbench UI.')
    parser.add_argument('--root', default=str(Path.cwd()))
    parser.add_argument('--port', type=_port, default=8765)
    parser.add_argument('--no-browser', action='store_true', help='Print the local URL without opening a browser')
    parser.add_argument('--check-environment', action='store_true', help='Check the locked interpreter/dependencies only')
    args = parser.parse_args(argv)
    if args.check_environment:
        environment = check_environment()
        for message in environment['problems']:
            print(message)
        return 0 if environment['ready'] else 1
    root = Path(args.root).absolute()
    result = inspect_workspace(root, port=args.port, workstation_defaults=False)
    if result['status'] != 'READY':
        for check in result['checks']:
            if check['status'] == 'BLOCKED':
                print(f"{check['id']}: {check['message']}")
                if check.get('action'):
                    print(check['action'])
        print('Startup stopped. Resolve the checks above, then launch again.')
        return 1
    try:
        start_ui(root, port=args.port, open_browser=not args.no_browser)
    except KeyboardInterrupt:
        print('Workbench stopped.', flush=True)
        return 0
    except (ValidationError, OSError) as exc:
        print(f'Startup stopped: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
