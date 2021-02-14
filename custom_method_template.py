#!/usr/bin/env python3
import sys


sys.path.append('/home/username/Projects/python_file_operations/')
sys.path.append('/home/username/Projects/python_file_operations/env/lib/python3.8/site-packages')
from utils.video_operations import make_movie as method


# this works when this file and 'python_nautilus_helper' is placed in the directory where nautilus expects
# the scripts to be. ('.local/share/nautilus/scrips').
from python_nautilus_helper import launch_entry_window


launch_entry_window(method=method)
