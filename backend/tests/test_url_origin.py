"""Unit tests for app.tools.url_origin — pure parsing, no network or DNS.

The rule this encodes: a local server standing in for a deployed site is
the substitution verification's URL override exists to allow, and anything
else that changes what's rendered is not.
"""

from app.tools.url_origin import is_local, same_page


def test_a_local_server_stands_in_for_the_deployed_site() -> None:
    """The whole point of the override — patches land in a local checkout,
    so the deployed page can't show them until it's rebuilt."""
    assert same_page(
        "https://studio.example.org/workshops/spring-term/",
        "http://localhost:8080/workshops/spring-term/",
    )


def test_a_local_server_need_not_reproduce_the_deployments_path() -> None:
    """The real shape of this: GitHub Pages serves the site under a path
    prefix that `python3 -m http.server` in the project folder serves at
    the root. Comparing paths here rejects the only case the override is
    ever used for — caught by checking the rule against real rows."""
    assert same_page("https://studio.example.org/workshops/spring-term/", "http://localhost:8080/")


def test_a_different_deployed_host_is_a_different_page() -> None:
    """This is the bug: comparing two sites reports their differences as
    damage the patch did."""
    assert not same_page("https://studio.example.org/a/", "https://example.com/a/")


def test_a_different_path_on_the_same_host_is_a_different_page() -> None:
    assert not same_page("https://example.com/pricing", "https://example.com/about")


def test_a_trailing_slash_is_the_same_page() -> None:
    assert same_page("https://example.com/a", "https://example.com/a/")


def test_an_empty_path_and_the_root_are_the_same_page() -> None:
    assert same_page("https://example.com", "https://example.com/")


def test_a_port_change_on_the_same_host_is_the_same_page() -> None:
    """A dev server for the same files on another port is not a different
    target."""
    assert same_page("http://localhost:8080/a/", "http://localhost:4321/a/")


def test_query_and_fragment_are_not_a_different_target() -> None:
    """Routing within a page. Treating these as different would block
    ordinary re-verifying."""
    assert same_page("https://example.com/a?v=1", "https://example.com/a#top")


def test_re_verifying_the_same_url_is_always_allowed() -> None:
    url = "https://studio.example.org/workshops/spring-term/"
    assert same_page(url, url)


def test_local_hosts_are_recognized_by_name_and_address() -> None:
    assert is_local("http://localhost:8080/")
    assert is_local("http://127.0.0.1:8080/")
    assert not is_local("https://studio.example.org/")
