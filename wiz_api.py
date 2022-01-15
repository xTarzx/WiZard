from pywizlight import wizlight, discovery, PilotBuilder
from pywizlight.scenes import get_id_from_scene_name


async def search() -> list[wizlight]:
    bulbs = await discovery.discover_lights(broadcast_space="192.168.1.255")

    return bulbs


async def turn_off(bulb: wizlight):
    await bulb.turn_off()


async def setBulb(bulb: wizlight, rgb=None, brightness=None, scene=None):
    if scene is not None:
        scene = get_id_from_scene_name(scene)
        builder = PilotBuilder(scene=scene)
    else:
        builder = PilotBuilder(rgb=rgb, brightness=brightness)

    await bulb.turn_on(builder)


async def getState(bulb: wizlight):
    curr = await bulb.updateState()
    return curr
