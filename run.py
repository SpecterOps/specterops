import argparse
import json
import os

from lib.builder import ReadMeBuilder
from lib.extractor import DataExtractor
from lib.loader import load_config

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, help="The action you want to run: fetch, build, update, all")
    parser.add_argument("-t", "--token", help="GitHub Personal Access Token")
    args = parser.parse_args()

    script_path = os.path.realpath(".")
    config_path = os.path.join(script_path, "config", "config.yml")

    cfg = load_config(config_path)
    output_path = os.path.join(script_path, "output", cfg["github"]["output"])

    command = args.command
    if command in ["fetch", "all"]:
        if args.token:
            token = args.token
            extractor = DataExtractor(token=token)
            extractor.fetch()
            extractor.dump_json()
        else:
            print("Please provide a GitHub Personal Access Token with the `-t` flag")
            raise SystemExit

    if command in ["build", "all"]:
        with open(output_path, "r") as f:
            data = json.load(f)

        builder = ReadMeBuilder(data)
        builder.build()

    if command == "update":
        extractor = DataExtractor(local_only=True)
        extractor.update()
        extractor.dump_json()
