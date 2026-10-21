import gc
import time
from collections_extra import LimitedSizeOrderedSet, LimitedSizeOrderedDict

# The MBTA V3 API documentation can be found at:
# https://www.mbta.com/developers/v3-api
# 
# In general, we query for a schedule of trains arriving/departing at a given
# MBTA station stop ID (e.g. "place-FB-0275" for Franklin / Dean College).
#
# We also include any predictions associated with a given schedule. This allows
# us to use real-time predictions when available, while falling back to scheduled
# times for trains further out that don't have predictions yet.
# 
# The "fields" query parameters use sparse fieldsets to only request the data
# we need. See https://www.mbta.com/developers/v3-api/best-practices#sparse-fieldsets
# 
# The schedules API returns schedules for the full service day, so we filter
# past trains upon receipt.
DEFAULT_STOP_ID = "place-FB-0275" 

# Direction Enum
# 
# In the MBTA V3 API:
#   direction_id: integer direction in which trip is traveling: 0 or 1.
#   Typically 0 = Outbound, 1 = Inbound.
class Direction:
    OUT_BOUND = 0
    IN_BOUND = 1

def direction_str(direction):
    if direction == Direction.OUT_BOUND:
        return "OUT"
    if direction == Direction.IN_BOUND:
        return "IN"
    return "UNKNOWN"

# TrainArrival represents a train arrival/departure at a station.
# 
# WARNING: schedule_id is not globally unique; it is reused from day to day.
# See TrainPredictor.clear_cache for details.
class TrainArrival:
    def __init__(self, schedule_id, time, direction):
        self.schedule_id = schedule_id
        self.time = time
        self.direction = direction

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"TrainArrival(schedule_id={self.schedule_id}, time={self.time}, direction={direction_str(self.direction)})"

    @staticmethod
    def sort_by_time(train):
        return train.time      

# TrainWarning is a warning for an arriving/departing train.
# 
# should_stop() can be called to determine if the warning can stop being
# displayed to the user.
class TrainWarning:
    def __init__(self, end_monotonic, direction):
        self._end_monotonic = end_monotonic
        self.direction = direction

    def should_stop(self) -> bool:
        return time.monotonic() > self._end_monotonic

class TrainPredictorDependencies:
    def __init__(self, network, datetime, timedelta, nowFcn, mbta_api_key, logger, stop_id="place-FB-0275", route_id=None):
        self.network = network 
        self.datetime = datetime 
        self.timedelta = timedelta
        self.nowFcn = nowFcn
        self.mbta_api_key = mbta_api_key
        self.logger = logger
        self.stop_id = stop_id
        self.route_id = route_id

# TrainPredictor is a class for predicting upcoming train arrival and departure times
# at an MBTA station.
# 
# We query the MBTA V3 API for schedules at the configured stop and include real-time
# predictions. We prefer real-time predictions when available, and fall back to scheduled
# times for trains further out.
class TrainPredictor:
    def __init__(self, dependencies: TrainPredictorDependencies, filterResultsAfterSeconds=30, trainWarningSeconds=0):
        self._network = dependencies.network
        self._datetime = dependencies.datetime
        self._timedelta = dependencies.timedelta
        self._nowFcn = dependencies.nowFcn
        self._logger = dependencies.logger
        self._stop_id = dependencies.stop_id
        self._route_id = dependencies.route_id

        self._filterResultsAfterSeconds = filterResultsAfterSeconds
        self._trainWarningOffset = self._timedelta(seconds=trainWarningSeconds)

        self._arrived_trains = LimitedSizeOrderedSet(100)

        # Cache predictions so that if a train departs before its scheduled time
        # and its prediction is removed, we don't fall back to displaying the later scheduled time.
        self._train_prediction_cache = LimitedSizeOrderedDict(10)

        self._mbta_api_headers = {
            "accept": "application/vnd.api+json"
        }
        if dependencies.mbta_api_key is not None:
            self._mbta_api_headers["x-api-key"] = dependencies.mbta_api_key
        
        # The MBTA API responds with a content type header of
        # "application/vnd.api+json". When the matrix portal looks at the
        # response from this API it looks at the content type header to decide
        # if it can parse the response into JSON. But the matrix portal doesn't
        # have "application/vnd.api+json" in its list of default JSON content
        # types so we need to add that in order for it to correctly recognize
        # the response as JSON.
        if self._network is not None:
            self._network.add_json_content_type("application/vnd.api+json") 

    def _get_data_source_url(self):
        url = (
            "https://api-v3.mbta.com/schedules?"
            f"filter[stop]={self._stop_id}&"
            "sort=arrival_time&"
            "include=prediction&"
            "fields[schedule]=arrival_time,departure_time,direction_id&"
            "fields[prediction]=arrival_time,departure_time,direction_id"
        )
        if self._route_id:
            url += f"&filter[route]={self._route_id}"
        return url

    # next_trains gets the next count trains sorted by expected time.
    # Returns a list of length count (padded with None if not enough trains).
    def next_trains(self, count):
        schedule_json = self._fetch_schedules_and_predictions()
        results = self._analyze_data(count, schedule_json)
        gc.collect()
        return results

    def train_passing_warning(self, train: TrainArrival):
        if train is None:
            return None

        now = self._nowFcn()
        warning_start_time = train.time - self._trainWarningOffset
        if warning_start_time > now:
            return None
        warning_stop_time = train.time
        remaining_seconds = (warning_stop_time - now).total_seconds()
        if remaining_seconds <= 0:
            return None
        now_monotonic = time.monotonic()
        end_monotonic = now_monotonic + remaining_seconds
        
        return TrainWarning(end_monotonic, train.direction)
        
    # mark_train_arrived marks the train as arrived to ensure that it is
    # filtered out from future next_trains calls.
    def mark_train_arrived(self, train):
        self._logger.debug(f"marking '{train.schedule_id}' as arrived")
        self._arrived_trains.add(train.schedule_id)

    # Schedule IDs can get reused from day to day, so clear caches nightly.
    def clear_cache(self):
        self._arrived_trains.clear()
        self._train_prediction_cache.clear()

    def _fetch_schedules_and_predictions(self):
        timeout = 10
        response = self._network.fetch(self._get_data_source_url(), headers=self._mbta_api_headers, timeout=timeout)
        if response.status_code is not 200:
            raise RuntimeError(f"Failed to fetch data from MBTA API. status_code: {response.status_code} response: {response.text}")
        return response.json()
    
    def _compute_train(self, schedule_id, schedule, prediction):
        self._logger.debug(f"Computing '{schedule_id}'")

        # If we know the train has already arrived then ignore it
        if schedule_id in self._arrived_trains:
            self._logger.debug(f"Filtering '{schedule_id}'. marked as arrived")
            return None

        direction = schedule.get("direction_id")
        station_time, time_is_from_prediction = self._get_station_time(schedule, prediction)
        if station_time is None:
            self._logger.debug(f"Filtering '{schedule_id}'. station time not computed")
            return None

        # Check prediction cache: if the current data has no prediction (e.g. train already departed
        # and MBTA dropped the prediction), but we previously cached a prediction for this schedule,
        # use the cached prediction so we don't revert to a later scheduled time.
        if not time_is_from_prediction and schedule_id in self._train_prediction_cache:
            train = self._train_prediction_cache[schedule_id]
            self._logger.debug(f"Using cached prediction for '{schedule_id}'")
        else:
            train = TrainArrival(schedule_id, station_time, direction)
            if time_is_from_prediction:
                self._logger.debug(f"Inserting prediction for '{schedule_id}' into cache")
                self._train_prediction_cache[schedule_id] = train
            self._logger.debug(f"Using computed prediction for '{schedule_id}'")

        # Remove any times more than self._filterResultsAfterSeconds in the past
        now = self._nowFcn()
        if (train.time - now).total_seconds() < (-1 * self._filterResultsAfterSeconds):
            self._logger.debug(f"Filtering '{schedule_id}'. time ({train.time}) is in the past")
            return None

        return train

    def _get_station_time(self, schedule, prediction):
        # Prefer using prediction data if available
        if prediction is not None:
            time = self._parse_time(prediction.get("departure_time") or prediction.get("arrival_time"))
            if time is not None:
                return time, True
        
        # Fall back to using schedule data
        return self._parse_time(schedule.get("departure_time") or schedule.get("arrival_time")), False

    def _parse_time(self, time_str):
        if not time_str:
            return None
        return self._datetime.fromisoformat(time_str).replace(tzinfo=None)

    def _analyze_data(self, count, schedule_json):
        trains = []
        included = {item["id"]: item for item in schedule_json.get("included", [])}

        # Build trains list
        for item in schedule_json.get("data", []):

            # Get prediction if available
            prediction = None 
            prediction_ref = item.get("relationships", {}).get("prediction", {}).get("data")
            if prediction_ref and prediction_ref.get("id") in included:
                prediction = included[prediction_ref["id"]]["attributes"]

            # Compute the train object
            schedule_attrs = item.get("attributes", {})
            train = self._compute_train(item.get("id"), schedule_attrs, prediction)
            if train is not None:
                trains.append(train)

        # Sort the list
        trains.sort(key=TrainArrival.sort_by_time)

        # We only need "count" times as we only display that many on the board. So we
        # will trim or pad the array so we always have "count" values:
        while len(trains) < count:
            trains.append(None)
        trains = trains[:count]

        return trains
    