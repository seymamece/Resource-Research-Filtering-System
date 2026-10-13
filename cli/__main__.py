import sys

from .resource_cli import cli

# Titles are Turkish as often as English. A Windows console or pipe defaults to cp1252,
# which cannot print "ğ" and would stop the command halfway through its output.
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

cli(prog_name="py -m cli")
