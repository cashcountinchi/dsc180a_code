import ee
import folium
import numpy as np
import urllib.request

import subprocess
try:
    import geemap
except ImportError:
    subprocess.check_call(["python", '-m', 'pip', 'install', 'geemap'])
    import geemap


def add_ee_layer(self, ee_image_object, vis_params, name, show=True, opacity=1, min_zoom=0):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        show=show,
        opacity=opacity,
        min_zoom=min_zoom,
        overlay=True,
        control=True
        ).add_to(self)

folium.Map.add_ee_layer = add_ee_layer


def calcVI(image):
  """
  Returns an ee.Image with two bands: ["NDVI", "EVI"]
  """
  ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
  nir, red, blue = image.select("B8"), image.select("B4"), image.select("B2")
  evi = ((nir.subtract(red)).multiply(2.5)).divide((red.multiply(6).subtract(blue.multiply(7.5))).add(nir).add(1)).rename("EVI")

  return ndvi.addBands(evi)


def rangeFormatter(date):
  """
  Improves formatting of an image's start and end dates for visualizations
  """
  return date[5:7] + "/" + date[2:4]


def genDates():
    """
    Generates dates for analysis
    """

    monthSeq = ["01-01", "02-01", "03-01", "04-01", "05-01", "06-01",
                "07-01", "08-01", "09-01", "10-01", "11-01", "12-01", "01-01"]

    yearSeq = ["2019", "2020", "2021", "2022", "2023"]

    dateRange = []
    for i in range(len(yearSeq)-1):
        for j in range(len(monthSeq)-1):
            if j != 11:
                dateRange.append(["{}-{}".format(yearSeq[i], monthSeq[j]),
                                  "{}-{}".format(yearSeq[i], monthSeq[j+1])])
            else:       # rolls December date range over into next year
                dateRange.append(["{}-{}".format(yearSeq[i], monthSeq[j]),
                                  "{}-{}".format(yearSeq[i+1], monthSeq[j+1])])

     # trainMonths = dateRange[:34]     # [2019-01-01, 2021-11-01]
     # months2019 = dateRange[:12]      # [2020-01-01, 2021-01-01]


    epochs2022 = []                # defines years since epoch for 2022
    for i in dateRange[35:]:
        epochs2022.append(np.round(ee.Date(i[0][:-2]+"15").difference(ee.Date('1970-01-01'), 'year').getInfo(), 3))

    return [dateRange, epochs2022]


def genEEGeometries():
    """
    Generates general geometries for analysis.
    """
    madagascar = ee.Geometry.Rectangle(41.264648, -26.259860,
                                       52.294922, -10.241276)

    subset = ee.Geometry.Rectangle(44.529451, -19.837477,     # smaller ee.Geometry of Madagascar to reduce runtime
                                   44.876404, -19.573569)

    madagascarCenter = madagascar.centroid().getInfo()["coordinates"][::-1]
    subsetCenter = subset.centroid().getInfo()['coordinates'][::-1]

    return [madagascar, madagascarCenter, subset, subsetCenter]


def genFeatureCollections():

    # level 1 administrative boundaries
    boundsLevel_1 = ee.FeatureCollection("FAO/GAUL/2015/level1"
                     ).filter(ee.Filter.eq("ADM0_NAME", "Madagascar"))
    # Madagascar national parks
    parks = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(46.942241, -24.839532, 46.702881, -24.636228),
                                             {"Region": "d'Andohahela"}),
                                  ee.Feature(ee.Geometry.Rectangle(47.223358, -23.723450, 46.852087, -23.550140),
                                             {"Region": "Midongy Betofaka"}),
                                  ee.Feature(ee.Geometry.Rectangle(44.002508, -24.390880, 43.697637, -23.974152),
                                             {"Region": "Tsimanampetsotsa"}),
                                  ee.Feature(ee.Geometry.Rectangle(46.753229, -16.165182, 47.087402, -16.259739),
                                             {"Region": "d'Ankarafantsika"}),
                                  ee.Feature(ee.Geometry.Rectangle(50.497992, -15.882093, 49.815574, -15.183482),
                                             {"Region": "Masoala"}),
                                  ee.Feature(ee.Geometry.Rectangle(44.554812, -20.091821, 44.767227, -19.703976),
                                             {"Region": "Alan'Ankirisa"})])
    return [boundsLevel_1, parks]


def downloadGif(collection, gifParams, filePath, textSequence, textPosition, imageDuration):
    """
    Generates a gif using Earth Engine, downloads to directory, and adds text.
    """
    gifURL = collection.getVideoThumbURL(gifParams)

    urllib.request.urlretrieve(gifURL, filePath)

    geemap.add_text_to_gif(in_gif=filePath, out_gif=filePath,
                           xy=textPosition, text_sequence=textSequence,
                           duration=imageDuration, font_color="red")
