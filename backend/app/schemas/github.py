from pydantic import BaseModel, Field


class InstallationLink(BaseModel):
    installation_id: int = Field(gt=0)


class InstallationRead(BaseModel):
    installation_id: int
    account_login: str


class RepositoryRead(BaseModel):
    full_name: str
    private: bool
    default_branch: str
    # False for a private repository while private analysis is deferred, so
    # the picker can show it, disable it, and say why — rather than letting
    # someone select it and meet an error on the next screen.
    analyzable: bool
    reason: str | None = None


class GitHubStatus(BaseModel):
    """Whether the server has a GitHub App at all, and where to install it."""

    configured: bool
    install_url: str | None = None
