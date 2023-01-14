import json
import os
import sys
from time import sleep

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError, TransportServerError
from graphql.error.graphql_error import GraphQLError
from graphql.language.ast import DocumentNode

from lib.loader import load_config
from lib.logger import logger


class DataExtractor:
    """Build the README.md file with data fetched from GitHub's GraphQL API."""
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

    def __init__(self, skip_tests: bool = False) -> None:
        # Load config and store required values
        cfg = load_config(self.config_path)
        self.token = cfg["github"]["token"]
        self.endpoint = cfg["github"]["endpoint"]

        # These two are optional values that we can ignore if they aren't present
        if "timeout" in cfg["github"]:
            self.timeout = cfg["github"]["timeout"]
        if "query_delay" in cfg["github"]:
            self.query_delay = cfg["github"]["query_delay"]
        if "output" in cfg["github"]:
            self.output = cfg["github"]["output"]
            self.output_path = os.path.join(self.script_path, "output", self.output)

        # Test the GraphQL connection and auth token
        self.client = self._prepare_gql_client()
        if not skip_tests:
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
            raise SystemExit("Config has not been set")

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
        """Determine which projects are featured."""
        extras = []
        featured_flag = False
        for project in self.featured:
            if repo.lower() == project["repo"].lower():
                featured_flag = True
                for key, value in project.items():
                    if key != "repo":
                        extras.append([key, value])
                logger.info("Repo %s flagged as a featured item", repo)
        self.repo_data[repo]["featured"] = featured_flag
        self.repo_data[repo]["extras"] = extras

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
                    self.all_repos.append(repo)
                    logger.info("Fetching data for: %s/%s", profile, repo)
                    repo_data = self._execute_query(self.repo_info_query, {"owner": profile, "name": repo})
                    logger.debug("Result: %s", repo_data)
                    self.repo_data[repo] = repo_data["repository"]
                    self._determine_featured(repo)
                    # Be kind to the GraphQL API
                    sleep(5)
            except KeyError:
                logger.warning("Entry is missing the `profile` and `repos` values: %s", entry)
                continue
        logger.info("Finished collecting project data!")

    def dump_json(self) -> None:
        """Dump the data to a JSON file."""
        logger.info("Writing project data to %s", self.output_path)
        with open(self.output_path, "w") as f:
            json.dump(self.repo_data, f, indent=4)

    def update(self) -> None:
        """Update existing project data with changes to the configured featured projects."""
        logger.info("Updating project data with featured projects")
        if os.path.isfile(self.output_path):
            with open(self.output_path, "r") as f:
                self.repo_data = json.load(f)
            for repo in self.repo_data:
                self._determine_featured(repo)
        else:
            logger.warning("No existing data found to update")
        with open("update.json", "w") as f:
            json.dump(self.repo_data, f, indent=4)

    def dump_projects_list(self) -> None:
        """Dump the list of projects to the console."""
        logger.info(self.all_repos)

    def dump_profiles_list(self) -> None:
        """Dump the list of profiles to the console."""
        logger.info(self.all_profiles)
