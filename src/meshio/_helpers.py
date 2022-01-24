from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike

from ._common import num_nodes_per_cell, warn
from ._exceptions import ReadError, WriteError
from ._files import is_buffer
from ._mesh import CellBlock, Mesh

extension_to_filetypes = {}
reader_map = {}
_writer_map = {}


def register_format(name: str, extensions: list[str], reader, writer_map):
    for ext in extensions:
        if ext not in extension_to_filetypes:
            extension_to_filetypes[ext] = []
        extension_to_filetypes[ext].append(name)

    if reader is not None:
        reader_map[name] = reader
    _writer_map.update(writer_map)


def _filetypes_from_path(path: Path) -> list[str]:
    ext = ""
    out = []
    for suffix in reversed(path.suffixes):
        ext = (suffix + ext).lower()
        try:
            out += extension_to_filetypes[ext]
        except KeyError:
            pass

    if not out:
        raise ReadError(f"Could not deduce file format from path '{path}'.")
    return out


def read(filename, file_format: str | None = None):
    """Reads an unstructured mesh with added data.

    :param filenames: The files/PathLikes to read from.
    :type filenames: str

    :returns mesh{2,3}d: The mesh data.
    """
    if is_buffer(filename, "r"):
        return _read_buffer(filename, file_format)

    return _read_file(Path(filename), file_format)


def _read_buffer(filename, file_format: str | None):
    if file_format is None:
        raise ReadError("File format must be given if buffer is used")
    if file_format == "tetgen":
        raise ReadError(
            "tetgen format is spread across multiple files "
            "and so cannot be read from a buffer"
        )
    if file_format not in reader_map:
        raise ReadError(f"Unknown file format '{file_format}'")

    return reader_map[file_format](filename)


def _read_file(path: Path, file_format: str | None):
    if not path.exists():
        raise ReadError(f"File {path} not found.")

    if file_format:
        file_formats = [file_format]
    else:
        # deduce possible file formats from extension
        file_formats = _filetypes_from_path(path)

    for file_format in file_formats:
        if file_format not in reader_map:
            raise ReadError(f"Unknown file format '{file_format}' of '{path}'.")

        try:
            return reader_map[file_format](str(path))
        except ReadError:
            warn(f"Failed to read {path} as {file_format}")


def write_points_cells(
    filename,
    points: ArrayLike,
    cells: dict[str, ArrayLike] | list[tuple[str, ArrayLike] | CellBlock],
    point_data: dict[str, ArrayLike] | None = None,
    cell_data: dict[str, list[ArrayLike]] | None = None,
    field_data=None,
    point_sets: dict[str, ArrayLike] | None = None,
    cell_sets: dict[str, list[ArrayLike]] | None = None,
    file_format: str | None = None,
    **kwargs,
):
    points = np.asarray(points)
    mesh = Mesh(
        points,
        cells,
        point_data=point_data,
        cell_data=cell_data,
        field_data=field_data,
        point_sets=point_sets,
        cell_sets=cell_sets,
    )
    mesh.write(filename, file_format=file_format, **kwargs)


def write(filename, mesh: Mesh, file_format: str | None = None, **kwargs):
    """Writes mesh together with data to a file.

    :params filename: File to write to.
    :type filename: str

    :params point_data: Named additional point data to write to the file.
    :type point_data: dict
    """
    if is_buffer(filename, "r"):
        if file_format is None:
            raise WriteError("File format must be supplied if `filename` is a buffer")
        if file_format == "tetgen":
            raise WriteError(
                "tetgen format is spread across multiple files, and so cannot be written to a buffer"
            )
    else:
        path = Path(filename)
        if not file_format:
            # deduce possible file formats from extension
            file_formats = _filetypes_from_path(path)
            # just take the first one
            file_format = file_formats[0]

    try:
        writer = _writer_map[file_format]
    except KeyError:
        formats = sorted(list(_writer_map.keys()))
        raise WriteError(f"Unknown format '{file_format}'. Pick one of {formats}")

    # check cells for sanity
    for cell_block in mesh.cells:
        key = cell_block.type
        value = cell_block.data
        if key in num_nodes_per_cell:
            if value.shape[1] != num_nodes_per_cell[key]:
                raise WriteError(
                    f"Unexpected cells array shape {value.shape} for {key} cells."
                )
        else:
            # we allow custom keys <https://github.com/nschloe/meshio/issues/501> and
            # cannot check those
            pass

    # Write
    return writer(filename, mesh, **kwargs)
