import httpx

from job_radar import __version__

USER_AGENT = f"job-radar/{__version__} (+https://github.com/paulocerqr/job-radar)"


def novo_cliente() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
