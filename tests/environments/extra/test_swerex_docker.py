import pytest

from tests.conftest import is_linux_container_available
from vera.environments.extra.swerex_docker import SwerexDockerEnvironment


def _is_docker_available():
    """Require the Linux engine needed by the SWE-ReX images."""
    return is_linux_container_available("docker")


@pytest.mark.slow
@pytest.mark.skipif(not _is_docker_available(), reason="Docker not available (swerex requires docker)")
def test_swerex_docker_basic_execution():
    """Test basic command execution in SwerexDockerEnvironment."""
    env = SwerexDockerEnvironment(image="python:3.11")

    result = env.execute({"command": "echo 'hello world'"})

    assert isinstance(result, dict)
    assert "output" in result
    assert "returncode" in result
    assert result["returncode"] == 0
    assert "hello world" in result["output"]


@pytest.mark.slow
@pytest.mark.skipif(not _is_docker_available(), reason="Docker not available (swerex requires docker)")
def test_swerex_docker_command_failure():
    """Test that command failures are properly captured in SwerexDockerEnvironment."""
    env = SwerexDockerEnvironment(image="python:3.11")

    result = env.execute({"command": "exit 1"})

    assert isinstance(result, dict)
    assert "output" in result
    assert "returncode" in result
    assert result["returncode"] == 1
