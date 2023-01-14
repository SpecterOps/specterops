import yaml
from lib.logger import logger


def load_config(config_path) -> dict:
    """Load the config.yml file and return the contents as a dictionary."""
    logger.debug("Loading config from: %s", config_path)
    try:
        with open(config_path, "r") as yml_file:
            cfg = yaml.load(yml_file, Loader=yaml.FullLoader)
    except FileNotFoundError:
        raise SystemExit("Config file not found")

    try:
        cfg["github"]
    except KeyError:
        raise SystemExit("GitHub section was not found in config")

    try:
        cfg["github"]["endpoint"]
    except KeyError:
        raise SystemExit("GitHub GraphQL endpoint was not found in config")

    try:
        cfg["github"]["token"]
    except KeyError:
        raise SystemExit("GitHub access token was not found in config")

    try:
        cfg["github"]["timeout"]
    except KeyError:
        logger.warning("GraphQL timeout was not found in config, will use the default value ")

    try:
        cfg["github"]["query_delay"]
    except KeyError:
        logger.warning("GitHub query delay value was not found in config, will use the default value")

    try:
        cfg["github"]["output"]
    except KeyError:
        logger.warning("A value for the output filename was not found in config, will use the default value")

    try:
        projects = cfg["projects"]
        if not projects:
            raise SystemExit("No projects found in config")
    except KeyError:
        raise SystemExit("Projects section not found in config")

    try:
        featured = cfg["featured"]
        if not featured:
            raise SystemExit("No featured projects found in config")
    except KeyError:
        raise SystemExit("Featured section not found in config")

    return cfg
