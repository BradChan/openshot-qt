"""
 @file
 @brief This file loads the title editor dialog (i.e SVG creator)
 @author Jonathan Thomas <jonathan@openshot.org>
 @author Andy Finch <andy@openshot.org>

 @section LICENSE

 Copyright (c) 2008-2018 OpenShot Studios, LLC
 (http://www.openshotstudios.com). This file is part of
 OpenShot Video Editor (http://www.openshot.org), an open-source project
 dedicated to delivering high quality video editing and animation solutions
 to the world.

 OpenShot Video Editor is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 OpenShot Video Editor is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with OpenShot Library.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
import re
import shutil
import functools
import subprocess
import tempfile

# TODO: Is there a defusedxml substitute for getDOMImplementation?
# Is one even necessary, or is it safe to use xml.dom.minidom for that?
from xml.dom import minidom

from PyQt5.QtCore import Qt, QTimer
from PyQt5 import QtGui
from PyQt5.QtWidgets import (
    QGraphicsScene, QMessageBox, QDialog, QColorDialog, QFontDialog,
    QPushButton, QTextEdit, QLabel
)

import openshot

from classes import info, ui_util, settings
from classes import openshot_rc  # noqa
from classes.logger import log
from classes.app import get_app
from classes.metrics import track_metric_screen
from classes.style_tools import style_to_dict, dict_to_style, set_if_existing

from windows.views.titles_listview import TitlesListView


class TitleEditor(QDialog):
    """ Title Editor Dialog """

    # Path to ui file
    ui_path = os.path.join(info.PATH, 'windows', 'ui', 'title-editor.ui')

    def __init__(self, edit_file_path=None, duplicate=False, *args, **kwargs):

        # Create dialog class
        super().__init__(*args, **kwargs)

        self.app = get_app()
        self.project = self.app.project
        self.edit_file_path = edit_file_path
        self.duplicate = duplicate

        # Get translation object
        _ = self.app._tr

        # Load UI from designer
        ui_util.load_ui(self, self.ui_path)

        # Init UI
        ui_util.init_ui(self)

        # Track metrics
        track_metric_screen("title-screen")

        # Initialize variables
        self.template_name = ""
        imp = minidom.getDOMImplementation()
        self.xmldoc = imp.createDocument(None, "any", None)

        self.bg_color_code = QtGui.QColor(Qt.black)
        self.font_color_code = QtGui.QColor(Qt.white)

        self.bg_style_string = ""
        self.title_style_string = ""
        self.subtitle_style_string = ""

        self.font_weight = 'normal'
        self.font_style = 'normal'
        self.font_size_pixel = 20

        self.new_title_text = ""
        self.sub_title_text = ""
        self.subTitle = False

        self.display_name = ""
        self.font_family = "Bitstream Vera Sans"
        self.tspan_node = None

        self.qfont = QtGui.QFont(self.font_family)

        # Add titles list view
        self.titlesTreeView = TitlesListView(self)
        self.verticalLayout.addWidget(self.titlesTreeView)

        # Disable Save button on window load
        self.buttonBox.button(self.buttonBox.Save).setEnabled(False)

        # If editing existing title svg file
        if self.edit_file_path:
            # Hide list of templates
            self.widget.setVisible(False)

            # Create temp version of title
            self.create_temp_title(self.edit_file_path)

            # Add all widgets for editing
            self.load_svg_template()

            # Display image (slight delay to allow screen to be shown first)
            QTimer.singleShot(50, self.display_svg)

    def txtLine_changed(self, txtWidget):

        # Loop through child widgets (and remove them)
        text_list = []
        for child in self.settingsContainer.children():
            if type(child) == QTextEdit and child.objectName() != "txtFileName":
                text_list.append(child.toPlainText())

        # Update text values in the SVG
        for i in range(0, self.text_fields):
            if len(self.tspan_node[i].childNodes) > 0 and i <= (len(text_list) - 1):
                new_text_node = self.xmldoc.createTextNode(text_list[i])
                old_text_node = self.tspan_node[i].childNodes[0]
                self.tspan_node[i].removeChild(old_text_node)
                # add new text node
                self.tspan_node[i].appendChild(new_text_node)

        # Something changed, so update temp SVG
        self.save_and_reload()

    def display_svg(self):
        # Create a temp file for this thumbnail image
        new_file, tmp_filename = tempfile.mkstemp(suffix=".png")
        os.close(new_file)

        # Create a clip object and get the reader
        clip = openshot.Clip(self.filename)
        reader = clip.Reader()

        # Open reader
        reader.Open()

        # Overwrite temp file with thumbnail image and close readers
        reader.GetFrame(1).Thumbnail(
            tmp_filename,
            self.graphicsView.width(),
            self.graphicsView.height(),
            "", "", "#000", False, "png", 85, 0.0)
        reader.Close()
        clip.Close()

        # Attempt to load saved thumbnail
        svg = QtGui.QPixmap()
        if not svg.load(tmp_filename):
            log.error("Couldn't load title preview from {}".format(tmp_filename))
            return

        # Display temp image
        scene = QGraphicsScene(self)
        view = self.graphicsView
        svg_scaled = svg.scaled(self.graphicsView.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scene.addPixmap(svg_scaled)
        view.setScene(scene)
        view.show()

        # Remove temporary file
        os.unlink(tmp_filename)

    def create_temp_title(self, template_path):

        # Set temp file path
        self.filename = os.path.join(info.USER_PATH, "title", "temp.svg")

        # Copy template to temp file
        shutil.copyfile(template_path, self.filename)

        # return temp path
        return self.filename

    def load_svg_template(self):
        """ Load an SVG title and init all textboxes and controls """

        # Get translation object
        _ = get_app()._tr

        # parse the svg object
        self.xmldoc = minidom.parse(self.filename)
        # get the text elements
        self.tspan_node = self.xmldoc.getElementsByTagName('tspan')
        self.text_fields = len(self.tspan_node)

        # Reset default font
        self.font_family = "Bitstream Vera Sans"
        if self.qfont:
            del self.qfont
        self.qfont = QtGui.QFont(self.font_family)

        # Loop through child widgets (and remove them)
        for child in self.settingsContainer.children():
            try:
                self.settingsContainer.layout().removeWidget(child)
                child.deleteLater()
            except Exception:
                log.debug('Failed to delete child settings widget')

        # Get text nodes and rect nodes
        self.text_node = self.xmldoc.getElementsByTagName('text')
        self.rect_node = self.xmldoc.getElementsByTagName('rect')

        # Create Label
        label = QLabel()
        label_line_text = _("File Name:")
        label.setText(label_line_text)
        label.setToolTip(label_line_text)

        # create text editor for file name
        self.txtFileName = QTextEdit()
        self.txtFileName.setObjectName("txtFileName")

        # If edit mode, set file name
        if self.edit_file_path and not self.duplicate:
            # Use existing name (and prevent editing name)
            self.txtFileName.setText(os.path.basename(self.edit_file_path))
            self.txtFileName.setEnabled(False)
        else:
            name = _("TitleFileName (%d)")
            offset = 0
            if self.duplicate and self.edit_file_path:
                # Re-use current name
                name = os.path.basename(self.edit_file_path)
                # Splits the filename into:
                #  [base-part][optional space][([number])].svg
                # Match groups are:
                #  1: Base name ("title", "Title-2", "Title number 3000")
                #  2: Space(s) preceding groups 3+4, IFF 3/4 are a match
                #  3: The entire parenthesized number ("(1)", "(20)", "(1000)")
                #  4: Just the number inside the parens ("1", "20", "1000")
                match = re.match(r"^(.+?)(\s*)(\(([0-9]*)\))?\.svg$", name)
                # Make sure the new title has " (%d)" appended by default
                name = match.group(1) + " (%d)"
                if match.group(4):
                    # Filename already contained a number -> start counting from there
                    offset = int(match.group(4))
                    # -> only include space(s) if there before
                    name = match.group(1) + match.group(2) + "(%d)"
            # Find an unused file name
            for i in range(1, 1000):
                curname = name % (offset + i)
                possible_path = os.path.join(info.TITLE_PATH, "%s.svg" % curname)
                if not os.path.exists(possible_path):
                    self.txtFileName.setText(curname)
                    break
        self.txtFileName.setFixedHeight(28)
        self.settingsContainer.layout().addRow(label, self.txtFileName)

        # Get text values
        title_text = []
        for i in range(0, self.text_fields):
            if len(self.tspan_node[i].childNodes) > 0:
                text = self.tspan_node[i].childNodes[0].data
                ar = self.tspan_node[i].attributes["style"].value.split(";")
                title_text.append(text)

                # Set font size (for possible font dialog)
                fs = self.find_in_list(ar, "font-size:")
                fs_value = ar[fs][10:]
                if fs_value.endswith("px"):
                    self.qfont.setPixelSize(float(fs_value[:-2]))
                elif fs_value.endswith("pt"):
                    self.qfont.setPointSizeF(float(fs_value[:-2]))

                # Create Label
                label = QLabel()
                label_line_text = _("Line %s:") % str(i + 1)
                label.setText(label_line_text)
                label.setToolTip(label_line_text)

                # create text editor for each text element in title
                widget = QTextEdit()
                widget.setText(_(text))
                widget.setFixedHeight(28)
                widget.textChanged.connect(functools.partial(self.txtLine_changed, widget))
                self.settingsContainer.layout().addRow(label, widget)

        # Add Font button
        label = QLabel()
        label.setText(_("Font:"))
        label.setToolTip(_("Font:"))
        self.btnFont = QPushButton()
        self.btnFont.setText(_("Change Font"))
        self.settingsContainer.layout().addRow(label, self.btnFont)
        self.btnFont.clicked.connect(self.btnFont_clicked)

        # Add Text color button
        label = QLabel()
        label.setText(_("Text:"))
        label.setToolTip(_("Text:"))
        self.btnFontColor = QPushButton()
        self.btnFontColor.setText(_("Text Color"))
        self.settingsContainer.layout().addRow(label, self.btnFontColor)
        self.btnFontColor.clicked.connect(self.btnFontColor_clicked)

        # Add Background color button
        label = QLabel()
        label.setText(_("Background:"))
        label.setToolTip(_("Background:"))
        self.btnBackgroundColor = QPushButton()
        self.btnBackgroundColor.setText(_("Background Color"))
        self.settingsContainer.layout().addRow(label, self.btnBackgroundColor)
        self.btnBackgroundColor.clicked.connect(self.btnBackgroundColor_clicked)

        # Add Advanced Editor button
        label = QLabel()
        label.setText(_("Advanced:"))
        label.setToolTip(_("Advanced:"))
        self.btnAdvanced = QPushButton()
        self.btnAdvanced.setText(_("Use Advanced Editor"))
        self.settingsContainer.layout().addRow(label, self.btnAdvanced)
        self.btnAdvanced.clicked.connect(self.btnAdvanced_clicked)

        # Update color buttons
        self.update_font_color_button()
        self.update_background_color_button()

        # Enable / Disable buttons based on # of text nodes
        if len(title_text) >= 1:
            self.btnFont.setEnabled(True)
            self.btnFontColor.setEnabled(True)
            self.btnBackgroundColor.setEnabled(True)
            self.btnAdvanced.setEnabled(True)
        else:
            self.btnFont.setEnabled(False)
            self.btnFontColor.setEnabled(False)

        # Enable Save button when a template is selected
        self.buttonBox.button(self.buttonBox.Save).setEnabled(True)

    def writeToFile(self, xmldoc):
        '''writes a new svg file containing the user edited data'''

        if not self.filename.endswith("svg"):
            self.filename = self.filename + ".svg"
        try:
            file = open(os.fsencode(self.filename), "wb")  # wb needed for windows support
            file.write(bytes(xmldoc.toxml(), 'UTF-8'))
            file.close()
        except IOError as inst:
            log.error("Error writing SVG title: {}".format(inst))

    def save_and_reload(self):
        """Something changed, so update temp SVG and redisplay"""
        self.writeToFile(self.xmldoc)
        self.display_svg()

    @staticmethod
    def best_contrast(bg: QtGui.QColor) -> QtGui.QColor:
        """Choose text color for best contrast against a background"""
        colrgb = bg.getRgbF()
        # Compute perceptive luminance of background color
        lum = (0.299 * colrgb[0] + 0.587 * colrgb[1] + 0.114 * colrgb[2])
        if (lum < 0.5):
            return QtGui.QColor(Qt.white)
        return QtGui.QColor(Qt.black)

    def btnFontColor_clicked(self):
        app = get_app()
        _ = app._tr

        # Get color from user
        col = QColorDialog.getColor(self.font_color_code, self, _("Select a Color"),
                                    QColorDialog.DontUseNativeDialog | QColorDialog.ShowAlphaChannel)

        # Update SVG colors
        if col.isValid():
            self.set_font_color_elements(col.name(), col.alphaF())
            self.update_font_color_button()

            # Something changed, so update temp SVG
            self.writeToFile(self.xmldoc)

            # Display SVG again
            self.display_svg()

    def btnBackgroundColor_clicked(self):
        app = get_app()
        _ = app._tr

        # Get color from user
        col = QColorDialog.getColor(self.bg_color_code, self, _("Select a Color"),
                                    QColorDialog.DontUseNativeDialog | QColorDialog.ShowAlphaChannel)

        # Update SVG colors
        if col.isValid():
            self.set_bg_style(col.name(), col.alphaF())
            self.update_background_color_button()

            # Something changed, so update temp SVG
            self.writeToFile(self.xmldoc)

            # Display SVG again
            self.display_svg()

    def btnFont_clicked(self):
        app = get_app()
        _ = app._tr

        # Default to previously-selected font
        oldfont = self.qfont

        # Get font from user
        font, ok = QFontDialog.getFont(oldfont, caption=("Change Font"))

        # Update SVG font
        if ok and font is not oldfont:
            self.qfont = font
            fontinfo = QtGui.QFontInfo(font)
            self.font_family = fontinfo.family()
            self.font_style = fontinfo.styleName()
            self.font_weight = fontinfo.weight()
            self.font_size_pixel = fontinfo.pixelSize()
            self.set_font_style()
            self.save_and_reload()

    def find_in_list(self, l, value):
        '''when passed a partial value, function will return the list index'''
        for i, item in enumerate(l):
            if item.startswith(value):
                return i

    def update_font_color_button(self):
        """Updates the color shown on the font color button"""

        # Loop through each TEXT element
        for node in self.text_node + self.tspan_node:

            # Get the value in the style attribute and turn into a dict
            s = node.attributes["style"].value
            ard = style_to_dict(s)
            # Get fill color or default to white
            color = ard.get("fill", "#FFF")
            # Look up color if needed
            # Some colors are located in a different node
            if color.startswith("url(#") and self.xmldoc.getElementsByTagName("defs").length == 1:
                color_ref_id = color[5:-1]
                ref_color = self.get_ref_color(color_ref_id)
                if ref_color:
                    color = ref_color
            # Get opacity or default to opaque
            opacity = float(ard.get("opacity", 1.0))

            color = QtGui.QColor(color)
            text_color = self.best_contrast(color)
            # Set the color of the button, ignoring alpha
            self.btnFontColor.setStyleSheet(
                "background-color: %s; opacity: %s; color: %s;"
                % (color.name(), 1, text_color.name()))
            # Store the opacity as the color's alpha level
            color.setAlphaF(opacity)
            self.font_color_code = color
            log.debug("Set color of font-color button to %s", color.name())

    def get_ref_color(self, id):
        """Get the color value from a reference id (i.e. linearGradient3267)"""
        found_color = ""
        for ref_node in self.xmldoc.getElementsByTagName("defs")[0].childNodes:
            if ref_node.attributes and "id" in ref_node.attributes:
                ref_node_id = ref_node.attributes["id"].value
                if id == ref_node_id:
                    # Found a matching color reference
                    if "xlink:href" in ref_node.attributes:
                        # look up color reference again
                        xlink_ref_id = ref_node.attributes["xlink:href"].value[1:]
                        return self.get_ref_color(xlink_ref_id)
                    if "href" in ref_node.attributes:
                        # look up color reference again
                        xlink_ref_id = ref_node.attributes["href"].value[1:]
                        return self.get_ref_color(xlink_ref_id)
                    elif ref_node.childNodes:
                        for stop_node in ref_node.childNodes:
                            if "stop" == stop_node.nodeName:
                                # get color from stop
                                ar = stop_node.attributes["style"].value.split(";")
                                sc = self.find_in_list(ar, "stop-color:")
                                return ar[sc][11:]
        return found_color

    def update_background_color_button(self):
        """Updates the color shown on the background color button"""

        if self.rect_node:
            # All backgrounds should be the first (index 0) rect tag in the svg
            s = self.rect_node[0].attributes["style"].value
            ard = style_to_dict(s)

            # Get fill color or default to black + full opacity
            color = ard.get("fill", "#000")
            opacity = float(ard.get("opacity", 1.0))

            color = QtGui.QColor(color)
            text_color = self.best_contrast(color)

            # Set the colors of the button, ignoring opacity
            self.btnBackgroundColor.setStyleSheet(
                "background-color: %s; opacity: %s; color: %s;"
                % (color.name(), 1, text_color.name()))

            # Store the opacity as the color's alpha level
            color.setAlphaF(opacity)
            self.bg_color_code = color
            log.debug("Set color of background-color button to %s", color.name())

    def set_font_style(self):
        '''sets the font properties'''
        # Loop through each TEXT element
        for text_child in self.text_node + self.tspan_node:
            # set the style elements for the main text node
            s = text_child.attributes["style"].value
            ard = style_to_dict(s)
            set_if_existing(ard, "font-style", self.font_style)
            set_if_existing(ard, "font-family", self.font_family)
            set_if_existing(ard, "font-size", f"{self.font_size_pixel}px")
            self.title_style_string = dict_to_style(ard)

            # set the text node
            text_child.setAttribute("style", self.title_style_string)
        log.debug("Updated font styles to %s", self.title_style_string)

    def set_bg_style(self, color, alpha):
        '''sets the background color'''

        if self.rect_node:
            # Turn the style attribute into a dict for modification
            s = self.rect_node[0].attributes["style"].value
            ard = style_to_dict(s)
            ard.update({
                "fill": color,
                "opacity": str(alpha),
                })
            # Convert back to a string and update the node in the xml doc
            self.bg_style_string = dict_to_style(ard)
            self.rect_node[0].setAttribute("style", self.bg_style_string)
            log.debug("Updated background style to %s", self.bg_style_string)

    def set_font_color_elements(self, color, alpha):
        # Loop through each TEXT element
        for text_child in self.text_node + self.tspan_node:
            # SET TEXT PROPERTIES
            s = text_child.attributes["style"].value
            ard = style_to_dict(s)
            ard.update({
                "fill": color,
                "opacity": str(alpha),
                })
            text_child.setAttribute("style", dict_to_style(ard))
        log.debug("Set text node style, fill:%s opacity:%s", color, alpha)

    def accept(self):
        app = get_app()
        _ = app._tr

        # If editing file, just update the existing file
        if self.edit_file_path and not self.duplicate:
            # Update filename
            self.filename = self.edit_file_path

            # Overwrite title svg file
            self.writeToFile(self.xmldoc)

        else:
            # Create new title (with unique name)
            file_name = "%s.svg" % self.txtFileName.toPlainText().strip()
            file_path = os.path.join(info.TITLE_PATH, file_name)

            if self.txtFileName.toPlainText().strip():
                # Do we have unsaved changes?
                if os.path.exists(file_path) and not self.edit_file_path:
                    ret = QMessageBox.question(
                        self, _("Title Editor"),
                        _("%s already exists.\nDo you want to replace it?") % file_name,
                        QMessageBox.No | QMessageBox.Yes
                    )
                    if ret == QMessageBox.No:
                        # Do nothing
                        return

                # Update filename
                self.filename = file_path

                # Save title
                self.writeToFile(self.xmldoc)

                # Add file to project
                app.window.files_model.add_files(self.filename)

        # Close window
        super().accept()

    def btnAdvanced_clicked(self):
        _ = self.app._tr
        # use an external editor to edit the image
        try:
            # Get settings
            s = settings.get_settings()

            # get the title editor executable path
            prog = s.get("title_editor")

            # launch advanced title editor
            # debug info
            log.info("Advanced title editor command: {} {} ".format(prog, self.filename))

            p = subprocess.Popen([prog, self.filename])

            # wait for process to finish (so we can update the preview)
            p.communicate()

            # update image preview
            self.load_svg_template()
            self.display_svg()

        except OSError:
            msg = QMessageBox()
            msg.setText(_("Please install %s to use this function" % prog))
            msg.exec_()
