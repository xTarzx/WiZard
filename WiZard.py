# region Imports
import asyncio
import json
from pywizlight.bulb import PilotParser
import wx
from wx.lib.intctrl import IntCtrl
from wx.core import LIST_AUTOSIZE_USEHEADER, VERTICAL, TextCtrl
from wxasync import WxAsyncApp, AsyncBind
from asyncio.events import get_event_loop

import wiz_api
from pywizlight import wizlight
from pywizlight.scenes import SCENES, get_id_from_scene_name
# endregion

# region Data Storage
data = {}


def write_settings():
    global data
    with open("bagui", "w") as f:
        json.dump(data, f)


def load_settings():
    global data
    with open("bagui", "r") as f:
        data = json.load(f)


def init_settings():
    try:
        load_settings()
    except FileNotFoundError:
        write_settings()


def update_data(content):
    global data
    data.update(content)
    write_settings()
# endregion

# region Bitmap


def scale_bitmap(bitmap: wx.Bitmap, width, height):
    image = bitmap.ConvertToImage()
    image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
    result = wx.Bitmap(image)
    return result


def getFilledRectBitmap(width, height, colour):
    r, g, b, a = colour.Get(includeAlpha=True)
    bitmap = wx.Bitmap.FromRGBA(width, height, r, g, b, a)
    return bitmap
# endregion


class ListCtrlComboPopup(wx.ComboPopup):
    def __init__(self):
        wx.ComboPopup.__init__(self)
        self.lc = None

    def AddItem(self, txt):
        self.lc.InsertItem(self.lc.GetItemCount(), txt)
        self.lc.SetColumnWidth(0, LIST_AUTOSIZE_USEHEADER)

    def OnMotion(self, evt):
        item, flags = self.lc.HitTest(evt.GetPosition())
        if item >= 0:
            self.lc.Select(item)
            self.curitem = item

    def OnLeftDown(self, evt):
        self.value = self.curitem
        self.Dismiss()

    def Init(self):
        self.value = -1
        self.curitem = -1

    def Create(self, parent):
        self.lc = wx.ListCtrl(parent, style=wx.LC_REPORT |
                              wx.LC_SINGLE_SEL | wx.SIMPLE_BORDER)
        self.lc.InsertColumn(0, "Presets")

        self.lc.Bind(wx.EVT_MOTION, self.OnMotion)
        self.lc.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        return True

    def GetControl(self):
        return self.lc

    def SetStringValue(self, val):
        idx = self.lc.FindItem(-1, val)
        if idx != wx.NOT_FOUND:
            self.lc.Select(idx)

    def GetStringValue(self):
        if self.value >= 0:
            return self.lc.GetItemText(self.value)
        return ""


class ListPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.buttons: list[wx.Button] = []

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        self.refresh_btn = wx.Button(self, label="Refresh")
        AsyncBind(wx.EVT_BUTTON,
                  self.GetTopLevelParent().refresh_bulbs, self.refresh_btn)

        self.sizer.Add(self.refresh_btn, 0, wx.ALL | wx.ALIGN_CENTER)

    def update_bulbs(self, bulbs: list[wizlight]):
        for btn in self.buttons:
            btn.Destroy()

        for idx, bulb in enumerate(bulbs):
            btn = wx.Button(self, label=data[bulb.mac]["name"])
            btn.idx = idx
            self.Bind(wx.EVT_BUTTON, self.open_properties, btn)
            self.sizer.Add(btn, 1, wx.ALL | wx.EXPAND)
            self.buttons.append(btn)

        self.Layout()
        self.set_status("Done")

        self.refresh_btn.Enable()

    def set_status(self, message):
        self.GetTopLevelParent().set_status(message)

    def open_properties(self, e: wx.Event):
        idx = e.GetEventObject().idx
        self.GetTopLevelParent().manage_bulb(idx)


class PropertyPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.main_sizer = wx.BoxSizer()
        self.SetSizer(self.main_sizer)

    def show_properties(self, bulb: wizlight):
        self.bulb = bulb

        self.main_sizer.Clear()
        panel = wx.Panel(self)

        self.property_sizer = wx.FlexGridSizer(cols=2, vgap=5, hgap=5)

        # region Name

        nameLabel = wx.StaticText(panel, label="Name: ")
        name = TextCtrl(
            panel, value=data[bulb.mac]["name"], style=wx.TE_LEFT, size=(150, -1))
        nameApply = wx.Button(panel, label="Apply")
        panel.Bind(wx.EVT_BUTTON, lambda e: self.apply_name(
            bulb, name), nameApply)

        nameSizer = wx.BoxSizer()
        nameSizer.Add(nameLabel, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        nameSizer.Add(name, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        nameSizer.Add(nameApply, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        # endregion

        offBtn = wx.Button(panel, label="OFF")
        AsyncBind(wx.EVT_BUTTON, self.turn_off, offBtn)

        # region Scenes Presets

        scenePreset = wx.ComboCtrl(panel, size=(120, -1), style=wx.CB_READONLY)
        scenePreset.SetCustomPaintWidth(100)
        self.popupControl = ListCtrlComboPopup()

        scenePreset.SetPopupControl(self.popupControl)
        # scenePreset.SetPopupMinWidth(150)

        for s in sorted(list(SCENES.values())):
            self.popupControl.AddItem(s)

        custom_presets = data.get(bulb.mac).get("presets")

        if custom_presets is not None:
            for entry in custom_presets:
                self.popupControl.AddItem(entry)

        scenePresetApply = wx.Button(panel, label="Apply")
        AsyncBind(wx.EVT_BUTTON, self.apply_preset, scenePresetApply)

        scenePresetSizer = wx.BoxSizer()
        scenePresetSizer.Add(scenePreset)
        scenePresetSizer.Add(scenePresetApply)

        # endregion

        # region Color Picker Slider

        slider_panel = wx.Panel(panel, style=wx.RAISED_BORDER)

        # region sliders

        labelR = wx.StaticText(slider_panel, label="R:")
        self.sliderR = wx.Slider(slider_panel, minValue=0, maxValue=255)
        self.sliderR.Bind(wx.EVT_SCROLL, self.on_slider_change)

        self.textR = IntCtrl(slider_panel, size=(50, -1),
                             style=wx.TE_CENTRE | wx.TE_PROCESS_ENTER, min=0, max=255, default_color=wx.WHITE, limited=True)
        self.textR.Bind(wx.EVT_TEXT_ENTER, self.on_slider_text_change)

        R_sizer = wx.BoxSizer()
        R_sizer.Add(labelR, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        R_sizer.Add(self.sliderR, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        R_sizer.Add(self.textR, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        labelG = wx.StaticText(slider_panel, label="G:")
        self.sliderG = wx.Slider(slider_panel, minValue=0, maxValue=255)
        self.sliderG.Bind(wx.EVT_SCROLL, self.on_slider_change)

        self.textG = IntCtrl(slider_panel, size=(50, -1),
                             style=wx.TE_CENTRE | wx.TE_PROCESS_ENTER, min=0, max=255, default_color=wx.WHITE, limited=True)
        self.textG.Bind(wx.EVT_TEXT_ENTER, self.on_slider_text_change)

        G_sizer = wx.BoxSizer()
        G_sizer.Add(labelG, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        G_sizer.Add(self.sliderG, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        G_sizer.Add(self.textG, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        labelB = wx.StaticText(slider_panel, label="B:")
        self.sliderB = wx.Slider(slider_panel, minValue=0, maxValue=255)
        self.sliderB.Bind(wx.EVT_SCROLL, self.on_slider_change)

        self.textB = IntCtrl(slider_panel, size=(50, -1),
                             style=wx.TE_CENTRE | wx.TE_PROCESS_ENTER, min=0, max=255, default_color=wx.WHITE, limited=True)
        self.textB.Bind(wx.EVT_TEXT_ENTER, self.on_slider_text_change)

        B_sizer = wx.BoxSizer()
        B_sizer.Add(labelB, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        B_sizer.Add(self.sliderB, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        B_sizer.Add(self.textB, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        labelBR = wx.StaticText(slider_panel, label="BR:")
        self.sliderBR = wx.Slider(
            slider_panel, value=255, minValue=0, maxValue=255)
        self.sliderBR.Bind(wx.EVT_SCROLL, self.on_slider_change)

        self.textBR = IntCtrl(slider_panel, size=(50, -1),
                              style=wx.TE_CENTRE | wx.TE_PROCESS_ENTER, min=0, max=255, value=255, default_color=wx.WHITE, limited=True)
        self.textBR.Bind(wx.EVT_TEXT_ENTER, self.on_slider_text_change)

        BR_sizer = wx.BoxSizer()
        BR_sizer.Add(labelBR, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        BR_sizer.Add(self.sliderBR, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        BR_sizer.Add(self.textBR, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        sliderSizer = wx.BoxSizer(VERTICAL)
        sliderSizer.Add(R_sizer, 0)
        sliderSizer.Add(G_sizer, 0)
        sliderSizer.Add(B_sizer, 0)
        sliderSizer.Add(BR_sizer, 0)

        # endregion

        # region RGB bitmap

        bitmap = getFilledRectBitmap(120, 120, wx.Colour(0, 0, 0))
        self.rect_bitmap = wx.StaticBitmap(
            slider_panel, bitmap=bitmap, size=(120, 120))

        # endregion

        sliderApply = wx.Button(slider_panel, label="Apply")
        AsyncBind(wx.EVT_BUTTON, self.apply_slider, sliderApply)

        applySizer = wx.BoxSizer(VERTICAL)
        applySizer.Add(self.rect_bitmap, 0)
        applySizer.Add(sliderApply, 0)

        sliderPanelSizer = wx.BoxSizer()

        sliderPanelSizer.Add(sliderSizer, 0)
        sliderPanelSizer.Add(applySizer, 0)

        slider_panel.SetSizer(sliderPanelSizer)

        # endregion

        save_preset = wx.Button(panel, label="Save")
        AsyncBind(wx.EVT_BUTTON, self.save_preset, save_preset)

        self.property_sizer.Add(nameSizer, 1)
        self.property_sizer.Add(offBtn, 1)
        self.property_sizer.Add(save_preset, 0)
        self.property_sizer.Add(scenePresetSizer, 0)
        self.property_sizer.Add(slider_panel, 0)

        panel.SetSizer(self.property_sizer)

        self.main_sizer.Add(panel, 1, wx.ALL | wx.EXPAND)

        self.Layout()

    def apply_name(self, bulb: wizlight, TextArea: wx.TextCtrl):
        new_name = TextArea.GetValue()
        update_data({bulb.mac: {"name": new_name}})

    async def apply_preset(self, e):
        presets = [list(n.keys())[0]
                   for n in data.get(self.bulb.mac).get("presets")]

        async def apply(bulb, scene):
            await wiz_api.setBulb(bulb, scene=scene)

        selected = self.popupControl.GetStringValue()
        if selected in SCENES.values():
            await apply(self.bulb, selected)
        elif selected in presets:
            print("this is preset")

        self.GetTopLevelParent().set_status(selected)

    async def apply_slider(self, e):
        await wiz_api.setBulb(self.bulb, rgb=self.slider_colors, brightness=self.slider_brightness)

    @property
    def slider_colors(self):
        return self.sliderR.GetValue(), self.sliderG.GetValue(), self.sliderB.GetValue()

    @property
    def slider_text_colors(self):
        return self.textR.GetValue(), self.textG.GetValue(), self.textB.GetValue()

    @property
    def slider_brightness(self):
        return self.sliderBR.GetValue()

    @property
    def slider_text_brightness(self):
        return self.textBR.GetValue()

    def update_bitmap(self):
        bitmap = getFilledRectBitmap(120, 120, wx.Colour(*self.slider_colors))
        self.rect_bitmap.SetBitmap(bitmap)

    def on_slider_change(self, e):
        self.textR.SetValue(self.slider_colors[0])
        self.textG.SetValue(self.slider_colors[1])
        self.textB.SetValue(self.slider_colors[2])
        self.textBR.SetValue(self.slider_brightness)
        self.update_bitmap()

    def on_slider_text_change(self, e):
        self.sliderR.SetValue(self.slider_text_colors[0])
        self.sliderG.SetValue(self.slider_text_colors[1])
        self.sliderB.SetValue(self.slider_text_colors[2])
        self.sliderBR.SetValue(self.slider_text_brightness)
        self.update_bitmap()

    async def turn_off(self, e):
        await wiz_api.turn_off(self.bulb)

    async def get_state(self):
        state = await wiz_api.getState(self.bulb)
        return state

    async def save_preset(self, e):
        state: PilotParser = await self.get_state()
        presets = data[self.bulb.mac].get("presets")
        if presets is None:
            presets = {}

        with wx.TextEntryDialog(self, "Preset Name") as dlg:
            ret = dlg.ShowModal()
            if ret == wx.ID_OK:
                preset_name = dlg.GetValue()

                presets[preset_name] = {
                    "rgb": state.get_rgb(), "brightness": state.get_brightness()}

                copy = data[self.bulb.mac]
                copy.update({"presets": presets})
                update_data({self.bulb.mac: copy})


class Main_Frame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="WiZard", size=(800, 400))

        self.bulbs: list[wizlight] = []

        self.status_bar: wx.StatusBar = self.CreateStatusBar(1)
        panel = wx.Panel(self)

        self.list_panel = ListPanel(
            panel, size=(200, 1), style=wx.RAISED_BORDER)
        self.property_panel = PropertyPanel(panel, style=wx.RAISED_BORDER)

        main_Sizer = wx.BoxSizer()
        main_Sizer.Add(self.list_panel, 0, wx.ALL | wx.EXPAND)
        main_Sizer.Add(self.property_panel, 1, wx.ALL | wx.EXPAND)
        panel.SetSizer(main_Sizer)
        self.Centre()

        self.set_status("Sample Text!")

    def set_status(self, message):
        self.status_bar.SetStatusText(message)

    def manage_bulb(self, bulb_idx):
        self.property_panel.show_properties(self.bulbs[bulb_idx])

    async def refresh_bulbs(self, e=None):
        e.GetEventObject().Enable(False)
        self.set_status("Searching...")
        bulbs = await wiz_api.search()
        self.bulbs = bulbs

        for bulb in self.bulbs:
            if bulb.mac not in data:
                update_data({bulb.mac: {"name": bulb.mac, "presets": []}})

        self.list_panel.update_bulbs(self.bulbs)


if __name__ == "__main__":
    init_settings()
    app = WxAsyncApp()
    frame = Main_Frame()
    frame.Show(True)
    app.SetTopWindow(frame)
    loop = get_event_loop()
    loop.run_until_complete(app.MainLoop())
