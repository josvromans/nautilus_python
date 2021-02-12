import inspect
import logging
import os
import glob


# do the logging at the script location (most likely .local/share/nautilus/scripts)
nautilus_scripts_dir = os.path.dirname(os.path.realpath(__file__))
logging.basicConfig(
    filename=os.path.join(nautilus_scripts_dir, 'nautilus_scripts.log'),
    level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
except Exception as e:
    logging.error(e)


PATH_PARAMETERS = ['file_path', 'file_paths', 'directory_path', 'directory_paths']


class EntryWindow(Gtk.Window):
    def __init__(self, method):
        """
        Loop through the parameters of the 'method', determine the name, type and default value.
        Add every parameter to a GUI window, with the default value filled in,
        except for the 'path' parameter. The path or paths are selected by the user in Nautilus, and will be handled
        by an environment variable set by Nautilus (in on_submit method).

        This 'path' parameter has to be one of the 'PATH_PARAMETERS' and will be saved as self.method_file_parameter
        The list of input entry attributes (with the parameter name and type) will be saved as self.entries
        """
        Gtk.Window.__init__(self, title=method.__name__)

        self.method = method

        grid = Gtk.Grid(column_homogeneous=True, column_spacing=10, row_spacing=10)
        self.add(grid)

        self.entries = []
        file_parameters = []  # collect them, later check if there is exactly one
        row_index = 0
        for parameter in inspect.signature(method).parameters.values():
            if parameter.name in PATH_PARAMETERS:
                file_parameters.append(parameter.name)
            else:
                parameter_type = parameter.annotation
                if parameter_type is inspect._empty:
                    if parameter.default is inspect._empty:
                        self._quit(error_message="Could not retrieve a type for parameter {}".format(parameter.name))
                    else:
                        parameter_type = type(parameter.default)

                # prevent that the parameter name equals an existing class variable, prepend them with 'entry_'
                param_entry_name = 'entry_{}'.format(parameter.name)
                self.entries.append((parameter.name, param_entry_name, parameter_type))

                if parameter_type is bool:
                    # for booleans, show a checkbutton, only set it to checked if the default value was (exactly) True
                    entry = Gtk.CheckButton()
                    entry.set_active(True if parameter.default is True else False)
                else:
                    # for all other types, show a text entry
                    entry = Gtk.Entry(text=str(parameter.default))
                setattr(self, param_entry_name, entry)

                label = Gtk.Label(label=parameter.name, halign=Gtk.Align.END)
                grid.attach(label, left=0, top=row_index, width=2, height=1)
                grid.attach_next_to(getattr(self, param_entry_name), sibling=label, side=Gtk.PositionType.RIGHT,
                                    width=2, height=1)

                row_index += 1

        if len(file_parameters) != 1:
            self._quit(error_message="The method should have exactly one parameter from {}".format(PATH_PARAMETERS))
            return
        self.method_file_parameter = file_parameters[0]

        cancel_button = Gtk.Button.new_with_mnemonic('cancel')
        cancel_button.connect("clicked", self._quit)
        submit_button = Gtk.Button.new_with_mnemonic(self.method.__name__)
        submit_button.connect("clicked", self.on_submit)

        grid.attach(cancel_button, 0, row_index, 2, 1)
        grid.attach(submit_button, 2, row_index, 2, 1)

    def _call_method(self, kwargs):
        try:
            logging.debug('Running method {} with {}'.format(self.method.__name__, kwargs))
            self.method(**kwargs)
        except Exception as e:
            logging.error(e)

    def _quit(self, error_message=None):
        if error_message is not None:
            logging.error(error_message)

        Gtk.main_quit()

    def on_submit(self, button):
        """
        Collect the values that the user submitted in the input fields (Entry), which could be the default values.
        Convert them to the parameter type that was retrieved earlier by inspecting the method.

        NAUTILUS added a list of the selected file paths to the environment. This list is based on the user input
        and can contain one or more items which can be file_paths and / or directories.
        When file path(s) is/are expected, all  file paths are passed to the method (even if they contain both files
        and directories)
        When directory path(s) is/are expected, (silently) ignore all items that are not a directory.

        The user can always select on ore more paths, but the method could expect either a single path or
        a list of several paths. Determine how to pass the file paths to the the method.

        When the method_file_parameter is
            - a single 'file_path': call the method for every path in the list
            - several 'file_paths': call the method once with the list of file paths
                If exactly one path was provided which is a directory, assume that the user means to apply
                the action on all files in this directory (this rule applies to the two options above, a file_path(s)
                was expected, not a directory_path)

            - a single 'directory_path': call the method for every path directory path in the list.
            - several 'directory_paths': call the method once for the list of directory paths.
        """
        input_values = {}
        for param_name, param_entry_name, param_type in self.entries:
            try:
                if param_type is bool:
                    user_input = getattr(self, param_entry_name).get_active()
                else:
                    user_input = getattr(self, param_entry_name).get_text()
                input_values[param_name] = param_type(user_input)
            except Exception as e:
                self._quit(error_message='Wrong user input {} for the field {}'.format(user_input, param_name))

        # If the file_paths variable is not in the environment, quit and log the error.
        # In case the code is not run via a nautilus menu, it will fail on the line below it, and the user
        # will see the error in his command line
        if 'NAUTILUS_SCRIPT_SELECTED_FILE_PATHS' not in os.environ:
            self._quit(error_message="NAUTILUS_SCRIPT_SELECTED_FILE_PATHS is not in os.environ. "
                                     "Did you run this code via a nautilus menu?")

        # the list of file paths that the user selected in Nautilus
        nautilus_file_paths = os.environ['NAUTILUS_SCRIPT_SELECTED_FILE_PATHS'].splitlines()

        if self.method_file_parameter in ['file_path', 'file_paths']:
            # if one or more file_paths are expected by the method, but the user selected a single directory,
            # assume that the user wants the method to be called for every file in this directory
            if len(nautilus_file_paths) == 1 and os.path.isdir(nautilus_file_paths[0]):
                # '*' could be changed to '*.jpeg' to filter on file format
                nautilus_file_paths = [path for path in glob.glob(os.path.join(nautilus_file_paths[0], '*')) if
                                       os.path.isfile(path)]
        elif self.method_file_parameter in ['directory_path', 'directory_paths']:
            # Only perform the method on directories, silently ignore all paths that are not directories
            nautilus_file_paths = [dir_path for dir_path in nautilus_file_paths if os.path.isdir(dir_path)]

        # When the method expects one single path, but the user selected multiple paths, call the method for every path
        if self.method_file_parameter in ['file_path', 'directory_path']:
            for file_path in nautilus_file_paths:
                input_values[self.method_file_parameter] = file_path
                self._call_method(kwargs=input_values)

        # When the method expects several paths, call the method once with the list of paths
        elif self.method_file_parameter in ['file_paths', 'directory_paths']:
            input_values[self.method_file_parameter] = nautilus_file_paths
            self._call_method(kwargs=input_values)

        else:
            self._quit(error_message='Method parameter {} was not recognised'.format(self.method_file_parameter))

        self._quit()


def launch_entry_window(method):
    win = EntryWindow(method=method)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

