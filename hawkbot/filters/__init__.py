try:
    import git
    import git.exc

    try:
        repo = git.Repo(search_parent_directories=True)
        repo_version = repo.git.describe(
            tags=True,
            first_parent=True,
            match="v[0-9]*",
            always=True,
            long=True,
        )
        branch_name = repo.active_branch.name
        __version__ = f"{repo_version} ({branch_name})"
        del repo
        del repo_version
        del branch_name
    except:
        __version__ = "UNKNOWN"
except ImportError:
    __version__ = "UNKNOWN"
