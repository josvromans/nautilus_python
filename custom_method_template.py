#!/usr/bin/env python3
import sys

"""
Only change the 3 lines directly below (the 2nd line is optional).
First, add the directory path to the project where your python method lives, so it can be imported.
Second, add the site-packages path. This is only needed if the method depends on packages that are not in 
    the standard Python library
Then import the method 'as method'. If the path was correct, and your method can be imported, it will be
used to display an EntryWindow where the user can set the parameters and call the method. This will work from
nautilus, when you have one or more files selected and then right click and choose 'scritps'.

Change the name of this python file to a name that you want to see in the nautilus menu. It wll be visible
under scripts --> my_python_method.py. (if this files is in '.local/share/nautilus/scrips', you can also 
add another directory to group methods, like scripts --> image_operations --> resize_image.py).

This file has to be made executable, otherwise nautilus will not make it available in the menu.

$ chmod +x my_python_method.py

"""
sys.path.append('/home/username/Projects/python_file_operations/')
sys.path.append('/home/username/Projects/python_file_operations/env/lib/python3.8/site-packages')
from utils.video_operations import make_movie as method


# this works when this file and 'python_nautilus_helper' is placed in the directory where nautilus expects
# the scripts to be. '.local/share/nautilus/scrips'. Nautilus will append it to the path.
from python_nautilus_helper import launch_entry_window


launch_entry_window(method=method)
