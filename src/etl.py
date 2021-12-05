import pandas as pd
import ee
from operator import itemgetter
from funcs import rangeFormatter
from cloudMask import *

def ndviReducer(image, collection, scale, tileScale):
    """
    Reduces an image over multiple geometries in a FeatureCollection
    and returns a dictionary with feature properties and
    aggregated band statistics per geometry
    """
    reducer = ee.Reducer.mean(
                       ).combine(reducer2 = ee.Reducer.max(),
                                 sharedInputs = True
                       ).combine(reducer2 = ee.Reducer.min(),
                                 sharedInputs = True)

    collection = image.reduceRegions(collection = collection,
                                     reducer = reducer,
                                     scale = scale,
                                     tileScale = tileScale)#.getInfo()["features"]

    return collection.map(lambda x: ee.Feature(None, x.toDictionary())
                    ).getInfo()["features"]


# Improve ETL
def applyReducer(geometry, dates, collection_1, collection_2):
    dfLst_1, dfLst_2 = [], []

    modis = ee.ImageCollection("MODIS/006/MOD13Q1"
             ).filterBounds(geometry
             ).filterDate("2019-01-01", "2021-12-01")

    for i in range(len(dates)):
        start, end = dates[i]
        yearsSinceEpoch = ee.Date(start[:-2]+"15").difference(ee.Date('1970-01-01'), 'year').getInfo()  # defined at middle of month

        # Computes park statistics from masked sentinel images
        sentinelImage = get_s2_sr_cld_col(geometry,
                                          start, end).map(add_cld_shdw_mask
                                                    ).map(apply_cld_shdw_mask
                                                    ).mosaic()

        sentinelNDVI = sentinelImage.normalizedDifference(["B8", "B4"]).rename("NDVI")

        # Computes administrative boundary statistics from derived MODIS VI
        modisNDVI = modis.filterDate(start, end
                        ).mosaic(
                        ).select("NDVI")

        # Applies reducers over feature collections
        adminStats = ndviReducer(modisNDVI, collection_1, 250, 8)
        parkStats = ndviReducer(sentinelNDVI, collection_2, 50, 5)

        # selects relevant feature properties and stores in lst
        dfLst_1 += list(map(lambda x: (rangeFormatter(start), yearsSinceEpoch) + \
                                      itemgetter("ADM1_NAME", "max", "mean", "min")(x["properties"]),
                            adminStats))

        dfLst_2 += list(map(lambda x: (rangeFormatter(start), yearsSinceEpoch) + \
                                      itemgetter("Region", "max", "mean", "min")(x["properties"]),
                            parkStats))


    # create and save as dataframe
    df_1, df_2 = pd.DataFrame(dfLst_1).round(3), pd.DataFrame(dfLst_2).round(3)
    df_1.columns = ["Month", "Years Since Epoch (t)", "Region", "Max NDVI", "Mean NDVI", "Min NDVI"]
    df_2.columns = ["Month", "Years Since Epoch (t)", "Region", "Max NDVI", "Mean NDVI", "Min NDVI"]

    df_1.to_csv("data/adminDistrictStats.csv", index=False)
    df_2.to_csv("data/nationalParkStats.csv", index=False)
    # df.to_csv("/content/drive/MyDrive/Colab Notebooks/regionalNDVI.csv", index=False)
