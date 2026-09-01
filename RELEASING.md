# Releasing

Publishing to PyPI is **permanent**. The name `pack-organic-price` is claimed
forever once the first release lands, and a released version can never be
changed or withdrawn — only superseded by a higher one. Read this before the
first upload rather than during it.

## Before the first release

1. **Claim the name on TestPyPI first.** It is a full rehearsal with no
   permanent consequence.
2. **Check what would ship.** `python -m build` then `tar tzf dist/*.tar.gz`.
   Anything in the repo that is not in `.gitignore` can end up in the archive,
   so look for cache directories, `.env` files and API keys.
3. **Decide the version.** `0.1.0` says "this works and the interface may
   still move". That is honest for this package today.

## Steps

```bash
pip install --upgrade build twine
python -m build                       # writes dist/*.whl and dist/*.tar.gz
twine check dist/*                    # catches broken metadata before upload
```

Rehearse on TestPyPI:

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ pack-organic-price
```

Then the real thing:

```bash
twine upload dist/*
```

Tag the commit so the release can be traced back to code:

```bash
git tag -a v0.1.0 -m "0.1.0" && git push --tags
```

## Credentials

Use a PyPI **API token**, not your account password. Create one scoped to this
project at pypi.org/manage/account/token/ and put it in `~/.pypirc`:

```ini
[pypi]
  username = __token__
  password = pypi-...
```

`~/.pypirc` is outside the repository for the same reason the marketplace keys
live in `~/.zshrc`: a credential in a git history is a credential that has to
be rotated.

## Afterwards

Bump `version` in `pyproject.toml` before the next upload. PyPI rejects a
re-upload of a version that already exists, which is the behaviour you want —
it means a version number always refers to exactly one set of bytes.
