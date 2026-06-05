"""Top-level orchestration: stage → generate → compile."""

from __future__ import annotations

from pathlib import Path

from engine.project import Project

from .compile import compile_check
from .generate import run_generators
from .stage import stage_project
from .types import GeneratedFile, GenerateResult


def generate_and_compile(
    project: Project,
    workdir: Path,
    *,
    source_dir: Path | None = None,
) -> GenerateResult:
    """Stage the project into `workdir`, run upstream generators,
    then gcc-syntax-check every generated `.c`.

    `workdir` should be empty or fresh. The caller owns its lifecycle.
    """
    workdir = Path(workdir)
    stage_project(project, workdir, source_dir=source_dir)
    written = run_generators(workdir)

    files: list[GeneratedFile] = []
    for path in written:
        files.append(
            GeneratedFile(
                path=str(path.relative_to(workdir)),
                module=_infer_module(path),
                size_bytes=path.stat().st_size,
            )
        )

    c_files = [p for p in written if p.suffix == ".c"]
    compile_result = compile_check(workdir, c_files)

    return GenerateResult(files=files, compile_result=compile_result)


def _infer_module(generated: Path) -> str:
    """Derive the producing module from the file name (Com_Cfg.* → Com)."""
    name = generated.stem
    for suffix in ("_Cfg", "_PBcfg"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
