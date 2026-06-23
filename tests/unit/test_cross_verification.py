from agent_data.quality.cross_verification import CrossVerifier


def test_candidate_urls_skip_x_navigation_and_auth_links() -> None:
    markdown = """
[](https://x.com/)
[Log in](https://x.com/i/jf/onboarding/web?mode=login)
[Sign up](https://x.com/i/jf/onboarding/web?mode=signup)
[Terms](https://x.com/tos)
[Article](https://x.com/i/article/2068024770029932544)
[Official](https://claude.com/blog/artifacts-in-claude-code)
"""

    urls = CrossVerifier._candidate_urls(
        markdown,
        "https://x.com/example/status/1",
    )

    assert urls == [
        "https://x.com/i/article/2068024770029932544",
        "https://claude.com/blog/artifacts-in-claude-code",
    ]


def test_candidate_urls_skip_media_and_profile_links_before_article() -> None:
    markdown = """
[![avatar](https://pbs.twimg.com/profile_images/1/avatar_normal.jpg)](https://x.com/Author)
[Author](https://x.com/Author)
[@Author](https://x.com/Author)
[![Article cover](https://pbs.twimg.com/media/article.jpg) Article title](https://x.com/i/article/2068024770029932544)
[1:40 PM](https://x.com/Author/status/2068328135611822149)
"""

    urls = CrossVerifier._candidate_urls(
        markdown,
        "https://x.com/Author/status/2068328135611822149",
    )

    assert urls == ["https://x.com/i/article/2068024770029932544"]
