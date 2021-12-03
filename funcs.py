import ee
import folium
import numpy as np

# Cloud masking parameters
CLOUD_FILTER = 60
CLD_PRB_THRESH = 50
NIR_DRK_THRESH = 0.15
CLD_PRJ_DIST = 2
BUFFER = 100


def Mapdisplay(center, dicc, Tiles="OpensTreetMap",zoom_start=10):
    '''
    :param center: Center of the map (Latitude and Longitude).
    :param dicc: Earth Engine Geometries or Tiles dictionary
    :param Tiles: Mapbox Bright,Mapbox Control Room,Stamen Terrain,Stamen Toner,stamenwatercolor,cartodbpositron.
    :zoom_start: Initial zoom level for the map.
    :return: A folium.Map object.
    '''
    mapViz = folium.Map(location=center,tiles=Tiles, zoom_start=zoom_start)
    for k,v in dicc.items():
      if ee.image.Image in [type(x) for x in v.values()]:
        folium.TileLayer(
            tiles = v["tile_fetcher"].url_format,
            attr  = 'Google Earth Engine',
            overlay =True,
            name  = k
          ).add_to(mapViz)
      else:
        folium.GeoJson(
        data = v,
        name = k
          ).add_to(mapViz)
    mapViz.add_child(folium.LayerControl())
    return mapViz


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


def get_s2_sr_cld_col(aoi, start_date, end_date):
    s2_sr_col = (ee.ImageCollection('COPERNICUS/S2_SR')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', CLOUD_FILTER)))

    s2_cloudless_col = (ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
        .filterBounds(aoi)
        .filterDate(start_date, end_date))

    return ee.ImageCollection(ee.Join.saveFirst('s2cloudless').apply(**{
        'primary': s2_sr_col,
        'secondary': s2_cloudless_col,
        'condition': ee.Filter.equals(**{
            'leftField': 'system:index',
            'rightField': 'system:index'
        })
    }))


def get_s2_Modified(aoi, start_date, end_date):
    # Import and filter S2 SR.
    s2 = ee.ImageCollection('COPERNICUS/S2_SR'
          ).filterBounds(aoi
          ).filterDate(start_date, end_date)

    s2_sr_col = s2.filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE',
                                         CLOUD_FILTER))

    # Import and filter s2cloudless.
    s2_cloudless_col = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY'
                        ).filterBounds(aoi
                        ).filterDate(start_date, end_date)

    # Join the filtered s2cloudless collection to the SR collection by the 'system:index' property.
    filtered_s2 = ee.ImageCollection(ee.Join.saveFirst('s2cloudless').apply(**{
        'primary': s2_sr_col,
        'secondary': s2_cloudless_col,
        'condition': ee.Filter.equals(**{
            'leftField': 'system:index',
            'rightField': 'system:index'
        })
    }))

    return filtered_s2, s2


def add_cloud_bands(img):
    cld_prb = ee.Image(img.get('s2cloudless')).select('probability')
    is_cloud = cld_prb.gt(CLD_PRB_THRESH).rename('clouds')

    return img.addBands(ee.Image([cld_prb, is_cloud]))


def add_shadow_bands(img):
    not_water = img.select('SCL').neq(6)

    SR_BAND_SCALE = 1e4
    dark_pixels = img.select('B8').lt(NIR_DRK_THRESH*SR_BAND_SCALE).multiply(not_water).rename('dark_pixels')
    shadow_azimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')));

    cld_proj = (img.select('clouds').directionalDistanceTransform(shadow_azimuth, CLD_PRJ_DIST*10)
        .reproject(**{'crs': img.select(0).projection(), 'scale': 100})
        .select('distance')
        .mask()
        .rename('cloud_transform'))

    shadows = cld_proj.multiply(dark_pixels).rename('shadows')

    return img.addBands(ee.Image([dark_pixels, cld_proj, shadows]))


def add_cld_shdw_mask(img):
    img_cloud = add_cloud_bands(img)
    img_cloud_shadow = add_shadow_bands(img_cloud)
    is_cld_shdw = img_cloud_shadow.select('clouds').add(img_cloud_shadow.select('shadows')).gt(0)

    is_cld_shdw = (is_cld_shdw.focal_min(2).focal_max(BUFFER*2/20)
        .reproject(**{'crs': img.select([0]).projection(), 'scale': 20})
        .rename('cloudmask'))

    return img_cloud_shadow.addBands(is_cld_shdw)
    # return img.addBands(is_cld_shdw)


def apply_cld_shdw_mask(img):
    not_cld_shdw = img.select('cloudmask').Not()
    return img.select('B.*').updateMask(not_cld_shdw)


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
  Improves formatting of an image's start and end dates
  """
  return date[5:7] + "/" + date[2:4]


def genDates():
    """
    Creates formatted date ranges
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
    for i in dateRange[34:]:
        epochs2022.append(np.round(ee.Date(i[0][:-2]+"15").difference(ee.Date('1970-01-01'), 'year').getInfo(), 3))

    return dateRange, epochs2022


def genEEGeometries():
    """
    """
    madagascar = ee.Geometry.Rectangle(41.264648, -26.259860,
                                       52.294922, -10.241276)

    subset = ee.Geometry.Rectangle(44.529451, -19.837477,     # smaller ee.Geometry of Madagascar to reduce runtime
                                   44.876404, -19.573569)

    madagascarCenter = madagascar.centroid().getInfo()["coordinates"][::-1]
    subsetCenter = subset.centroid().getInfo()['coordinates'][::-1]

    return [madagascar, madagascarCenter, subset, subsetCenter]
