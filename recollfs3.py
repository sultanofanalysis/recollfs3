#!/usr/bin/python3

import fuse  # type: ignore
from dataclasses import dataclass
import os
import sys
import stat
import pathlib
from recoll import recoll  # type: ignore
import urllib
import logging
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from typing import Generator
from pathlib import Path
import errno
import time
import re

# Some file managers (Windows explorer, Caja (Linux) behave like this:
# When the user wants to create a folder and is prompted for the folder
# name, the file manager has already created an empty folder with a
# placeholder name like "New Folder" and renames it afterwards.
# Therefor when performing a recoll query, we check if the query string
# i a placeholder name and return an empty result in such cases without
# doing the recoll query.
PLACEHOLDER_NAMES = {
    "New Folder", "untitled folder",  # English
    "Neuer Ordner", "Unbenannter Ordner",  # German
    # Add others as needed
}

# Utility functions


def NormalizePath(x: str) -> str:
    """Normalize a path and expand ~"""
    return (str(pathlib.PosixPath(x).expanduser()))


def setup_logging(debug: bool = False) -> None:
    """ Set log level"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        stream=sys.stderr
    )


def is_readable_file(path: str) -> bool:
    """ Check if path is a regular file with read permission"""
    p = Path(path)
    return p.is_file() and os.access(p, os.R_OK)


def split_path(path: str) -> tuple[str, str]:
    """Return (dirname, basename) for a path.
    For the root ('/'), dirname is '/' and basename is ''.
    """
    path = path.rstrip('/')
    if path == '':
        return ('/', '')
    dirname, basename = os.path.split(path)
    # os.path.split on '/quantum' returns ('/', 'quantum')
    return dirname, basename


@contextmanager
def silence_fd() -> Generator[None, None, None]:
    """Temporarily redirect stdout (fd 1) and stderr (fd 2) to /dev/null.
    Used to suppress output from noisy library functions.

    Example:
        with silence_fd():
            some_c_extension_function()
            print("This Python print is also suppressed")
    """
    # Open the null device
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    # Save original file descriptors
    original_stdout_fd = os.dup(1)   # duplicate stdout
    original_stderr_fd = os.dup(2)   # duplicate stderr

    try:
        # Redirect stdout and stderr to /dev/null
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)

        # Yield control to the with‑block
        yield

    finally:
        # Restore original file descriptors
        os.dup2(original_stdout_fd, 1)
        os.dup2(original_stderr_fd, 2)

        # Close the duplicates and the null device
        os.close(original_stdout_fd)
        os.close(original_stderr_fd)
        os.close(devnull_fd)

# Representation of recoll hits


@dataclass(frozen=True)
class FileInfo:
    virtual_path: str  # Path inside the mount, e.g., "/quantum/paper.pdf"
    real_path: str    # Actual filesystem path of the document
    # Perhaps we need attributes, file size etc.


class recollclient:
    """
    Recoll interface
      Args:
          confdir: Recoll config directory
"""

    def __init__(self, confdir: str):
        """
        Initialize self
        Args:
          confdir: Recoll config directory
        """
        confdir = NormalizePath(confdir)
        try:
            with silence_fd():
                self.rdb = recoll.connect(confdir=confdir)
        except Exception:
            logging.error("Could not open recoll confdir: %s", confdir)
            exit(1)
        self.rdbquery = self.rdb.query()
        logging.debug("Recoll client created with config dir %s", confdir)

    def query(self, qstring: str) -> dict[str, FileInfo]:
        nres = self.rdbquery.execute(qstring)
        # We omit duplicate basenames, but emit a warning
        hits = dict()
        for i in range(nres):
            doc = self.rdbquery.fetchone()
            path = doc.url[7:]
            if not (is_readable_file(path)):
                logging.warning("Ignoring %s (not a readable file", path)
                continue
            basename = os.path.basename(path)
            if basename in hits:
                # logging.warning("Ignoring duplicate basename %s for %s",
                #                basename, path)
                continue
            # Todo: check if virtualpath is a valid path name.
            hits[basename] = FileInfo(
                virtual_path="/" + qstring + "/" + basename,
                real_path=path)
        return hits


class RecollFS(fuse.Fuse):  # type: ignore[misc]
    def __init__(self):
        super().__init__(dash_s_do='setsingle')
        # Defaults for custom options
        self.confdir = "~/.recoll"
        self.debug_recollfs = False  # our own debug flag
        self.transform_query = False  # workaround for windows, see create_query
        self.subdirs: dict[str, dict[str, FileInfo]] = {}

        # Define custom options
        self.parser.add_option(
            mountopt="confdir",
            default=self.confdir,
            help="Recoll config directory (default: ~/.recoll)"
        )
        self.parser.add_option(
            mountopt="debug_recollfs",  # avoid confusion with fuse -d
            action="store_true",
            default=False,
            help="Enable recollfs3 debug logging"
        )
        self.parser.add_option(
            mountopt="transform_query",
            action="store_true",
            default=False,
            help="Enable workarounds for using recollfs via samba on windows"
        )

    def create_query_dir(self, qstring: str) -> dict[str, FileInfo]:
        """
        Workarounds necessary when accessing a RecollFS folder using a samba
        mount from windows.
        1. When creating  folder from the windows explorer, the explorer 
        immediately creates a folder using a placeholder name and renames
        it when the user enters a folder name.
        Some linux file managers (e.g. caja) show the same behavior.
        Hence placeholder names should not trigger queries, but just
        return an empty query directory.
        2. The explorer does not allow the use of colons and quotation marks
        in folder names. This would prevent the user from searches like
        "author:einstein" or '"bohmian mechanics"' (exact phrase search).
        As a workaround, we let the user search for "author_einstein" and
        "{bohmain mechanics}", and transfrom this into "author:einstein" and
        '"bohmian mechanics"'.
        """
        if qstring in PLACEHOLDER_NAMES or qstring.startswith('.'):
            logging.debug("leaving directory empty for placeholde name %s",
                          qstring)
            return {}
        if self.transform_query:
            qstring = qstring.replace('author_', 'author:')
            qstring = qstring.replace('title_', 'title:')
            qstring = re.sub(r'\{([^{}]*)\}', r'"\1"', qstring)
        return self.rc.query(qstring)

    def finalize_init(self):
        self.confdir = os.path.expanduser(self.confdir)
        # Set up logging based on self.debug_recollfs
        setup_logging(self.debug_recollfs)
        # Initialize Recoll client
        self.rc = recollclient(self.confdir)

    def getattr(self, path):
        dirname, basename = split_path(path)

    # Root directory
        if dirname == '/' and basename == '':
            st = fuse.Stat()
            st.st_mode = stat.S_IFDIR | 0o755
            st.st_nlink = 2 + len(self.subdirs)   # + '.' and '..'
            st.st_uid = os.getuid()
            st.st_gid = os.getgid()
            now = time.time()
            st.st_atime = now
            st.st_mtime = now
            st.st_ctime = now
            return st

        # Subdirectory (query)
        if dirname == '/' and basename in self.subdirs:
            st = fuse.Stat()
            st.st_mode = stat.S_IFDIR | 0o755
            st.st_nlink = 2 + len(self.subdirs[basename])
            st.st_uid = os.getuid()
            st.st_gid = os.getgid()
            now = time.time()
            st.st_atime = now
            st.st_mtime = now
            st.st_ctime = now
            return st

        # File inside a subdirectory
        dirname = dirname.lstrip("/")
        if dirname in self.subdirs:
            files = self.subdirs[dirname]
            if basename in files:
                real_path = files[basename].real_path
                try:
                    # Get real file stats
                    stat_res = os.lstat(real_path)
                    st = fuse.Stat()
                    # Copy relevant attributes
                    for attr in ('st_mode', 'st_ino', 'st_dev', 'st_nlink',
                                 'st_uid', 'st_gid', 'st_size', 'st_atime',
                                 'st_mtime', 'st_ctime'):
                        setattr(st, attr, getattr(stat_res, attr))
                    # Force read-only
                    st.st_mode &= ~0o222
                    return st
                except FileNotFoundError:
                    logging.warning(f"Real file missing: {real_path}")
                    # Remove stale entry
                    del self.subdirs[dirname][basename]
                    return -errno.ENOENT
# logging.debug("getattr error: %s", path)
        return -errno.ENOENT

    def readdir(self, path, offset):  # Fixme: respect offset
        dirname, basename = split_path(path)

        if dirname == '/' and basename == '':  # root directory
            entries = ['.', '..'] + list(self.subdirs.keys())
        elif dirname == '/' and basename in self.subdirs:  # query directory
            entries = ['.', '..'] + list(self.subdirs[basename].keys())
        else:
            return -errno.ENOENT

        for i in range(offset, len(entries)):
            yield fuse.Direntry(entries[i])

    def mkdir(self, path, mode):
        logging.debug(f"mkdir({path})")
        dirname, basename = split_path(path)

        # Only allow directories directly under the root
        if dirname != '/':
            return -errno.ENOTSUP
        if not basename:
            return -errno.EEXIST   # trying to create root itself
        if basename in self.subdirs:
            return -errno.EEXIST

        if basename in PLACEHOLDER_NAMES:
            fileinfos = {}
        else:
            fileinfos = self.create_query_dir(basename)
        self.subdirs[basename] = fileinfos
        return 0

    def rmdir(self, path):
        logging.debug("rmdir: %s", path)
        dirname, basename = split_path(path)
        if dirname != '/' or basename not in self.subdirs:
            return -errno.ENOENT

        # Would work without this check, not not be POSIX compliant
        if self.subdirs[basename]:
            return -errno.ENOTEMPTY

        del self.subdirs[basename]
        self.Invalidate(path)
        self.Invalidate("/")
        logging.debug(f"Removed query directory '{basename}'")

    def open(self, path, flags):
        """Open a file. Only read-only access is allowed."""
        logging.debug(f"open({path}, {flags})")
        try:
            dirname, basename = split_path(path)
            dirname = dirname.lstrip("/")

            # Check that the path corresponds to a file
            if dirname not in self.subdirs:
                return -errno.ENOENT
            files = self.subdirs[dirname]
            if basename not in files:
                return -errno.ENOENT

            # Only allow read-only access
            if flags & (os.O_WRONLY | os.O_RDWR):
                return -errno.EACCES

            # Success – no file handle needed
            return 0
        except Exception as e:
            logging.exception(f"Unexpected error in open for {path}")
            return -errno.EIO

    def read(self, path, size, offset):
        """Read data from a file."""
        logging.debug(f"read({path}, {size}, {offset})")

        dirname, basename = split_path(path)
        dirname = dirname.lstrip("/")

        if dirname not in self.subdirs:
            return -errno.ENOENT
        files = self.subdirs[dirname]
        if basename not in files:
            return -errno.ENOENT

        real_path = files[basename].real_path

        try:
            # Open the real file and read the requested chunk
            with open(real_path, 'rb') as f:
                f.seek(offset)
                data = f.read(size)
                return data  # bytes object

        except FileNotFoundError:
            logging.warning(f"Real file missing: {real_path}")
            # Optionally remove the stale entry
            del self.subdirs[dirname][basename]
            return -errno.ENOENT
        except PermissionError:
            return -errno.EACCES
        except Exception as e:
            logging.exception(f"Unexpected error in read for {path}")
            return -errno.EIO

    def unlink(self, path):
        """Unlink a file in a search folder."""
        logging.debug("unlink: %s", path)

        dirname, basename = split_path(path)
        dirname = dirname.lstrip("/")

        if dirname not in self.subdirs:
            return -errno.ENOENT
        files = self.subdirs[dirname]
        if basename not in files:
            return -errno.ENOENT

        del files[basename]
        logging.debug(f"Removed '{basename}' from '{dirname}'")

    def rename(self, old: str, new: str) -> int:
        """
        Rename a query folder, also updating its contents with a recoll query
        """
        logging.debug(f"rename({old} -> {new})")
        old_dirname, old_basename = split_path(old)
        new_dirname, new_basename = split_path(new)

        # Only support renaming directories directly under the root
        if old_dirname != '/' or new_dirname != '/':
            return -errno.ENOTSUP
        if not old_basename or not new_basename:
            return -errno.EINVAL
        if old_basename not in self.subdirs:
            return -errno.ENOENT
        if new_basename in self.subdirs:
            return -errno.EEXIST

        if new_basename in PLACEHOLDER_NAMES:
            fileinfos = {}
        else:
            fileinfos = self.create_query_dir(new_basename)
        self.subdirs[new_basename] = fileinfos
        del self.subdirs[old_basename]
        return 0


def main() -> None:
    fuse.fuse_python_api = (0, 2)
    server = RecollFS()
    # Force single-threaded, duplicate -s is harmless.
    forced_args = ["-s"]
    server.parse(sys.argv + forced_args, values=server)
    # Finalize initialization using parsed cusom options
    server.finalize_init()
    # Start the FUSE main loop
    server.main()


if __name__ == '__main__':
    main()
