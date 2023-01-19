import json
import os
import sys
from collections import OrderedDict
from time import sleep

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError, TransportServerError
from graphql.error.graphql_error import GraphQLError
from graphql.language.ast import DocumentNode

from lib.loader import load_config
from lib.logger import logger


class DataExtractor:
    """
    Build the README.md file with data fetched from GitHub's GraphQL API.

    **Parameters**

    ``local_only``
        Use the local JSON data and skip the GitHub connection and token tests for faster execution. Useful for
        updating the JSON with changes to featured projects. (default: False)
    """
    script_path = os.path.realpath(".")

    # Values to be loaded from the config YAML
    token = None
    endpoint = None
    client = None
    projects = None
    featured = None
    all_repos = []
    all_profiles = []
    repo_data = {}

    # Default values
    timeout = 10
    query_delay = 5
    output = "repo_data.json"
    output_path = os.path.join(script_path, "output", output)

    # Config YAML's file path
    config_path = os.path.join(script_path, "config", "config.yml")

    # This query fetches the relevant information for each repository
    # It is primarily concerned with general repo information, activity, licensing, the latest release, and languages
    # The query is parameterized to allow for the profile and repository names to be passed in
    # To explore the query, visit https://developer.github.com/v4/explorer/
    repo_info_query = gql(
        """
            query($owner:String!, $name:String!) {
                repository(owner: $owner, name: $name) {
                    name
                    nameWithOwner
                    description
                    url
                    isArchived
                    createdAt
                    pushedAt
                    homepageUrl
                    forkCount
                    openGraphImageUrl
                    stargazerCount
                    isEmpty
                    isFork
                    isInOrganization
                    isMirror
                    isPrivate
                    latestRelease {
                        publishedAt
                        tagName
                        name
                    }
                    licenseInfo {
                        name
                        nickname
                        spdxId
                    }
                    languages(first: 20) {
                        edges {
                            node {
                                name
                            }
                            size
                        }
                        totalCount
                        totalSize
                    }
                    issues(states: OPEN) {
                      totalCount
                    }
                    mentionableUsers(first: 10) {
                      nodes {
                        login
                        name
                        bio
                        company
                      }
                    }
                    owner {
                      login
                      avatarUrl
                    }
                    releases {
                      totalCount
                    }
                }
            }
        """
    )

    # This query tests the access token provided from the config file
    auth_test_query = gql(
        """
            query {
                viewer {
                    login
                }
            }
        """
    )

    def __init__(self, token: str = None, local_only: bool = False) -> None:
        # Load config and store required values
        cfg = load_config(self.config_path)
        self.token = token
        self.endpoint = cfg["github"]["endpoint"]

        # These are optional values that we can ignore if they aren't present
        if "timeout" in cfg["github"]:
            self.timeout = cfg["github"]["timeout"]
        if "query_delay" in cfg["github"]:
            self.query_delay = cfg["github"]["query_delay"]
        if "output" in cfg["github"]:
            self.output = cfg["github"]["output"]
            self.output_path = os.path.join(self.script_path, "output", self.output)

        # Test the GraphQL connection and auth token
        # The test can be skipped if just updating the featured repos from the config
        if not local_only and self.token:
            self.client = self._prepare_gql_client()
            self._test_github()

        self.projects = cfg["projects"]
        self.featured = cfg["featured"]

    def _prepare_gql_client(self) -> Client:
        """Prepare the GraphQL client for use."""
        if self.token and self.endpoint:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"Bearer {self.token}",
            }
            transport = AIOHTTPTransport(url=self.endpoint, timeout=self.timeout, headers=headers)
            return Client(transport=transport, fetch_schema_from_transport=True)
        else:
            raise SystemExit("You must provide a token and have a GitHub endpoint set")

    def _execute_query(self, query: DocumentNode, variable_values: dict) -> dict:
        """
        Execute a GraphQL query against the GitHub GraphQL endpoint.

        **Parameters**

        ``query``
            The GraphQL query to execute
        ``variable_values``
            The parameters to pass to the query
        """
        result = {}
        try:
            result = self.client.execute(query, variable_values=variable_values)
            logger.debug("Successfully executed query with result: %s", result)
        except TimeoutError:
            logger.error("Timeout occurred while trying to connect to GitHub's GraphQL API")
        except TransportQueryError as e:
            logger.error("Error encountered while fetching GraphQL schema: %s", e)
        except TransportServerError as e:
            logger.error("Error encountered while authenticating to GitHub: %s", e)
            sys.exit()
        except GraphQLError as e:
            logger.error("Error with GraphQL query: %s", e)
        return result

    def _test_github(self) -> None:
        """Test the GitHub access token provided in the config file."""
        # GQL exception will be raised if anything goes wrong here
        result = self._execute_query(self.auth_test_query, {})
        logger.info("Successfully authenticated as: %s", result["viewer"]["login"])

    def _determine_featured(self, repo: str) -> None:
        """Determine which projects are featured and set some values."""
        extras = []
        img = None
        project_type = "red"
        featured_flag = False
        for project in self.featured:
            if repo.lower() == project["repo"].lower():
                featured_flag = True
                for key, value in project.items():
                    if key == "type":
                        project_type = value
                    elif key == "img":
                        img = value
                    elif key == "repo":
                        continue
                    else:
                        extras.append([key, value])
                logger.info("Repo `%s` flagged as a featured item", repo)
        self.repo_data[repo]["img"] = img
        self.repo_data[repo]["type"] = project_type
        self.repo_data[repo]["featured"] = featured_flag
        self.repo_data[repo]["extras"] = extras

    def _sort_keys(self) -> None:
        """
        Sort the keys in the `repo_data` dictionary so the featured repositories
        are first in the order they appear in the config.yml file.
        """
        reordered = OrderedDict()
        # self.repo_data = OrderedDict(self.repo_data)
        for repo in self.featured:
            try:
                reordered[repo["repo"]] = self.repo_data.pop(repo["repo"])
            except KeyError:
                logger.warning("Repo `%s` is not a valid repository", repo["repo"])
        for repo in self.repo_data:
            reordered[repo] = self.repo_data[repo]
        self.repo_data = reordered

    def fetch(self) -> None:
        """Fetch the project data from GitHub."""
        for entry in self.projects:
            try:
                profile = entry["profile"]
                if "org" in entry:
                    if entry["org"]:
                        pass
                self.all_profiles.append(profile)
                repos = entry["repos"]
                for repo in repos:
                    name = repo.lower()
                    self.all_repos.append(repo)
                    logger.info("Fetching data for: %s/%s", profile, repo)
                    repo_data = self._execute_query(self.repo_info_query, {"owner": profile, "name": repo})
                    logger.debug("Result: %s", repo_data)
                    if "repository" in repo_data:
                        self.repo_data[name] = repo_data["repository"]
                        self._determine_featured(name)
                    # Be kind to the GraphQL API
                    sleep(5)
            except KeyError:
                logger.error("Entry is missing the `profile` and `repos` values: %s", entry)
                continue
        logger.info("Finished collecting project data!")

    def dump_json(self) -> None:
        """Dump the data to a JSON file."""
        logger.info("Writing project data to %s", self.output_path)
        self._sort_keys()
        with open(self.output_path, "w") as f:
            json.dump(self.repo_data, f, indent=4)

    def update(self) -> None:
        """Update existing project data with changes to the configured featured projects."""
        logger.info("Updating project data with featured projects")
        if os.path.isfile(self.output_path):
            logger.info("Loading existing project data from %s", self.output_path)
            with open(self.output_path, "r") as f:
                self.repo_data = json.load(f)
            for repo in self.repo_data:
                self._determine_featured(repo)
        else:
            logger.warning("No existing data found to update")

    def dump_projects_list(self) -> None:
        """Dump the list of projects to the console."""
        logger.info(self.all_repos)

    def dump_profiles_list(self) -> None:
        """Dump the list of profiles to the console."""
        logger.info(self.all_profiles)
