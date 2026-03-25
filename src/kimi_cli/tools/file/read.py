import difflib
import hashlib
import json
from pathlib import Path
from typing import override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.file.utils import MEDIA_SNIFF_BYTES, detect_file_type
from kimi_cli.tools.utils import load_desc, truncate_line
from kimi_cli.utils.path import is_within_directory

MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10  # 100KB

# Files larger than this won't be cached for diff (to avoid memory bloat)
_MAX_CACHEABLE_BYTES = 200 << 10  # 200KB


class Params(BaseModel):
    path: str = Field(
        description=(
            "The path to the file to read. Absolute paths are required when reading files "
            "outside the working directory."
        )
    )
    line_offset: int = Field(
        description=(
            "The line number to start reading from. "
            "By default read from the beginning of the file. "
            "Set this when the file is too large to read at once."
        ),
        default=1,
        ge=1,
    )
    n_lines: int = Field(
        description=(
            "The number of lines to read. "
            f"By default read up to {MAX_LINES} lines, which is the max allowed value. "
            "Set this value when the file is too large to read at once."
        ),
        default=MAX_LINES,
        ge=1,
    )
    json_keys: list[str] | None = Field(
        description=(
            "For JSON files only. When provided, only return these top-level keys "
            "instead of the full file content. This significantly reduces context usage "
            "for large JSON files when you only need specific sections. "
            'Example: json_keys=["characters", "production_styles"] returns only those sections.'
        ),
        default=None,
    )


class _CachedFileView:
    """Cached snapshot of a file's content for diff-based deduplication."""

    __slots__ = ("content_hash", "lines")

    def __init__(self, content_hash: str, lines: list[str]) -> None:
        self.content_hash = content_hash
        self.lines = lines


class ReadFile(CallableTool2[Params]):
    name: str = "ReadFile"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        description = load_desc(
            Path(__file__).parent / "read.md",
            {
                "MAX_LINES": MAX_LINES,
                "MAX_LINE_LENGTH": MAX_LINE_LENGTH,
                "MAX_BYTES": MAX_BYTES,
            },
        )
        super().__init__(description=description)
        self._runtime = runtime
        self._work_dir = runtime.builtin_args.KIMI_WORK_DIR
        # Per-instance cache: canonical_path -> _CachedFileView
        # Shared across calls within the same agent/subagent run.
        self._file_cache: dict[str, _CachedFileView] = {}

    async def _validate_path(self, path: KaosPath) -> ToolError | None:
        """Validate that the path is safe to read."""
        resolved_path = path.canonical()

        if not is_within_directory(resolved_path, self._work_dir) and not path.is_absolute():
            # Outside files can only be read with absolute paths
            return ToolError(
                message=(
                    f"`{path}` is not an absolute path. "
                    "You must provide an absolute path to read a file "
                    "outside the working directory."
                ),
                brief="Invalid path",
            )
        return None

    async def _read_json_keys(
        self, p: KaosPath, display_path: str, keys: list[str]
    ) -> ToolReturnValue:
        """Read a JSON file and return only the requested top-level keys."""
        try:
            raw = await p.read_text(errors="replace")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ToolError(
                message=f"`{display_path}` is not valid JSON: {e}",
                brief="Invalid JSON",
            )

        if not isinstance(data, dict):
            return ToolError(
                message=f"`{display_path}` top-level value is not an object. json_keys only works with JSON objects.",
                brief="Not a JSON object",
            )

        filtered = {k: data[k] for k in keys if k in data}
        missing = [k for k in keys if k not in data]

        output = json.dumps(filtered, ensure_ascii=False, indent=2)
        all_keys = list(data.keys())

        message = (
            f"Returned {len(filtered)} of {len(all_keys)} top-level keys "
            f"from `{display_path}`."
        )
        if missing:
            message += f" Keys not found: {missing}."
        message += f" Available keys: {all_keys}"

        return ToolOk(output=output, message=message)

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        # TODO: checks:
        # - check if the path may contain secrets

        if not params.path:
            return ToolError(
                message="File path cannot be empty.",
                brief="Empty file path",
            )

        try:
            p = KaosPath(params.path).expanduser()
            if err := await self._validate_path(p):
                return err
            p = p.canonical()

            if not await p.exists():
                return ToolError(
                    message=f"`{params.path}` does not exist.",
                    brief="File not found",
                )
            if not await p.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.",
                    brief="Invalid path",
                )

            header = await p.read_bytes(MEDIA_SNIFF_BYTES)
            file_type = detect_file_type(str(p), header=header)
            if file_type.kind in ("image", "video"):
                return ToolError(
                    message=(
                        f"`{params.path}` is a {file_type.kind} file. "
                        "Use other appropriate tools to read image or video files."
                    ),
                    brief="Unsupported file type",
                )

            if file_type.kind == "unknown":
                return ToolError(
                    message=(
                        f"`{params.path}` seems not readable. "
                        "You may need to read it with proper shell commands, Python tools "
                        "or MCP tools if available. "
                        "If you read/operate it with Python, you MUST ensure that any "
                        "third-party packages are installed in a virtual environment (venv)."
                    ),
                    brief="File not readable",
                )

            # --- JSON section extraction (when json_keys is provided) ---
            if params.json_keys is not None:
                return await self._read_json_keys(p, params.path, params.json_keys)

            assert params.line_offset >= 1
            assert params.n_lines >= 1

            lines: list[str] = []
            n_bytes = 0
            truncated_line_numbers: list[int] = []
            max_lines_reached = False
            max_bytes_reached = False
            current_line_no = 0
            async for line in p.read_lines(errors="replace"):
                current_line_no += 1
                if current_line_no < params.line_offset:
                    continue
                truncated = truncate_line(line, MAX_LINE_LENGTH)
                if truncated != line:
                    truncated_line_numbers.append(current_line_no)
                lines.append(truncated)
                n_bytes += len(truncated.encode("utf-8"))
                if len(lines) >= params.n_lines:
                    break
                if len(lines) >= MAX_LINES:
                    max_lines_reached = True
                    break
                if n_bytes >= MAX_BYTES:
                    max_bytes_reached = True
                    break

            # Determine if this was a full-file read (started from line 1, reached EOF)
            is_full_read = (
                params.line_offset == 1
                and not max_lines_reached
                and not max_bytes_reached
            )

            # --- Diff-based dedup for full-file reads ---
            canonical = str(p)
            if is_full_read and n_bytes <= _MAX_CACHEABLE_BYTES:
                content_hash = hashlib.md5(
                    "".join(lines).encode("utf-8"), usedforsecurity=False
                ).hexdigest()

                cached = self._file_cache.get(canonical)
                if cached is not None:
                    if cached.content_hash == content_hash:
                        # File unchanged since last read
                        return ToolOk(
                            output="",
                            message=(
                                f"File `{params.path}` ({len(lines)} lines) is unchanged "
                                f"since your last read. Use the content already in your context."
                            ),
                        )
                    else:
                        # File changed — return unified diff
                        diff_lines = list(difflib.unified_diff(
                            cached.lines,
                            lines,
                            fromfile=f"{params.path} (previous read)",
                            tofile=f"{params.path} (current)",
                            lineterm="",
                        ))
                        # Update cache
                        self._file_cache[canonical] = _CachedFileView(content_hash, list(lines))

                        diff_output = "\n".join(diff_lines)
                        diff_bytes = len(diff_output.encode("utf-8"))

                        # If diff is small enough relative to full content, return diff
                        if diff_bytes < n_bytes * 0.7:
                            return ToolOk(
                                output=diff_output,
                                message=(
                                    f"File changed since last read. "
                                    f"Returning diff ({diff_bytes} bytes) instead of "
                                    f"full content ({n_bytes} bytes). "
                                    f"Apply this diff to your previous knowledge of the file."
                                ),
                            )
                        # else: diff is too large (massive rewrite), fall through to full content

                # First full read or diff too large — cache and return full content
                self._file_cache[canonical] = _CachedFileView(content_hash, list(lines))

            # --- Standard full-content return ---

            # Format output with line numbers like `cat -n`
            lines_with_no: list[str] = []
            for line_num, line in zip(
                range(params.line_offset, params.line_offset + len(lines)), lines, strict=True
            ):
                # Use 6-digit line number width, right-aligned, with tab separator
                lines_with_no.append(f"{line_num:6d}\t{line}")

            message = (
                f"{len(lines)} lines read from file starting from line {params.line_offset}."
                if len(lines) > 0
                else "No lines read from file."
            )
            if max_lines_reached:
                message += f" Max {MAX_LINES} lines reached."
            elif max_bytes_reached:
                message += f" Max {MAX_BYTES} bytes reached."
            elif len(lines) < params.n_lines:
                message += " End of file reached."
            if truncated_line_numbers:
                message += f" Lines {truncated_line_numbers} were truncated."
            return ToolOk(
                output="".join(lines_with_no),  # lines already contain \n, just join them
                message=message,
            )
        except Exception as e:
            return ToolError(
                message=f"Failed to read {params.path}. Error: {e}",
                brief="Failed to read file",
            )
