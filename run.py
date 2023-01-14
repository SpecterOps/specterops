import json
import os
import sys

from lib.builder import ReadMeBuilder
from lib.extractor import DataExtractor
from lib.loader import load_config

if __name__ == "__main__":
    script_path = os.path.realpath(".")
    config_path = os.path.join(script_path, "config", "config.yml")

    cfg = load_config(config_path)
    output_path = os.path.join(script_path, "output", cfg["github"]["output"])

    try:
        command = sys.argv[1]
    except IndexError:
        print("Please provide a command: fetch, build, all")
        raise SystemExit

    if command not in ["fetch", "build", "update", "all"]:
        print("Please provide a valid command: fetch, build, update, all")
        raise SystemExit

    if command in ["fetch", "all"]:
        extractor = DataExtractor()
        extractor.fetch()
        extractor.dump_json()

    if command in ["build", "all"]:
        with open(output_path, "r") as f:
            data = json.load(f)

        builder = ReadMeBuilder(data)
        builder.build()

    if command == "update":
        extractor = DataExtractor(skip_tests=True)
        extractor.update()
        extractor.dump_json()
