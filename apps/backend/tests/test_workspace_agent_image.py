"""Exercise imports using only the sources copied into the runtime image."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def test_agent_image_sources_can_import_the_runtime_without_the_backend_checkout(tmp_path):
    repository = Path(__file__).resolve().parents[3]
    dockerfile = repository / "deploy" / "Dockerfile.agent"
    for line in dockerfile.read_text().splitlines():
        if not line.startswith("COPY "):
            continue
        arguments = [part for part in shlex.split(line)[1:] if not part.startswith("--")]
        destination = tmp_path / arguments[-1].removeprefix("./")
        for source_name in arguments[:-1]:
            source = repository / source_name
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__"))
            else:
                target = destination / source.name if arguments[-1].endswith("/") else destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    # Retain installed dependencies for both venv and pip --user runners, while
    # omitting the checkout, pytest's import roots, and arbitrary PYTHONPATH.
    dependencies = [
        path for path in sys.path
        if Path(path).name in {"site-packages", "dist-packages"}
    ]
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys; from pathlib import Path; sys.path.extend(sys.argv[2:]); "
         "sys.path.insert(0, sys.argv[1]); "
         "import workspace_agent.app; import api.workspaces.html_documents as html; "
         "assert Path(workspace_agent.app.__file__).is_relative_to(sys.argv[1]); "
         "assert Path(html.__file__).is_relative_to(sys.argv[1]); "
         "assert workspace_agent.app.app is not None",
         str(tmp_path), *dependencies],
        cwd=tmp_path,
        env={**os.environ, "AWS_EC2_METADATA_DISABLED": "true",
             "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
