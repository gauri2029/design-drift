class GitHubNotConfiguredError(Exception):
    """No GitHub App credentials are configured."""


class GitHubAPIError(Exception):
    """GitHub returned an error, or the response couldn't be used."""


class RepositoryNotPermittedError(Exception):
    """The repository exists but Design Drift won't analyze it.

    Distinct from "not found": the caller may legitimately own the repo, and
    the refusal is a policy of ours (see client.assert_analyzable), so the
    message explains rather than pretending the repo isn't there.
    """
