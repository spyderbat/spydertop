# Spydertop Project Structure

This document is designed to describe the structure of the Spydertop code base and provide a walkthrough for how it functions.

## Execution

Spydertop uses the [Click][click_docs] python CLI library to handle command-line arguments and initialization. When the program is run from the terminal, the first function to be called is `cli` in [`cli.py`](spydertop/cli.py). It creates a `Config` object, which processes the command-line arguments, and calls the `start_screen` function.

`start_screen` creates the TUI with [Asciimatics][asciimatics_docs]. It initializes the `AppModel` object, which contains the central data store for the UI, as well as several `Frames` and a `Screen`. The `Screen.play` function is then called, which starts the main event and render loops. When the screen is resized, a `ResizeScreenError` is raised by Asciimatics, and the screen is restarted using the last scene that was showing before the resize.

The first scene to be shown is the `ConfigurationFrame`. This frame handles asking the user for the details necessary to call the API. If these details are already available through CLI args or because input is coming from a file, the frame will trigger the `AppModel` to begin preparing records and immediately move to the `LoadingFrame`.

The `LoadingFrame` is a simple progress bar that displays when the `AppModel` is loading records to be displayed. This is triggered at startup, after configuration, and any time the application needs to load more records, such as if the user moved forward in time. During this time, the model will read records from disk or fetch them from the Spyderbat API, then process those records to make displaying them faster. See the [`AppModel`](#AppModel) section for more information on how the model works.

After the model loads, the `LoadingFrame` will trigger the `MainFrame`. The `MainFrame` is the core display for Spydertop, and closely imitates [`htop`][htop_github] in its design. It displays the records stored in the model using the `Table` widget, provides key binds and buttons for user interaction, and triggers popup modals and other scenes when a new menu is needed.

When the user decides to quit the application, the `MainFrame` triggers the `QuitFrame`. If the user has already submitted feedback, or if the application is being run in a container, this frame will immediately exit. Otherwise, it will present a simple feedback form to the user before quitting. 

When the `Screen.play` function exits, one of the frames has raised a `StopApplication` exception signaling Asciimatics to exit the main event loop. The `start_screen` function then performs some clean up and exits.

### An overview of an Asciimatics TUI

Spydertop uses [Asciimatics][asciimatics_docs] for the UI, and that dictates the structure for most of the program. Asciimatics uses a Model-View structure for user interfaces, meaning that the `AppModel` type contains the central data store and logic for the program, while the screen and its children handle presenting that data to the user. This design means that the view components are often thrown away and recreated as the user moves around the UI or the screen resizes. More details can be found in the [Asciimatics documentation][model_view_docs]. While this is a simple design, it does come with some challenges. For certain applications, such as the `Table` widget, this can cause significant lag when triggering certain updates with large sets of data.

The view component hierarchy is structured like this:

```
Screen
└─Scene
  └─Frame
    └─Layout
      └─Widget
```

The way Spydertop is set up, each frame imported in [`screens/__init__.py`](spydertop/screens/__init__.py) is a separate full-screen view. Some frames will spawn pop-up frames in the same scene. Each frame contains one or more `Layout`s, which are analogous to rows in the UI and are responsible for arranging `Widgets` in columns. Each `Widget` is a separate UI component which takes up a block of space and is responsible for drawing itself to the screen. See [Layouts in more detail][layout_docs].

#### The Asciimatics Control Flow

While the `Screen` is running, Asciimatics handles all events and update handling. When an update is triggered, due to user input or a regular update interval, the following occurs:

- The current frames' `process_event` functions are called with the event (if there is one)
    - If the event is not handled by the frame, it is passed down to the contained widgets
- The frames' `update` functions are called
    - This recursively calls `update` on the contained widgets, and they draw themselves to the screen

If the current frame raises a `NextScene` exception, Asciimatics calls `update` on that scene's frames, and continues the render loop from there. If the frame raises a `StopApplication` exception, then Asciimatics will end the render loop and exit the `Screen.play` function. See [flow of control][control_docs] for more.

#### Styling in Asciimatics

Asciimatics provides parsing objects that allow for styling terminal output. There are three attributes to a specific style: foreground color, font style, and background color. The fore- and background colors can be from a 16-color palette which is available in nearly every terminal, or a 256-color palette which is only available in terminals which support it. The font style can be bold, normal, underline, etc.

While the 16-color palette is more widely supported, these colors are often customized by the terminal application. This means that the colors *could* be anything, but generally the colors will be in this order:

- 0: black
- 1: red
- 2: green
- 3: yellow
- 4: blue
- 5: magenta
- 6: cyan
- 7: white
- 8-15: modified (darker/lighter) versions of the first 8, sometimes identical to the first 8

Colors and styles are defined centrally in the theme palette, which is defined in [`utils.py`](spydertop/utils.py). This palette is only directly available to widgets, so most styling functions will use the coloring format directly (i.e. `"${2,1,7}Green bold text with a white background"`).

## Spydertop's Objects

### [Config](spydertop/config.py)

The config object is responsible for the command-line arguments and settings, as well as reading and writing those values to disk. It is initialized with the CLI args, and reads the rest of the required values from disk. The application will go through configuration, and if necessary, trigger the config to write these values (the command-line arguments, usually specific to API calls) to disk in `~/.spyderbat-api/config.yaml`. During the application's main loop, the UI can read and write these configuration values from the `AppModel`, usually as `model.config`. When the application finishes, the `Config` object writes the changed settings values to disk in `~/.spyderbat-api/.spydertop-settings.yaml`.

Note: the goal with these file names is to allow for more that one application to use the configuration in `~/.spyderbat-api/config.yaml` for the Spyderbat API. Spydertop-specific values are stored in the hidden `.spydertop-settings.yaml` more as a cache than as a configurable settings file.

### [AppModel](spydertop/model.py)

The `AppModel` object is the central data store for the program as well as an interface with the Spyderbat API. Because of this, it is somewhat monolithic, and is a good candidate for splitting up into more self-contained chunks.

#### Loading

After the `Config` object is complete, the `AppModel.init` function is called, which calls `AppModel.load_data` in a separate thread. `load_data` reads data in from an input, which is either the Spyderbat API or a file. In either case, a list of JSON-encoded records is received and sent to `AppModel._process_records`. This function parses the JSON objects and sorts them by schema. Most records are stored in a dictionary by their ID in the `_records` attribute, but `event_top` records are stored in the custom `CursorList` data structure. This class sorts the records by time and keeps a pointer to the record closes to the 'cursor' to make it possible to index the records by time instead of ID. The model also builds a tree representation of the processes received, based on the parent ID field.

#### Updating Time

Each time the user moves to a new time, the model calls `_fix_state` to handle any necessary changes. This will update the `CursorList` cursor to the new time, check to see if more records need to be loaded, and update cached values such as the `_meminfo` object and `_time_elapsed`.

To determine if new records need to be fetched, `_fix_state` checks a list of loaded time spans which is updated each time records are loaded. It is possible that a loaded time will have missing data, in which case no new data is loaded but the UI will show "No Data" in fields where the necessary information is missing.

#### Failures

In the case that an unexpected exception occurs or the model is put in a state where it cannot automatically recover, the `fail` function is called with a message for the user. This message is presented to the user in the `FailureFrame`, and they are given a few recovery options. These will call the `AppModel.recover` function, which will attempt to put the model back in a valid state.

In addition to these functions, the model also provides ways to access the loaded data, to cache some data specific to certain frames or widgets, and access to the `Config` object through the `AppModel.config` attribute.

### [MainFrame](spydertop/screens/main.py)

The `MainFrame`, being the most used screen in the application, is also somewhat monolithic. The `Table` widget helps abstract away some of the complexity involved with displaying records, but more can still be done.

The `MainFrame` is responsible for handling user input and deciding how much of the state to update. Because the process list can take a significant amount of time to update, there are various levels of caching and cache updating:

- `needs_screen_refresh`: The child widgets need to redraw.
- `needs_update`: The cached list of displayable data needs to be sent to the `Table` object. Also triggers a screen refresh
- `needs_recalculate`: Data needs to be fetched from the model and columns need to be recalculated for those records. Also triggers an update

#### Updating Columns

When `needs_recalculate` triggers a recalculation of columns, `_build_options` is called. This will get the correct type of records from the model depending on the current tab, then create a set of column data which can be sorted and displayed. The columns are defined by a set of objects in [`columns.py`](spydertop/columns.py) containing metadata for displaying the columns as well as a pair of functions to calculate a sortable value and displayable value for that cell.

### [Table](spydertop/table.py)

The `Table` object is responsible for displaying the records for the current tab in addition to sorting, filtering, and searching those records. It receives the calculated columns from the `MainFrame` and stores, sorts, then filters them. When displaying the records on screen, only the rows shown on the screen are rendered to improve responsiveness.

## Release

Releases are triggered on the creation of a [SemVer][semver] named tag, such as `v1.3.9`. To create a release, create a tag with the version of that release, and monitor the GitHub action to ensure it runs properly.


[click_docs]: https://click.palletsprojects.com/en/8.1.x/
[asciimatics_docs]: https://asciimatics.readthedocs.io/en/stable/
[model_view_docs]: https://asciimatics.readthedocs.io/en/stable/widgets.html#model-view-design
[layout_docs]: https://asciimatics.readthedocs.io/en/stable/widgets.html#layouts-in-more-detail
[control_docs]: https://asciimatics.readthedocs.io/en/stable/widgets.html#flow-of-control
[htop_github]: https://github.com/htop-dev/htop
[semver]: https://semver.org/
