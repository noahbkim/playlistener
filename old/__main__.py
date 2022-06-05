import argparse
import json
from pathlib import Path

parent = Path(__file__).absolute().parent.parent

credentials_path = parent.joinpath("credentials.json")
if not credentials_path.exists():
    print("Please populate credentials.json")
    exit(-1)

with credentials_path.open() as file:
    credentials = json.load(file)

parser = argparse.ArgumentParser()
command_parser = parser.add_subparsers(title="command", required=False, dest="command")
command_parser.add_parser("setup")
arguments = parser.parse_args()

if arguments.command is None:
    from playlistener.client import main
    main(credentials)

elif arguments.command == "setup":
    from playlistener.spotify import generate_authentication_url

    print("url:", generate_authentication_url(credentials["spotify"]["id"]))
    code = input("code: ")
    spotify_path = parent.joinpath("spotify.json")
    spotify_path.write_text(json.dumps({"initial_code": code}))
