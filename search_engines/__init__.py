from search_engines.github_search import search_github, fetch_readme, fetch_repo_info
from search_engines.huggingface_search import search_huggingface
from search_engines.pypi_search import search_pypi
from search_engines.npm_search import search_npm
from search_engines.docker_search import search_docker
from search_engines.platform_base import search_ddg, smart_deduplicate, prefilter_results

__all__ = [
    "search_github", "fetch_readme", "fetch_repo_info",
    "search_huggingface", "search_pypi", "search_npm",
    "search_docker", "search_ddg",
    "smart_deduplicate", "prefilter_results",
]
