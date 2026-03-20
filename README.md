RecollFS3: Rewrite of https://github.com/pidlug/recollfs in python3. 

*Yet in a rudimentary stage and poorly tested. Use at your own risk.*

In contrast to the original recollfs, recoll hits appear as ordinary file, not symlinks.
I have also give credits to deepseek, which was a great help for understanding the poorly documented fuse-python API.

Installation:
Just put recollfs3.py somewhere in your path (e.g. /usr/local/bin) and make it executable
Prerequisites:
In Debian: recoll, python-recoll and python-fuse packages and a recoll index.


Usage:

1. Mounting the file system
- From the shell, assuming you have an empty folder ~/mysearches:
recollfs3.py ~/mysearches
Check further options with recollfs3.py -h

- using fstab:
recollfs3.py /home/user/mysearches fuse defaults 0 0

2. Searching:
Create a subdirectory ("query folder") inside the mounted folder, e.g. mkdir ~/mysearches/"quantum cryptography".
All matches in your indexed collection of scientific papers will then appear in this folder.
If your paper collection has metadata, you can use these in the folder names, e.g. 
mkdir ~/mysearches/"author:einstein". See the recollq manpage for the format of query strings.
(The original recollfs from https://github.com/pidlug/recollfs created symlinks, with recollfs3.py
the matches appear as ordinary files.

Limitations and future plans:
Currently, only a limited set of fuse operations is supported:
- Creating renaming and deleting query folder (but no files) in the mounted directory.
  If a folder is renamed, also it contents is updated.
- Deleting files in the query folder.

3. Placeholder folder names:
Some file managers (e.g. caja) show this behavior when creating a directory: When the user is prompted for the folder name, the folder has already been create with a placeholder name like 'New Directory' and renamed if the user folder enters a folder name. Therefor Recollfs3 checks if the folder name is a just placeholder and leaves the folder empty (not recoll search). I your file manager uses a different plaeholder name, add it to the list PLACEHOLDER_NAMES at the beginning of recollfs3.py.

3. Future plans:
- Improve usability, if the search folder is mounted via samba to overcome annoyances of the windows explorer. E.g. the windows explorer does not allow folders with colon in the folder name, so searches of the of the form author:name are currently not possible using the windows explorer on a samba share. Also, the windows explorer does not allow quotation marks in the folder name, so search for an exact phrase is not possible. 
- Implementing the creation of files in the mounted subfolder (use case: create a tar.gz from a query folder from the file manager menu.)
