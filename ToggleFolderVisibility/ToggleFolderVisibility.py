"""
ToggleFolderVisibility.py

Purpose:
    Fusion 360 add-in that toggles the visibility (light bulb) of the
    "Bodies" folder and the "Sketches" folder for the active component,
    matching a click on the folder's own eyeball icon in the browser tree.

    This does NOT touch the visibility of individual bodies/sketches, so
    any bodies or sketches you've manually hidden/shown stay exactly as
    they were once the folder is toggled back on.

Pre-requisites:
    - Autodesk Fusion 360 (desktop). Tested against Fusion API as of
      Fusion 2026.8.
    - No third-party Python libraries required, only the built-in
      adsk.core / adsk.fusion modules provided by Fusion.

Installation:
    1. Copy this whole "ToggleFolderVisibility" folder (the .py file, the
       .manifest file, and the "resources" subfolder with the button icons)
       into your Fusion "AddIns" folder:
         Windows: %appdata%\Autodesk\Autodesk Fusion 360\API\AddIns
         macOS:   ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns
    2. In Fusion: Utilities tab > Add-Ins > Scripts and Add-Ins > Add-Ins
       tab > select "ToggleFolderVisibility" > Run (tick "Run on Startup"
       if you want it to load automatically).
    3. Two buttons are added to Solid tab > Modify panel:
         "Toggle Bodies Folder" and "Toggle Sketches Folder"
    4. To assign a hot key: find the button on the Modify panel, hover over
       it so the "..." (three dots) appears in the corner, click it, then
       "Change Keyboard Shortcut". (Fusion's API cannot silently bind a
       global hot key - the user must assign it once via this standard
       Fusion UI. It's also reachable from Tools tab > Keyboard Shortcuts,
       searching by the command name above.)

Source:
    Component.isBodiesFolderLightBulbOn / Component.isSketchFolderLightBulbOn
    and Design.activeComponent are documented/used properties of the
    Fusion 360 API - confirmed against Autodesk forum sample code, e.g.:
    https://forums.autodesk.com/t5/fusion-api-and-scripts-forum/how-to-export-step-file-of-each-part-in-assembly/td-p/11781416
    https://forums.autodesk.com/t5/fusion-api-and-scripts/activating-a-component/td-p/10809160
"""

import adsk.core
import adsk.fusion
import traceback
from pathlib import Path

# Keep references to event handlers so they aren't garbage collected.
_handlers = []

_app = None
_ui = None

_CMD_ID_BODIES = 'ToggleBodiesFolderVisibility_cmd'
_CMD_ID_SKETCHES = 'ToggleSketchesFolderVisibility_cmd'

_WORKSPACE_ID = 'FusionSolidEnvironment'
_PANEL_ID = 'SolidModifyPanel'

# Fusion only shows the "..." keyboard-shortcut control on hover for commands
# that have a valid icon resource folder - a text-only button (no icon) is
# never offered a shortcut. Confirmed against community add-in source (e.g.
# https://github.com/lf-/ShortcutItPy: "Commands need to have icons so the
# shortcut option is shown") and an Autodesk forum reply asking "do you set
# the resourceFolder?" when troubleshooting the exact same symptom
# (https://forums.autodesk.com/t5/fusion-api-and-scripts-forum/keyboard-shortcut/td-p/10748104).
_ADDIN_DIR = Path(__file__).resolve().parent
_RESOURCES_DIR = _ADDIN_DIR / 'resources'
_ICON_BODIES = str(_RESOURCES_DIR / 'ToggleBodies')
_ICON_SKETCHES = str(_RESOURCES_DIR / 'ToggleSketches')


def _toggle_bodies_folder():
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        _ui.messageBox('Switch to the Design workspace first.')
        return
    comp = design.activeComponent
    comp.isBodiesFolderLightBulbOn = not comp.isBodiesFolderLightBulbOn


def _toggle_sketches_folder():
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        _ui.messageBox('Switch to the Design workspace first.')
        return
    comp = design.activeComponent
    comp.isSketchFolderLightBulbOn = not comp.isSketchFolderLightBulbOn


class ToggleBodiesExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            _toggle_bodies_folder()
        except:
            _ui.messageBox('Failed to toggle Bodies folder:\n{}'.format(traceback.format_exc()))


class ToggleSketchesExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            _toggle_sketches_folder()
        except:
            _ui.messageBox('Failed to toggle Sketches folder:\n{}'.format(traceback.format_exc()))


class BodiesCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            on_execute = ToggleBodiesExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class SketchesCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            on_execute = ToggleSketchesExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def _panel():
    """Resolves the panel through its owning workspace, matching how Fusion
    builds the ribbon. Going via allToolbarPanels can return a panel that
    Fusion doesn't consistently treat as ribbon-attached, which is what
    stops the Keyboard Shortcuts dialog picking the control up."""
    workspace = _ui.workspaces.itemById(_WORKSPACE_ID)
    if not workspace:
        return None
    return workspace.toolbarPanels.itemById(_PANEL_ID)


def _remove_command(cmd_id):
    """Removes an existing control + command definition for cmd_id, if any.
    Run before re-adding so stale duplicates never linger across repeated
    Add-Ins stop/run cycles - a leftover duplicate is a classic cause of a
    shortcut silently binding to a control that isn't the one on screen."""
    panel = _panel()
    if panel:
        ctrl = panel.controls.itemById(cmd_id)
        if ctrl:
            ctrl.deleteMe()
    cmd_def = _ui.commandDefinitions.itemById(cmd_id)
    if cmd_def:
        cmd_def.deleteMe()


def _add_toggle_command(cmd_id, name, tooltip, icon_path, created_handler_cls):
    _remove_command(cmd_id)

    cmd_def = _ui.commandDefinitions.addButtonDefinition(
        cmd_id, name, tooltip, icon_path
    )

    on_created = created_handler_cls()
    cmd_def.commandCreated.add(on_created)
    _handlers.append(on_created)

    panel = _panel()
    if panel:
        ctrl = panel.controls.addCommand(cmd_def)
        if ctrl:
            ctrl.isVisible = True
            # Leave the command unpinned so the user's own pin choice sticks
            # instead of being reset on every load.
            ctrl.isPromotedByDefault = False
            ctrl.isPromoted = False


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        _add_toggle_command(
            _CMD_ID_BODIES,
            'Toggle Bodies Folder',
            'Toggles visibility of the active component\'s Bodies folder, '
            'without changing which individual bodies are shown/hidden.',
            _ICON_BODIES,
            BodiesCommandCreatedHandler,
        )

        _add_toggle_command(
            _CMD_ID_SKETCHES,
            'Toggle Sketches Folder',
            'Toggles visibility of the active component\'s Sketches folder, '
            'without changing which individual sketches are shown/hidden.',
            _ICON_SKETCHES,
            SketchesCommandCreatedHandler,
        )

    except:
        if _ui:
            _ui.messageBox('Failed to start add-in:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        _remove_command(_CMD_ID_BODIES)
        _remove_command(_CMD_ID_SKETCHES)
        _handlers.clear()
    except:
        if _ui:
            _ui.messageBox('Failed to stop add-in:\n{}'.format(traceback.format_exc()))
