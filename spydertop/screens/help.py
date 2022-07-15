#
# help.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
The help screen, shown when F1 is pressed
"""

from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout
from asciimatics.exceptions import NextScene
from asciimatics.event import KeyboardEvent

from spydertop.model import AppModel
from spydertop.widgets import FuncLabel
from spydertop.utils import ExtendedParser, add_palette


class HelpFrame(Frame):
    """A class to show the help screen"""

    _model: AppModel

    def __init__(self, screen: Screen, model: AppModel) -> None:
        # pylint: disable=line-too-long
        super().__init__(screen, screen.height, screen.width, reduce_cpu=True)

        single_column = Layout([1])
        self.add_layout(single_column)
        single_column.add_widget(
            FuncLabel(
                lambda: add_palette(
                    """\
${{{label},1}}spydertop 0.1.0 - (C) 2022 Spyderbat
${{{label},1}}Styled after htop.

CPU usage bar: ${{{borders},1}}[${{4,1}}low-priority/${{2}}normal/${{1}}kernel/${{6}}virtualized            ${{{background},1}}used%${{{borders},1}}]
Memory bar:    ${{{borders},1}}[${{2}}used/${{4,1}}buffers/${{5}}shared/${{3}}cache                    ${{{background},1}}used/total${{{borders},1}}]
Swap bar:      ${{{borders},1}}[${{1}}used/${{3}}cache                                   ${{{background},1}}used/total${{{borders},1}}]

Process Status: R: running; S: sleeping; T: traced/stopped; Z: zombie; D: disk sleep, I: idle
""",
                    model,
                ),
                parser=ExtendedParser(),
            )
        )

        double_column = Layout([1, 1])
        self.add_layout(double_column)

        # left side
        double_column.add_widget(
            FuncLabel(
                lambda: add_palette(
                    """\
${{{label},1}}  Arrows:${{{background}}} scroll record list
${{{label},1}}S-Arrows:${{{background}}} scroll faster
${{{label},1}}Home/End:${{{background}}} jump to list top/bottom
${{{label},1}} PgUp/Dn:${{{background}}} jump one page up/down
${{{label},1}}   Enter:${{{background}}} Show full record details
${{{label},1}}       H:${{{background}}} show/hide threads
${{{label},1}}       K:${{{background}}} show/hide kernel threads
${{{label},1}}       I:${{{background}}} toggle sorting direction
${{{label},1}}       p:${{{background}}} Switch to processes tab
${{{label},1}}       f:${{{background}}} Switch to flags tab
${{{label},1}}       s:${{{background}}} Switch to sessions tab
${{{label},1}}       c:${{{background}}} Switch to connections tab
${{{label},1}}       l:${{{background}}} Switch to listening tab\
""",
                    model,
                ),
                parser=ExtendedParser(),
                align="<",
            )
        )

        # right side
        double_column.add_widget(
            FuncLabel(
                lambda: add_palette(
                    """\
${{{label},1}}  F1 h ?:${{{background}}} show this help screen
${{{label},1}}  F2 C S:${{{background}}} show setup screen
${{{label},1}}    F3 /:${{{background}}} search (in all columns)
${{{label},1}}    F4 \\:${{{background}}} filter (by all columns)
${{{label},1}}    F5 t:${{{background}}} toggle tree view
${{{label},1}}  F6 > .:${{{background}}} select a column to sort by
${{{label},1}}      F7:${{{background}}} show time selection menu
${{{label},1}}F9 Space:${{{background}}} play
${{{label},1}} F10 q Q:${{{background}}} quit
${{{label},1}}   + - =:${{{background}}} expand/collapse tree
${{{label},1}}       *:${{{background}}} fully expand/collapse tree
${{{label},1}}     [ ]:${{{background}}} move forward/backward 1 sec
${{{label},1}}     {{ }}:${{{background}}} move forward/backward 1 min\
""",
                    model,
                ),
                parser=ExtendedParser(),
                align="<",
            ),
            column=1,
        )

        single_column2 = Layout([1])
        self.add_layout(single_column2)
        single_column2.add_widget(
            FuncLabel(
                lambda: add_palette(
                    """
Current time is listed in the bottom-right corner. ${{{label},1}}\
Play${{{background},0}} will start time moving based on the play speed setting. \
${{{label},1}}Time${{{background},0}} will switch to a relative time selection menu. \
The custom time input \
allows you to input a time in a similar format to the command line arguments. \
These can have an optional unit at the end. Accepted units are s: seconds, \
m: minutes, h: hours, d: days, y: years. Default is seconds. For example:

Custom: -5.5d    -- 5 and a half days backward

When changing time to a period which has not yet been loaded, the application \
will attempt to load those records from the specified input. This often takes \
a few seconds. In the case that a file was provided for input, all records are \
loaded in the initial load process. If the application moves to a time which is \
unloaded, ${{1,1}}No Data${{{background},0}} will be shown.\
""",
                    model,
                ),
                parser=ExtendedParser(),
                align="^",
            )
        )

        self._model = model
        self.set_theme(model.config["theme"])

        self.fix()

    def update(self, frame_no):
        self.set_theme(self._model.config["theme"])
        return super().update(frame_no)

    def process_event(self, event):
        # on any keyboard event, go back to Main
        if isinstance(event, KeyboardEvent):
            raise NextScene("Main")
