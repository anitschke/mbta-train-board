import os
import board

from adafruit_matrixportal.matrixportal import MatrixPortal
from adafruit_datetime import datetime,timedelta

import logging_extra
from train_predictor import TrainPredictor, TrainPredictorDependencies
from time_conversion import TimeConversion, TimeConversionDependencies
from display import Display, DisplayDependencies
from application import Application, ApplicationDependencies

matrix_portal = MatrixPortal(status_neopixel=board.NEOPIXEL)

log_levels = logging_extra.LogLevels(aio_handler=logging_extra.INFO, print_handler=logging_extra.DEBUG)
logger = logging_extra.newLogger(logging_extra.LoggerDependencies(matrix_portal), log_levels)

mbta_api_key = os.getenv("MBTA_API_KEY")
if mbta_api_key is None:
    logger.error("missing MBTA API key")
    raise KeyError("missing MBTA API key")

mbta_stop_id = os.getenv("MBTA_STOP_ID")
if mbta_stop_id is None:
    logger.error("missing MBTA stop ID")
    raise KeyError("missing MBTA stop ID")

mbta_route_id = os.getenv("MBTA_ROUTE_ID")

train_predictor = TrainPredictor(
    TrainPredictorDependencies(
        matrix_portal.network,
        datetime,
        timedelta,
        datetime.now,
        mbta_api_key,
        logger,
        stop_id=mbta_stop_id,
        route_id=mbta_route_id,
    ),
    trainWarningSeconds=60,
)

time_conversion = TimeConversion(TimeConversionDependencies(datetime.now))
display = Display(DisplayDependencies(matrix_portal, time_conversion, logger), text_scroll_delay=0.1, train_frame_duration=0.08)

app = Application(ApplicationDependencies(matrix_portal, train_predictor, time_conversion, display, datetime.now, logger))

app.run()