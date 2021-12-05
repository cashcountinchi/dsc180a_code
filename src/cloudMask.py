import ee

# Cloud masking parameters
CLOUD_FILTER = 60
CLD_PRB_THRESH = 50
NIR_DRK_THRESH = 0.15
CLD_PRJ_DIST = 2
BUFFER = 100


def get_s2_sr_cld_col(aoi, start_date, end_date):
    """
    Returns an ImageCollection with joined Sentinel 2 surface reflectance and s2cloudless images
    """
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
