import claude_mnemos


def test_package_imports():
    assert claude_mnemos.__version__ == "0.0.1"


def test_subpackages_import():
    import claude_mnemos.core  # noqa: F401
    import claude_mnemos.ingest  # noqa: F401
    import claude_mnemos.state  # noqa: F401
    import claude_mnemos.wiki  # noqa: F401
