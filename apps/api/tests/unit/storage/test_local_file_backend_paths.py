"""
Security tests for the local file storage backend: project ids and filenames
must not be able to escape the storage root (path traversal).
"""
import pytest

from middleware.error_handler import StructuralError
from storage.file_backends.local import LocalFileBackend


@pytest.fixture
def backend(tmp_path):
    return LocalFileBackend(base_dir=tmp_path)


@pytest.mark.parametrize("bad_id", ["../etc", "..", ".", "a/b", "a\\b", "", "with space", "x/../y"])
def test_project_dir_rejects_traversal(backend, bad_id):
    with pytest.raises(StructuralError) as exc:
        backend._project_dir(bad_id)
    assert exc.value.error_code == "INVALID_PATH"


def test_project_dir_accepts_uuid_like_id(backend):
    d = backend._project_dir("3f9a1b2c-0001-4abc-8def-0123456789ab")
    assert d.exists()


@pytest.mark.parametrize("bad_name", ["../secret.txt", "a/b.dxf", "..", ""])
async def test_get_url_rejects_bad_filename(backend, bad_name):
    with pytest.raises(StructuralError) as exc:
        await backend.get_url("proj_1", bad_name)
    assert exc.value.error_code == "INVALID_PATH"


def test_list_and_delete_reject_traversal(backend):
    with pytest.raises(StructuralError):
        backend.list_files("../../etc")
    with pytest.raises(StructuralError):
        backend.delete_project("..")
