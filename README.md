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

Searching:
Create a subdirectory inside the mounted folder, e.g. mkdir ~/mysearches/"quantum cryptography".
All matches in your indexed collection of scientific papers will then appear in this folder.
If your paper collection has metadata, you can use these in the folder names, e.g. 
mkdir ~/mysearches/"author:einstein". See the recollq manpage for the format of query strings.
(The original recollfs from https://github.com/pidlug/recollfs created symlinks, with recollfs3.py
the matches appear as ordinary files.

Limitations and future plans:
Currently, only a minimal set of fuse operations is supported:
- Creating subfolders (but no files) in the mounted directory.
- Subfolders are readonly. 

Future plans:
- Implementing deletion of subfolders (i.e. forgetting queries) and files (easy)
- Implementing the creation of files in the mounted subfolder (use case: create a tar.gz from a query folder)

