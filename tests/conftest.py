import pytest

from localpdf_hub import settings


@pytest.fixture(autouse=True)
def job_folder(tmp_path_factory, monkeypatch):
    # Tests must not write into the user's real cache folder.
    monkeypatch.setattr(settings, "TEMP_DIR", tmp_path_factory.mktemp("jobs"))
